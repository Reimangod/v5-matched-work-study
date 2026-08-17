from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from v5_matched_work.atomic_artifacts import canonical_json_bytes
from v5_final.s11_v2_native_preparation_runtime_v1 import (
    CumulativeVerifierLedger,
    VerifierComponentwiseCapRejected,
    _digest,
    build_magnitude_verifier_v2,
    conservative_session_upper_bound,
    magnitude_session_upper_bound,
    policy_from_queue_item,
)
from v5_final.s11_v2_queue_freeze import _max_relation_terms
from v5_final.s11_v2_queue_native_adapter import QueueV2NativeAdapter
from v5_final.verifier_v2 import DETERMINISTIC_COUNTER_FIELDS


def _scaled_session_cap(base: dict[str, int], multiplier: int) -> dict[str, int]:
    return {
        field: (
            value
            if field in {"matrix_dimension", "qubit_count"}
            else value * multiplier
        )
        for field, value in base.items()
        if field not in {"optimizer_iterations", "energy_evaluations"}
    }


def test_session_formula_exactly_reconstructs_all_90_frozen_verifier_caps() -> None:
    adapter = QueueV2NativeAdapter()
    cases = {
        value["case_id"]: value
        for value in json.loads(
            (
                Path("artifacts/v5-final/parent-native/s11-development-queue-v4")
                / "development-source-catalog-v1.json"
            ).read_text()
        )["cases"]
    }
    for item in adapter.queue["items"]:
        case = cases[item["case_id"]]
        count = int(item["candidate_binding"]["candidate_count"])
        policy = policy_from_queue_item(item)
        base = conservative_session_upper_bound(
            candidate_count=count,
            selected_count=min(policy.top_k, count),
            source_block_count=int(case["source_resources"]["logical_block_count"]),
            maximum_relation_terms=_max_relation_terms(case),
            matrix_dimension=int(item["verifier_componentwise_cap"]["matrix_dimension"]),
            qubit_count=int(item["verifier_componentwise_cap"]["qubit_count"]),
            probe_count=policy.probe_count,
        )
        assert _scaled_session_cap(base, int(item["work_envelope_multiplier"])) == item[
            "verifier_componentwise_cap"
        ]


def _counts(**overrides: int) -> dict[str, int]:
    value = {field: 0 for field in DETERMINISTIC_COUNTER_FIELDS}
    value.update(
        matrix_dimension=4,
        qubit_count=2,
        candidate_generations=1,
        unique_semantic_candidates=1,
        unique_physical_states=1,
        rewrite_verifications=1,
        resource_recounts=1,
    )
    value.update(overrides)
    return value


def _result(counters: dict[str, int], candidate_id: str) -> dict:
    top_k = {"selected_candidate_ids": [candidate_id]}
    core = {
        "schema": "v5-final.verifier-v2-core.v1",
        "status": "VERIFIED_READY_AWAITING_OUTCOME_AUTHORIZATION",
        "top_k_freeze": top_k,
        "deterministic_work_counters": counters,
        "authorization": {
            "optimizer": "NOT_AUTHORIZED",
            "candidate_energy": "NOT_AUTHORIZED",
        },
    }
    core["core_digest"] = _digest(core)
    return {
        "core": core,
        "operational_telemetry": {
            "schema": "test-operational-sidecar",
            "core_digest": core["core_digest"],
        },
    }


def _frozen_cap(rounds: int) -> dict[str, int]:
    unit = _counts()
    return {
        field: (
            unit[field]
            if field in {"matrix_dimension", "qubit_count"}
            else unit[field] * rounds
        )
        for field in DETERMINISTIC_COUNTER_FIELDS
        if field not in {"optimizer_iterations", "energy_evaluations"}
    }


def test_cumulative_verifier_ledger_replays_and_rejects_before_third_session(
    tmp_path,
) -> None:
    ledger = CumulativeVerifierLedger(tmp_path / "verifier", cap=_frozen_cap(2))
    upper = _counts()
    for index in (1, 2):
        ledger.precheck(upper)
        receipt = ledger.commit(
            phase=f"round-{index}",
            source_state_preparation_id="state-v1:" + str(index) * 64,
            result=_result(_counts(), f"candidate-{index}"),
            session_upper_bound=upper,
        )
        assert receipt.round_index == index
    assert ledger.total["candidate_generations"] == 2
    assert ledger.total["matrix_dimension"] == 4
    with pytest.raises(VerifierComponentwiseCapRejected, match="before session"):
        ledger.precheck(upper)
    assert len(ledger.replay()) == 2


def test_cumulative_verifier_ledger_detects_core_tamper(tmp_path) -> None:
    ledger = CumulativeVerifierLedger(tmp_path / "verifier", cap=_frozen_cap(1))
    upper = _counts()
    ledger.precheck(upper)
    ledger.commit(
        phase="initial",
        source_state_preparation_id="state-v1:" + "1" * 64,
        result=_result(_counts(), "candidate-1"),
        session_upper_bound=upper,
    )
    core_path = tmp_path / "verifier/round-0001-session/verification-core-v2.json"
    core = json.loads(core_path.read_text())
    core["status"] = "TAMPERED"
    core_path.write_bytes(canonical_json_bytes(core))
    with pytest.raises(Exception, match="core binding invalid"):
        ledger.replay()


def test_round_receipt_recovers_after_core_was_already_published(tmp_path) -> None:
    ledger = CumulativeVerifierLedger(tmp_path / "verifier", cap=_frozen_cap(1))
    upper = _counts()
    result = _result(_counts(), "candidate-1")
    session = tmp_path / "verifier/round-0001-session"
    session.mkdir(parents=True)
    (session / "verification-core-v2.json").write_bytes(
        canonical_json_bytes(result["core"])
    )
    (session / "operational-telemetry-v2.json").write_bytes(
        canonical_json_bytes(result["operational_telemetry"])
    )
    receipt = ledger.commit(
        phase="initial-recovery",
        source_state_preparation_id="state-v1:" + "1" * 64,
        result=result,
        session_upper_bound=upper,
    )
    assert receipt.round_index == 1
    assert len(ledger.replay()) == 1


def test_actual_magnitude_builder_uses_analytic_deletion_and_no_outcome(
    tmp_path, monkeypatch
) -> None:
    from v5_final import s11_v2_native_preparation_runtime_v1 as subject
    from dvg_obs_ceo.resources import AnsatzStructure

    source = AnsatzStructure.create((1, 2), (0.2, 0.1), (2,))
    snapshot = SimpleNamespace(
        cnot_count=2,
        cnot_depth=2,
        total_depth=3,
        parameter_count=2,
        logical_block_count=1,
    )
    resources = SimpleNamespace(snapshot=snapshot)
    monkeypatch.setattr(subject, "evaluate_full_circuit_resources", lambda *a, **k: resources)
    monkeypatch.setattr(
        subject,
        "recover_dvg_blocks",
        lambda *a, **k: (SimpleNamespace(family="toy", pool_indices=(1,)),),
    )
    monkeypatch.setattr(subject, "generator_definition_digest", lambda pool: "g" * 64)
    monkeypatch.setattr(
        subject,
        "state_preparation_spec",
        lambda *a, **k: SimpleNamespace(state_preparation_id="state-v1:" + "1" * 64),
    )

    class FakeStatePreparationSpec:
        @staticmethod
        def create(**kwargs):
            suffix = "2" if tuple(kwargs["ansatz_indices"]) == (1,) else "3"
            return SimpleNamespace(state_preparation_id="state-v1:" + suffix * 64)

    monkeypatch.setattr(subject, "StatePreparationSpec", FakeStatePreparationSpec)
    monkeypatch.setattr(
        subject,
        "canonical_proposed_physical_state_id",
        lambda **kwargs: "physical-state-v3:" + "4" * 64,
    )
    context = SimpleNamespace(
        case_id="toy",
        problem_id="problem-v1:" + "5" * 64,
        hamiltonian_digest="6" * 64,
        source_checkpoint_digest="7" * 64,
        pool=SimpleNamespace(n=2),
        runtime=SimpleNamespace(ansatz=source),
        _actual_algorithm=SimpleNamespace(n=2, ref_det=(1, 0)),
    )
    item = QueueV2NativeAdapter().first_request_for_method(
        "structural-magnitude-pruning"
    ).item
    policy = policy_from_queue_item(item)
    bundle = build_magnitude_verifier_v2(
        context=context,
        policy=policy,
        checkpoint_dir=tmp_path / "magnitude-session",
    )
    upper = magnitude_session_upper_bound(bundle=bundle, policy=policy, context=context)
    result = bundle.verifier.run(bundle.candidates)
    deletion = bundle.selected_deletion(result)
    counters = result["core"]["deterministic_work_counters"]
    assert deletion.position == 1
    assert counters["N_dense_expm"] == 0
    assert counters["N_generator_materializations"] == 0
    assert counters["energy_evaluations"] == 0
    assert counters["optimizer_iterations"] == 0
    assert counters["candidate_generations"] == 2
    assert all(counters[field] <= upper[field] for field in counters)

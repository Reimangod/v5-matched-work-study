from __future__ import annotations

import inspect
import hashlib
import json
import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from dvg_obs_ceo.block_ir import CompressionCandidate
from dvg_obs_ceo.quadratic import ConstraintTargetIR

from v5_final.s11_v2_native_preparation_runtime_v1 import (
    CumulativeVerifierLedger,
    VerifierComponentwiseCapRejected,
    relation_aware_session_upper_bound,
)
from v5_final.s11_v2_prepared_executor_v1 import run_typed_verifier_session
from v5_final.s11_v2_queue_native_adapter import QueueV2NativeAdapter
from v5_final.s11_v2_relation_aware_symbolic_precheck_v1 import (
    MAX_COUNTER,
    REGISTERED_RELATION_ARITIES,
    RelationAwareSymbolicPrecheckError,
    relation_aware_symbolic_upper_bound,
    relation_symbolic_cost,
    selected_relation_costs,
    symbolic_check_cost_from_arity,
)
from v5_final.verifier_v2 import (
    CandidateV2,
    DETERMINISTIC_COUNTER_FIELDS,
    VerifierV2,
    VerifierV2Policy,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE_CATALOG = (
    ROOT
    / "artifacts/v5-final/parent-native/s11-development-queue-v4"
    / "development-source-catalog-v1.json"
)
ITEM022_TOP_K = (
    ROOT
    / "artifacts/v5-final/parent-native/s11-v2-production-execution-v1"
    / "verifier-ledgers/0022-b9e587bb7f9b2fc9"
    / "round-0001-session/checkpoints/top-k-freeze-v2.json"
)
ITEM022_BINDING = ITEM022_TOP_K.with_name("session-binding-v2.json")
QUEUE_V2 = (
    ROOT
    / "artifacts/v5-final/parent-native/s11-v2-queue-freeze-v2"
    / "s11-v2-queue-v2.json"
)
CAP_FREEZE = (
    ROOT
    / "artifacts/v5-final/parent-native/s11-v2-outcome-cap-freeze-v1"
    / "outcome-cap-freeze-v1.json"
)
P7_V5 = (
    ROOT
    / "artifacts/v5-final/parent-native/s11-v2-preexecution-gate-v5"
    / "p7-go-v5.json"
)


def _candidate_from_record(record: dict) -> SimpleNamespace:
    return SimpleNamespace(
        candidate_id=record["candidate_id"],
        kind=record["kind"],
        source_pool_indices=tuple(record["source_pool_indices"]),
        target_pool_indices=tuple(record["target_pool_indices"]),
        jacobian=tuple(tuple(row) for row in record["jacobian"]),
    )


def _catalog_records() -> list[dict]:
    value = json.loads(SOURCE_CATALOG.read_text(encoding="utf-8"))
    return [
        candidate
        for case in value["cases"]
        for candidate in case["source_structural_catalog"]
    ]


def _actual_parent_candidate(record: dict) -> CompressionCandidate:
    transformation = ConstraintTargetIR.create(
        constraint_matrix=np.asarray(record["constraint_matrix"], dtype=np.float64),
        constraint_rhs=np.asarray(record["constraint_rhs"], dtype=np.float64),
        offset=np.asarray(record["offset"], dtype=np.float64),
        jacobian=np.asarray(record["jacobian"], dtype=np.float64),
        source_slots=record["source_slots"],
        target_slots=record["target_slots"],
        generator_normalization=record["generator_normalization"],
        orientation=record["orientation"],
        units=record["units"],
    )
    return CompressionCandidate(
        candidate_id=record["candidate_id"],
        equivalence_class_id=record["equivalence_class_id"],
        kind=record["kind"],
        source_block_id=record["source_block_id"],
        source_pool_indices=tuple(record["source_pool_indices"]),
        target_family=record["target_family"],
        target_pool_indices=tuple(record["target_pool_indices"]),
        removed_source_slots=tuple(record["removed_source_slots"]),
        transformation=transformation,
        target_operator_digests=tuple(record["target_operator_digests"]),
        semantic_conflict_positions=tuple(record["semantic_conflict_positions"]),
        numerical_context_digest=record["numerical_context_digest"],
        exact_generator_relation=(
            None
            if record["exact_generator_relation"] is None
            else tuple(record["exact_generator_relation"])
        ),
    )


def test_registered_costs_match_verifier_operation_enumeration() -> None:
    source = json.loads(SOURCE_CATALOG.read_text(encoding="utf-8"))
    assert {case["case_id"] for case in source["cases"]} == {
        "lih-3.0",
        "h6-1.5",
        "h6-3.0",
        "beh2-3.0",
        "h4-1.5-known-development",
    }
    records = [
        candidate
        for case in source["cases"]
        for candidate in case["source_structural_catalog"]
    ]
    assert records
    assert {record["kind"] for record in records} == set(
        REGISTERED_RELATION_ARITIES
    )
    for record in records:
        derived = relation_symbolic_cost(_candidate_from_record(record))
        source = range(derived.source_arity)
        target = range(derived.target_arity)
        independently_enumerated = 0 if derived.deletion_shortcut else len(
            [*(f"source-{index}" for index in source)]
            + [*(f"target-{index}" for index in target)]
            + [
                f"commutator-{left}-{right}"
                for left in source
                for right in source
                if left < right
            ]
            + [*(f"reconstruct-{index}" for index in target)]
        )
        assert derived.symbolic_check_cost == independently_enumerated


def test_all_frozen_records_use_actual_parent_shape_and_conservative_cost() -> None:
    records = _catalog_records()
    assert len(records) == 949
    assert {record["kind"] for record in records} == set(
        REGISTERED_RELATION_ARITIES
    )
    for record in records:
        candidate = _actual_parent_candidate(record)
        assert not hasattr(candidate, "jacobian")
        derived = relation_symbolic_cost(candidate)
        source = derived.source_arity
        target = derived.target_arity
        reconstructed_required_checks = (
            0
            if derived.deletion_shortcut
            else source + target + source * (source - 1) // 2 + target
        )
        assert derived.symbolic_check_cost >= reconstructed_required_checks
        assert math.isfinite(float(derived.symbolic_check_cost))


def test_bound_dominates_every_preserved_numeric_checkpoint() -> None:
    roots = sorted(
        (
            ROOT
            / "artifacts/v5-final/parent-native/s11-v2-production-execution-v1"
            / "verifier-ledgers"
        ).glob("*/round-*-session/checkpoints")
    )
    observed = 0
    for checkpoint_root in roots:
        binding_path = checkpoint_root / "session-binding-v2.json"
        if not binding_path.is_file():
            continue
        binding = json.loads(binding_path.read_text(encoding="utf-8"))
        descriptors = {
            value["candidate_id"]: value
            for value in binding["candidate_descriptors"]
        }
        for path in sorted(checkpoint_root.glob("numeric-*.json")):
            numeric = json.loads(path.read_text(encoding="utf-8"))
            descriptor = descriptors[numeric["candidate_id"]]
            predicted = symbolic_check_cost_from_arity(
                source_arity=len(descriptor["source_generator_digests"]),
                target_arity=len(descriptor["target_generator_digests"]),
                deletion_shortcut=bool(descriptor["deletion_shortcut"]),
            )
            assert predicted >= numeric["primitive_delta"]["N_symbolic_checks"]
            observed += 1
    assert observed > 0


def test_normal_relations_and_frozen_five_check_case_remain_exact() -> None:
    assert symbolic_check_cost_from_arity(
        source_arity=2, target_arity=1, deletion_shortcut=False
    ) == 5
    assert relation_aware_symbolic_upper_bound(
        candidate_count=427, selected_costs=(5, 5, 5, 5)
    ) == 447


def test_item022_selected_relations_require_452_without_outcomes() -> None:
    source = json.loads(SOURCE_CATALOG.read_text(encoding="utf-8"))
    h6 = next(case for case in source["cases"] if case["case_id"] == "h6-1.5")
    catalog = SimpleNamespace(
        candidates=tuple(
            _actual_parent_candidate(record)
            for record in h6["source_structural_catalog"]
        )
    )
    selected = tuple(
        json.loads(ITEM022_TOP_K.read_text(encoding="utf-8"))[
            "selected_candidate_ids"
        ]
    )
    costs = selected_relation_costs(
        catalog=catalog, selected_candidate_ids=selected
    )
    assert [value.symbolic_check_cost for value in costs] == [5, 5, 5, 10]
    assert relation_aware_symbolic_upper_bound(
        candidate_count=427,
        selected_costs=tuple(value.symbolic_check_cost for value in costs),
    ) == 452


def test_item023_shares_outcome_free_h6_source_catalog_and_requires_452() -> None:
    adapter = QueueV2NativeAdapter()
    item022 = adapter.request(adapter.queue["items"][22]["queue_item_id"])
    item023 = adapter.request(adapter.queue["items"][23]["queue_item_id"])
    assert item022.item["source_identity"] == item023.item["source_identity"]
    assert item022.admitted_candidate_ids == item023.admitted_candidate_ids
    assert len(item023.admitted_candidate_ids) == 427
    assert item023.item["candidate_binding"]["candidate_outcomes_used"] is False

    source = json.loads(SOURCE_CATALOG.read_text(encoding="utf-8"))
    h6 = next(case for case in source["cases"] if case["case_id"] == "h6-1.5")
    catalog = SimpleNamespace(
        candidates=tuple(
            _actual_parent_candidate(record)
            for record in h6["source_structural_catalog"]
        )
    )
    selected = tuple(
        json.loads(ITEM022_TOP_K.read_text(encoding="utf-8"))[
            "selected_candidate_ids"
        ]
    )
    assert set(selected).issubset(item023.admitted_candidate_ids)
    costs = selected_relation_costs(
        catalog=catalog, selected_candidate_ids=selected
    )
    assert [value.symbolic_check_cost for value in costs] == [5, 5, 5, 10]
    assert relation_aware_symbolic_upper_bound(
        candidate_count=len(item023.admitted_candidate_ids),
        selected_costs=tuple(value.symbolic_check_cost for value in costs),
    ) == 452
    assert item023.item["verifier_componentwise_cap"]["N_symbolic_checks"] == 447


def test_item022_outcome_free_preview_preserves_frozen_selection(
    tmp_path,
) -> None:
    binding = json.loads(ITEM022_BINDING.read_text(encoding="utf-8"))
    top_k = json.loads(ITEM022_TOP_K.read_text(encoding="utf-8"))
    ranked = {
        value["candidate_id"]: tuple(value["resource_vector"])
        for value in top_k["ranked_candidates"]
    }
    candidates = []
    for descriptor in binding["candidate_descriptors"]:
        candidate_id = descriptor["candidate_id"]

        def recount(
            *, candidate_id: str = candidate_id
        ) -> tuple[int, ...]:
            if candidate_id not in ranked:
                raise AssertionError("deduplicated candidate was recounted")
            return ranked[candidate_id]

        candidates.append(
            CandidateV2(
                candidate_id=candidate_id,
                semantic_id=descriptor["semantic_id"],
                proposed_state_preparation_id=descriptor[
                    "proposed_state_preparation_id"
                ],
                source_generator_digests=tuple(
                    descriptor["source_generator_digests"]
                ),
                target_generator_digests=tuple(
                    descriptor["target_generator_digests"]
                ),
                jacobian=tuple(
                    tuple(float.fromhex(value) for value in row)
                    for row in descriptor["jacobian_float64_hex"]
                ),
                obs_predicted_loss=float.fromhex(
                    descriptor["OBS_predicted_loss_float64_hex"]
                ),
                matrix_dimension=descriptor["matrix_dimension"],
                qubit_count=descriptor["qubit_count"],
                resource_recount=recount,
                deletion_shortcut=descriptor["deletion_shortcut"],
            )
        )
    policy_record = binding["policy"]
    verifier = VerifierV2(
        policy=VerifierV2Policy(
            top_k=policy_record["top_k"],
            tie_break=tuple(policy_record["tie_break"]),
            probe_count=policy_record["probe_count"],
            seed=policy_record["seed"],
            tolerance=float.fromhex(policy_record["tolerance_float64_hex"]),
        ),
        generator_loader=lambda _: None,
        checkpoint_dir=tmp_path / "item022-preview",
        source_binding={"preserved_item022": True},
    )
    assert verifier.preview_selected_candidate_ids(tuple(candidates)) == tuple(
        top_k["selected_candidate_ids"]
    )
    assert not (tmp_path / "item022-preview").exists()


def test_unknown_missing_invalid_and_overflowing_relations_fail_closed() -> None:
    base = dict(
        candidate_id="candidate-1",
        source_pool_indices=(1, 2),
        target_pool_indices=(3,),
        jacobian=((1.0,), (-1.0,)),
    )
    with pytest.raises(RelationAwareSymbolicPrecheckError, match="unknown"):
        relation_symbolic_cost(SimpleNamespace(kind="unregistered", **base))
    with pytest.raises(RelationAwareSymbolicPrecheckError, match="Jacobian"):
        relation_symbolic_cost(
            SimpleNamespace(kind="mvp-to-ovp-diff", **(base | {"jacobian": ()}))
        )
    with pytest.raises(RelationAwareSymbolicPrecheckError, match="arity"):
        relation_symbolic_cost(
            SimpleNamespace(
                kind="mvp-to-ovp-diff",
                **(base | {"source_pool_indices": (1, 2, 3, 4)}),
            )
        )
    with pytest.raises(RelationAwareSymbolicPrecheckError, match="overflow"):
        relation_aware_symbolic_upper_bound(
            candidate_count=MAX_COUNTER, selected_costs=(1,)
        )


def test_nested_direct_ambiguity_and_invalid_values_fail_closed() -> None:
    base = dict(
        candidate_id="candidate-1",
        kind="mvp-to-ovp-diff",
        source_pool_indices=(1, 2),
        target_pool_indices=(3,),
    )
    nested = SimpleNamespace(
        jacobian=((1.0,), (-1.0,)),
        source_slots=("source-1", "source-2"),
        target_slots=("target-1",),
    )
    derived = relation_symbolic_cost(SimpleNamespace(transformation=nested, **base))
    assert derived.symbolic_check_cost == 5
    with pytest.raises(RelationAwareSymbolicPrecheckError, match="differ"):
        relation_symbolic_cost(
            SimpleNamespace(
                jacobian=((1.0,), (1.0,)), transformation=nested, **base
            )
        )
    with pytest.raises(RelationAwareSymbolicPrecheckError, match="non-finite"):
        relation_symbolic_cost(
            SimpleNamespace(
                transformation=SimpleNamespace(
                    jacobian=((1.0,), (float("nan"),)),
                    source_slots=nested.source_slots,
                    target_slots=nested.target_slots,
                ),
                **base,
            )
        )
    with pytest.raises(RelationAwareSymbolicPrecheckError, match="slot dimensions"):
        relation_symbolic_cost(
            SimpleNamespace(
                transformation=SimpleNamespace(
                    jacobian=nested.jacobian,
                    source_slots=("source-1",),
                    target_slots=nested.target_slots,
                ),
                **base,
            )
        )


def _candidate(
    candidate_id: str,
    semantic_id: str,
    physical_id: str,
    score: float,
    recounts: list[str],
) -> CandidateV2:
    def recount() -> tuple[int, ...]:
        recounts.append(candidate_id)
        return (1, 1, 1, 1, 1)

    return CandidateV2(
        candidate_id=candidate_id,
        semantic_id=semantic_id,
        proposed_state_preparation_id=physical_id,
        source_generator_digests=("source", "source-2"),
        target_generator_digests=("target",),
        jacobian=((1.0,), (-1.0,)),
        obs_predicted_loss=score,
        matrix_dimension=4,
        qubit_count=2,
        resource_recount=recount,
    )


def test_preview_deduplicates_semantic_and_physical_relations_once(tmp_path) -> None:
    recounts: list[str] = []
    candidates = (
        _candidate("a", "semantic-a", "physical-a", 0.1, recounts),
        _candidate("b", "semantic-a", "physical-a", 0.2, recounts),
        _candidate("c", "semantic-c", "physical-a", 0.3, recounts),
        _candidate("d", "semantic-d", "physical-d", 0.4, recounts),
    )
    verifier = VerifierV2(
        policy=VerifierV2Policy(
            top_k=4,
            tie_break=(
                "OBS_predicted_loss_float64",
                "resource_vector_lexicographic",
                "candidate_id",
            ),
            probe_count=3,
            seed=1,
            tolerance=1e-8,
        ),
        generator_loader=lambda _: None,
        checkpoint_dir=tmp_path / "checkpoints",
        source_binding={"test": True},
    )
    assert verifier.preview_selected_candidate_ids(candidates) == ("a", "d")
    assert recounts == ["a", "d"]
    assert not (tmp_path / "checkpoints").exists()


def test_relation_aware_rejection_occurs_before_numeric_verifier(
    tmp_path, monkeypatch
) -> None:
    from v5_final import s11_v2_prepared_executor_v1 as subject

    candidate = SimpleNamespace(
        candidate_id="candidate-1",
        kind="mvp-to-ovp-diff",
        source_pool_indices=(1, 2),
        target_pool_indices=(3,),
        jacobian=((1.0,), (-1.0,)),
    )
    catalog = SimpleNamespace(candidates=(candidate,))
    run_called = False

    class Bundle:
        def preview_selected_candidate_ids(self) -> tuple[str, ...]:
            return ("candidate-1",)

        def run(self):
            nonlocal run_called
            run_called = True
            raise AssertionError("numeric verifier must not run")

    monkeypatch.setattr(subject, "build_parent_verifier_v2", lambda **_: Bundle())
    cap = {
        field: (5 if field == "N_symbolic_checks" else MAX_COUNTER)
        for field in DETERMINISTIC_COUNTER_FIELDS
        if field not in {"optimizer_iterations", "energy_evaluations"}
    }
    cap["N_dense_expm"] = 0
    ledger = CumulativeVerifierLedger(tmp_path / "ledger", cap=cap)
    context = SimpleNamespace(
        runtime=SimpleNamespace(
            ansatz=SimpleNamespace(cumulative_parameter_counts=(1,))
        ),
        pool=SimpleNamespace(n=2),
        state_preparation_id="state-v1:" + "1" * 64,
    )
    policy = SimpleNamespace(top_k=1, probe_count=3)
    with pytest.raises(VerifierComponentwiseCapRejected, match="N_symbolic_checks"):
        run_typed_verifier_session(
            context=context,
            catalog=catalog,
            admitted_candidate_ids=("candidate-1",),
            policy=policy,
            ledger=ledger,
            phase="test",
        )
    assert run_called is False
    assert ledger.replay() == ()
    assert not (tmp_path / "ledger").exists()


def test_relation_aware_bound_is_retry_deterministic_and_not_item_specific() -> None:
    first = relation_aware_session_upper_bound(
        candidate_count=427,
        selected_relation_costs=(5, 5, 5, 10),
        source_block_count=38,
        maximum_relation_terms=5,
        matrix_dimension=4096,
        qubit_count=12,
        probe_count=3,
    )
    second = relation_aware_session_upper_bound(
        candidate_count=427,
        selected_relation_costs=(5, 5, 5, 10),
        source_block_count=38,
        maximum_relation_terms=5,
        matrix_dimension=4096,
        qubit_count=12,
        probe_count=3,
    )
    assert first == second
    assert first["N_symbolic_checks"] == 452
    source = inspect.getsource(
        __import__(
            "v5_final.s11_v2_relation_aware_symbolic_precheck_v1",
            fromlist=["unused"],
        )
    )
    assert "b9e587bb" not in source
    assert "item022" not in source.lower()


def test_frozen_queue_cap_and_p7_bytes_remain_exact() -> None:
    assert hashlib.sha256(QUEUE_V2.read_bytes()).hexdigest() == (
        "be88c730f7ba44efd8867c0bf571ecb01afe0349d68e5fdc11733e67c779b1b4"
    )
    assert hashlib.sha256(CAP_FREEZE.read_bytes()).hexdigest() == (
        "3f0b7c5a8c09dcfb9e5553231894a923efc1e87bd92a6dde54afd5f028a68fb9"
    )
    assert hashlib.sha256(P7_V5.read_bytes()).hexdigest() == (
        "7ffd316208758bd4a5f63357b0e74b6b8f4df7fac0fe9a1e0b42240d70eb3a63"
    )

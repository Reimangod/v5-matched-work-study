from __future__ import annotations

from types import SimpleNamespace

import pytest

from v5_final.parent_native_development_runtime_factory_v1 import (
    build_queue_bound_development_runtime_v1,
)
from v5_final.s11_v2_native_preparation_runtime_v1 import (
    _digest,
    build_magnitude_verifier_v2,
    policy_from_queue_item,
)
from v5_final.s11_v2_prepared_executor_v1 import (
    PreparedSessionV1,
    _CurrentRuntimeVerifierContext,
    prepare_dynamic_v5_v1,
    prepare_initial_executor_v1,
)
from v5_final.s11_v2_queue_native_adapter import QueueV2NativeAdapter
from v5_final.verifier_v2 import DETERMINISTIC_COUNTER_FIELDS


def _verifier_result(selected: tuple[str, ...]) -> dict:
    counters = {field: 0 for field in DETERMINISTIC_COUNTER_FIELDS}
    counters.update(
        matrix_dimension=4,
        qubit_count=2,
        candidate_generations=len(selected),
        unique_semantic_candidates=len(selected),
        unique_physical_states=len(selected),
        rewrite_verifications=len(selected),
        resource_recounts=len(selected),
    )
    core = {
        "schema": "v5-final.verifier-v2-core.v1",
        "status": "VERIFIED_READY_AWAITING_OUTCOME_AUTHORIZATION",
        "top_k_freeze": {"selected_candidate_ids": list(selected)},
        "deterministic_work_counters": counters,
        "authorization": {
            "optimizer": "NOT_AUTHORIZED",
            "candidate_energy": "NOT_AUTHORIZED",
            "FCI_reporting": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
    }
    core["core_digest"] = _digest(core)
    return {"core": core, "operational_telemetry": {"core_digest": core["core_digest"]}}


class _FakeLedger:
    def __init__(self, root):
        self.root = root
        self.prechecks = []
        self.commits = []

    def precheck(self, value):
        self.prechecks.append(value)

    def replay(self):
        return tuple(self.commits)

    def commit(self, **values):
        receipt = SimpleNamespace(
            selected_candidate_ids=tuple(
                values["result"]["core"]["top_k_freeze"]["selected_candidate_ids"]
            ),
            verifier_core_digest=values["result"]["core"]["core_digest"],
        )
        self.commits.append(receipt)
        return receipt


@pytest.mark.parametrize(
    "method",
    ("immutable-ceo-star-source", "same-structure-reoptimization"),
)
def test_control_methods_use_same_adapter_without_structural_verifier(
    method, tmp_path, monkeypatch
) -> None:
    from v5_final import s11_v2_prepared_executor_v1 as subject

    adapter = QueueV2NativeAdapter()
    request = adapter.first_request_for_method(method)
    from v5_final.parent_native_executors import PreparedMethodNativeExecutor

    marker = PreparedMethodNativeExecutor(
        method,
        "case",
        "old-item",
        object(),
        None,
        (),
        (),
        (),
        (),
        None,
        0,
        0,
        {},
        (),
    )
    monkeypatch.setattr(subject, "prepare_method_executor", lambda *a, **k: marker)
    executor, prepared = prepare_initial_executor_v1(
        adapter=adapter,
        request=request,
        context=object(),
        verifier_ledger=_FakeLedger(tmp_path),
    )
    assert executor.queue_item_id == request.item["queue_item_id"]
    assert prepared.selected_candidate_ids == ()
    assert prepared.preparation_status == "CONTROL_WITHOUT_STRUCTURAL_CANDIDATE"


@pytest.mark.parametrize(
    "method",
    (
        "v5-fixed-source-whitelist-no-replenishment",
        "v5-sequential-with-rebuilding",
    ),
)
def test_both_v5_methods_consume_only_verifier_v2_prepared_candidates(
    method, tmp_path, monkeypatch
) -> None:
    from v5_final import s11_v2_prepared_executor_v1 as subject

    adapter = QueueV2NativeAdapter()
    request = adapter.first_request_for_method(method)
    selected = request.admitted_candidate_ids[:2]
    result = _verifier_result(selected)
    plans = tuple(
        SimpleNamespace(candidates=(SimpleNamespace(candidate_id=value),))
        for value in selected
    )
    rewrites = tuple(
        SimpleNamespace(candidate_id=value, target=object(), target_inverse_hessian=object())
        for value in selected
    )
    session = PreparedSessionV1(
        result,
        selected,
        plans,
        rewrites,
        len(request.admitted_candidate_ids),
        len(request.admitted_candidate_ids),
        result["core"]["core_digest"],
    )
    monkeypatch.setattr(subject, "build_typed_catalog", lambda *a, **k: object())
    monkeypatch.setattr(
        subject, "run_typed_verifier_session", lambda **kwargs: session
    )
    context = SimpleNamespace(
        case_id=request.item["case_id"],
        pool=object(),
        runtime=SimpleNamespace(ansatz=object()),
    )
    executor, prepared = prepare_initial_executor_v1(
        adapter=adapter,
        request=request,
        context=context,
        verifier_ledger=_FakeLedger(tmp_path),
    )
    assert executor.selected_candidate_ids == selected
    assert executor.prepared_rewrites == rewrites
    assert executor.execution_directives["preparation_engine"] == "VerifierV2"
    assert prepared.verifier_core_digest == _digest(result["core"])


def test_magnitude_executor_uses_verified_first_deletion(
    tmp_path, monkeypatch
) -> None:
    from v5_final import s11_v2_prepared_executor_v1 as subject

    adapter = QueueV2NativeAdapter()
    request = adapter.first_request_for_method("structural-magnitude-pruning")
    selected = request.admitted_candidate_ids[:2]
    result = _verifier_result(selected)
    deletion = SimpleNamespace(candidate_id=selected[0])
    bundle = SimpleNamespace(
        candidates=(object(), object()),
        source_state_preparation_id="state-v1:" + "1" * 64,
        verifier=SimpleNamespace(run=lambda values: result),
        selected_deletion=lambda value: deletion,
    )
    monkeypatch.setattr(subject, "build_magnitude_verifier_v2", lambda **k: bundle)
    monkeypatch.setattr(
        subject,
        "magnitude_session_upper_bound",
        lambda **k: subject.conservative_session_upper_bound(
            candidate_count=2,
            selected_count=2,
            source_block_count=1,
            maximum_relation_terms=1,
            matrix_dimension=4,
            qubit_count=2,
            probe_count=3,
        ),
    )
    context = SimpleNamespace(
        case_id=request.item["case_id"],
        pool=SimpleNamespace(n=2),
        runtime=SimpleNamespace(
            ansatz=SimpleNamespace(indices=(1, 2), cumulative_parameter_counts=(2,))
        ),
    )
    executor, prepared = prepare_initial_executor_v1(
        adapter=adapter,
        request=request,
        context=context,
        verifier_ledger=_FakeLedger(tmp_path),
    )
    assert executor.magnitude_deletion is deletion
    assert executor.selected_candidate_ids == (selected[0],)
    assert prepared.selected_candidate_ids == selected


def test_actual_magnitude_candidate_ids_match_frozen_queue(
    tmp_path,
) -> None:
    adapter = QueueV2NativeAdapter()
    request = adapter.first_request_for_method("structural-magnitude-pruning")
    context = build_queue_bound_development_runtime_v1(
        request.execution_item_v4["queue_item_id"]
    )
    bundle = build_magnitude_verifier_v2(
        context=context,
        policy=policy_from_queue_item(request.item),
        checkpoint_dir=tmp_path / "checkpoints",
    )
    actual_ids = {candidate.candidate_id for candidate in bundle.candidates}

    assert actual_ids == set(request.admitted_candidate_ids)
    result = bundle.verifier.run(bundle.candidates)
    selected = set(result["core"]["top_k_freeze"]["selected_candidate_ids"])
    assert selected
    assert selected.issubset(actual_ids)


def test_dynamic_context_binds_current_state_and_snapshot(monkeypatch) -> None:
    from v5_final import s11_v2_prepared_executor_v1 as subject

    monkeypatch.setattr(
        subject,
        "state_preparation_spec",
        lambda *a, **k: SimpleNamespace(state_preparation_id="state-v1:" + "9" * 64),
    )
    context = SimpleNamespace(
        runtime=SimpleNamespace(
            snapshot=lambda: SimpleNamespace(snapshot_digest="8" * 64)
        ),
        _actual_algorithm=object(),
        pool=object(),
        state_preparation_id="state-v1:" + "1" * 64,
        source_checkpoint_digest="2" * 64,
        problem_id="problem-v1:" + "3" * 64,
    )
    view = _CurrentRuntimeVerifierContext(context)
    assert view.state_preparation_id == "state-v1:" + "9" * 64
    assert view.source_checkpoint_digest == "8" * 64
    assert view.problem_id == context.problem_id


def test_dynamic_fixed_whitelist_and_rebuilding_use_same_frozen_policy(
    tmp_path, monkeypatch
) -> None:
    from v5_final import s11_v2_prepared_executor_v1 as subject

    candidates = (
        SimpleNamespace(candidate_id="a", whitelist="keep"),
        SimpleNamespace(candidate_id="b", whitelist="drop"),
    )
    catalog = SimpleNamespace(candidates=candidates, generated_candidate_intent_count=2)
    monkeypatch.setattr(subject, "build_typed_catalog", lambda *a, **k: catalog)
    monkeypatch.setattr(
        subject,
        "candidate_structural_whitelist_key",
        lambda candidate: candidate.whitelist,
    )
    observed = []

    def run(**values):
        observed.append(values)
        return PreparedSessionV1({}, (), (), (), 0, 0, "0" * 64)

    monkeypatch.setattr(subject, "run_typed_verifier_session", run)
    base_context = SimpleNamespace(
        pool=object(),
        runtime=SimpleNamespace(
            ansatz=object(),
            metadata={
                "candidate_work_binding": {
                    "dynamic_catalog_generation_upper_bound": 2,
                    "source_whitelist_keys": ["keep"],
                }
            },
        ),
    )
    queue_item = QueueV2NativeAdapter().first_request_for_method(
        "v5-sequential-with-rebuilding"
    ).item
    for method, expected in (
        ("v5-fixed-source-whitelist-no-replenishment", ("a",)),
        ("v5-sequential-with-rebuilding", ("a", "b")),
    ):
        executor = SimpleNamespace(method_id=method, context=base_context)
        prepare_dynamic_v5_v1(
            executor=executor,
            queue_item=queue_item,
            verifier_ledger=_FakeLedger(tmp_path / method),
        )
        assert observed[-1]["admitted_candidate_ids"] == expected
        assert observed[-1]["bind_current_runtime"] is True

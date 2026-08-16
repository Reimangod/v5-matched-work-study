from copy import deepcopy

import pytest

from v5_final.parent_native_work_accounting import (
    ComponentwiseCapRejected,
    ParentNativeWorkRecorder,
)
from v5_final.semantic_contract_v2 import WorkDelta
from v5_final.s11_v2_queue_native_adapter import (
    METHOD_IDS,
    QueueV2NativeAdapter,
    QueueV2NativeAdapterError,
    audit_adapter_contract,
)
from v5_final.verifier_v2 import CandidateV2, VerifierV2, VerifierV2Policy


def _toy_verifier_result(request, directory):
    candidates = tuple(
        CandidateV2(
            candidate_id,
            f"semantic-{index}",
            f"state-{index}",
            (f"unused-generator-{index}",),
            (),
            ((),),
            float(index),
            2,
            1,
            lambda: (1, 1, 1),
            deletion_shortcut=True,
        )
        for index, candidate_id in enumerate(request.admitted_candidate_ids)
    )
    policy_record = request.item["verifier_policy"]
    verifier = VerifierV2(
        policy=VerifierV2Policy(
            top_k=int(policy_record["top_k"]),
            tie_break=tuple(policy_record["tie_break"]),
            probe_count=int(policy_record["probe_count"]),
            seed=int(policy_record["seed"]),
            tolerance=float.fromhex(policy_record["tolerance_float64_hex"]),
        ),
        generator_loader=lambda _: (_ for _ in ()).throw(
            AssertionError("analytic deletion must not load a generator")
        ),
        checkpoint_dir=directory,
        source_binding={"case_id": request.item["case_id"], "outcome_free": True},
    )
    return verifier.run(candidates)


def test_all_90_items_bind_exact_queue_v2_request_identity() -> None:
    report = audit_adapter_contract()
    assert report["status"] == "PASS_QUEUE_V2_NATIVE_ADAPTER_OUTCOME_BLOCKED"
    assert report["method_count"] == 6
    assert all(report["checks"].values())
    assert report["candidate_energy_evaluations"] == 0


@pytest.mark.parametrize("method_id", METHOD_IDS)
def test_all_six_methods_use_one_outcome_free_adapter_interface(
    method_id, tmp_path
) -> None:
    adapter = QueueV2NativeAdapter()
    request = adapter.first_request_for_method(method_id)
    result = (
        None
        if not request.admitted_candidate_ids
        else _toy_verifier_result(request, tmp_path / method_id)
    )
    prepared = adapter.consume_verifier_v2(request, result)
    audit = prepared.to_audit_dict()
    assert audit["method_id"] == method_id
    assert audit["preparation_engine"] == "VerifierV2"
    assert audit["candidate_energy_evaluations"] == 0
    assert audit["optimizer_iterations"] == 0
    assert audit["FCI_evaluations"] == 0
    assert audit["outcome_execution_authorized"] is False
    assert prepared.deterministic_work_counters["N_dense_expm"] == 0


def test_cap_rejection_occurs_before_state_is_exposed_or_mutated(tmp_path) -> None:
    adapter = QueueV2NativeAdapter()
    request = adapter.first_request_for_method("structural-magnitude-pruning")
    prepared = adapter.consume_verifier_v2(
        request, _toy_verifier_result(request, tmp_path / "verifier")
    )
    recorder = ParentNativeWorkRecorder(
        request=request.work_request,
        cap=request.outcome_cap,
    )
    impossible = WorkDelta(
        energy_evaluations=request.outcome_cap.energy_evaluations + 1
    )
    state = {"mutations": 0}
    with pytest.raises(ComponentwiseCapRejected):
        adapter.precheck_outcome_release(
            prepared, recorder=recorder, projected=impossible
        )
        state["mutations"] += 1
    assert state["mutations"] == 0
    assert len(recorder.events) == 1
    assert recorder.events[0].operation == "cap-rejection"
    assert recorder.events[0].outcome == "cap-rejected"
    assert recorder.events[0].delta == WorkDelta()
    assert recorder.total == WorkDelta()


def test_queue_cap_or_executor_tamper_is_fail_closed() -> None:
    base = QueueV2NativeAdapter()
    queue = deepcopy(base.queue)
    queue["items"][0]["combined_all_counter_cap_digest"] = "0" * 64
    with pytest.raises(QueueV2NativeAdapterError):
        QueueV2NativeAdapter(
            queue=queue,
            predecessor=base.predecessor,
            execution_plan=base.execution_plan,
        )


def test_unknown_method_is_fail_closed() -> None:
    with pytest.raises(QueueV2NativeAdapterError, match="unregistered"):
        QueueV2NativeAdapter().first_request_for_method("unknown")

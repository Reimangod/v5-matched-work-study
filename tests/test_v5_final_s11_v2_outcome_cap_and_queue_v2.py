from __future__ import annotations

from dataclasses import asdict

import pytest

from v5_final.parent_native_work_accounting import (
    ComponentwiseCapRejected,
    ParentNativeWorkRecorder,
    ParentNativeWorkRequest,
    reconstruct,
    work_cap_digest,
)
from v5_final.semantic_contract_v2 import WorkDelta
from v5_final.s11_v2_outcome_cap_freeze import audit as audit_caps
from v5_final.s11_v2_queue_freeze_v2 import audit as audit_queue


def _request(cap: WorkDelta) -> ParentNativeWorkRequest:
    return ParentNativeWorkRequest(
        queue_item_id="synthetic-s11-v2-item",
        method_id="immutable-ceo-star-source",
        case_id="synthetic",
        state_preparation_id="state-v1:" + "1" * 64,
        problem_id="problem-v1:" + "2" * 64,
        hamiltonian_digest="3" * 64,
        source_checkpoint_digest="4" * 64,
        frozen_queue_digest="5" * 64,
        work_cap_digest=work_cap_digest(cap),
    )


def test_frozen_cap_and_queue_v2_audits_pass_without_outcomes() -> None:
    assert audit_caps()["status"].startswith("PASS_Q2_Q4")
    assert audit_queue()["status"].startswith("PASS_Q5")


@pytest.mark.parametrize(
    ("operation", "component", "dimension"),
    (
        ("optimizer-start", "optimizer_starts", None),
        ("optimizer-iteration", "optimizer_iterations", None),
        ("candidate-energy-evaluation", "energy_evaluations", None),
        ("full-gradient-evaluation", "gradient_vector_evaluations", 7),
        ("statevector-recomputation", "statevector_recomputations", None),
        ("full-physical-resource-recount", "resource_recounts", None),
        ("rewrite-verification", "rewrite_verifications", None),
    ),
)
def test_cap_equal_passes_and_plus_one_rejects_before_kernel(
    operation: str, component: str, dimension: int | None
) -> None:
    values = {component: 1}
    if operation == "full-gradient-evaluation":
        values["gradient_component_equivalents"] = 7
    cap = WorkDelta(**values)
    recorder = ParentNativeWorkRecorder(request=_request(cap), cap=cap)
    calls = []
    recorder.invoke(
        operation,
        lambda: calls.append("at-cap") or 1,
        dimension=dimension,
    )
    with pytest.raises(ComponentwiseCapRejected):
        recorder.invoke(
            operation,
            lambda: calls.append("over-cap") or 2,
            dimension=dimension,
        )
    assert calls == ["at-cap"]
    assert recorder.events[-1].operation == "cap-rejection"
    assert recorder.events[-1].delta.is_zero()
    assert recorder.events[-1].evidence["kernel_executed"] is False


def test_failed_kernel_call_is_counted_and_survives_resume() -> None:
    cap = WorkDelta(energy_evaluations=2)
    request = _request(cap)
    recorder = ParentNativeWorkRecorder(request=request, cap=cap)
    with pytest.raises(RuntimeError):
        recorder.invoke(
            "candidate-energy-evaluation",
            lambda: (_ for _ in ()).throw(RuntimeError("synthetic")),
        )
    assert recorder.total.energy_evaluations == 1
    assert recorder.events[-1].outcome == "failed"
    resumed = ParentNativeWorkRecorder.resume(
        request=request, cap=cap, events=recorder.events
    )
    resumed.invoke("candidate-energy-evaluation", lambda: -1.0)
    assert resumed.total.energy_evaluations == 2
    assert reconstruct(resumed.events, request) == resumed.total


def test_physical_state_duplicate_counts_generation_not_search_state() -> None:
    cap = WorkDelta(candidate_generations=2, search_states=1)
    recorder = ParentNativeWorkRecorder(request=_request(cap), cap=cap)
    physical = "physical-state-v3:" + "6" * 64
    assert recorder.register_candidate_intent(
        candidate_id="candidate-a", proposed_physical_state_id=physical
    )
    assert not recorder.register_candidate_intent(
        candidate_id="candidate-b", proposed_physical_state_id=physical
    )
    assert asdict(recorder.total)["candidate_generations"] == 2
    assert asdict(recorder.total)["search_states"] == 1
    duplicate = [
        event for event in recorder.events
        if event.operation == "candidate-physical-state-alias"
    ]
    assert len(duplicate) == 1 and duplicate[0].delta.is_zero()


def test_unknown_operation_fails_closed() -> None:
    cap = WorkDelta()
    recorder = ParentNativeWorkRecorder(request=_request(cap), cap=cap)
    with pytest.raises(Exception, match="unregistered kernel operation"):
        recorder.invoke("new-unregistered-kernel", lambda: None)

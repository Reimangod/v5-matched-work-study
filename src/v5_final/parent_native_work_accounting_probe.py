"""Synthetic, outcome-free behavioral proof for parent-native work accounting."""

from __future__ import annotations

from dataclasses import asdict
import json
from typing import Any

from .parent_native_work_accounting import (
    ComponentwiseCapRejected,
    ParentNativeWorkError,
    ParentNativeWorkRecorder,
    ParentNativeWorkRequest,
    _digest,
    event_from_dict_strict,
    release_summary,
    work_cap_digest,
)
from .semantic_contract_v2 import WorkDelta


def _request(cap: WorkDelta, suffix: str = "main") -> ParentNativeWorkRequest:
    return ParentNativeWorkRequest(
        queue_item_id=f"synthetic-accounting-proof-{suffix}",
        method_id="v5-fixed-source-whitelist-no-replenishment",
        case_id="synthetic-non-molecular-accounting-proof",
        state_preparation_id="state-v1:" + "1" * 64,
        problem_id="problem-v1:" + "2" * 64,
        hamiltonian_digest="3" * 64,
        source_checkpoint_digest="4" * 64,
        frozen_queue_digest="5" * 64,
        work_cap_digest=work_cap_digest(cap),
    )


def _physical(value: str) -> str:
    return "physical-state-v3:" + value * 64


def run_probe() -> dict[str, Any]:
    expected = WorkDelta(
        energy_evaluations=2,
        gradient_vector_evaluations=3,
        gradient_component_equivalents=12,
        hvp_evaluations=1,
        optimizer_starts=1,
        optimizer_iterations=2,
        resource_recounts=1,
        candidate_generations=3,
        search_states=2,
        rewrite_verifications=1,
        statevector_recomputations=1,
    )
    request = _request(expected)
    recorder = ParentNativeWorkRecorder(request=request, cap=expected)
    physical_a = _physical("a")
    physical_b = _physical("b")
    uniqueness = [
        recorder.register_candidate_intent(
            candidate_id="candidate-intent-a1",
            proposed_physical_state_id=physical_a,
        ),
        recorder.register_candidate_intent(
            candidate_id="candidate-intent-a2",
            proposed_physical_state_id=physical_a,
        ),
        recorder.register_candidate_intent(
            candidate_id="candidate-intent-b1",
            proposed_physical_state_id=physical_b,
        ),
    ]
    recorder.invoke("candidate-energy-evaluation", lambda: -1.0)
    recorder.invoke("full-gradient-evaluation", lambda: (0.0,) * 4, dimension=4)
    recorder.invoke("optimizer-start", lambda: None)
    recorder.invoke("optimizer-iteration", lambda: None)
    recorder.invoke("optimizer-iteration", lambda: None)
    recorder.invoke("full-physical-resource-recount", lambda: {"cnot_count": 0})
    recorder.invoke("rewrite-verification", lambda: True)
    recorder.invoke("statevector-recomputation", lambda: (1.0,))
    recorder.record_hvp(
        plus_gradient=lambda: (0.0,) * 4,
        minus_gradient=lambda: (0.0,) * 4,
        dimension=4,
        hvp_call_id="synthetic-hvp-1",
    )

    class SyntheticKernelFailure(RuntimeError):
        pass

    try:
        recorder.invoke(
            "candidate-energy-evaluation",
            lambda: (_ for _ in ()).throw(SyntheticKernelFailure("synthetic")),
        )
    except SyntheticKernelFailure:
        failed_kernel_recorded = True
    else:
        failed_kernel_recorded = False
    ledger = recorder.close()
    summary = release_summary(ledger, request)

    cap_spy = {"calls": 0}
    zero_cap = WorkDelta()
    cap_request = _request(zero_cap, "cap")
    cap_recorder = ParentNativeWorkRecorder(request=cap_request, cap=zero_cap)

    def forbidden_kernel() -> None:
        cap_spy["calls"] += 1

    try:
        cap_recorder.invoke("candidate-energy-evaluation", forbidden_kernel)
    except ComponentwiseCapRejected:
        cap_rejected = True
    else:
        cap_rejected = False
    cap_ledger = cap_recorder.close()

    resume_cap = WorkDelta(energy_evaluations=1, candidate_generations=2, search_states=1)
    resume_request = _request(resume_cap, "resume")
    initial = ParentNativeWorkRecorder(request=resume_request, cap=resume_cap)
    initial.register_candidate_intent(
        candidate_id="resume-a1", proposed_physical_state_id=physical_a
    )
    initial.invoke("candidate-energy-evaluation", lambda: -1.0)
    resumed = ParentNativeWorkRecorder.resume(
        request=resume_request, cap=resume_cap, events=initial.events
    )
    resume_alias_unique = resumed.register_candidate_intent(
        candidate_id="resume-a2", proposed_physical_state_id=physical_a
    )
    resume_spy = {"calls": 0}
    try:
        resumed.invoke(
            "candidate-energy-evaluation",
            lambda: resume_spy.__setitem__("calls", resume_spy["calls"] + 1),
        )
    except ComponentwiseCapRejected:
        resume_cap_rejected = True
    else:
        resume_cap_rejected = False
    resumed_ledger = resumed.close()

    tampered = dict(ledger["events"][6])
    tampered["operation"] = "gradient-component-evaluation"
    tampered_without_digest = dict(tampered)
    tampered_without_digest.pop("event_digest")
    tampered["event_digest"] = _digest(tampered_without_digest)
    try:
        event_from_dict_strict(tampered, request)
    except ParentNativeWorkError:
        semantic_tamper_rejected = True
    else:
        semantic_tamper_rejected = False

    failed_events = [event for event in ledger["events"] if event["outcome"] == "failed"]
    duplicate_events = [
        event for event in ledger["events"] if event["outcome"] == "duplicate"
    ]
    result = {
        "schema": "v5-final.parent-native-work-accounting-probe.v1",
        "probe_kind": "synthetic_non_molecular_control",
        "expected_total": asdict(expected),
        "raw_total": ledger["raw_total"],
        "reconstructed_total": ledger["reconstructed_total"],
        "release_total": summary["work_total"],
        "event_count": ledger["event_count"],
        "candidate_intent_uniqueness": uniqueness,
        "duplicate_event_count": len(duplicate_events),
        "duplicate_events_zero_delta": all(
            not any(event["delta"].values()) for event in duplicate_events
        ),
        "failed_kernel_recorded": failed_kernel_recorded,
        "failed_kernel_event_count": len(failed_events),
        "failed_kernel_work_preserved": (
            len(failed_events) == 1
            and failed_events[0]["delta"]["energy_evaluations"] == 1
        ),
        "componentwise_cap_rejected": cap_rejected,
        "cap_rejection_kernel_calls": cap_spy["calls"],
        "cap_rejection_event": cap_ledger["events"][0],
        "resume_alias_unique": resume_alias_unique,
        "resume_cap_rejected": resume_cap_rejected,
        "resume_rejected_kernel_calls": resume_spy["calls"],
        "resume_raw_total": resumed_ledger["raw_total"],
        "semantic_rehash_tamper_rejected": semantic_tamper_rejected,
        "paper_measurement_cost": summary["paper_measurement_cost"],
        "paper_measurement_cost_claimed_equivalent": summary[
            "paper_measurement_cost_claimed_equivalent"
        ],
        "molecular_candidate_energy_evaluations": 0,
        "H2_H4_queue_executed": False,
        "performance_evidence": False,
    }
    result["probe_digest"] = _digest(result)
    return result


def main() -> None:
    print(json.dumps(run_probe(), sort_keys=True))


if __name__ == "__main__":
    main()

from __future__ import annotations

from dataclasses import asdict
import copy
import hashlib

import pytest

from v5_matched_work.atomic_artifacts import canonical_json_bytes
from v5_final.live_semantic_ledger import (
    LiveSemanticLedgerError,
    LiveSemanticRecorder,
    build_chain_root,
    build_completeness_manifest,
    build_queue_binding,
    build_segment,
    event_from_dict_strict,
    release_summary,
)
from v5_final.method_native_interface import METHOD_IDS, MethodNativeRequest
from v5_final.semantic_contract_v2 import WorkDelta


def _digest(value) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _cap(**updates: int) -> WorkDelta:
    values = {
        "energy_evaluations": 10,
        "gradient_vector_evaluations": 10,
        "gradient_component_equivalents": 100,
        "hvp_evaluations": 10,
        "optimizer_starts": 10,
        "optimizer_iterations": 10,
        "resource_recounts": 10,
        "candidate_generations": 10,
        "search_states": 10,
        "rewrite_verifications": 10,
        "statevector_recomputations": 10,
    }
    values.update(updates)
    return WorkDelta(**values)


def _request(queue_item_id: str = "q1", method_id: str = METHOD_IDS[0], cap: WorkDelta | None = None):
    cap = cap or _cap()
    return MethodNativeRequest(
        queue_item_id=queue_item_id,
        method_id=method_id,
        case_id="synthetic-case",
        state_preparation_id="state-v1:" + "1" * 64,
        problem_id="problem-v1:" + "2" * 64,
        source_checkpoint_digest="3" * 64,
        hamiltonian_digest="4" * 64,
        frozen_queue_digest="5" * 64,
        work_envelope="SYNTHETIC",
        work_cap_digest=_digest(asdict(cap)),
        optimizer_policy_digest="7" * 64,
        acceptance_policy_digest="8" * 64,
        protocol_digest="9" * 64,
        rng_identity={"status": "NOT_USED"},
        environment_identity={"status": "SYNTHETIC"},
        environment_digest="a" * 64,
    )


def _recorder(request: MethodNativeRequest, cap: WorkDelta, *, first_sequence: int = 0):
    return LiveSemanticRecorder(
        request=request,
        cap=cap,
        root_digest="0" * 64,
        producer="v5_final.method_native.synthetic_kernel",
        first_sequence=first_sequence,
    )


def test_live_kernel_calls_charge_energy_and_full_gradient_semantics() -> None:
    cap = _cap()
    request = _request(cap=cap)
    recorder = _recorder(request, cap)
    assert recorder.execute_kernel(
        "candidate-energy-evaluation", lambda: -1.25, candidate_id="candidate-a"
    ) == -1.25
    assert recorder.execute_kernel(
        "full-gradient-evaluation", lambda: [0.0] * 6, dimension=6
    ) == [0.0] * 6
    ledger = recorder.close()
    summary = release_summary(ledger)
    assert summary["work_total"]["energy_evaluations"] == 1
    assert summary["work_total"]["gradient_vector_evaluations"] == 1
    assert summary["work_total"]["gradient_component_equivalents"] == 6
    assert summary["work_total"] == ledger["raw_counter_total"]


def test_digest_valid_but_semantically_wrong_delta_is_rejected() -> None:
    cap = _cap()
    recorder = _recorder(_request(cap=cap), cap)
    recorder.execute_kernel("candidate-energy-evaluation", lambda: 0.0)
    value = copy.deepcopy(recorder.events[0].to_dict())
    value["delta"]["energy_evaluations"] = 0
    payload = {key: item for key, item in value.items() if key != "event_id"}
    value["event_id"] = "live-kernel-event-v1:" + _digest(payload)
    with pytest.raises(LiveSemanticLedgerError, match="inconsistent"):
        event_from_dict_strict(value)


def test_different_candidate_ids_share_one_canonical_search_state() -> None:
    cap = _cap()
    recorder = _recorder(_request(cap=cap), cap)
    state = "physical-state-v1:" + "f" * 64
    assert recorder.register_candidate_state(candidate_id="intent-a", proposed_physical_state_id=state)
    assert not recorder.register_candidate_state(candidate_id="intent-b", proposed_physical_state_id=state)
    ledger = recorder.close()
    assert ledger["raw_counter_total"]["candidate_generations"] == 2
    assert ledger["raw_counter_total"]["search_states"] == 1
    duplicates = [event for event in recorder.events if event.operation == "canonical-state-duplicate"]
    assert len(duplicates) == 1
    assert not any(asdict(duplicates[0].delta).values())


def test_cap_rejection_occurs_before_kernel_call_or_mutation() -> None:
    cap = _cap(energy_evaluations=0)
    recorder = _recorder(_request(cap=cap), cap)
    called = False

    def kernel() -> float:
        nonlocal called
        called = True
        return 0.0

    with pytest.raises(LiveSemanticLedgerError, match="exceed"):
        recorder.execute_kernel("candidate-energy-evaluation", kernel)
    assert called is False
    assert recorder.events == ()
    assert not any(asdict(recorder.raw_total).values())


def test_nonempty_frozen_queue_chain_global_sequence_and_completeness() -> None:
    cap = _cap()
    queue = {
        "schema": "synthetic.mb3.queue",
        "status": "FROZEN_PRE_OUTCOME",
        "queue": [
            {"queue_item_id": "q1", "method_id": METHOD_IDS[0]},
            {"queue_item_id": "q2", "method_id": METHOD_IDS[1]},
        ],
    }
    binding = build_queue_binding(queue, _digest(queue))
    root = build_chain_root(binding)
    first_request = _request("q1", METHOD_IDS[0], cap)
    first_recorder = _recorder(first_request, cap)
    first_recorder.execute_kernel("full-physical-resource-recount", lambda: {"ok": True})
    first = build_segment(
        previous_digest=root["root_digest"],
        segment_index=0,
        request=first_request,
        events=first_recorder.events,
    )
    second_request = _request("q2", METHOD_IDS[1], cap)
    second_recorder = _recorder(second_request, cap, first_sequence=1)
    second_recorder.execute_kernel("optimizer-start", lambda: None)
    second = build_segment(
        previous_digest=first["segment_digest"],
        segment_index=1,
        request=second_request,
        events=second_recorder.events,
    )
    incomplete = build_completeness_manifest(
        root=root, binding=binding, completed_queue_item_ids=[], segments=[]
    )
    complete = build_completeness_manifest(
        root=root,
        binding=binding,
        completed_queue_item_ids=["q1", "q2"],
        segments=[first, second],
    )
    assert incomplete["complete"] is False
    assert complete["complete"] is True
    assert complete["event_count"] == 2

    empty = {"schema": "synthetic", "status": "FROZEN_PRE_OUTCOME", "queue": []}
    with pytest.raises(LiveSemanticLedgerError, match="nonempty"):
        build_queue_binding(empty, _digest(empty))

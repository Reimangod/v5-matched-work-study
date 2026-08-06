from __future__ import annotations

from dataclasses import asdict
import copy
import hashlib
import pytest

from v5_matched_work.atomic_artifacts import canonical_json_bytes
from v5_matched_work.kernel_ledger_v4 import (
    KernelEventV4, KernelLedgerV4Error, bind_frozen_queue, build_chain_root,
    build_completeness_manifest, build_segment, event_from_dict_strict, event_to_dict, protocol,
)


def _queue():
    artifact = {
        "schema": "test.freeze.v4", "status": "FROZEN_PRE_OUTCOME",
        "queue": [
            {"queue_item_id": "q1", "case_id": "h2", "method_id": "m"},
            {"queue_item_id": "q2", "case_id": "h4", "method_id": "m"},
        ],
    }
    digest = hashlib.sha256(canonical_json_bytes(artifact)).hexdigest()
    return artifact, bind_frozen_queue(artifact, digest)


def _event(sequence: int, queue: str, state_digit: str, operation: str, *, units: int = 1):
    return KernelEventV4.create(
        sequence=sequence, queue_item_id=queue,
        state_preparation_id="state-v1:" + state_digit * 64,
        problem_id="problem-v1:" + state_digit * 64,
        method_id="m", case_id="c", candidate_id="x", path_id=queue + "/root",
        operation=operation, outcome="duplicate" if operation == "duplicate-detection" else "completed",
        units=0 if operation == "duplicate-detection" else units,
    )


def test_semantic_event_validation_rejects_digest_valid_wrong_delta() -> None:
    event = _event(0, "q1", "1", "candidate-energy-evaluation")
    value = event_to_dict(event)
    value["delta"]["N_E"] = 0
    payload = {key: value[key] for key in value if key not in {"event_id", "delta"}}
    payload["delta"] = value["delta"]
    value["event_id"] = "work-event-v4:" + hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    with pytest.raises(KernelLedgerV4Error, match="semantically inconsistent"):
        event_from_dict_strict(value)
    duplicate = _event(0, "q1", "1", "duplicate-detection")
    assert all(component == 0 for component in asdict(duplicate.delta).values())


def test_nonempty_frozen_queue_binding_and_complete_chain() -> None:
    _, binding = _queue(); root = build_chain_root(binding)
    first_event = _event(0, "q1", "1", "candidate-energy-evaluation")
    first = build_segment(
        previous_digest=root["root_digest"], segment_index=0, queue_item_id="q1",
        state_preparation_id=first_event.state_preparation_id, problem_id=first_event.problem_id,
        events=[first_event],
    )
    second_event = _event(1, "q2", "2", "full-physical-resource-recount")
    second = build_segment(
        previous_digest=first["segment_digest"], segment_index=1, queue_item_id="q2",
        state_preparation_id=second_event.state_preparation_id, problem_id=second_event.problem_id,
        events=[second_event],
    )
    manifest = build_completeness_manifest(
        root=root, binding=binding, completed_queue_item_ids=["q1", "q2"], segments=[first, second],
    )
    assert manifest["complete"]
    assert manifest["expected_queue_count"] == 2
    assert manifest["candidate_energy_evaluations"] == 1
    assert protocol()["status"].startswith("IMPLEMENTED")


def test_empty_or_forged_queue_and_event_segment_binding_fail_closed() -> None:
    empty = {"schema": "test", "status": "FROZEN_PRE_OUTCOME", "queue": []}
    with pytest.raises(KernelLedgerV4Error, match="nonempty"):
        bind_frozen_queue(empty, hashlib.sha256(canonical_json_bytes(empty)).hexdigest())
    _, binding = _queue(); root = build_chain_root(binding)
    event = _event(0, "q1", "1", "candidate-energy-evaluation")
    with pytest.raises(KernelLedgerV4Error, match="queue item differs"):
        build_segment(
            previous_digest=root["root_digest"], segment_index=0, queue_item_id="q2",
            state_preparation_id=event.state_preparation_id, problem_id=event.problem_id,
            events=[event],
        )

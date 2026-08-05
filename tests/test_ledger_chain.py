from __future__ import annotations

import copy
import pytest

from v5_matched_work.ledger_chain import (
    LedgerChainError, build_completeness_manifest, build_segment, protocol, verify_chain,
)
from v5_matched_work.work_ledger import WorkEvent, WorkVector


def _event(sequence: int, queue: str, operation: str) -> WorkEvent:
    return WorkEvent.create(
        sequence=sequence, method_id="m", case_id="c", candidate_id="candidate",
        path_id=queue, operation=operation, outcome="completed", cache="not-applicable",
        delta=WorkVector(N_E=1) if operation == "candidate-energy-evaluation" else WorkVector(N_recount=1),
    )


def test_content_addressed_segments_and_complete_manifest() -> None:
    root = "0" * 64
    first = build_segment(
        previous_segment_digest=root, segment_index=0, queue_item_id="q1",
        state_preparation_id="state-v1:" + "1" * 64,
        problem_id="problem-v1:" + "2" * 64,
        events=[_event(0, "q1", "candidate-energy-evaluation")],
    )
    second = build_segment(
        previous_segment_digest=first["segment_digest"], segment_index=1, queue_item_id="q2",
        state_preparation_id="state-v1:" + "3" * 64,
        problem_id="problem-v1:" + "4" * 64,
        events=[_event(1, "q2", "full-physical-resource-recount")],
    )
    assert len(verify_chain(root, [first, second])) == 2
    manifest = build_completeness_manifest(
        root_digest=root, expected_queue_item_ids=["q1", "q2"],
        completed_queue_item_ids=["q1", "q2"], segments=[first, second],
    )
    assert manifest["complete"]
    assert manifest["candidate_energy_evaluations"] == 1
    assert protocol()["status"].startswith("IMPLEMENTED")


def test_broken_chain_and_incomplete_queue_fail_closed() -> None:
    root = "0" * 64
    segment = build_segment(
        previous_segment_digest=root, segment_index=0, queue_item_id="q1",
        state_preparation_id="state-v1:" + "1" * 64,
        problem_id="problem-v1:" + "2" * 64,
        events=[_event(0, "q1", "candidate-energy-evaluation")],
    )
    broken = copy.deepcopy(segment); broken["previous_segment_digest"] = "f" * 64
    with pytest.raises(LedgerChainError):
        verify_chain(root, [broken])
    manifest = build_completeness_manifest(
        root_digest=root, expected_queue_item_ids=["q1", "q2"],
        completed_queue_item_ids=["q1"], segments=[segment],
    )
    assert not manifest["complete"]

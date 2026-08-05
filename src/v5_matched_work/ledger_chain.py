"""Content-addressed raw-event segments and completeness manifests for S6+."""

from __future__ import annotations

import hashlib
from typing import Any, Iterable, Sequence

from .atomic_artifacts import canonical_json_bytes
from .work_ledger import (
    WorkEvent, WorkLedgerError, WorkVector, event_from_dict, event_to_dict,
    reconstruct_candidate_energy_evaluations,
)


class LedgerChainError(RuntimeError):
    pass


def _digest_without(value: dict[str, Any], field: str) -> str:
    payload = dict(value); payload.pop(field, None)
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def build_segment(
    *,
    previous_segment_digest: str,
    segment_index: int,
    queue_item_id: str,
    state_preparation_id: str,
    problem_id: str,
    events: Iterable[WorkEvent],
) -> dict[str, Any]:
    materialized = list(events)
    if not previous_segment_digest or len(previous_segment_digest) != 64:
        raise LedgerChainError("previous segment/root digest is required")
    if isinstance(segment_index, bool) or not isinstance(segment_index, int) or segment_index < 0:
        raise LedgerChainError("segment index must be a nonnegative integer")
    if not queue_item_id or not state_preparation_id.startswith("state-v1:") or not problem_id.startswith("problem-v1:"):
        raise LedgerChainError("queue item and scientific source identities are required")
    if not materialized:
        raise LedgerChainError("event segments cannot be empty")
    sequences = [event.sequence for event in materialized]
    if sequences != list(range(sequences[0], sequences[0] + len(sequences))):
        raise LedgerChainError("segment event sequence is not contiguous")
    result = {
        "schema": "v5-matched-work.work-event-segment.v3",
        "segment_index": segment_index,
        "previous_segment_digest": previous_segment_digest,
        "queue_item_id": queue_item_id,
        "source_identity": {
            "StatePreparationID": state_preparation_id,
            "ProblemID": problem_id,
        },
        "first_sequence": sequences[0], "last_sequence": sequences[-1],
        "event_count": len(materialized),
        "events": [event_to_dict(event) for event in materialized],
    }
    result["segment_digest"] = _digest_without(result, "segment_digest")
    return result


def verify_chain(root_digest: str, segments: Sequence[dict[str, Any]]) -> list[WorkEvent]:
    previous = root_digest
    next_sequence = 0
    events: list[WorkEvent] = []
    for expected_index, segment in enumerate(segments):
        if segment["segment_index"] != expected_index:
            raise LedgerChainError("segment index is missing or reordered")
        if segment["previous_segment_digest"] != previous:
            raise LedgerChainError("segment digest chain is broken")
        if segment["segment_digest"] != _digest_without(segment, "segment_digest"):
            raise LedgerChainError("segment content digest mismatch")
        materialized = [event_from_dict(value) for value in segment["events"]]
        if not materialized or materialized[0].sequence != next_sequence:
            raise LedgerChainError("global event sequence is missing or duplicated")
        if [event.sequence for event in materialized] != list(range(next_sequence, next_sequence + len(materialized))):
            raise LedgerChainError("global event sequence is not monotonic")
        if segment["first_sequence"] != materialized[0].sequence or segment["last_sequence"] != materialized[-1].sequence:
            raise LedgerChainError("segment sequence bounds mismatch")
        if segment["event_count"] != len(materialized):
            raise LedgerChainError("segment event count mismatch")
        events.extend(materialized)
        next_sequence += len(materialized)
        previous = segment["segment_digest"]
    return events


def build_completeness_manifest(
    *,
    root_digest: str,
    expected_queue_item_ids: Sequence[str],
    completed_queue_item_ids: Sequence[str],
    segments: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    events = verify_chain(root_digest, segments)
    expected = list(expected_queue_item_ids)
    completed = list(completed_queue_item_ids)
    segment_queue_ids = [segment["queue_item_id"] for segment in segments]
    checks = {
        "expected_queue_unique": len(expected) == len(set(expected)),
        "completed_queue_unique": len(completed) == len(set(completed)),
        "all_completed_are_expected": set(completed).issubset(expected),
        "all_segment_queue_items_expected": set(segment_queue_ids).issubset(expected),
        "every_completed_queue_item_has_segment": set(completed).issubset(segment_queue_ids),
        "all_expected_queue_items_completed": set(completed) == set(expected),
        "global_sequence_monotonic": [event.sequence for event in events] == list(range(len(events))),
    }
    result = {
        "schema": "v5-matched-work.work-ledger-completeness-manifest.v3",
        "root_digest": root_digest,
        "expected_queue_item_ids": expected,
        "completed_queue_item_ids": completed,
        "segment_digests": [segment["segment_digest"] for segment in segments],
        "final_segment_digest": segments[-1]["segment_digest"] if segments else root_digest,
        "segment_count": len(segments), "event_count": len(events),
        "candidate_energy_evaluations": reconstruct_candidate_energy_evaluations(events),
        "checks": checks, "complete": all(checks.values()),
    }
    result["manifest_digest"] = _digest_without(result, "manifest_digest")
    return result


def protocol() -> dict[str, Any]:
    result = {
        "schema": "v5-matched-work.work-ledger-chain-protocol.v3",
        "status": "IMPLEMENTED_NOT_YET_BOUND_TO_PRODUCTION_KERNELS",
        "segment_required_fields": [
            "previous_segment_digest", "segment_index", "queue_item_id",
            "source_identity", "first_sequence", "last_sequence", "events", "segment_digest",
        ],
        "manifest_required_checks": [
            "expected queue uniqueness", "queue completion", "segment coverage",
            "global monotonic sequence", "full candidate-energy reconstruction",
        ],
        "publication": "exclusive-create content-addressed segments; no in-place append or overwrite",
        "claim_boundary": "Ledger-chain infrastructure only; no production kernel binding or candidate performance.",
    }
    result["protocol_digest"] = _digest_without(result, "protocol_digest")
    return result

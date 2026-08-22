"""Nonempty content-bound pre-outcome execution queues."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Iterable, Mapping

from v5_matched_work.atomic_artifacts import canonical_json_bytes


class FrozenQueueError(ValueError):
    pass


@dataclass(frozen=True)
class QueueItem:
    execution_request_id: str
    candidate_intent_id: str
    proposed_physical_state_id: str
    source_digest: str
    catalog_digest: str

    def payload(self) -> dict[str, str]:
        return {
            "execution_request_id": self.execution_request_id,
            "candidate_intent_id": self.candidate_intent_id,
            "proposed_physical_state_id": self.proposed_physical_state_id,
            "source_digest": self.source_digest,
            "catalog_digest": self.catalog_digest,
        }

    @property
    def queue_item_id(self) -> str:
        return "queue-item-v1:" + hashlib.sha256(
            canonical_json_bytes(self.payload())
        ).hexdigest()


def freeze_queue(items: Iterable[QueueItem], *, protocol_digest: str) -> dict[str, Any]:
    materialized = tuple(items)
    if not materialized:
        raise FrozenQueueError("frozen queue must be nonempty")
    if len(protocol_digest) != 64:
        raise FrozenQueueError("protocol digest must be SHA-256")
    ids = [item.queue_item_id for item in materialized]
    if len(ids) != len(set(ids)):
        raise FrozenQueueError("frozen queue items must be unique")
    snapshot = [item.payload() | {"queue_item_id": item.queue_item_id} for item in materialized]
    result: dict[str, Any] = {
        "schema": "v5-final.frozen-queue.v1",
        "status": "FROZEN_PRE_OUTCOME",
        "protocol_digest": protocol_digest,
        "expected_queue_count": len(snapshot),
        "expected_queue_item_ids": ids,
        "queue": snapshot,
    }
    result["queue_digest"] = hashlib.sha256(canonical_json_bytes(result)).hexdigest()
    return result


def verify_frozen_queue(value: Mapping[str, Any]) -> tuple[str, ...]:
    payload = dict(value)
    observed = payload.pop("queue_digest", None)
    if observed != hashlib.sha256(canonical_json_bytes(payload)).hexdigest():
        raise FrozenQueueError("frozen queue digest mismatch")
    queue = list(value.get("queue", []))
    expected = list(value.get("expected_queue_item_ids", []))
    if not queue or value.get("expected_queue_count") != len(queue):
        raise FrozenQueueError("frozen queue is empty or count mismatched")
    rebuilt = []
    for item in queue:
        body = {key: item[key] for key in QueueItem.__dataclass_fields__}
        rebuilt.append(QueueItem(**body).queue_item_id)
    if rebuilt != expected or len(rebuilt) != len(set(rebuilt)):
        raise FrozenQueueError("frozen queue item identity or order mismatch")
    return tuple(rebuilt)

"""Atomic raw-counter/semantic-ledger path and three-way reconciliation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from typing import Any, Mapping, Sequence

from v5_matched_work.atomic_artifacts import canonical_json_bytes

from .semantic_contract_v2 import SemanticDelta, WorkDelta, WORK_COMPONENTS
from .semantic_events import SemanticEvent, SemanticEventError, SemanticEventType, event_from_dict_strict


class WorkLedgerError(RuntimeError):
    pass


def _add(left: WorkDelta, right: WorkDelta) -> WorkDelta:
    return WorkDelta(
        **{
            field: getattr(left, field) + getattr(right, field)
            for field in WORK_COMPONENTS
        }
    )


def _fits(value: WorkDelta, cap: WorkDelta) -> bool:
    return all(getattr(value, field) <= getattr(cap, field) for field in WORK_COMPONENTS)


def reconstruct_work(
    events: Sequence[SemanticEvent], *, root_digest: str | None = None
) -> WorkDelta:
    if [event.sequence for event in events] != list(range(len(events))):
        raise WorkLedgerError("semantic event sequence is missing, duplicated, or reordered")
    previous = root_digest
    total = WorkDelta()
    for event in events:
        if previous is not None and event.previous_event_digest != previous:
            raise WorkLedgerError("semantic event digest chain is broken")
        previous = event.event_digest
        total = _add(total, event.delta.work_delta)
    return total


class IntegratedWorkLedger:
    """The only public API for counted executor operations.

    A successful call appends the semantic event and increments the in-memory raw
    counter as one operation. Cap rejection happens before either mutation.
    """

    def __init__(self, *, cap: WorkDelta, root_digest: str, producer: str) -> None:
        if len(root_digest) != 64:
            raise WorkLedgerError("ledger root digest must be SHA-256")
        if not producer.startswith("v5_final.executor"):
            raise WorkLedgerError("ledger producer must be a production executor")
        self.cap = cap
        self.root_digest = root_digest
        self.producer = producer
        self._raw_total = WorkDelta()
        self._events: list[SemanticEvent] = []
        self._closed = False

    @property
    def events(self) -> tuple[SemanticEvent, ...]:
        return tuple(self._events)

    @property
    def raw_total(self) -> WorkDelta:
        return self._raw_total

    def record_operation(
        self,
        *,
        event_type: SemanticEventType,
        queue_item_id: str,
        delta: SemanticDelta,
        evidence: Mapping[str, Any],
        execution_request_id: str | None = None,
        candidate_intent_id: str | None = None,
        proposed_physical_state_id: str | None = None,
    ) -> SemanticEvent:
        if self._closed:
            raise WorkLedgerError("closed ledger cannot accept operations")
        projected = _add(self._raw_total, delta.work_delta)
        if not _fits(projected, self.cap):
            raise WorkLedgerError("operation would exceed a componentwise work cap")
        previous = self._events[-1].event_digest if self._events else self.root_digest
        try:
            event = SemanticEvent._create(
                previous_event_digest=previous,
                sequence=len(self._events),
                event_type=event_type,
                producer=self.producer,
                queue_item_id=queue_item_id,
                execution_request_id=execution_request_id,
                candidate_intent_id=candidate_intent_id,
                proposed_physical_state_id=proposed_physical_state_id,
                delta=delta,
                evidence=evidence,
            )
        except SemanticEventError as error:
            raise WorkLedgerError(str(error)) from error
        self._events.append(event)
        self._raw_total = projected
        return event

    def close(self) -> dict[str, Any]:
        if self._closed:
            raise WorkLedgerError("ledger is already closed")
        self._closed = True
        ledger_total = reconstruct_work(self.events, root_digest=self.root_digest)
        document: dict[str, Any] = {
            "schema": "v5-final.integrated-work-ledger.v1",
            "producer": self.producer,
            "root_digest": self.root_digest,
            "event_count": len(self._events),
            "events": [event.to_dict() for event in self._events],
            "raw_counter_total": asdict(self._raw_total),
            "semantic_ledger_total": asdict(ledger_total),
            "cap": asdict(self.cap),
            "final_event_digest": self._events[-1].event_digest
            if self._events
            else self.root_digest,
        }
        document["ledger_digest"] = hashlib.sha256(canonical_json_bytes(document)).hexdigest()
        return document


def _validated_document_total(ledger_document: Mapping[str, Any]) -> WorkDelta:
    document_without_digest = dict(ledger_document)
    observed_digest = document_without_digest.pop("ledger_digest", None)
    if observed_digest != hashlib.sha256(canonical_json_bytes(document_without_digest)).hexdigest():
        raise WorkLedgerError("integrated ledger digest mismatch")
    events = [event_from_dict_strict(value) for value in ledger_document["events"]]
    if ledger_document["event_count"] != len(events):
        raise WorkLedgerError("integrated ledger event count mismatch")
    ledger_total = reconstruct_work(events, root_digest=ledger_document["root_digest"])
    expected_final = events[-1].event_digest if events else ledger_document["root_digest"]
    if ledger_document["final_event_digest"] != expected_final:
        raise WorkLedgerError("integrated ledger final event digest mismatch")
    if ledger_document["semantic_ledger_total"] != asdict(ledger_total):
        raise WorkLedgerError("integrated ledger recorded semantic total mismatch")
    if ledger_document["raw_counter_total"] != asdict(ledger_total):
        raise WorkLedgerError("integrated ledger raw and semantic totals differ")
    if not _fits(ledger_total, WorkDelta(**dict(ledger_document["cap"]))):
        raise WorkLedgerError("integrated ledger exceeds its componentwise cap")
    return ledger_total


def release_summary(ledger_document: Mapping[str, Any]) -> dict[str, Any]:
    ledger_total = _validated_document_total(ledger_document)
    result: dict[str, Any] = {
        "schema": "v5-final.release-work-summary.v1",
        "ledger_digest": ledger_document["ledger_digest"],
        "event_count": ledger_document["event_count"],
        "work_total": asdict(ledger_total),
    }
    result["summary_digest"] = hashlib.sha256(canonical_json_bytes(result)).hexdigest()
    return result


def reconcile(
    *,
    independent_raw_counter: WorkDelta,
    ledger_document: Mapping[str, Any],
    summary: Mapping[str, Any],
) -> dict[str, bool]:
    document_without_digest = dict(ledger_document)
    observed_ledger_digest = document_without_digest.pop("ledger_digest", None)
    ledger_digest_valid = observed_ledger_digest == hashlib.sha256(
        canonical_json_bytes(document_without_digest)
    ).hexdigest()
    semantic_total = _validated_document_total(ledger_document)
    expected_summary = release_summary(ledger_document)
    raw_dict = asdict(independent_raw_counter)
    semantic_dict = asdict(semantic_total)
    checks = {
        "ledger_digest_valid": ledger_digest_valid,
        "document_raw_equals_independent_raw": ledger_document["raw_counter_total"]
        == raw_dict,
        "raw_equals_semantic_ledger": raw_dict == semantic_dict,
        "semantic_ledger_equals_release_summary": semantic_dict == summary["work_total"],
        "release_summary_digest_valid": dict(summary) == expected_summary,
        "every_component_reconciled": all(
            raw_dict[field]
            == semantic_dict[field]
            == summary["work_total"][field]
            for field in WORK_COMPONENTS
        ),
    }
    return checks

"""Componentwise work accounting with pre-operation cap enforcement."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from typing import Any, Iterable

from .atomic_artifacts import canonical_json_bytes


FIELDS = ("N_E", "N_G", "N_gradcomp", "N_HVP", "N_exact", "N_recount", "N_rewrite", "N_states", "N_rounds")


class WorkLedgerError(RuntimeError):
    pass


@dataclass(frozen=True)
class WorkVector:
    N_E: int = 0
    N_G: int = 0
    N_gradcomp: int = 0
    N_HVP: int = 0
    N_exact: int = 0
    N_recount: int = 0
    N_rewrite: int = 0
    N_states: int = 0
    N_rounds: int = 0

    def __post_init__(self) -> None:
        if any(isinstance(getattr(self, field), bool) or not isinstance(getattr(self, field), int) or getattr(self, field) < 0 for field in FIELDS):
            raise WorkLedgerError("work components must be nonnegative integers")

    def add(self, other: "WorkVector") -> "WorkVector":
        return WorkVector(**{field: getattr(self, field) + getattr(other, field) for field in FIELDS})

    def fits(self, cap: "WorkVector") -> bool:
        return all(getattr(self, field) <= getattr(cap, field) for field in FIELDS)


@dataclass(frozen=True)
class WorkEvent:
    event_id: str
    sequence: int
    method_id: str
    case_id: str
    candidate_id: str | None
    path_id: str
    operation: str
    outcome: str
    cache: str
    delta: WorkVector

    @classmethod
    def create(cls, *, sequence: int, method_id: str, case_id: str, candidate_id: str | None, path_id: str, operation: str, outcome: str, cache: str, delta: WorkVector) -> "WorkEvent":
        if outcome not in {"accepted", "rejected", "failed", "duplicate", "rollback", "completed"}:
            raise WorkLedgerError("unregistered work outcome")
        if cache not in {"not-applicable", "hit", "miss"}:
            raise WorkLedgerError("cache disposition is invalid")
        payload = {"sequence": sequence, "method_id": method_id, "case_id": case_id, "candidate_id": candidate_id, "path_id": path_id, "operation": operation, "outcome": outcome, "cache": cache, "delta": asdict(delta)}
        return cls(
            "work-event-v1:" + hashlib.sha256(canonical_json_bytes(payload)).hexdigest(),
            sequence,
            method_id,
            case_id,
            candidate_id,
            path_id,
            operation,
            outcome,
            cache,
            delta,
        )


class WorkLedger:
    def __init__(self, cap: WorkVector):
        self.cap = cap
        self.total = WorkVector()
        self.events: list[WorkEvent] = []

    def can_start(self, delta: WorkVector) -> bool:
        return self.total.add(delta).fits(self.cap)

    def record(self, **values: Any) -> WorkEvent:
        delta = values.pop("delta")
        if not self.can_start(delta):
            raise WorkLedgerError("operation would exceed a componentwise work cap")
        event = WorkEvent.create(sequence=len(self.events), delta=delta, **values)
        self.events.append(event)
        self.total = self.total.add(delta)
        return event


def reconstruct(events: Iterable[WorkEvent]) -> WorkVector:
    ordered = sorted(events, key=lambda event: event.sequence)
    if [event.sequence for event in ordered] != list(range(len(ordered))):
        raise WorkLedgerError("event sequence is missing or duplicated")
    total = WorkVector()
    for event in ordered:
        total = total.add(event.delta)
    return total

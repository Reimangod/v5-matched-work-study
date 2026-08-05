"""Componentwise work accounting with pre-operation cap enforcement."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from typing import Any, Iterable, Mapping

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

    def charge(
        self,
        operation: str,
        *,
        method_id: str,
        case_id: str,
        candidate_id: str | None,
        path_id: str,
        outcome: str = "completed",
        cache: str = "not-applicable",
        units: int = 1,
        dimension: int | None = None,
    ) -> WorkEvent:
        """Charge a registered physical operation through the shared counter API.

        Adapters are not allowed to construct counter deltas themselves.  Keeping
        the mapping here makes equal operation names mean equal work everywhere.
        """

        delta = operation_delta(operation, units=units, dimension=dimension)
        return self.record(
            method_id=method_id,
            case_id=case_id,
            candidate_id=candidate_id,
            path_id=path_id,
            operation=operation,
            outcome=outcome,
            cache=cache,
            delta=delta,
        )


OPERATION_COMPONENT = {
    "source-energy-evaluation": "N_E",
    "candidate-energy-evaluation": "N_E",
    "full-gradient-evaluation": "N_G",
    "gradient-component-evaluation": "N_gradcomp",
    "hessian-vector-product": "N_HVP",
    "exact-candidate-attempt": "N_exact",
    "full-physical-resource-recount": "N_recount",
    "exact-algebraic-rewrite": "N_rewrite",
    "unique-search-state-expansion": "N_states",
    "sequential-round-attempt": "N_rounds",
}


def operation_delta(operation: str, *, units: int = 1, dimension: int | None = None) -> WorkVector:
    if isinstance(units, bool) or not isinstance(units, int) or units < 0:
        raise WorkLedgerError("operation units must be a nonnegative integer")
    if operation == "full-gradient-evaluation":
        if isinstance(dimension, bool) or not isinstance(dimension, int) or dimension < 0:
            raise WorkLedgerError("full gradients require a nonnegative dimension")
        return WorkVector(N_G=units, N_gradcomp=units * dimension)
    try:
        field = OPERATION_COMPONENT[operation]
    except KeyError as error:
        raise WorkLedgerError(f"unregistered work operation: {operation}") from error
    return WorkVector(**{field: units})


def event_to_dict(event: WorkEvent) -> dict[str, Any]:
    value = asdict(event)
    return value


def event_from_dict(value: Mapping[str, Any]) -> WorkEvent:
    delta = WorkVector(**dict(value["delta"]))
    rebuilt = WorkEvent.create(
        sequence=int(value["sequence"]),
        method_id=str(value["method_id"]),
        case_id=str(value["case_id"]),
        candidate_id=value.get("candidate_id"),
        path_id=str(value["path_id"]),
        operation=str(value["operation"]),
        outcome=str(value["outcome"]),
        cache=str(value["cache"]),
        delta=delta,
    )
    if rebuilt.event_id != value["event_id"]:
        raise WorkLedgerError("raw event digest mismatch")
    return rebuilt


def reconstruct_candidate_energy_evaluations(events: Iterable[WorkEvent]) -> int:
    ordered = list(events)
    reconstruct(ordered)
    return sum(
        event.delta.N_E
        for event in ordered
        if event.operation == "candidate-energy-evaluation"
    )


def raw_ledger_document(
    *,
    ledger_id: str,
    phase: str,
    cap: WorkVector,
    events: Iterable[WorkEvent],
) -> dict[str, Any]:
    materialized = list(events)
    total = reconstruct(materialized)
    result = {
        "schema": "v5-matched-work.raw-work-ledger.v2",
        "ledger_id": ledger_id,
        "phase": phase,
        "counter_api": "v5_matched_work.work_ledger.WorkLedger.charge",
        "operation_component": dict(sorted(OPERATION_COMPONENT.items())),
        "cap": asdict(cap),
        "events": [event_to_dict(event) for event in materialized],
        "reconstructed_total": asdict(total),
        "reconstructed_candidate_energy_evaluations": reconstruct_candidate_energy_evaluations(materialized),
    }
    result["ledger_digest"] = hashlib.sha256(canonical_json_bytes(result)).hexdigest()
    return result


def reconstruct(events: Iterable[WorkEvent]) -> WorkVector:
    ordered = sorted(events, key=lambda event: event.sequence)
    if [event.sequence for event in ordered] != list(range(len(ordered))):
        raise WorkLedgerError("event sequence is missing or duplicated")
    total = WorkVector()
    for event in ordered:
        total = total.add(event.delta)
    return total

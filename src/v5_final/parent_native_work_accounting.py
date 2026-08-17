"""Kernel-boundary work accounting with strict semantic reconstruction."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from typing import Any, Callable, Mapping, Sequence, TypeVar

from v5_matched_work.atomic_artifacts import canonical_json_bytes

from .semantic_contract_v2 import WORK_COMPONENTS, WorkDelta


T = TypeVar("T")

METHOD_IDS = (
    "immutable-ceo-star-source",
    "same-structure-reoptimization",
    "structural-magnitude-pruning",
    "v4.1-one-shot-joint-compression",
    "v5-fixed-source-whitelist-no-replenishment",
    "v5-sequential-with-rebuilding",
)

OPERATION_COMPONENT = {
    "source-energy-evaluation": "energy_evaluations",
    "candidate-energy-evaluation": "energy_evaluations",
    "gradient-component-evaluation": "gradient_component_equivalents",
    "hessian-vector-product": "hvp_evaluations",
    "optimizer-start": "optimizer_starts",
    "optimizer-iteration": "optimizer_iterations",
    "full-physical-resource-recount": "resource_recounts",
    "candidate-generation": "candidate_generations",
    "unique-search-state-expansion": "search_states",
    "rewrite-verification": "rewrite_verifications",
    "statevector-recomputation": "statevector_recomputations",
}
ZERO_DELTA_OPERATION_OUTCOMES = {
    "candidate-physical-state-alias": "duplicate",
    "cap-rejection": "cap-rejected",
    "engineering-failure-evidence": "failed",
}
ZERO_DELTA_OPERATIONS = set(ZERO_DELTA_OPERATION_OUTCOMES)
OUTCOMES = {"completed", "failed", "duplicate", "cap-rejected"}


class ParentNativeWorkError(RuntimeError):
    pass


class ComponentwiseCapRejected(ParentNativeWorkError):
    pass


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _is_digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _add(left: WorkDelta, right: WorkDelta) -> WorkDelta:
    return WorkDelta(
        **{
            component: getattr(left, component) + getattr(right, component)
            for component in WORK_COMPONENTS
        }
    )


def _fits(value: WorkDelta, cap: WorkDelta) -> bool:
    return all(
        getattr(value, component) <= getattr(cap, component)
        for component in WORK_COMPONENTS
    )


def work_cap_digest(cap: WorkDelta) -> str:
    return _digest(asdict(cap))


def operation_delta(
    operation: str,
    *,
    units: int,
    dimension: int | None,
    outcome: str,
) -> WorkDelta:
    if outcome not in OUTCOMES:
        raise ParentNativeWorkError("unregistered operation outcome")
    if operation in ZERO_DELTA_OPERATIONS:
        expected_outcome = ZERO_DELTA_OPERATION_OUTCOMES[operation]
        if outcome != expected_outcome or units != 0 or dimension is not None:
            raise ParentNativeWorkError("evidence operation must have exact zero semantics")
        return WorkDelta()
    if outcome not in {"completed", "failed"}:
        raise ParentNativeWorkError("counted operation must be completed or failed")
    if isinstance(units, bool) or not isinstance(units, int) or units <= 0:
        raise ParentNativeWorkError("counted operation units must be positive integers")
    if operation == "full-gradient-evaluation":
        if isinstance(dimension, bool) or not isinstance(dimension, int) or dimension <= 0:
            raise ParentNativeWorkError("full gradient requires a positive dimension")
        return WorkDelta(
            gradient_vector_evaluations=units,
            gradient_component_equivalents=units * dimension,
        )
    if dimension is not None:
        raise ParentNativeWorkError("dimension is valid only for full gradients")
    try:
        component = OPERATION_COMPONENT[operation]
    except KeyError as error:
        raise ParentNativeWorkError(f"unregistered kernel operation: {operation}") from error
    return WorkDelta(**{component: units})


@dataclass(frozen=True)
class ParentNativeWorkRequest:
    queue_item_id: str
    method_id: str
    case_id: str
    state_preparation_id: str
    problem_id: str
    hamiltonian_digest: str
    source_checkpoint_digest: str
    frozen_queue_digest: str
    work_cap_digest: str

    def __post_init__(self) -> None:
        if not self.queue_item_id or self.method_id not in METHOD_IDS or not self.case_id:
            raise ParentNativeWorkError("work request identity is incomplete")
        if not self.state_preparation_id.startswith("state-v1:"):
            raise ParentNativeWorkError("work request StatePreparationID is invalid")
        if not self.problem_id.startswith("problem-v1:"):
            raise ParentNativeWorkError("work request ProblemID is invalid")
        for value in (
            self.hamiltonian_digest,
            self.source_checkpoint_digest,
            self.frozen_queue_digest,
            self.work_cap_digest,
        ):
            if not _is_digest(value):
                raise ParentNativeWorkError("work request digest is invalid")

    def payload(self) -> dict[str, Any]:
        return {
            "schema": "v5-final.parent-native-work-request.v1",
            "queue_item_id": self.queue_item_id,
            "method_id": self.method_id,
            "case_id": self.case_id,
            "StatePreparationID": self.state_preparation_id,
            "ProblemID": self.problem_id,
            "Hamiltonian_digest": self.hamiltonian_digest,
            "source_checkpoint_digest": self.source_checkpoint_digest,
            "frozen_queue_digest": self.frozen_queue_digest,
            "work_cap_digest": self.work_cap_digest,
        }

    @property
    def request_id(self) -> str:
        return "parent-native-work-request-v1:" + _digest(self.payload())


@dataclass(frozen=True)
class ParentNativeWorkEvent:
    sequence: int
    previous_event_digest: str
    request_id: str
    queue_item_id: str
    method_id: str
    case_id: str
    state_preparation_id: str
    problem_id: str
    hamiltonian_digest: str
    path_id: str
    operation: str
    outcome: str
    units: int
    dimension: int | None
    candidate_id: str | None
    proposed_physical_state_id: str | None
    delta: WorkDelta
    evidence: Mapping[str, Any]
    event_digest: str

    @classmethod
    def create(
        cls,
        *,
        sequence: int,
        previous_event_digest: str,
        request: ParentNativeWorkRequest,
        path_id: str,
        operation: str,
        outcome: str,
        units: int,
        dimension: int | None,
        candidate_id: str | None,
        proposed_physical_state_id: str | None,
        evidence: Mapping[str, Any],
    ) -> "ParentNativeWorkEvent":
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
            raise ParentNativeWorkError("event sequence is invalid")
        if not _is_digest(previous_event_digest):
            raise ParentNativeWorkError("previous event digest is invalid")
        if path_id != request.queue_item_id and not path_id.startswith(
            request.queue_item_id + "/"
        ):
            raise ParentNativeWorkError("event path is not queue-bound")
        if proposed_physical_state_id is not None and not proposed_physical_state_id.startswith(
            "physical-state-v3:"
        ):
            raise ParentNativeWorkError("event physical-state identity is not canonical v3")
        if operation in {
            "candidate-generation",
            "unique-search-state-expansion",
            "candidate-physical-state-alias",
        } and (not candidate_id or not proposed_physical_state_id):
            raise ParentNativeWorkError("candidate operation lacks both identities")
        delta = operation_delta(
            operation, units=units, dimension=dimension, outcome=outcome
        )
        payload = {
            "sequence": sequence,
            "previous_event_digest": previous_event_digest,
            "request_id": request.request_id,
            "queue_item_id": request.queue_item_id,
            "method_id": request.method_id,
            "case_id": request.case_id,
            "state_preparation_id": request.state_preparation_id,
            "problem_id": request.problem_id,
            "hamiltonian_digest": request.hamiltonian_digest,
            "path_id": path_id,
            "operation": operation,
            "outcome": outcome,
            "units": units,
            "dimension": dimension,
            "candidate_id": candidate_id,
            "proposed_physical_state_id": proposed_physical_state_id,
            "delta": asdict(delta),
            "evidence": dict(evidence),
        }
        return cls(
            delta=delta,
            evidence=dict(evidence),
            event_digest=_digest(payload),
            **{key: value for key, value in payload.items() if key not in {"delta", "evidence"}},
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def event_from_dict_strict(
    value: Mapping[str, Any], request: ParentNativeWorkRequest
) -> ParentNativeWorkEvent:
    rebuilt = ParentNativeWorkEvent.create(
        sequence=value["sequence"],
        previous_event_digest=value["previous_event_digest"],
        request=request,
        path_id=value["path_id"],
        operation=value["operation"],
        outcome=value["outcome"],
        units=value["units"],
        dimension=value.get("dimension"),
        candidate_id=value.get("candidate_id"),
        proposed_physical_state_id=value.get("proposed_physical_state_id"),
        evidence=dict(value["evidence"]),
    )
    if rebuilt.to_dict() != dict(value):
        raise ParentNativeWorkError("event digest, identity, operation, or delta mismatch")
    return rebuilt


class ParentNativeWorkRecorder:
    def __init__(
        self,
        *,
        request: ParentNativeWorkRequest,
        cap: WorkDelta,
        first_sequence: int = 0,
        previous_event_digest: str = "0" * 64,
    ) -> None:
        if work_cap_digest(cap) != request.work_cap_digest:
            raise ParentNativeWorkError("request and cap digest differ")
        self.request = request
        self.cap = cap
        self.first_sequence = first_sequence
        self._previous = previous_event_digest
        self._total = WorkDelta()
        self._events: list[ParentNativeWorkEvent] = []
        self._seen_physical_states: set[str] = set()
        self._closed = False

    @classmethod
    def resume(
        cls,
        *,
        request: ParentNativeWorkRequest,
        cap: WorkDelta,
        events: Sequence[ParentNativeWorkEvent],
    ) -> "ParentNativeWorkRecorder":
        """Resume without resetting work or semantic-state deduplication."""

        if not events:
            return cls(request=request, cap=cap)
        total = reconstruct(events, request)
        if not _fits(total, cap):
            raise ParentNativeWorkError("prior work already exceeds the bound cap")
        recorder = cls(
            request=request,
            cap=cap,
            first_sequence=events[0].sequence,
            previous_event_digest=events[0].previous_event_digest,
        )
        recorder._events = list(events)
        recorder._total = total
        recorder._previous = events[-1].event_digest
        recorder._seen_physical_states = {
            event.proposed_physical_state_id
            for event in events
            if event.operation == "unique-search-state-expansion"
            and event.proposed_physical_state_id is not None
        }
        return recorder

    @property
    def events(self) -> tuple[ParentNativeWorkEvent, ...]:
        return tuple(self._events)

    @property
    def total(self) -> WorkDelta:
        return self._total

    def _append(
        self,
        *,
        operation: str,
        outcome: str,
        units: int,
        dimension: int | None = None,
        candidate_id: str | None = None,
        proposed_physical_state_id: str | None = None,
        path_id: str | None = None,
        evidence: Mapping[str, Any] | None = None,
    ) -> ParentNativeWorkEvent:
        if self._closed:
            raise ParentNativeWorkError("closed recorder cannot append")
        event = ParentNativeWorkEvent.create(
            sequence=self.first_sequence + len(self._events),
            previous_event_digest=self._previous,
            request=self.request,
            path_id=path_id or self.request.queue_item_id,
            operation=operation,
            outcome=outcome,
            units=units,
            dimension=dimension,
            candidate_id=candidate_id,
            proposed_physical_state_id=proposed_physical_state_id,
            evidence=dict(evidence or {}),
        )
        if not _fits(_add(self._total, event.delta), self.cap):
            raise ParentNativeWorkError("internal append exceeded prechecked cap")
        self._events.append(event)
        self._total = _add(self._total, event.delta)
        self._previous = event.event_digest
        return event

    def _precheck(self, delta: WorkDelta, operation: str) -> None:
        if self._closed:
            raise ParentNativeWorkError("closed recorder cannot execute")
        projected = _add(self._total, delta)
        if _fits(projected, self.cap):
            return
        exceeded = [
            component
            for component in WORK_COMPONENTS
            if getattr(projected, component) > getattr(self.cap, component)
        ]
        self._append(
            operation="cap-rejection",
            outcome="cap-rejected",
            units=0,
            evidence={
                "rejected_operation": operation,
                "requested_delta": asdict(delta),
                "exceeded_components": exceeded,
                "kernel_executed": False,
            },
        )
        raise ComponentwiseCapRejected(
            "componentwise cap rejected before kernel: " + ", ".join(exceeded)
        )

    def invoke(
        self,
        operation: str,
        kernel: Callable[[], T],
        *,
        units: int = 1,
        dimension: int | None = None,
        candidate_id: str | None = None,
        proposed_physical_state_id: str | None = None,
        path_id: str | None = None,
        evidence: Mapping[str, Any] | None = None,
    ) -> T:
        delta = operation_delta(
            operation, units=units, dimension=dimension, outcome="completed"
        )
        self._precheck(delta, operation)
        try:
            result = kernel()
        except BaseException as error:
            self._append(
                operation=operation,
                outcome="failed",
                units=units,
                dimension=dimension,
                candidate_id=candidate_id,
                proposed_physical_state_id=proposed_physical_state_id,
                path_id=path_id,
                evidence={
                    **dict(evidence or {}),
                    "exception_type": type(error).__name__,
                },
            )
            raise
        self._append(
            operation=operation,
            outcome="completed",
            units=units,
            dimension=dimension,
            candidate_id=candidate_id,
            proposed_physical_state_id=proposed_physical_state_id,
            path_id=path_id,
            evidence=evidence,
        )
        return result

    def register_candidate_intent(
        self,
        *,
        candidate_id: str,
        proposed_physical_state_id: str,
        evidence: Mapping[str, Any] | None = None,
    ) -> bool:
        generation = operation_delta(
            "candidate-generation", units=1, dimension=None, outcome="completed"
        )
        unique = proposed_physical_state_id not in self._seen_physical_states
        search = (
            operation_delta(
                "unique-search-state-expansion",
                units=1,
                dimension=None,
                outcome="completed",
            )
            if unique
            else WorkDelta()
        )
        self._precheck(_add(generation, search), "candidate-generation")
        self._append(
            operation="candidate-generation",
            outcome="completed",
            units=1,
            candidate_id=candidate_id,
            proposed_physical_state_id=proposed_physical_state_id,
            evidence=evidence,
        )
        if not unique:
            self._append(
                operation="candidate-physical-state-alias",
                outcome="duplicate",
                units=0,
                candidate_id=candidate_id,
                proposed_physical_state_id=proposed_physical_state_id,
                evidence={
                    **dict(evidence or {}),
                    "deduplication_key": proposed_physical_state_id,
                },
            )
            return False
        self._seen_physical_states.add(proposed_physical_state_id)
        self._append(
            operation="unique-search-state-expansion",
            outcome="completed",
            units=1,
            candidate_id=candidate_id,
            proposed_physical_state_id=proposed_physical_state_id,
            evidence={
                **dict(evidence or {}),
                "deduplication_key": proposed_physical_state_id,
            },
        )
        return True

    def record_hvp(
        self,
        *,
        plus_gradient: Callable[[], T],
        minus_gradient: Callable[[], T],
        dimension: int,
        hvp_call_id: str,
    ) -> tuple[T, T]:
        gradient_delta = operation_delta(
            "full-gradient-evaluation",
            units=2,
            dimension=dimension,
            outcome="completed",
        )
        hvp_delta = operation_delta(
            "hessian-vector-product",
            units=1,
            dimension=None,
            outcome="completed",
        )
        self._precheck(_add(gradient_delta, hvp_delta), "hessian-vector-product")
        completed = 0
        try:
            plus = self.invoke(
                "full-gradient-evaluation",
                plus_gradient,
                dimension=dimension,
                evidence={"hvp_call_id": hvp_call_id, "side": "plus"},
            )
            completed += 1
            minus = self.invoke(
                "full-gradient-evaluation",
                minus_gradient,
                dimension=dimension,
                evidence={"hvp_call_id": hvp_call_id, "side": "minus"},
            )
            completed += 1
        except BaseException as error:
            self._append(
                operation="hessian-vector-product",
                outcome="failed",
                units=1,
                evidence={
                    "hvp_call_id": hvp_call_id,
                    "recorded_internal_gradient_events": completed + 1,
                    "exception_type": type(error).__name__,
                },
            )
            raise
        self._append(
            operation="hessian-vector-product",
            outcome="completed",
            units=1,
            evidence={
                "hvp_call_id": hvp_call_id,
                "recorded_internal_gradient_events": 2,
            },
        )
        return plus, minus

    def close(self) -> dict[str, Any]:
        if self._closed:
            raise ParentNativeWorkError("recorder already closed")
        self._closed = True
        reconstructed = reconstruct(self.events, self.request)
        result = {
            "schema": "v5-final.parent-native-work-ledger.v1",
            "request": self.request.payload() | {"request_id": self.request.request_id},
            "first_sequence": self.first_sequence,
            "event_count": len(self.events),
            "events": [event.to_dict() for event in self.events],
            "raw_total": asdict(self.total),
            "reconstructed_total": asdict(reconstructed),
            "cap": asdict(self.cap),
            "unique_physical_state_count": len(self._seen_physical_states),
            "paper_measurement_cost": None,
            "paper_measurement_cost_claimed_equivalent": False,
        }
        result["ledger_digest"] = _digest(result)
        return result


def reconstruct(
    events: Sequence[ParentNativeWorkEvent],
    request: ParentNativeWorkRequest,
) -> WorkDelta:
    if not events:
        return WorkDelta()
    expected_sequences = list(range(events[0].sequence, events[0].sequence + len(events)))
    if [event.sequence for event in events] != expected_sequences:
        raise ParentNativeWorkError("event sequence is missing or duplicated")
    previous = events[0].previous_event_digest
    hvp_gradients: dict[str, list[str]] = {}
    hvp_claims: dict[str, tuple[int, str]] = {}
    total = WorkDelta()
    for event in events:
        if event.previous_event_digest != previous:
            raise ParentNativeWorkError("event hash chain is broken")
        strict = event_from_dict_strict(event.to_dict(), request)
        previous = strict.event_digest
        if strict.operation == "full-gradient-evaluation" and "hvp_call_id" in strict.evidence:
            key = str(strict.evidence["hvp_call_id"])
            side = str(strict.evidence.get("side", ""))
            if not key or side not in {"plus", "minus"}:
                raise ParentNativeWorkError("HVP internal gradient identity is invalid")
            hvp_gradients.setdefault(key, []).append(side)
        if strict.operation == "hessian-vector-product":
            key = str(strict.evidence.get("hvp_call_id", ""))
            if not key or key in hvp_claims:
                raise ParentNativeWorkError("HVP call identity is empty or duplicated")
            claimed = strict.evidence.get("recorded_internal_gradient_events", -1)
            if isinstance(claimed, bool) or not isinstance(claimed, int):
                raise ParentNativeWorkError("HVP internal gradient claim is invalid")
            if strict.outcome == "completed" and claimed != 2:
                raise ParentNativeWorkError("completed HVP requires two internal gradients")
            if strict.outcome == "failed" and claimed not in {1, 2}:
                raise ParentNativeWorkError("failed HVP has an invalid partial gradient count")
            hvp_claims[key] = (claimed, strict.outcome)
        total = _add(total, strict.delta)
    if set(hvp_gradients) != set(hvp_claims) or any(
        len(hvp_gradients[key]) != claim[0]
        or len(set(hvp_gradients[key])) != len(hvp_gradients[key])
        for key, claim in hvp_claims.items()
    ):
        raise ParentNativeWorkError("HVP internal gradient accounting is incomplete")
    return total


def release_summary(
    ledger: Mapping[str, Any], request: ParentNativeWorkRequest
) -> dict[str, Any]:
    body = dict(ledger)
    observed = body.pop("ledger_digest", None)
    if observed != _digest(body):
        raise ParentNativeWorkError("work ledger digest mismatch")
    expected_request = request.payload() | {"request_id": request.request_id}
    if ledger.get("schema") != "v5-final.parent-native-work-ledger.v1":
        raise ParentNativeWorkError("work ledger schema mismatch")
    if ledger.get("request") != expected_request:
        raise ParentNativeWorkError("work ledger request binding mismatch")
    events = [event_from_dict_strict(value, request) for value in ledger["events"]]
    if ledger.get("event_count") != len(events):
        raise ParentNativeWorkError("work ledger event count mismatch")
    if events and ledger.get("first_sequence") != events[0].sequence:
        raise ParentNativeWorkError("work ledger first sequence mismatch")
    total = reconstruct(events, request)
    if ledger["raw_total"] != asdict(total) or ledger["reconstructed_total"] != asdict(total):
        raise ParentNativeWorkError("raw, reconstructed, and serialized totals differ")
    cap = WorkDelta(**dict(ledger["cap"]))
    if work_cap_digest(cap) != request.work_cap_digest or not _fits(total, cap):
        raise ParentNativeWorkError("work ledger cap binding mismatch")
    unique_states = {
        event.proposed_physical_state_id
        for event in events
        if event.operation == "unique-search-state-expansion"
    }
    if ledger.get("unique_physical_state_count") != len(unique_states):
        raise ParentNativeWorkError("work ledger physical-state count mismatch")
    if (
        ledger.get("paper_measurement_cost") is not None
        or ledger.get("paper_measurement_cost_claimed_equivalent") is not False
    ):
        raise ParentNativeWorkError("paper Measurement Cost non-equivalence was altered")
    result = {
        "schema": "v5-final.parent-native-work-release-summary.v1",
        "request_id": request.request_id,
        "ledger_digest": ledger["ledger_digest"],
        "event_count": len(events),
        "work_total": asdict(total),
        "paper_measurement_cost": None,
        "paper_measurement_cost_claimed_equivalent": False,
    }
    result["summary_digest"] = _digest(result)
    return result

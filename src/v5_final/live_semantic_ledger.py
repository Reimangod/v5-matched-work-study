"""Live semantic operation accounting for method-native executor kernels."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from typing import Any, Callable, Mapping, Sequence, TypeVar

from v5_matched_work.atomic_artifacts import canonical_json_bytes

from .method_native_interface import MethodNativeRequest
from .semantic_contract_v2 import WORK_COMPONENTS, WorkDelta


class LiveSemanticLedgerError(RuntimeError):
    pass


T = TypeVar("T")

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
EVIDENCE_OPERATIONS = {"canonical-state-duplicate"}
OUTCOMES = {"completed", "failed", "duplicate"}


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _digest_without(value: Mapping[str, Any], field: str) -> str:
    payload = dict(value)
    payload.pop(field, None)
    return _digest(payload)


def _add(left: WorkDelta, right: WorkDelta) -> WorkDelta:
    return WorkDelta(
        **{field: getattr(left, field) + getattr(right, field) for field in WORK_COMPONENTS}
    )


def _fits(value: WorkDelta, cap: WorkDelta) -> bool:
    return all(getattr(value, field) <= getattr(cap, field) for field in WORK_COMPONENTS)


def operation_delta(
    operation: str,
    *,
    units: int,
    dimension: int | None,
    outcome: str,
) -> WorkDelta:
    if outcome not in OUTCOMES:
        raise LiveSemanticLedgerError("unregistered operation outcome")
    if operation in EVIDENCE_OPERATIONS:
        if outcome != "duplicate" or units != 0 or dimension is not None:
            raise LiveSemanticLedgerError("duplicate evidence must be zero-unit and zero-delta")
        return WorkDelta()
    if isinstance(units, bool) or not isinstance(units, int) or units <= 0:
        raise LiveSemanticLedgerError("counted operations require positive integer units")
    if operation == "full-gradient-evaluation":
        if isinstance(dimension, bool) or not isinstance(dimension, int) or dimension <= 0:
            raise LiveSemanticLedgerError("full gradients require a positive dimension")
        return WorkDelta(
            gradient_vector_evaluations=units,
            gradient_component_equivalents=units * dimension,
        )
    if dimension is not None:
        raise LiveSemanticLedgerError("dimension is permitted only for full gradients")
    try:
        component = OPERATION_COMPONENT[operation]
    except KeyError as error:
        raise LiveSemanticLedgerError(f"unregistered live operation: {operation}") from error
    return WorkDelta(**{component: units})


@dataclass(frozen=True)
class LiveKernelEvent:
    event_id: str
    sequence: int
    request_id: str
    queue_item_id: str
    method_id: str
    case_id: str
    state_preparation_id: str
    problem_id: str
    hamiltonian_digest: str
    path_id: str
    producer: str
    operation: str
    outcome: str
    units: int
    dimension: int | None
    candidate_id: str | None
    proposed_physical_state_id: str | None
    delta: WorkDelta
    evidence: Mapping[str, Any]

    @classmethod
    def create(
        cls,
        *,
        sequence: int,
        request: MethodNativeRequest,
        path_id: str,
        producer: str,
        operation: str,
        outcome: str,
        units: int,
        dimension: int | None,
        candidate_id: str | None,
        proposed_physical_state_id: str | None,
        evidence: Mapping[str, Any],
    ) -> "LiveKernelEvent":
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
            raise LiveSemanticLedgerError("event sequence must be nonnegative")
        if path_id != request.queue_item_id and not path_id.startswith(request.queue_item_id + "/"):
            raise LiveSemanticLedgerError("event path is not bound to the queue item")
        if not producer.startswith("v5_final.method_native"):
            raise LiveSemanticLedgerError("event producer is not a method-native kernel site")
        if proposed_physical_state_id is not None and not proposed_physical_state_id.startswith(
            "physical-state-v1:"
        ):
            raise LiveSemanticLedgerError("proposed physical state identity is invalid")
        delta = operation_delta(
            operation, units=units, dimension=dimension, outcome=outcome
        )
        payload = {
            "sequence": sequence,
            "request_id": request.request_id,
            "queue_item_id": request.queue_item_id,
            "method_id": request.method_id,
            "case_id": request.case_id,
            "state_preparation_id": request.state_preparation_id,
            "problem_id": request.problem_id,
            "hamiltonian_digest": request.hamiltonian_digest,
            "path_id": path_id,
            "producer": producer,
            "operation": operation,
            "outcome": outcome,
            "units": units,
            "dimension": dimension,
            "candidate_id": candidate_id,
            "proposed_physical_state_id": proposed_physical_state_id,
            "delta": asdict(delta),
            "evidence": dict(evidence),
        }
        event_id = "live-kernel-event-v1:" + _digest(payload)
        return cls(
            event_id=event_id,
            delta=delta,
            evidence=dict(evidence),
            **{key: value for key, value in payload.items() if key not in {"delta", "evidence"}},
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def event_from_dict_strict(value: Mapping[str, Any]) -> LiveKernelEvent:
    request = MethodNativeRequest(
        queue_item_id=value["queue_item_id"],
        method_id=value["method_id"],
        case_id=value["case_id"],
        state_preparation_id=value["state_preparation_id"],
        problem_id=value["problem_id"],
        source_checkpoint_digest=value["evidence"]["source_checkpoint_digest"],
        hamiltonian_digest=value["hamiltonian_digest"],
        frozen_queue_digest=value["evidence"]["frozen_queue_digest"],
        work_envelope=value["evidence"]["work_envelope"],
        work_cap_digest=value["evidence"]["work_cap_digest"],
        optimizer_policy_digest=value["evidence"]["optimizer_policy_digest"],
        acceptance_policy_digest=value["evidence"]["acceptance_policy_digest"],
        protocol_digest=value["evidence"]["protocol_digest"],
        rng_identity=dict(value["evidence"]["rng_identity"]),
        environment_identity=dict(value["evidence"]["environment_identity"]),
        environment_digest=value["evidence"]["environment_digest"],
    )
    if request.request_id != value["request_id"]:
        raise LiveSemanticLedgerError("event request identity is inconsistent")
    rebuilt = LiveKernelEvent.create(
        sequence=value["sequence"],
        request=request,
        path_id=value["path_id"],
        producer=value["producer"],
        operation=value["operation"],
        outcome=value["outcome"],
        units=value["units"],
        dimension=value.get("dimension"),
        candidate_id=value.get("candidate_id"),
        proposed_physical_state_id=value.get("proposed_physical_state_id"),
        evidence=dict(value["evidence"]),
    )
    if rebuilt.to_dict() != dict(value):
        raise LiveSemanticLedgerError(
            "operation semantics, request binding, event digest, or delta is inconsistent"
        )
    return rebuilt


def _request_evidence(request: MethodNativeRequest, evidence: Mapping[str, Any]) -> dict[str, Any]:
    return {
        **dict(evidence),
        "source_checkpoint_digest": request.source_checkpoint_digest,
        "frozen_queue_digest": request.frozen_queue_digest,
        "work_envelope": request.work_envelope,
        "work_cap_digest": request.work_cap_digest,
        "optimizer_policy_digest": request.optimizer_policy_digest,
        "acceptance_policy_digest": request.acceptance_policy_digest,
        "protocol_digest": request.protocol_digest,
        "rng_identity": dict(request.rng_identity),
        "environment_identity": dict(request.environment_identity),
        "environment_digest": request.environment_digest,
    }


class LiveSemanticRecorder:
    """Cap-check an operation, run the kernel call, then emit its exact event."""

    def __init__(
        self,
        *,
        request: MethodNativeRequest,
        cap: WorkDelta,
        root_digest: str,
        producer: str,
        first_sequence: int = 0,
    ) -> None:
        if _digest(asdict(cap)) != request.work_cap_digest:
            raise LiveSemanticLedgerError("request work-cap digest differs from live cap")
        if len(root_digest) != 64:
            raise LiveSemanticLedgerError("ledger root digest must be SHA-256")
        if isinstance(first_sequence, bool) or not isinstance(first_sequence, int) or first_sequence < 0:
            raise LiveSemanticLedgerError("first sequence must be nonnegative")
        self.request = request
        self.cap = cap
        self.root_digest = root_digest
        self.producer = producer
        self.first_sequence = first_sequence
        self._total = WorkDelta()
        self._events: list[LiveKernelEvent] = []
        self._seen_states: set[str] = set()
        self._closed = False

    @property
    def events(self) -> tuple[LiveKernelEvent, ...]:
        return tuple(self._events)

    @property
    def raw_total(self) -> WorkDelta:
        return self._total

    def _precheck(self, delta: WorkDelta) -> None:
        if self._closed:
            raise LiveSemanticLedgerError("closed recorder cannot accept operations")
        if not _fits(_add(self._total, delta), self.cap):
            raise LiveSemanticLedgerError("operation would exceed the componentwise work cap")

    def _append(
        self,
        *,
        operation: str,
        outcome: str,
        units: int,
        dimension: int | None,
        candidate_id: str | None,
        proposed_physical_state_id: str | None,
        path_id: str,
        evidence: Mapping[str, Any],
    ) -> LiveKernelEvent:
        event = LiveKernelEvent.create(
            sequence=self.first_sequence + len(self._events),
            request=self.request,
            path_id=path_id,
            producer=self.producer,
            operation=operation,
            outcome=outcome,
            units=units,
            dimension=dimension,
            candidate_id=candidate_id,
            proposed_physical_state_id=proposed_physical_state_id,
            evidence=_request_evidence(self.request, evidence),
        )
        self._precheck(event.delta)
        self._events.append(event)
        self._total = _add(self._total, event.delta)
        return event

    def execute_kernel(
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
        delta = operation_delta(operation, units=units, dimension=dimension, outcome="completed")
        self._precheck(delta)
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
                path_id=path_id or self.request.queue_item_id,
                evidence={**dict(evidence or {}), "exception_type": type(error).__name__},
            )
            raise
        self._append(
            operation=operation,
            outcome="completed",
            units=units,
            dimension=dimension,
            candidate_id=candidate_id,
            proposed_physical_state_id=proposed_physical_state_id,
            path_id=path_id or self.request.queue_item_id,
            evidence=dict(evidence or {}),
        )
        return result

    def register_candidate_state(
        self,
        *,
        candidate_id: str,
        proposed_physical_state_id: str,
        path_id: str | None = None,
        evidence: Mapping[str, Any] | None = None,
    ) -> bool:
        base = path_id or self.request.queue_item_id
        self._append(
            operation="candidate-generation",
            outcome="completed",
            units=1,
            dimension=None,
            candidate_id=candidate_id,
            proposed_physical_state_id=proposed_physical_state_id,
            path_id=base,
            evidence=dict(evidence or {}),
        )
        if proposed_physical_state_id in self._seen_states:
            self._append(
                operation="canonical-state-duplicate",
                outcome="duplicate",
                units=0,
                dimension=None,
                candidate_id=candidate_id,
                proposed_physical_state_id=proposed_physical_state_id,
                path_id=base,
                evidence={**dict(evidence or {}), "deduplication_key": proposed_physical_state_id},
            )
            return False
        self._precheck(
            operation_delta(
                "unique-search-state-expansion",
                units=1,
                dimension=None,
                outcome="completed",
            )
        )
        self._seen_states.add(proposed_physical_state_id)
        self._append(
            operation="unique-search-state-expansion",
            outcome="completed",
            units=1,
            dimension=None,
            candidate_id=candidate_id,
            proposed_physical_state_id=proposed_physical_state_id,
            path_id=base,
            evidence={**dict(evidence or {}), "deduplication_key": proposed_physical_state_id},
        )
        return True

    def close(self) -> dict[str, Any]:
        if self._closed:
            raise LiveSemanticLedgerError("live recorder is already closed")
        self._closed = True
        total = reconstruct(self.events)
        result = {
            "schema": "v5-final.live-semantic-ledger.v1",
            "request_id": self.request.request_id,
            "root_digest": self.root_digest,
            "producer": self.producer,
            "first_sequence": self.first_sequence,
            "event_count": len(self._events),
            "events": [event.to_dict() for event in self._events],
            "raw_counter_total": asdict(self._total),
            "semantic_ledger_total": asdict(total),
            "cap": asdict(self.cap),
            "canonical_state_count": len(self._seen_states),
        }
        result["ledger_digest"] = _digest(result)
        return result


def reconstruct(events: Sequence[LiveKernelEvent]) -> WorkDelta:
    first = events[0].sequence if events else 0
    if [event.sequence for event in events] != list(range(first, first + len(events))):
        raise LiveSemanticLedgerError("global event sequence is missing or duplicated")
    total = WorkDelta()
    for event in events:
        total = _add(total, event.delta)
    return total


def release_summary(ledger: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(ledger)
    observed = payload.pop("ledger_digest", None)
    if observed != _digest(payload):
        raise LiveSemanticLedgerError("live ledger digest mismatch")
    events = [event_from_dict_strict(value) for value in ledger["events"]]
    if events and events[0].sequence != ledger["first_sequence"]:
        raise LiveSemanticLedgerError("ledger first sequence differs from its events")
    total = reconstruct(events)
    if ledger["raw_counter_total"] != asdict(total) or ledger["semantic_ledger_total"] != asdict(total):
        raise LiveSemanticLedgerError("raw and semantic ledger totals differ")
    result = {
        "schema": "v5-final.live-semantic-release-summary.v1",
        "request_id": ledger["request_id"],
        "ledger_digest": ledger["ledger_digest"],
        "event_count": len(events),
        "work_total": asdict(total),
    }
    result["summary_digest"] = _digest(result)
    return result


def build_queue_binding(queue_artifact: Mapping[str, Any], artifact_sha256: str) -> dict[str, Any]:
    status = str(queue_artifact.get("status", ""))
    queue = list(queue_artifact.get("queue", queue_artifact.get("items", [])))
    if "FROZEN" not in status or not queue:
        raise LiveSemanticLedgerError("expected queue must be a nonempty pre-outcome freeze")
    if artifact_sha256 != _digest(dict(queue_artifact)):
        raise LiveSemanticLedgerError("frozen queue artifact digest mismatch")
    ids = [item["queue_item_id"] for item in queue]
    if len(ids) != len(set(ids)):
        raise LiveSemanticLedgerError("frozen queue item IDs are duplicated")
    result = {
        "schema": "v5-final.live-semantic-queue-binding.v1",
        "frozen_queue_artifact_sha256": artifact_sha256,
        "expected_queue_count": len(queue),
        "expected_queue_item_ids": ids,
        "expected_queue_digest": _digest(queue),
        "queue_snapshot": queue,
    }
    result["binding_digest"] = _digest(result)
    return result


def build_chain_root(binding: Mapping[str, Any]) -> dict[str, Any]:
    if not binding.get("expected_queue_count"):
        raise LiveSemanticLedgerError("chain root requires a nonempty queue")
    result = {
        "schema": "v5-final.live-semantic-chain-root.v1",
        "binding_digest": binding["binding_digest"],
        "expected_queue_count": binding["expected_queue_count"],
        "expected_queue_digest": binding["expected_queue_digest"],
        "first_sequence": 0,
    }
    result["root_digest"] = _digest(result)
    return result


def build_segment(
    *,
    previous_digest: str,
    segment_index: int,
    request: MethodNativeRequest,
    events: Sequence[LiveKernelEvent],
) -> dict[str, Any]:
    if not events:
        raise LiveSemanticLedgerError("live event segment cannot be empty")
    if any(event.request_id != request.request_id for event in events):
        raise LiveSemanticLedgerError("segment contains an event for another request")
    sequences = [event.sequence for event in events]
    if sequences != list(range(sequences[0], sequences[0] + len(sequences))):
        raise LiveSemanticLedgerError("segment sequence is not contiguous")
    result = {
        "schema": "v5-final.live-semantic-segment.v1",
        "segment_index": segment_index,
        "previous_digest": previous_digest,
        "queue_item_id": request.queue_item_id,
        "request_id": request.request_id,
        "method_id": request.method_id,
        "case_id": request.case_id,
        "StatePreparationID": request.state_preparation_id,
        "ProblemID": request.problem_id,
        "Hamiltonian_digest": request.hamiltonian_digest,
        "first_sequence": sequences[0],
        "last_sequence": sequences[-1],
        "event_count": len(events),
        "events": [event.to_dict() for event in events],
    }
    result["segment_digest"] = _digest(result)
    return result


def verify_chain(
    root: Mapping[str, Any],
    binding: Mapping[str, Any],
    segments: Sequence[Mapping[str, Any]],
) -> list[LiveKernelEvent]:
    if root["binding_digest"] != binding["binding_digest"]:
        raise LiveSemanticLedgerError("chain root differs from frozen queue binding")
    previous = root["root_digest"]
    sequence = root["first_sequence"]
    expected_ids = set(binding["expected_queue_item_ids"])
    result: list[LiveKernelEvent] = []
    for index, segment in enumerate(segments):
        if segment["segment_index"] != index or segment["previous_digest"] != previous:
            raise LiveSemanticLedgerError("segment chain order or digest is broken")
        if segment["queue_item_id"] not in expected_ids:
            raise LiveSemanticLedgerError("segment queue item is absent from frozen queue")
        if segment["segment_digest"] != _digest_without(segment, "segment_digest"):
            raise LiveSemanticLedgerError("segment content digest mismatch")
        events = [event_from_dict_strict(value) for value in segment["events"]]
        if not events or events[0].sequence != sequence:
            raise LiveSemanticLedgerError("global sequence is missing or duplicated")
        if any(
            event.request_id != segment["request_id"]
            or event.queue_item_id != segment["queue_item_id"]
            or event.method_id != segment["method_id"]
            or event.case_id != segment["case_id"]
            or event.state_preparation_id != segment["StatePreparationID"]
            or event.problem_id != segment["ProblemID"]
            or event.hamiltonian_digest != segment["Hamiltonian_digest"]
            for event in events
        ):
            raise LiveSemanticLedgerError("event identity differs from segment identity")
        result.extend(events)
        sequence += len(events)
        previous = segment["segment_digest"]
    return result


def build_completeness_manifest(
    *,
    root: Mapping[str, Any],
    binding: Mapping[str, Any],
    completed_queue_item_ids: Sequence[str],
    segments: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    events = verify_chain(root, binding, segments)
    expected = list(binding["expected_queue_item_ids"])
    completed = list(completed_queue_item_ids)
    segment_ids = [segment["queue_item_id"] for segment in segments]
    checks = {
        "expected_queue_nonempty": bool(expected),
        "frozen_queue_count_matches": len(expected) == binding["expected_queue_count"],
        "frozen_queue_digest_matches": _digest(binding["queue_snapshot"])
        == binding["expected_queue_digest"],
        "root_bound_to_queue": root["binding_digest"] == binding["binding_digest"],
        "completed_unique": len(completed) == len(set(completed)),
        "completed_expected": set(completed).issubset(expected),
        "segments_expected": set(segment_ids).issubset(expected),
        "completed_have_segments": set(completed).issubset(segment_ids),
        "all_expected_completed": set(completed) == set(expected),
        "global_sequence_monotonic": [event.sequence for event in events]
        == list(range(len(events))),
    }
    result = {
        "schema": "v5-final.live-semantic-completeness.v1",
        "frozen_queue_artifact_sha256": binding["frozen_queue_artifact_sha256"],
        "expected_queue_count": binding["expected_queue_count"],
        "expected_queue_digest": binding["expected_queue_digest"],
        "completed_queue_item_ids": completed,
        "segment_digests": [segment["segment_digest"] for segment in segments],
        "event_count": len(events),
        "candidate_energy_evaluations": sum(
            event.delta.energy_evaluations
            for event in events
            if event.operation == "candidate-energy-evaluation"
        ),
        "work_total": asdict(reconstruct(events)),
        "checks": checks,
        "complete": all(checks.values()),
    }
    result["manifest_digest"] = _digest(result)
    return result


def protocol() -> dict[str, Any]:
    result = {
        "schema": "v5-final.live-semantic-ledger-protocol.v1",
        "operation_component": dict(sorted(OPERATION_COMPONENT.items())),
        "full_gradient_rule": "one vector plus units times dimension component equivalents",
        "semantic_dedup_key": "ProposedPhysicalStateID, never candidate ID",
        "cap_policy": "pre-operation componentwise rejection with no kernel call and no mutation",
        "event_binding": [
            "request", "queue item", "method", "case", "StatePreparationID",
            "ProblemID", "Hamiltonian", "path", "producer",
        ],
        "chain": "content-addressed segments with one global sequence and frozen nonempty queue binding",
        "reconciliation": "independent raw total = strict event reconstruction = release summary",
        "candidate_execution": "NOT_AUTHORIZED_BY_THIS_PROTOCOL",
        "claim_boundary": "live accounting infrastructure with synthetic probes only until MB4 native executor binding",
    }
    result["protocol_digest"] = _digest(result)
    return result

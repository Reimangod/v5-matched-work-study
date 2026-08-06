"""Semantically validated kernel events bound to a frozen nonempty queue."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from typing import Any, Iterable, Mapping, Sequence

from .atomic_artifacts import canonical_json_bytes
from .work_ledger import WorkLedgerError, WorkVector, operation_delta


class KernelLedgerV4Error(RuntimeError):
    pass


OUTCOMES = {"accepted", "rejected", "failed", "duplicate", "rollback", "completed"}
CACHES = {"not-applicable", "hit", "miss"}
EVIDENCE_ONLY_OPERATIONS = {"duplicate-detection"}


def _digest_without(value: dict[str, Any], field: str) -> str:
    payload = dict(value); payload.pop(field, None)
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _path_is_bound(path_id: str, queue_item_id: str) -> bool:
    return path_id == queue_item_id or path_id.startswith(queue_item_id + "/")


def semantic_delta(operation: str, *, units: int, dimension: int | None, outcome: str) -> WorkVector:
    if operation in EVIDENCE_ONLY_OPERATIONS:
        if units != 0 or dimension is not None or outcome != "duplicate":
            raise KernelLedgerV4Error("duplicate evidence must be zero-unit, zero-delta, and duplicate")
        return WorkVector()
    if isinstance(units, bool) or not isinstance(units, int) or units <= 0:
        raise KernelLedgerV4Error("charged kernel events require positive integer units")
    if operation == "full-gradient-evaluation":
        if isinstance(dimension, bool) or not isinstance(dimension, int) or dimension <= 0:
            raise KernelLedgerV4Error("full-gradient events require positive dimension")
    elif dimension is not None:
        raise KernelLedgerV4Error("dimension is allowed only for full-gradient events")
    try:
        return operation_delta(operation, units=units, dimension=dimension)
    except WorkLedgerError as error:
        raise KernelLedgerV4Error(str(error)) from error


@dataclass(frozen=True)
class KernelEventV4:
    event_id: str
    sequence: int
    queue_item_id: str
    state_preparation_id: str
    problem_id: str
    method_id: str
    case_id: str
    candidate_id: str | None
    path_id: str
    operation: str
    outcome: str
    cache: str
    units: int
    dimension: int | None
    delta: WorkVector

    @classmethod
    def create(
        cls,
        *,
        sequence: int,
        queue_item_id: str,
        state_preparation_id: str,
        problem_id: str,
        method_id: str,
        case_id: str,
        candidate_id: str | None,
        path_id: str,
        operation: str,
        outcome: str,
        cache: str = "not-applicable",
        units: int = 1,
        dimension: int | None = None,
    ) -> "KernelEventV4":
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
            raise KernelLedgerV4Error("event sequence must be a nonnegative integer")
        if not queue_item_id or not state_preparation_id.startswith("state-v1:") or not problem_id.startswith("problem-v1:"):
            raise KernelLedgerV4Error("queue and source identities are required")
        if not _path_is_bound(path_id, queue_item_id):
            raise KernelLedgerV4Error("event path is not bound to its queue item")
        if outcome not in OUTCOMES or cache not in CACHES:
            raise KernelLedgerV4Error("event outcome or cache disposition is invalid")
        delta = semantic_delta(operation, units=units, dimension=dimension, outcome=outcome)
        payload = {
            "sequence": sequence, "queue_item_id": queue_item_id,
            "state_preparation_id": state_preparation_id, "problem_id": problem_id,
            "method_id": method_id, "case_id": case_id, "candidate_id": candidate_id,
            "path_id": path_id, "operation": operation, "outcome": outcome, "cache": cache,
            "units": units, "dimension": dimension, "delta": asdict(delta),
        }
        event_id = "work-event-v4:" + hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
        return cls(event_id=event_id, delta=delta, **{key: payload[key] for key in payload if key != "delta"})


def event_to_dict(event: KernelEventV4) -> dict[str, Any]:
    return asdict(event)


def event_from_dict_strict(value: Mapping[str, Any]) -> KernelEventV4:
    rebuilt = KernelEventV4.create(
        sequence=value["sequence"], queue_item_id=value["queue_item_id"],
        state_preparation_id=value["state_preparation_id"], problem_id=value["problem_id"],
        method_id=value["method_id"], case_id=value["case_id"], candidate_id=value.get("candidate_id"),
        path_id=value["path_id"], operation=value["operation"], outcome=value["outcome"],
        cache=value["cache"], units=value["units"], dimension=value.get("dimension"),
    )
    if dict(value["delta"]) != asdict(rebuilt.delta):
        raise KernelLedgerV4Error("operation, units, dimension, and delta are semantically inconsistent")
    if value["event_id"] != rebuilt.event_id:
        raise KernelLedgerV4Error("kernel event content digest mismatch")
    return rebuilt


def bind_frozen_queue(queue_artifact: Mapping[str, Any], artifact_sha256: str) -> dict[str, Any]:
    if queue_artifact.get("status") != "FROZEN_PRE_OUTCOME":
        raise KernelLedgerV4Error("queue artifact is not a pre-outcome freeze")
    queue = list(queue_artifact.get("queue", []))
    if not queue:
        raise KernelLedgerV4Error("frozen expected queue must be nonempty")
    queue_ids = [item["queue_item_id"] for item in queue]
    if len(queue_ids) != len(set(queue_ids)):
        raise KernelLedgerV4Error("frozen queue item IDs are duplicated")
    observed_artifact_sha = hashlib.sha256(canonical_json_bytes(dict(queue_artifact))).hexdigest()
    if artifact_sha256 != observed_artifact_sha:
        raise KernelLedgerV4Error("frozen queue artifact SHA-256 mismatch")
    queue_digest = hashlib.sha256(canonical_json_bytes(queue)).hexdigest()
    result = {
        "schema": "v5-matched-work.frozen-queue-binding.v4",
        "frozen_queue_artifact_schema": queue_artifact.get("schema"),
        "frozen_queue_artifact_sha256": artifact_sha256,
        "expected_queue_count": len(queue),
        "expected_queue_item_ids": queue_ids,
        "expected_queue_digest": queue_digest,
        "queue_snapshot": queue,
    }
    result["binding_digest"] = _digest_without(result, "binding_digest")
    return result


def build_chain_root(binding: Mapping[str, Any]) -> dict[str, Any]:
    if not binding.get("expected_queue_count"):
        raise KernelLedgerV4Error("chain root requires a nonempty frozen queue")
    result = {
        "schema": "v5-matched-work.kernel-event-chain-root.v4",
        "frozen_queue_binding_digest": binding["binding_digest"],
        "frozen_queue_artifact_sha256": binding["frozen_queue_artifact_sha256"],
        "expected_queue_count": binding["expected_queue_count"],
        "expected_queue_digest": binding["expected_queue_digest"],
        "first_sequence": 0,
    }
    result["root_digest"] = _digest_without(result, "root_digest")
    return result


def build_segment(
    *, previous_digest: str, segment_index: int, queue_item_id: str,
    state_preparation_id: str, problem_id: str, events: Iterable[KernelEventV4],
) -> dict[str, Any]:
    materialized = list(events)
    if not materialized:
        raise KernelLedgerV4Error("kernel event segments cannot be empty")
    if any(event.queue_item_id != queue_item_id for event in materialized):
        raise KernelLedgerV4Error("event queue item differs from segment")
    if any(event.state_preparation_id != state_preparation_id or event.problem_id != problem_id for event in materialized):
        raise KernelLedgerV4Error("event source identity differs from segment")
    sequences = [event.sequence for event in materialized]
    if sequences != list(range(sequences[0], sequences[0] + len(sequences))):
        raise KernelLedgerV4Error("segment sequence is not contiguous")
    result = {
        "schema": "v5-matched-work.kernel-event-segment.v4",
        "segment_index": segment_index, "previous_digest": previous_digest,
        "queue_item_id": queue_item_id,
        "source_identity": {"StatePreparationID": state_preparation_id, "ProblemID": problem_id},
        "first_sequence": sequences[0], "last_sequence": sequences[-1],
        "event_count": len(materialized), "events": [event_to_dict(event) for event in materialized],
    }
    result["segment_digest"] = _digest_without(result, "segment_digest")
    return result


def verify_chain(root: Mapping[str, Any], binding: Mapping[str, Any], segments: Sequence[Mapping[str, Any]]) -> list[KernelEventV4]:
    if root["frozen_queue_binding_digest"] != binding["binding_digest"]:
        raise KernelLedgerV4Error("chain root is not bound to the frozen queue")
    previous = root["root_digest"]
    expected_sequence = root["first_sequence"]
    events: list[KernelEventV4] = []
    expected_queue_ids = set(binding["expected_queue_item_ids"])
    for index, segment in enumerate(segments):
        if segment["segment_index"] != index or segment["previous_digest"] != previous:
            raise KernelLedgerV4Error("segment order or digest chain is broken")
        if segment["queue_item_id"] not in expected_queue_ids:
            raise KernelLedgerV4Error("segment queue item is absent from frozen queue")
        if segment["segment_digest"] != _digest_without(dict(segment), "segment_digest"):
            raise KernelLedgerV4Error("segment content digest mismatch")
        materialized = [event_from_dict_strict(value) for value in segment["events"]]
        if not materialized or materialized[0].sequence != expected_sequence:
            raise KernelLedgerV4Error("global event sequence is missing or duplicated")
        if any(event.queue_item_id != segment["queue_item_id"] for event in materialized):
            raise KernelLedgerV4Error("event path/queue binding differs from segment")
        identity = segment["source_identity"]
        if any(event.state_preparation_id != identity["StatePreparationID"] or event.problem_id != identity["ProblemID"] for event in materialized):
            raise KernelLedgerV4Error("event source binding differs from segment")
        events.extend(materialized)
        expected_sequence += len(materialized)
        previous = segment["segment_digest"]
    return events


def build_completeness_manifest(
    *, root: Mapping[str, Any], binding: Mapping[str, Any],
    completed_queue_item_ids: Sequence[str], segments: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    events = verify_chain(root, binding, segments)
    expected = list(binding["expected_queue_item_ids"])
    completed = list(completed_queue_item_ids)
    segment_queue_ids = [segment["queue_item_id"] for segment in segments]
    queue_digest_rebuilt = hashlib.sha256(canonical_json_bytes(binding["queue_snapshot"])).hexdigest()
    checks = {
        "expected_queue_nonempty": bool(expected),
        "expected_queue_count_matches_frozen_binding": len(expected) == binding["expected_queue_count"],
        "frozen_queue_digest_matches": queue_digest_rebuilt == binding["expected_queue_digest"],
        "root_bound_to_frozen_queue": root["frozen_queue_binding_digest"] == binding["binding_digest"],
        "completed_queue_unique": len(completed) == len(set(completed)),
        "all_completed_queue_items_expected": set(completed).issubset(expected),
        "all_segment_queue_items_expected": set(segment_queue_ids).issubset(expected),
        "every_completed_queue_item_has_segment": set(completed).issubset(segment_queue_ids),
        "all_frozen_queue_items_completed": set(completed) == set(expected),
        "global_sequence_monotonic": [event.sequence for event in events] == list(range(len(events))),
    }
    result = {
        "schema": "v5-matched-work.kernel-ledger-completeness-manifest.v4",
        "frozen_queue_artifact_sha256": binding["frozen_queue_artifact_sha256"],
        "expected_queue_count": binding["expected_queue_count"],
        "expected_queue_digest": binding["expected_queue_digest"],
        "completed_queue_item_ids": completed,
        "segment_digests": [segment["segment_digest"] for segment in segments],
        "event_count": len(events),
        "candidate_energy_evaluations": sum(
            event.delta.N_E for event in events if event.operation == "candidate-energy-evaluation"
        ),
        "checks": checks, "complete": all(checks.values()),
    }
    result["manifest_digest"] = _digest_without(result, "manifest_digest")
    return result


def protocol() -> dict[str, Any]:
    result = {
        "schema": "v5-matched-work.semantic-kernel-ledger-protocol.v4",
        "status": "IMPLEMENTED_NOT_BOUND_TO_FROZEN_PRODUCTION_QUEUE_OR_KERNELS",
        "event_validation": [
            "operation-to-component", "units-and-dimension-to-delta", "evidence-event-zero-delta",
            "event-to-segment-queue", "event-to-segment-source", "content digest",
        ],
        "queue_binding": [
            "nonempty frozen queue", "frozen queue count", "canonical queue digest",
            "frozen artifact SHA-256", "complete expected/completed equality",
        ],
        "candidate_energy_reconstruction": "all semantically validated v4 segments bound to the frozen queue",
        "claim_boundary": "Production ledger contract only; no frozen S5-v4 queue and no kernel events exist.",
    }
    result["protocol_digest"] = _digest_without(result, "protocol_digest")
    return result

"""Fail-closed MB3.1 hardening for method-native result and ledger records.

This module is additive.  It does not alter the historical MB2/MB3 evidence
or authorize a molecular executor.  In particular, the helpers here only
bind identities and synthetic/infrastructure records.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from pathlib import Path
from typing import Any, Mapping, Sequence

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .live_semantic_ledger import (
    LiveKernelEvent,
    LiveSemanticLedgerError,
    LiveSemanticRecorder,
    event_from_dict_strict,
    reconstruct,
)
from .method_native_interface import (
    MethodNativeInterfaceError,
    MethodNativeRequest,
    MethodNativeResult,
    NativeExecutorIdentity,
    bind_result_to_request,
)
from .semantic_contract_v2 import WorkDelta


ATTEMPT_STATUSES = {
    "COMPLETED",
    "REJECTED",
    "CAP_EXHAUSTED",
    "FAILED_ROLLED_BACK",
}
ITEM_TERMINAL_STATUSES = {"COMPLETED", "REJECTED", "CAP_EXHAUSTED"}


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _digest_without(value: Mapping[str, Any], field: str) -> str:
    payload = dict(value)
    payload.pop(field, None)
    return _digest(payload)


def require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise MethodNativeInterfaceError(f"{label} must be a lowercase SHA-256 digest")


def require_content_id(value: str, prefix: str, label: str) -> None:
    namespace = prefix + ":"
    if not value.startswith(namespace):
        raise MethodNativeInterfaceError(f"{label} has the wrong identity namespace")
    require_sha256(value[len(namespace):], label)


def verify_executor_implementation(
    executor: NativeExecutorIdentity,
    implementation_path: Path,
    *,
    expected_method_id: str,
) -> None:
    """Bind a declared executor identity to the exact local implementation bytes."""

    if executor.method_id != expected_method_id:
        raise MethodNativeInterfaceError("executor method differs from request method")
    observed = hashlib.sha256(implementation_path.resolve().read_bytes()).hexdigest()
    if observed != executor.implementation_sha256:
        raise MethodNativeInterfaceError("executor implementation digest mismatch")


def validate_executor_bound_event(
    value: Mapping[str, Any],
    *,
    request: MethodNativeRequest,
    executor: NativeExecutorIdentity,
) -> LiveKernelEvent:
    """Strictly reconstruct an event and require its exact executor identity."""

    event = event_from_dict_strict(value)
    evidence = dict(event.evidence)
    if evidence.get("native_executor_id") != executor.executor_id:
        raise LiveSemanticLedgerError("event is not bound to the native executor ID")
    if evidence.get("native_executor") != executor.to_dict():
        raise LiveSemanticLedgerError("event native executor identity is inconsistent")
    if event.producer != executor.entrypoint:
        raise LiveSemanticLedgerError("event producer differs from executor entrypoint")
    if event.request_id != request.request_id or event.method_id != request.method_id:
        raise LiveSemanticLedgerError("event differs from the bound request")
    return event


class ExecutorBoundRecorder(LiveSemanticRecorder):
    """A v1 recorder whose every event is bound to one exact executor identity."""

    def __init__(
        self,
        *,
        request: MethodNativeRequest,
        executor: NativeExecutorIdentity,
        implementation_path: Path,
        cap: WorkDelta,
        root_digest: str,
        first_sequence: int = 0,
    ) -> None:
        require_sha256(root_digest, "ledger root")
        verify_executor_implementation(
            executor, implementation_path, expected_method_id=request.method_id
        )
        self.executor = executor
        self.implementation_path = implementation_path.resolve()
        super().__init__(
            request=request,
            cap=cap,
            root_digest=root_digest,
            producer=executor.entrypoint,
            first_sequence=first_sequence,
        )

    def _append(self, **values: Any) -> LiveKernelEvent:
        evidence = {
            **dict(values.pop("evidence")),
            "native_executor_id": self.executor.executor_id,
            "native_executor": self.executor.to_dict(),
        }
        event = super()._append(evidence=evidence, **values)
        validate_executor_bound_event(
            event.to_dict(), request=self.request, executor=self.executor
        )
        return event

    def register_candidate_state(
        self,
        *,
        candidate_id: str,
        proposed_physical_state_id: str,
        path_id: str | None = None,
        evidence: Mapping[str, Any] | None = None,
    ) -> str:
        """Charge generation, then return the expansion disposition.

        A generation that actually occurred remains in the ledger when the
        subsequent unique-state expansion would exceed its cap.  The rejected
        expansion is represented by the return status and never mutates the
        event chain or canonical-state set.
        """

        require_content_id(
            proposed_physical_state_id, "physical-state-v1", "proposed physical state"
        )
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
                evidence={
                    **dict(evidence or {}),
                    "deduplication_key": proposed_physical_state_id,
                },
            )
            return "DUPLICATE"
        expansion = WorkDelta(search_states=1)
        try:
            self._precheck(expansion)
        except LiveSemanticLedgerError:
            return "CAP_REJECTED"
        self._seen_states.add(proposed_physical_state_id)
        self._append(
            operation="unique-search-state-expansion",
            outcome="completed",
            units=1,
            dimension=None,
            candidate_id=candidate_id,
            proposed_physical_state_id=proposed_physical_state_id,
            path_id=base,
            evidence={
                **dict(evidence or {}),
                "deduplication_key": proposed_physical_state_id,
            },
        )
        return "EXPANDED"


def build_queue_binding_v2(
    queue_artifact: Mapping[str, Any],
    *,
    artifact_sha256: str,
    schema_audit: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind a nonempty pre-outcome queue and its successful schema audit."""

    require_sha256(artifact_sha256, "frozen queue artifact")
    if artifact_sha256 != _digest(dict(queue_artifact)):
        raise LiveSemanticLedgerError("frozen queue artifact digest mismatch")
    status = str(queue_artifact.get("status", ""))
    queue = list(queue_artifact.get("queue", queue_artifact.get("items", [])))
    if "FROZEN" not in status or not queue:
        raise LiveSemanticLedgerError("queue must be a nonempty pre-outcome freeze")
    audit = dict(schema_audit)
    checks = audit.get("checks")
    if (
        audit.get("queue_artifact_sha256") != artifact_sha256
        or not isinstance(checks, Mapping)
        or not checks
        or not all(value is True for value in checks.values())
    ):
        raise LiveSemanticLedgerError("queue schema audit is absent, failed, or misbound")
    ids = [item["queue_item_id"] for item in queue]
    if len(ids) != len(set(ids)):
        raise LiveSemanticLedgerError("frozen queue item IDs are duplicated")
    result = {
        "schema": "v5-final.live-semantic-queue-binding.v2",
        "frozen_queue_artifact_sha256": artifact_sha256,
        "queue_schema_audit": audit,
        "queue_schema_audit_digest": _digest(audit),
        "expected_queue_count": len(queue),
        "expected_queue_item_ids": ids,
        "expected_queue_digest": _digest(queue),
        "queue_snapshot": queue,
    }
    result["binding_digest"] = _digest(result)
    return result


def build_chain_root_v2(binding: Mapping[str, Any]) -> dict[str, Any]:
    if not binding.get("expected_queue_count"):
        raise LiveSemanticLedgerError("chain root requires a nonempty queue")
    require_sha256(binding["queue_schema_audit_digest"], "queue schema audit")
    result = {
        "schema": "v5-final.live-semantic-chain-root.v2",
        "binding_digest": binding["binding_digest"],
        "queue_schema_audit_digest": binding["queue_schema_audit_digest"],
        "expected_queue_count": binding["expected_queue_count"],
        "expected_queue_digest": binding["expected_queue_digest"],
        "first_sequence": 0,
    }
    result["root_digest"] = _digest(result)
    return result


def build_attempt_segment_v2(
    *,
    previous_digest: str,
    segment_index: int,
    attempt_id: str,
    attempt_ordinal: int,
    attempt_status: str,
    item_terminal: bool,
    request: MethodNativeRequest,
    executor: NativeExecutorIdentity,
    events: Sequence[LiveKernelEvent],
) -> dict[str, Any]:
    require_content_id(attempt_id, "method-attempt-v1", "attempt")
    if attempt_status not in ATTEMPT_STATUSES:
        raise LiveSemanticLedgerError("unregistered attempt status")
    if item_terminal != (attempt_status in ITEM_TERMINAL_STATUSES):
        raise LiveSemanticLedgerError("item terminal flag differs from attempt status")
    if isinstance(attempt_ordinal, bool) or not isinstance(attempt_ordinal, int) or attempt_ordinal < 0:
        raise LiveSemanticLedgerError("attempt ordinal must be nonnegative")
    if not events:
        raise LiveSemanticLedgerError("attempt segment cannot be empty")
    strict_events = [
        validate_executor_bound_event(
            event.to_dict(), request=request, executor=executor
        )
        for event in events
    ]
    sequences = [event.sequence for event in strict_events]
    if sequences != list(range(sequences[0], sequences[0] + len(sequences))):
        raise LiveSemanticLedgerError("attempt segment sequence is not contiguous")
    result = {
        "schema": "v5-final.live-semantic-attempt-segment.v2",
        "segment_index": segment_index,
        "previous_digest": previous_digest,
        "queue_item_id": request.queue_item_id,
        "request_id": request.request_id,
        "method_id": request.method_id,
        "case_id": request.case_id,
        "attempt_id": attempt_id,
        "attempt_ordinal": attempt_ordinal,
        "attempt_status": attempt_status,
        "item_terminal": item_terminal,
        "executor_id": executor.executor_id,
        "first_sequence": sequences[0],
        "last_sequence": sequences[-1],
        "event_count": len(strict_events),
        "events": [event.to_dict() for event in strict_events],
    }
    result["segment_digest"] = _digest(result)
    return result


def verify_attempt_chain_v2(
    *,
    root: Mapping[str, Any],
    binding: Mapping[str, Any],
    requests: Mapping[str, MethodNativeRequest],
    executors: Mapping[str, NativeExecutorIdentity],
    segments: Sequence[Mapping[str, Any]],
) -> list[LiveKernelEvent]:
    if binding.get("binding_digest") != _digest_without(binding, "binding_digest"):
        raise LiveSemanticLedgerError("queue binding content digest mismatch")
    if root.get("root_digest") != _digest_without(root, "root_digest"):
        raise LiveSemanticLedgerError("chain root content digest mismatch")
    if root["binding_digest"] != binding["binding_digest"]:
        raise LiveSemanticLedgerError("chain root differs from queue binding")
    if root["queue_schema_audit_digest"] != binding["queue_schema_audit_digest"]:
        raise LiveSemanticLedgerError("chain root differs from queue schema audit")
    expected = set(binding["expected_queue_item_ids"])
    previous = root["root_digest"]
    sequence = root["first_sequence"]
    seen_attempts: set[str] = set()
    per_item_ordinals: dict[str, list[int]] = {}
    terminal_seen: set[str] = set()
    result: list[LiveKernelEvent] = []
    for index, segment in enumerate(segments):
        item = segment["queue_item_id"]
        if segment["segment_index"] != index or segment["previous_digest"] != previous:
            raise LiveSemanticLedgerError("segment chain order or digest is broken")
        if segment["segment_digest"] != _digest_without(segment, "segment_digest"):
            raise LiveSemanticLedgerError("segment content digest mismatch")
        if item not in expected or item not in requests:
            raise LiveSemanticLedgerError("segment queue item is not bound")
        if segment.get("attempt_status") not in ATTEMPT_STATUSES:
            raise LiveSemanticLedgerError("unregistered attempt status")
        if segment.get("item_terminal") != (
            segment["attempt_status"] in ITEM_TERMINAL_STATUSES
        ):
            raise LiveSemanticLedgerError("item terminal flag differs from attempt status")
        if item in terminal_seen:
            raise LiveSemanticLedgerError("attempt exists after the item terminal segment")
        attempt_id = segment["attempt_id"]
        require_content_id(attempt_id, "method-attempt-v1", "attempt")
        if attempt_id in seen_attempts:
            raise LiveSemanticLedgerError("attempt ID is duplicated")
        seen_attempts.add(attempt_id)
        ordinals = per_item_ordinals.setdefault(item, [])
        ordinals.append(segment["attempt_ordinal"])
        if ordinals != list(range(len(ordinals))):
            raise LiveSemanticLedgerError("attempt ordinals are missing or duplicated")
        executor = executors.get(segment["executor_id"])
        if executor is None:
            raise LiveSemanticLedgerError("segment executor is not registered")
        request = requests[item]
        expected_segment_identity = {
            "request_id": request.request_id,
            "method_id": request.method_id,
            "case_id": request.case_id,
            "executor_id": executor.executor_id,
        }
        if any(
            segment.get(field) != value
            for field, value in expected_segment_identity.items()
        ):
            raise LiveSemanticLedgerError("attempt segment identity differs from its bindings")
        events = [
            validate_executor_bound_event(value, request=request, executor=executor)
            for value in segment["events"]
        ]
        if not events or events[0].sequence != sequence:
            raise LiveSemanticLedgerError("global sequence is missing or duplicated")
        if (
            segment.get("first_sequence") != events[0].sequence
            or segment.get("last_sequence") != events[-1].sequence
            or segment.get("event_count") != len(events)
        ):
            raise LiveSemanticLedgerError("attempt segment event bounds are inconsistent")
        if segment["item_terminal"]:
            terminal_seen.add(item)
        result.extend(events)
        sequence += len(events)
        previous = segment["segment_digest"]
    return result


def build_completeness_manifest_v2(
    *,
    root: Mapping[str, Any],
    binding: Mapping[str, Any],
    requests: Mapping[str, MethodNativeRequest],
    executors: Mapping[str, NativeExecutorIdentity],
    segments: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    events = verify_attempt_chain_v2(
        root=root,
        binding=binding,
        requests=requests,
        executors=executors,
        segments=segments,
    )
    expected = list(binding["expected_queue_item_ids"])
    terminal = [segment["queue_item_id"] for segment in segments if segment["item_terminal"]]
    checks = {
        "expected_queue_nonempty": bool(expected),
        "frozen_queue_count_matches": len(expected) == binding["expected_queue_count"],
        "frozen_queue_digest_matches": _digest(binding["queue_snapshot"])
        == binding["expected_queue_digest"],
        "schema_audit_digest_matches": _digest(binding["queue_schema_audit"])
        == binding["queue_schema_audit_digest"],
        "root_bound_to_queue_and_schema": root["binding_digest"] == binding["binding_digest"]
        and root["queue_schema_audit_digest"] == binding["queue_schema_audit_digest"],
        "one_terminal_segment_per_item": len(terminal) == len(set(terminal)),
        "all_expected_terminal": set(terminal) == set(expected),
        "global_sequence_monotonic": [event.sequence for event in events]
        == list(range(len(events))),
    }
    result = {
        "schema": "v5-final.live-semantic-completeness.v2",
        "frozen_queue_artifact_sha256": binding["frozen_queue_artifact_sha256"],
        "queue_schema_audit_digest": binding["queue_schema_audit_digest"],
        "expected_queue_count": binding["expected_queue_count"],
        "expected_queue_digest": binding["expected_queue_digest"],
        "terminal_queue_item_ids": terminal,
        "attempt_count": len(segments),
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


def publish_bound_result_exclusive(
    path: Path,
    *,
    request: MethodNativeRequest,
    result: MethodNativeResult,
) -> dict[str, Any]:
    """The sole supported publication path for a method-native result."""

    bind_result_to_request(result, request)
    for event in result.raw_semantic_events:
        validate_executor_bound_event(event, request=request, executor=result.executor)
    artifact = {
        "schema": "v5-final.bound-method-native-result.v2",
        "request": request.to_dict(),
        "result": result.to_dict(),
        "binding": {
            "request_id": request.request_id,
            "result_id": result.result_id,
            "executor_id": result.executor.executor_id,
        },
    }
    artifact["artifact_digest"] = _digest(artifact)
    write_json_exclusive(path, artifact)
    return artifact


def verify_published_bound_result(
    artifact: Mapping[str, Any],
) -> tuple[MethodNativeRequest, MethodNativeResult]:
    if artifact.get("schema") != "v5-final.bound-method-native-result.v2":
        raise MethodNativeInterfaceError("bound result artifact schema mismatch")
    if artifact.get("artifact_digest") != _digest_without(artifact, "artifact_digest"):
        raise MethodNativeInterfaceError("bound result artifact digest mismatch")
    request = MethodNativeRequest.from_dict(artifact["request"])
    result = MethodNativeResult.from_dict(artifact["result"])
    bind_result_to_request(result, request)
    expected = {
        "request_id": request.request_id,
        "result_id": result.result_id,
        "executor_id": result.executor.executor_id,
    }
    if artifact.get("binding") != expected:
        raise MethodNativeInterfaceError("bound result publication identity mismatch")
    for event in result.raw_semantic_events:
        validate_executor_bound_event(event, request=request, executor=result.executor)
    return request, result


def protocol() -> dict[str, Any]:
    result = {
        "schema": "v5-final.method-native-hardening-protocol.v1",
        "status": "INFRASTRUCTURE_ONLY_NOT_EXECUTION_AUTHORIZATION",
        "result_publication": "exclusive-create after mandatory request/result/executor binding",
        "executor_event_binding": [
            "method", "entrypoint", "implementation SHA-256", "parent commit", "CEO* commit"
        ],
        "sha256_validation": "lowercase 64-hex for IDs, roots, implementations, and artifacts",
        "candidate_cap_policy": (
            "record work already spent on generation; reject unique-state expansion without "
            "kernel call, state mutation, or expansion event"
        ),
        "segment_lifecycle": (
            "unique attempt IDs, contiguous per-item ordinals, rollback may retry, exactly one "
            "terminal segment per queue item, and no attempt after terminal"
        ),
        "queue_binding": "nonempty frozen queue plus successful schema-audit digest",
        "candidate_execution": "NOT_AUTHORIZED",
        "development_queue_execution": "NOT_AUTHORIZED",
    }
    result["protocol_digest"] = _digest(result)
    return result

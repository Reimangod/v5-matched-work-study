"""Additive residual hardening for future method-native execution records.

No function in this module authorizes or performs a molecular energy call.
"""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import importlib
import importlib.metadata
import inspect
import json
from pathlib import Path
import re
import subprocess
from typing import Any, Callable, Mapping, Sequence

from jsonschema import Draft202012Validator

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .live_semantic_ledger import LiveKernelEvent, LiveSemanticLedgerError
from .method_native_hardening import (
    ExecutorBoundRecorder,
    require_content_id,
    require_sha256,
    validate_executor_bound_event,
)
from .method_native_interface import (
    MethodNativeInterfaceError,
    MethodNativeRequest,
    MethodNativeResult,
    NativeExecutorIdentity,
    bind_result_to_request,
)
from .s0_successor import CEO_COMMIT, PARENT_COMMIT, ROOT
from .semantic_contract_v2 import WORK_COMPONENTS, WorkDelta


QUEUE_SCHEMA = ROOT / "schemas/v5-final-method-native-queue-v3.schema.json"
QUEUE_SCHEMA_ID = (
    "https://github.com/Reimangod/v5-matched-work-study/"
    "schemas/v5-final-method-native-queue-v3.schema.json"
)
ENTRYPOINT_RE = re.compile(
    r"^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*:[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*$"
)


class ResidualHardeningError(RuntimeError):
    pass


def synthetic_no_molecule() -> None:
    """Importable synthetic probe; never loads a molecule or Hamiltonian."""


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _digest_without(value: Mapping[str, Any], field: str) -> str:
    payload = dict(value)
    payload.pop(field, None)
    return _digest(payload)


def _git(*arguments: str, cwd: Path = ROOT) -> str:
    return subprocess.check_output(["git", "-C", str(cwd), *arguments], text=True).strip()


def resolve_executor_callable(
    executor: NativeExecutorIdentity,
    *,
    implementation_path: Path,
    expected_method_id: str,
) -> tuple[Callable[..., Any], Path]:
    """Resolve and bind module:qualname, exact file bytes, method, and gitlinks."""

    if not ENTRYPOINT_RE.fullmatch(executor.entrypoint):
        raise MethodNativeInterfaceError("executor entrypoint is not canonical module:qualname")
    module_name, qualname = executor.entrypoint.split(":", 1)
    module = importlib.import_module(module_name)
    target: Any = module
    for part in qualname.split("."):
        target = getattr(target, part, None)
        if target is None:
            raise MethodNativeInterfaceError("executor entrypoint does not resolve")
    if not callable(target):
        raise MethodNativeInterfaceError("executor entrypoint is not callable")
    source = inspect.getsourcefile(target)
    if source is None:
        raise MethodNativeInterfaceError("executor callable has no inspectable source file")
    resolved_source = Path(source).resolve()
    declared_path = implementation_path.resolve()
    if resolved_source != declared_path:
        raise MethodNativeInterfaceError("executor entrypoint source differs from implementation path")
    if executor.method_id != expected_method_id:
        raise MethodNativeInterfaceError("executor method differs from request method")
    if executor.parent_repository_commit != PARENT_COMMIT:
        raise MethodNativeInterfaceError("executor parent commit differs from pinned parent")
    if executor.ceo_adapt_vqe_commit != CEO_COMMIT:
        raise MethodNativeInterfaceError("executor CEO* commit differs from pinned provenance")
    if _git("rev-parse", "HEAD", cwd=ROOT / "provenance/dvg-obs-ceo") != PARENT_COMMIT:
        raise MethodNativeInterfaceError("checked-out parent submodule differs from pinned commit")
    if (
        _git("rev-parse", "HEAD", cwd=ROOT / "provenance/dvg-obs-ceo/vendor/ceo-adapt-vqe")
        != CEO_COMMIT
    ):
        raise MethodNativeInterfaceError("checked-out CEO* submodule differs from pinned commit")
    observed = hashlib.sha256(resolved_source.read_bytes()).hexdigest()
    if observed != executor.implementation_sha256:
        raise MethodNativeInterfaceError("executor implementation digest mismatch")
    return target, resolved_source


def build_validated_queue_binding_v3(
    queue_artifact: Mapping[str, Any],
    *,
    artifact_sha256: str,
    schema_path: Path = QUEUE_SCHEMA,
) -> dict[str, Any]:
    """Run the pinned validator; callers cannot supply a self-asserted audit."""

    require_sha256(artifact_sha256, "queue artifact")
    queue_payload = dict(queue_artifact)
    if artifact_sha256 != _digest(queue_payload):
        raise ResidualHardeningError("queue artifact digest mismatch")
    resolved_schema = schema_path.resolve()
    if resolved_schema != QUEUE_SCHEMA.resolve():
        raise ResidualHardeningError("queue schema path is not the pinned schema")
    schema = json.loads(resolved_schema.read_text())
    if schema.get("$id") != QUEUE_SCHEMA_ID:
        raise ResidualHardeningError("queue schema ID differs from the pinned ID")
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(queue_payload),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        raise ResidualHardeningError(
            "queue schema validation failed: " + "; ".join(error.message for error in errors)
        )
    ids = [item["queue_item_id"] for item in queue_payload["queue"]]
    if len(ids) != len(set(ids)):
        raise ResidualHardeningError("queue item IDs are duplicated")
    schema_audit = {
        "schema": "v5-final.method-native-queue-schema-audit.v3",
        "pinned_schema_path": str(resolved_schema.relative_to(ROOT)),
        "pinned_schema_id": QUEUE_SCHEMA_ID,
        "schema_sha256": hashlib.sha256(resolved_schema.read_bytes()).hexdigest(),
        "validator": "jsonschema.validators.Draft202012Validator",
        "validator_package": "jsonschema",
        "validator_version": importlib.metadata.version("jsonschema"),
        "queue_artifact_sha256": artifact_sha256,
        "schema_error_count": 0,
        "valid": True,
    }
    schema_audit["schema_audit_sha256"] = _digest(schema_audit)
    result = {
        "schema": "v5-final.live-semantic-queue-binding.v3",
        "frozen_queue_artifact_sha256": artifact_sha256,
        "frozen_queue_artifact": queue_payload,
        "queue_schema_audit": schema_audit,
        "queue_schema_audit_sha256": schema_audit["schema_audit_sha256"],
        "expected_queue_count": len(ids),
        "expected_queue_item_ids": ids,
        "expected_queue_digest": _digest(queue_payload["queue"]),
        "queue_snapshot": queue_payload["queue"],
    }
    result["binding_digest"] = _digest(result)
    return result


def verify_queue_binding_v3(binding: Mapping[str, Any]) -> None:
    if binding.get("schema") != "v5-final.live-semantic-queue-binding.v3":
        raise ResidualHardeningError("queue binding schema mismatch")
    if binding.get("binding_digest") != _digest_without(binding, "binding_digest"):
        raise ResidualHardeningError("queue binding digest mismatch")
    artifact = binding.get("frozen_queue_artifact", {})
    observed_artifact_sha = binding.get("frozen_queue_artifact_sha256")
    rebuilt = build_validated_queue_binding_v3(
        artifact,
        artifact_sha256=observed_artifact_sha,
        schema_path=QUEUE_SCHEMA,
    )
    if dict(binding) != rebuilt:
        raise ResidualHardeningError("queue binding does not reproduce from pinned schema and artifact")


def _zero_delta() -> dict[str, int]:
    return {field: 0 for field in WORK_COMPONENTS}


def _rejection_record(
    *,
    request: MethodNativeRequest,
    executor: NativeExecutorIdentity,
    attempt_id: str,
    candidate_id: str,
    proposed_physical_state_id: str,
    path_id: str,
    cap: WorkDelta,
    total_before: WorkDelta,
) -> dict[str, Any]:
    record = {
        "schema": "v5-final.persistent-cap-rejection.v2",
        "status": "CAP_REJECTED",
        "reason": "UNIQUE_STATE_EXPANSION_COMPONENTWISE_CAP_EXCEEDED",
        "request_id": request.request_id,
        "queue_item_id": request.queue_item_id,
        "method_id": request.method_id,
        "attempt_id": attempt_id,
        "executor_id": executor.executor_id,
        "path_id": path_id,
        "candidate_id": candidate_id,
        "proposed_physical_state_id": proposed_physical_state_id,
        "cap_snapshot": asdict(cap),
        "total_before": asdict(total_before),
        "rejected_delta": asdict(WorkDelta(search_states=1)),
        "recorded_delta": _zero_delta(),
    }
    record["rejection_id"] = "cap-rejection-v2:" + _digest(record)
    return record


def verify_rejection_record(
    record: Mapping[str, Any],
    *,
    request: MethodNativeRequest,
    executor: NativeExecutorIdentity,
    attempt_id: str,
) -> None:
    require_content_id(record["rejection_id"], "cap-rejection-v2", "cap rejection")
    require_content_id(attempt_id, "method-attempt-v1", "attempt")
    if record["rejection_id"] != "cap-rejection-v2:" + _digest_without(record, "rejection_id"):
        raise ResidualHardeningError("cap rejection digest mismatch")
    required = {
        "schema": "v5-final.persistent-cap-rejection.v2",
        "status": "CAP_REJECTED",
        "request_id": request.request_id,
        "queue_item_id": request.queue_item_id,
        "method_id": request.method_id,
        "attempt_id": attempt_id,
        "executor_id": executor.executor_id,
    }
    if any(record.get(key) != value for key, value in required.items()):
        raise ResidualHardeningError("cap rejection identity mismatch")
    if record.get("recorded_delta") != _zero_delta():
        raise ResidualHardeningError("cap rejection must have zero recorded work")
    if record.get("rejected_delta") != asdict(WorkDelta(search_states=1)):
        raise ResidualHardeningError("cap rejection proposed delta is invalid")
    if record.get("reason") != "UNIQUE_STATE_EXPANSION_COMPONENTWISE_CAP_EXCEEDED":
        raise ResidualHardeningError("cap rejection reason is invalid")
    if _digest(record.get("cap_snapshot")) != request.work_cap_digest:
        raise ResidualHardeningError("cap rejection snapshot differs from request cap")
    total = record.get("total_before", {})
    cap = record.get("cap_snapshot", {})
    rejected = record.get("rejected_delta", {})
    if set(total) != set(WORK_COMPONENTS) or set(cap) != set(WORK_COMPONENTS):
        raise ResidualHardeningError("cap rejection counter shape is invalid")
    if not any(total[field] + rejected[field] > cap[field] for field in WORK_COMPONENTS):
        raise ResidualHardeningError("cap rejection did not actually exceed the recorded cap")
    if record.get("path_id") != request.queue_item_id and not str(
        record.get("path_id", "")
    ).startswith(request.queue_item_id + "/"):
        raise ResidualHardeningError("cap rejection path differs from queue item")
    require_content_id(
        record["proposed_physical_state_id"],
        "physical-state-v1",
        "rejected physical state",
    )


class PersistentRecorderV2(ExecutorBoundRecorder):
    def __init__(
        self,
        *,
        request: MethodNativeRequest,
        executor: NativeExecutorIdentity,
        implementation_path: Path,
        attempt_id: str,
        cap: WorkDelta,
        root_digest: str,
        first_sequence: int = 0,
    ) -> None:
        require_content_id(attempt_id, "method-attempt-v1", "attempt")
        resolve_executor_callable(
            executor,
            implementation_path=implementation_path,
            expected_method_id=request.method_id,
        )
        self.attempt_id = attempt_id
        self._rejections: list[dict[str, Any]] = []
        self._journal: list[dict[str, str]] = []
        super().__init__(
            request=request,
            executor=executor,
            implementation_path=implementation_path,
            cap=cap,
            root_digest=root_digest,
            first_sequence=first_sequence,
        )

    def _append(self, **values: Any) -> LiveKernelEvent:
        event = super()._append(**values)
        self._journal.append({"kind": "event", "record_id": event.event_id})
        return event

    @property
    def rejections(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(dict(value) for value in self._rejections)

    def register_candidate_state(
        self,
        *,
        candidate_id: str,
        proposed_physical_state_id: str,
        path_id: str | None = None,
        evidence: Mapping[str, Any] | None = None,
    ) -> str:
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
                evidence={"deduplication_key": proposed_physical_state_id},
            )
            return "DUPLICATE"
        expansion = WorkDelta(search_states=1)
        try:
            self._precheck(expansion)
        except LiveSemanticLedgerError:
            rejection = _rejection_record(
                request=self.request,
                executor=self.executor,
                attempt_id=self.attempt_id,
                candidate_id=candidate_id,
                proposed_physical_state_id=proposed_physical_state_id,
                path_id=base,
                cap=self.cap,
                total_before=self.raw_total,
            )
            self._rejections.append(rejection)
            self._journal.append(
                {"kind": "cap_rejection", "record_id": rejection["rejection_id"]}
            )
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
            evidence={"deduplication_key": proposed_physical_state_id},
        )
        return "EXPANDED"

    def close(self) -> dict[str, Any]:
        ledger = super().close()
        ledger.pop("ledger_digest")
        ledger["schema"] = "v5-final.persistent-live-semantic-ledger.v2"
        ledger["attempt_id"] = self.attempt_id
        ledger["rejection_count"] = len(self._rejections)
        ledger["rejections"] = [dict(value) for value in self._rejections]
        ledger["journal"] = list(self._journal)
        ledger["journal_count"] = len(self._journal)
        ledger["ledger_digest"] = _digest(ledger)
        return ledger


def replay_persistent_ledger(
    ledger: Mapping[str, Any],
    *,
    request: MethodNativeRequest,
    executor: NativeExecutorIdentity,
) -> dict[str, Any]:
    if ledger.get("schema") != "v5-final.persistent-live-semantic-ledger.v2":
        raise ResidualHardeningError("persistent ledger schema mismatch")
    if ledger.get("ledger_digest") != _digest_without(ledger, "ledger_digest"):
        raise ResidualHardeningError("persistent ledger digest mismatch")
    if ledger.get("request_id") != request.request_id:
        raise ResidualHardeningError("persistent ledger request mismatch")
    attempt_id = ledger["attempt_id"]
    events = [
        validate_executor_bound_event(value, request=request, executor=executor)
        for value in ledger["events"]
    ]
    rejections = [dict(value) for value in ledger["rejections"]]
    for record in rejections:
        verify_rejection_record(
            record, request=request, executor=executor, attempt_id=attempt_id
        )
    event_ids = [event.event_id for event in events]
    rejection_ids = [record["rejection_id"] for record in rejections]
    journal = list(ledger["journal"])
    observed_event_ids = [item["record_id"] for item in journal if item["kind"] == "event"]
    observed_rejection_ids = [
        item["record_id"] for item in journal if item["kind"] == "cap_rejection"
    ]
    if (
        observed_event_ids != event_ids
        or observed_rejection_ids != rejection_ids
        or len(journal) != ledger["journal_count"]
        or len(events) != ledger["event_count"]
        or len(rejections) != ledger["rejection_count"]
    ):
        raise ResidualHardeningError("persistent ledger journal is incomplete or reordered")
    return {
        "event_count": len(events),
        "rejection_count": len(rejections),
        "cap_rejected_attempt_ids": sorted({record["attempt_id"] for record in rejections}),
        "candidate_energy_evaluations": sum(
            event.delta.energy_evaluations
            for event in events
            if event.operation == "candidate-energy-evaluation"
        ),
        "raw_counter_total": ledger["raw_counter_total"],
    }


def build_transaction_record_v2(
    *,
    request: MethodNativeRequest,
    attempt_id: str,
    ledger: Mapping[str, Any],
    terminal_status: str,
) -> dict[str, Any]:
    if terminal_status not in {"COMPLETED", "REJECTED", "CAP_EXHAUSTED", "FAILED_ROLLED_BACK"}:
        raise ResidualHardeningError("unregistered transaction terminal status")
    rollback = terminal_status == "FAILED_ROLLED_BACK"
    result = {
        "schema": "v5-final.method-native-transaction.v2",
        "request_id": request.request_id,
        "queue_item_id": request.queue_item_id,
        "attempt_id": attempt_id,
        "ledger_digest": ledger["ledger_digest"],
        "terminal_status": terminal_status,
        "rollback_required": rollback,
        "rollback_complete": rollback,
    }
    result["transaction_digest"] = _digest(result)
    return result


def build_item_completeness_v3(
    *,
    request: MethodNativeRequest,
    attempt_id: str,
    ledger: Mapping[str, Any],
    queue_binding: Mapping[str, Any],
    transaction: Mapping[str, Any],
) -> dict[str, Any]:
    verify_queue_binding_v3(queue_binding)
    matching_items = [
        item
        for item in queue_binding["queue_snapshot"]
        if item["queue_item_id"] == request.queue_item_id
    ]
    checks = {
        "request_in_queue": len(matching_items) == 1,
        "queue_item_identity_matches": len(matching_items) == 1
        and matching_items[0]["method_id"] == request.method_id
        and matching_items[0]["case_id"] == request.case_id,
        "queue_binding_matches_request": request.frozen_queue_digest
        == queue_binding["binding_digest"],
        "transaction_bound": transaction["request_id"] == request.request_id
        and transaction["attempt_id"] == attempt_id
        and transaction["ledger_digest"] == ledger["ledger_digest"],
        "transaction_digest_valid": transaction["transaction_digest"]
        == _digest_without(transaction, "transaction_digest"),
        "journal_nonempty": ledger["journal_count"] > 0,
    }
    result = {
        "schema": "v5-final.method-native-item-completeness.v3",
        "request_id": request.request_id,
        "queue_item_id": request.queue_item_id,
        "attempt_id": attempt_id,
        "queue_binding_digest": queue_binding["binding_digest"],
        "ledger_digest": ledger["ledger_digest"],
        "transaction_digest": transaction["transaction_digest"],
        "rejection_ids": [record["rejection_id"] for record in ledger["rejections"]],
        "checks": checks,
        "complete": all(checks.values()),
    }
    result["manifest_digest"] = _digest(result)
    return result


def build_bound_result_artifact_v3(
    *,
    request: MethodNativeRequest,
    result: MethodNativeResult,
    implementation_path: Path,
    queue_binding: Mapping[str, Any],
    ledger: Mapping[str, Any],
    completeness: Mapping[str, Any],
    transaction: Mapping[str, Any],
) -> dict[str, Any]:
    bind_result_to_request(result, request)
    resolve_executor_callable(
        result.executor,
        implementation_path=implementation_path,
        expected_method_id=request.method_id,
    )
    verify_queue_binding_v3(queue_binding)
    replay = replay_persistent_ledger(ledger, request=request, executor=result.executor)
    expected_transaction = build_transaction_record_v2(
        request=request,
        attempt_id=ledger["attempt_id"],
        ledger=ledger,
        terminal_status=result.terminal_status,
    )
    if dict(transaction) != expected_transaction:
        raise ResidualHardeningError("published transaction does not reproduce")
    if result.raw_semantic_events != tuple(ledger["events"]):
        raise ResidualHardeningError("published result events differ from persistent ledger")
    if dict(result.work_ledger) != dict(ledger):
        raise ResidualHardeningError("published result work ledger differs from persistent ledger")
    if dict(result.completeness_manifest) != dict(completeness):
        raise ResidualHardeningError("published result completeness differs from validated manifest")
    if dict(result.transaction_record) != dict(transaction):
        raise ResidualHardeningError("published result transaction differs from validated transaction")
    expected_completeness = build_item_completeness_v3(
        request=request,
        attempt_id=ledger["attempt_id"],
        ledger=ledger,
        queue_binding=queue_binding,
        transaction=transaction,
    )
    if dict(completeness) != expected_completeness or completeness["complete"] is not True:
        raise ResidualHardeningError("publication completeness is invalid")
    if transaction["terminal_status"] != result.terminal_status:
        raise ResidualHardeningError("result and transaction terminal statuses differ")
    if transaction["rollback_required"]:
        rollback = result.failure_rollback_record
        if (
            rollback is None
            or rollback.get("transaction_digest") != transaction["transaction_digest"]
            or rollback.get("rollback_complete") is not True
            or rollback.get("rollback_digest") != _digest_without(rollback, "rollback_digest")
        ):
            raise ResidualHardeningError("failed result rollback record is not transaction-bound")
    elif result.failure_rollback_record is not None:
        raise ResidualHardeningError("non-rollback result contains a rollback record")
    if result.terminal_status == "CAP_EXHAUSTED" and replay["rejection_count"] == 0:
        raise ResidualHardeningError("cap-exhausted result has no persistent rejection")
    artifact = {
        "schema": "v5-final.bound-method-native-result.v3",
        "request": request.to_dict(),
        "result": result.to_dict(),
        "executor_source_path": str(implementation_path.resolve().relative_to(ROOT)),
        "queue_binding": dict(queue_binding),
        "persistent_ledger": dict(ledger),
        "completeness": dict(completeness),
        "transaction": dict(transaction),
        "binding": {
            "request_id": request.request_id,
            "result_id": result.result_id,
            "executor_id": result.executor.executor_id,
            "queue_binding_digest": queue_binding["binding_digest"],
            "ledger_digest": ledger["ledger_digest"],
            "manifest_digest": completeness["manifest_digest"],
            "transaction_digest": transaction["transaction_digest"],
        },
    }
    artifact["artifact_digest"] = _digest(artifact)
    return artifact


def publish_bound_result_exclusive_v3(
    path: Path,
    **values: Any,
) -> dict[str, Any]:
    artifact = build_bound_result_artifact_v3(**values)
    write_json_exclusive(path, artifact)
    return artifact


def protocol() -> dict[str, Any]:
    result = {
        "schema": "v5-final.method-native-residual-hardening.v2",
        "status": "INFRASTRUCTURE_ONLY_NOT_EXECUTION_AUTHORIZATION",
        "executor_binding": "imported callable + inspected exact file + SHA-256 + pinned gitlinks",
        "queue_binding": "pinned Draft 2020-12 schema is executed; no caller-supplied audit",
        "cap_rejection": "zero-work persistent rejection in an integrity-bound journal",
        "publication": "callable, request, executor, queue, ledger, completeness, and transaction revalidated",
        "molecular_candidate_energy": "NOT_AUTHORIZED",
        "development_queue_execution": "NOT_AUTHORIZED",
    }
    result["protocol_digest"] = _digest(result)
    return result

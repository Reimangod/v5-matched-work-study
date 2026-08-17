"""Exact frozen-queue S11-v2 production runner.

The public entrypoint remains fail-closed until execution-readiness v2/P7-v6
is frozen GO.  The internal implementation is testable outcome-free and binds
queue-v2 identity, separate verifier and outcome caps, durable raw events,
atomic outcome checkpoints, exact rollback, and terminal receipts.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
import hashlib
import json
import os
import platform
from pathlib import Path
import random
import sys
import threading
from datetime import datetime, timezone
from typing import Any, Iterator, Mapping

import numpy as np

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from . import parent_native_execution_services as services
from .parent_native_development_runtime_factory_v1 import (
    build_queue_bound_development_runtime_v1,
    preflight_development_binding_v1,
)
from .parent_native_persistent_runner import (
    ParentNativePersistentRunner,
    make_attempt_id,
    recover_terminal_result,
    replay_raw_ledger,
)
from .parent_native_work_accounting import ComponentwiseCapRejected
from .s0_successor import ROOT
from .s11_v2_native_preparation_runtime_v1 import (
    CumulativeVerifierLedger,
    VerifierComponentwiseCapRejected,
)
from .s11_v2_prepared_executor_v1 import (
    prepare_dynamic_magnitude_v1,
    prepare_dynamic_v5_v1,
    prepare_initial_executor_v1,
)
from .s11_v2_preexecution_gate_v5 import audit_frozen as audit_p7_v5
from .s11_v2_queue_native_adapter import (
    QUEUE_V2,
    QueueV2NativeAdapter,
    QueueV2NativeRequest,
)
from .semantic_contract_v2 import WorkDelta


DEFAULT_PRODUCTION_ROOT = (
    ROOT / "artifacts/v5-final/parent-native/s11-v2-production-execution-v1"
)
READINESS_V2 = (
    ROOT
    / "artifacts/v5-final/parent-native/s11-v2-execution-readiness-v4"
    / "execution-readiness-go-v4.json"
)
READINESS_GO = "GO_S11_V2_ITEM002_RETRY_AND_FROZEN_QUEUE_CONTINUATION"
P7_V5 = (
    ROOT
    / "artifacts/v5-final/parent-native/s11-v2-preexecution-gate-v5"
    / "p7-go-v5.json"
)
EXECUTION_ENVIRONMENT = (
    ROOT
    / "artifacts/v5-final/mb6-v2"
    / "execution-environment-v2.json"
)
OUTCOME_CAP_FREEZE = (
    ROOT
    / "artifacts/v5-final/parent-native/s11-v2-outcome-cap-freeze-v1"
    / "outcome-cap-freeze-v1.json"
)
ITEM000_INCIDENT = (
    ROOT
    / "artifacts/v5-final/parent-native/s11-v2-item000-incident-v1"
    / "environment-contract-incident-v1.json"
)
ITEM002_INCIDENT = (
    ROOT
    / "artifacts/v5-final/parent-native/s11-v2-item002-incident-v1"
    / "candidate-identity-incident-v1.json"
)
ITEM002_RETRY_AUTHORIZATION = (
    ROOT
    / "artifacts/v5-final/parent-native/s11-v2-item002-retry-authorization-v1"
    / "retry-authorization-v1.json"
)
ITEM002_QUEUE_ID = (
    "s11-v2-item-v2:"
    "7e30eb71e976122ee8c25d54648f3c55ab5b24f631efa666798058130a8c4ad4"
)
ADAPTER_SOURCE = ROOT / "src/v5_final/s11_v2_queue_native_adapter.py"
KERNEL_SOURCE_PATHS = (
    ROOT / "src/v5_final/parent_native_development_execution_v1.py",
    ROOT / "src/v5_final/parent_native_development_runtime_factory_v1.py",
    ROOT / "src/v5_final/parent_native_execution_services.py",
    ROOT / "src/v5_final/parent_native_persistent_runner.py",
    ROOT / "src/v5_final/parent_native_work_accounting.py",
)
MINIMUM_FREE_BYTES = 40 * 1024**3
TERMINAL_STATUS_MAP = {
    "ACCEPTED": "COMPLETED",
    "ALGORITHM_REJECTED": "ALGORITHM_REJECTED",
    "CAP_REJECTED": "CAP_REJECTED",
    "KERNEL_FAILURE": "FAILED_ENGINEERING_PRESERVED",
}


class S11V2ExecutionRunnerError(RuntimeError):
    pass


_LOCK = threading.RLock()
_FROZEN_DYNAMIC_V5 = services._dynamic_v5_preparation
_FROZEN_DYNAMIC_MAGNITUDE = services._dynamic_magnitude_preparation


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise S11V2ExecutionRunnerError(f"invalid JSON: {path}") from error
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise S11V2ExecutionRunnerError(f"noncanonical artifact: {path}")
    return value


def _embedded_digest(value: Mapping[str, Any], field: str) -> bool:
    body = dict(value)
    observed = body.pop(field, None)
    return isinstance(observed, str) and observed == _digest(body)


def _item_paths(root: Path, queue_index: int, request: QueueV2NativeRequest) -> dict[str, Path]:
    suffix = str(request.item["queue_item_id"]).split(":", 1)[-1][:16]
    stem = f"{queue_index:04d}-{suffix}"
    return {
        "raw": root / "raw-ledgers" / stem,
        "verifier": root / "verifier-ledgers" / stem,
        "result": root / "results" / f"{stem}.json",
        "receipt": root / "receipts" / f"{stem}.json",
        "dispatch": root / "dispatch" / f"{stem}.json",
        "progress": root / "progress" / f"{queue_index + 1:04d}-terminal.json",
    }


def _retry_dispatch_path(paths: Mapping[str, Path]) -> Path:
    return paths["dispatch"].with_name(paths["dispatch"].stem + "-retry-0002.json")


def _audit_retry_authorization(
    request: QueueV2NativeRequest,
    raw_last_record_digest: str,
) -> dict[str, Any]:
    if request.item["queue_item_id"] != ITEM002_QUEUE_ID:
        raise S11V2ExecutionRunnerError("retry is not authorized for this queue item")
    if not ITEM002_RETRY_AUTHORIZATION.is_file():
        raise S11V2ExecutionRunnerError("item002 retry authorization is absent")
    artifact = _load(ITEM002_RETRY_AUTHORIZATION)
    bindings = artifact.get("bindings", {})
    sources = bindings.get("source_sha256", {})
    if (
        artifact.get("schema")
        != "v5-final.s11-v2-item002-retry-authorization.v1"
        or artifact.get("decision")
        != "AUTHORIZE_S11_V2_ITEM002_SAME_ITEM_APPEND_ONLY_RETRY"
        or not _embedded_digest(artifact, "authorization_digest")
        or not all(artifact.get("checks", {}).values())
        or artifact.get("queue_index") != 2
        or artifact.get("queue_item_id") != ITEM002_QUEUE_ID
        or artifact.get("retry_attempt_ordinal") != 2
        or artifact.get("scientific_change") is not False
        or artifact.get("candidate_outcomes_used") is not False
        or artifact.get("authorization", {}).get("item002_retry")
        != "AUTHORIZED_ONCE_APPEND_ONLY_SAME_CAP_EXPECTED_CAP_REJECTION"
        or bindings.get("item002_incident_sha256") != _sha(ITEM002_INCIDENT)
        or bindings.get("pre_retry_last_record_digest")
        != raw_last_record_digest
        or not sources
        or any(_sha(ROOT / path) != expected for path, expected in sources.items())
    ):
        raise S11V2ExecutionRunnerError("item002 retry authorization is invalid")
    return artifact


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _free_bytes() -> int:
    state = os.statvfs(ROOT)
    return state.f_bavail * state.f_frsize


def _runtime_environment() -> dict[str, Any]:
    frozen = _load(EXECUTION_ENVIRONMENT)
    required_threads = dict(frozen.get("required_threads", {}))
    observed_threads = {name: os.environ.get(name) for name in required_threads}
    runtime = {
        "byte_order": sys.byteorder,
        "machine": platform.machine().lower(),
        "python_implementation": platform.python_implementation().lower(),
        "python_version": platform.python_version(),
        "system": platform.system().lower(),
    }
    locks = frozen.get("dependency_locks", {})
    checks = {
        "threads_exact": observed_threads == required_threads,
        "runtime_exact": runtime == frozen.get("runtime"),
        "root_lock_exact": locks.get("root_uv_lock_sha256") == _sha(ROOT / "uv.lock"),
        "parent_lock_exact": locks.get("parent_uv_lock_sha256")
        == _sha(ROOT / "provenance/dvg-obs-ceo/uv.lock"),
    }
    record = {
        "frozen_environment_digest": frozen.get("environment_digest"),
        "frozen_environment_sha256": _sha(EXECUTION_ENVIRONMENT),
        "required_threads": required_threads,
        "observed_threads": observed_threads,
        "required_runtime": frozen.get("runtime"),
        "observed_runtime": runtime,
        "dependency_locks": locks,
        "checks": checks,
    }
    record["observed_environment_digest"] = _digest(
        {
            "threads": observed_threads,
            "runtime": runtime,
            "dependency_locks": locks,
        }
    )
    if not all(checks.values()):
        failures = [name for name, passed in checks.items() if not passed]
        raise S11V2ExecutionRunnerError(
            "frozen execution environment differs: " + ", ".join(failures)
        )
    return record


def _source_binding(
    adapter: QueueV2NativeAdapter,
    readiness: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    queue_manifest = adapter.queue.get("execution_source_sha256", {})
    p7 = _load(P7_V5)
    p7_manifest = p7.get("artifact_bindings", {}).get("source_manifest", {})
    observed = {
        str(path.relative_to(ROOT)): _sha(path) for path in KERNEL_SOURCE_PATHS
    }
    readiness_manifest = (
        {} if readiness is None else readiness.get("binding", {}).get("source_sha256", {})
    )
    expected = {
        path: readiness_manifest.get(
            path, p7_manifest.get(path, queue_manifest.get(path))
        )
        for path in observed
    }
    if observed != expected or any(value is None for value in expected.values()):
        raise S11V2ExecutionRunnerError("actual molecular kernel source binding differs")
    return {
        "queue_sha256": _sha(QUEUE_V2),
        "queue_digest": adapter.queue["queue_digest"],
        "outcome_cap_freeze_sha256": _sha(OUTCOME_CAP_FREEZE),
        "P7_v5_sha256": _sha(P7_V5),
        "adapter_sha256": _sha(ADAPTER_SOURCE),
        "runner_sha256": _sha(Path(__file__)),
        "queue_frozen_kernel_source_sha256": queue_manifest,
        "P7_v5_authoritative_kernel_source_sha256": expected,
        "kernel_source_sha256": observed,
        "kernel_bundle_digest": _digest(observed),
    }


def _validate_terminal_receipt(
    *,
    request: QueueV2NativeRequest,
    paths: Mapping[str, Path],
    readiness_digest: str,
    predecessor_readiness_digests: tuple[str, ...] = (),
) -> dict[str, Any]:
    receipt = _load(paths["receipt"])
    result = _load(paths["result"])
    verifier = CumulativeVerifierLedger(
        paths["verifier"], cap=request.item["verifier_componentwise_cap"]
    )
    rebuilt = _result_artifact(
        request=request,
        raw_root=paths["raw"],
        verifier_ledger=verifier,
        outcome_checkpoint=(
            services._read_outcome_checkpoint(
                services._outcome_checkpoint_path(paths["raw"]),
                request.work_request,
            )
            if services._outcome_checkpoint_path(paths["raw"]).is_file()
            else None
        ),
    )
    if result != rebuilt or not _embedded_digest(receipt, "receipt_digest"):
        raise S11V2ExecutionRunnerError("terminal result or receipt reconstruction differs")
    if (
        receipt.get("queue_item_id") != request.item["queue_item_id"]
        or receipt.get("request_id") != request.work_request.request_id
        or receipt.get("result_digest") != result["result_digest"]
        or receipt.get("execution_readiness_digest")
        not in {readiness_digest, *predecessor_readiness_digests}
        or receipt.get("N_dense_expm") != 0
        or receipt.get("FCI_evaluations") != 0
    ):
        raise S11V2ExecutionRunnerError("terminal receipt binding differs")
    return receipt


def _terminal_prefix(
    *,
    adapter: QueueV2NativeAdapter,
    production_root: Path,
    readiness_digest: str,
    predecessor_readiness_digests: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    receipts: list[dict[str, Any]] = []
    gap_seen = False
    for index, item in enumerate(adapter.queue["items"]):
        request = adapter.request(str(item["queue_item_id"]))
        paths = _item_paths(production_root, index, request)
        terminal_present = paths["receipt"].is_file()
        any_started = any(
            paths[name].exists()
            for name in ("raw", "verifier", "result", "receipt", "dispatch")
        )
        if terminal_present:
            if gap_seen:
                raise S11V2ExecutionRunnerError("terminal receipts are not a queue prefix")
            receipts.append(
                _validate_terminal_receipt(
                    request=request,
                    paths=paths,
                    readiness_digest=readiness_digest,
                    predecessor_readiness_digests=predecessor_readiness_digests,
                )
            )
        else:
            if any_started and gap_seen:
                raise S11V2ExecutionRunnerError("work exists after the first queue gap")
            gap_seen = True
    return receipts


def _write_dispatch(
    *,
    adapter: QueueV2NativeAdapter,
    request: QueueV2NativeRequest,
    paths: Mapping[str, Path],
    queue_index: int,
    readiness_digest: str,
    environment: Mapping[str, Any],
    source_binding: Mapping[str, Any],
    retry_authorization: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    fixed = {
        "schema": "v5-final.s11-v2-item-dispatch.v1",
        "queue_index": queue_index,
        "queue_item_id": request.item["queue_item_id"],
        "request_id": request.work_request.request_id,
        "case_id": request.item["case_id"],
        "method_id": request.method_id,
        "work_envelope": request.item["work_envelope"],
        "execution_readiness_digest": readiness_digest,
        "source_binding": dict(source_binding),
        "environment": dict(environment),
        "outcome_cap_digest": request.item["outcome_work_cap"]["cap_digest"],
        "verifier_cap_digest": request.item["verifier_componentwise_cap_digest"],
        "free_bytes_before_dispatch": _free_bytes(),
        "minimum_free_bytes": MINIMUM_FREE_BYTES,
        "FCI_reporting_authorized": False,
        "performance_claim_authorized": False,
    }
    if fixed["free_bytes_before_dispatch"] < MINIMUM_FREE_BYTES:
        raise S11V2ExecutionRunnerError("free storage is below 40 GiB before dispatch")
    if retry_authorization is not None:
        if not paths["dispatch"].is_file():
            raise S11V2ExecutionRunnerError("retry lacks its original dispatch")
        original = _load(paths["dispatch"])
        if (
            not _embedded_digest(original, "dispatch_digest")
            or original.get("queue_item_id") != request.item["queue_item_id"]
            or original.get("queue_index") != queue_index
        ):
            raise S11V2ExecutionRunnerError("original retry dispatch is invalid")
        retry_fixed = {
            **fixed,
            "schema": "v5-final.s11-v2-item-retry-dispatch.v1",
            "retry_attempt_ordinal": 2,
            "retry_authorization_digest": retry_authorization[
                "authorization_digest"
            ],
            "retry_authorization_sha256": _sha(ITEM002_RETRY_AUTHORIZATION),
            "original_dispatch_digest": original["dispatch_digest"],
            "original_dispatch_sha256": _sha(paths["dispatch"]),
        }
        retry_path = _retry_dispatch_path(paths)
        if retry_path.exists():
            existing = _load(retry_path)
            if (
                not _embedded_digest(existing, "dispatch_digest")
                or any(existing.get(field) != value for field, value in retry_fixed.items())
            ):
                raise S11V2ExecutionRunnerError("existing retry dispatch differs")
            return existing
        retry = {
            **retry_fixed,
            "started_at_utc": _utc_now(),
            "process": {
                "pid": os.getpid(),
                "pgid": os.getpgid(0),
                "exact_command": [sys.executable, *sys.argv],
                "working_directory": str(Path.cwd()),
            },
        }
        retry["dispatch_digest"] = _digest(retry)
        write_json_exclusive(retry_path, retry)
        return retry
    if paths["dispatch"].exists():
        dispatch = _load(paths["dispatch"])
        for field, value in fixed.items():
            if field == "free_bytes_before_dispatch":
                continue
            if dispatch.get(field) != value:
                raise S11V2ExecutionRunnerError(
                    f"existing dispatch binding differs: {field}"
                )
        if not _embedded_digest(dispatch, "dispatch_digest"):
            raise S11V2ExecutionRunnerError("existing dispatch digest differs")
        return dispatch
    dispatch = fixed | {
        "started_at_utc": _utc_now(),
        "process": {
            "pid": os.getpid(),
            "pgid": os.getpgid(0),
            "exact_command": [sys.executable, *sys.argv],
            "working_directory": str(Path.cwd()),
        },
    }
    dispatch["dispatch_digest"] = _digest(dispatch)
    paths["dispatch"].parent.mkdir(parents=True, exist_ok=True)
    write_json_exclusive(paths["dispatch"], dispatch)
    return dispatch


def _write_progress(
    *,
    adapter: QueueV2NativeAdapter,
    production_root: Path,
    receipts: list[Mapping[str, Any]],
    readiness_digest: str,
) -> dict[str, Any]:
    terminal_counts = {status: 0 for status in sorted(set(TERMINAL_STATUS_MAP.values()))}
    for receipt in receipts:
        terminal_counts[str(receipt["terminal_status"])] += 1
    body = {
        "schema": "v5-final.s11-v2-progress.v1",
        "queue_digest": adapter.queue["queue_digest"],
        "execution_readiness_digest": readiness_digest,
        "expected_item_count": 90,
        "terminal_count": len(receipts),
        "terminal_queue_item_ids": [value["queue_item_id"] for value in receipts],
        "terminal_receipt_digests": [value["receipt_digest"] for value in receipts],
        "terminal_status_counts": terminal_counts,
        "N_dense_expm": sum(int(value["N_dense_expm"]) for value in receipts),
        "FCI_evaluations": 0,
        "performance_claim": "NOT_AUTHORIZED",
        "complete": len(receipts) == 90,
    }
    body["progress_digest"] = _digest(body)
    path = production_root / "progress" / f"{len(receipts):04d}-terminal.json"
    if path.exists():
        if _load(path) != body:
            raise S11V2ExecutionRunnerError("existing progress artifact differs")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json_exclusive(path, body)
    return body


def _queue_index(adapter: QueueV2NativeAdapter, queue_item_id: str) -> int:
    matches = [
        index
        for index, item in enumerate(adapter.queue["items"])
        if item["queue_item_id"] == queue_item_id
    ]
    if len(matches) != 1:
        raise S11V2ExecutionRunnerError("queue item index is absent or duplicated")
    return matches[0]


def _record_verifier_cap_rejection(boundary: Any, reason: str) -> None:
    boundary.recorder._append(
        operation="cap-rejection",
        outcome="cap-rejected",
        units=0,
        evidence={
            "rejected_operation": "verifier-v2-session",
            "verifier_cap_reason": reason,
            "kernel_executed": False,
        },
    )
    boundary.runner.persist_new_work_events(boundary.recorder.events)


@contextmanager
def _queue_v2_dynamic_scope(
    *,
    queue_item: Mapping[str, Any],
    verifier_ledger: CumulativeVerifierLedger,
    boundary: Any,
    maximum_rounds: int,
) -> Iterator[None]:
    """Replace only post-commit preparation, never outcome semantics."""

    with _LOCK:
        if (
            services._dynamic_v5_preparation is not _FROZEN_DYNAMIC_V5
            or services._dynamic_magnitude_preparation is not _FROZEN_DYNAMIC_MAGNITUDE
        ):
            raise S11V2ExecutionRunnerError("unexpected dynamic override is active")
        calls = {"v5": 0, "magnitude": 0}

        def _round_precheck(kind: str) -> None:
            if calls[kind] >= maximum_rounds - 1:
                _record_verifier_cap_rejection(
                    boundary, "frozen maximum_rounds reached before rebuild"
                )
                raise ComponentwiseCapRejected("frozen maximum rounds reached")
            calls[kind] += 1

        def dynamic_v5(executor: Any, _: Any):
            _round_precheck("v5")
            try:
                prepared = prepare_dynamic_v5_v1(
                    executor=executor,
                    queue_item=queue_item,
                    verifier_ledger=verifier_ledger,
                )
            except VerifierComponentwiseCapRejected as error:
                _record_verifier_cap_rejection(boundary, str(error))
                raise ComponentwiseCapRejected(str(error)) from error
            return (
                prepared.plans,
                prepared.rewrites,
                {
                    "selection_engine": "VerifierV2",
                    "verifier_core_digest": prepared.verifier_core_digest,
                    "selected_attempt_count": len(prepared.plans),
                    "candidate_outcomes_used": False,
                },
            )

        def dynamic_magnitude(executor: Any, _: Any):
            _round_precheck("magnitude")
            try:
                deletion = prepare_dynamic_magnitude_v1(
                    executor=executor,
                    queue_item=queue_item,
                    verifier_ledger=verifier_ledger,
                )
            except VerifierComponentwiseCapRejected as error:
                _record_verifier_cap_rejection(boundary, str(error))
                raise ComponentwiseCapRejected(str(error)) from error
            if deletion is None:
                return None
            inverse = np.delete(
                np.delete(
                    executor.context.runtime.inverse_hessian,
                    deletion.position,
                    axis=0,
                ),
                deletion.position,
                axis=1,
            )
            return deletion.candidate_id, deletion.target, inverse

        services._dynamic_v5_preparation = dynamic_v5
        services._dynamic_magnitude_preparation = dynamic_magnitude
        try:
            yield
        finally:
            if (
                services._dynamic_v5_preparation is not dynamic_v5
                or services._dynamic_magnitude_preparation is not dynamic_magnitude
            ):
                services._dynamic_v5_preparation = _FROZEN_DYNAMIC_V5
                services._dynamic_magnitude_preparation = _FROZEN_DYNAMIC_MAGNITUDE
                raise S11V2ExecutionRunnerError("dynamic override changed during item")
            services._dynamic_v5_preparation = _FROZEN_DYNAMIC_V5
            services._dynamic_magnitude_preparation = _FROZEN_DYNAMIC_MAGNITUDE


def _result_artifact(
    *,
    request: QueueV2NativeRequest,
    raw_root: Path,
    verifier_ledger: CumulativeVerifierLedger,
    outcome_checkpoint: Mapping[str, Any] | None,
) -> dict[str, Any]:
    replay = replay_raw_ledger(
        raw_root,
        request=request.work_request,
        cap=request.outcome_cap,
        require_terminal=True,
    )
    terminal = dict(replay.terminal or {})
    status = TERMINAL_STATUS_MAP[str(terminal["terminal_status"])]
    verifier_receipts = verifier_ledger.replay()
    operation_units: dict[str, int] = {}
    for event in replay.work_events:
        operation_units[event.operation] = operation_units.get(event.operation, 0) + int(
            event.units
        )
    outcome_payload = None
    if outcome_checkpoint is not None:
        outcome_payload = outcome_checkpoint["outcome_payload"]
        outcome_digest = str(outcome_checkpoint["outcome_digest"])
        terminal_bound = (
            terminal.get("outcome_digest") == outcome_digest
            if terminal["terminal_status"] == "ACCEPTED"
            else f"outcome_digest={outcome_digest}"
            in str(terminal.get("rejection_reason"))
        )
        if not terminal_bound:
            raise S11V2ExecutionRunnerError("raw terminal does not bind outcome checkpoint")
    body = {
        "schema": "v5-final.s11-v2-item-result.v1",
        "queue_item_id": request.item["queue_item_id"],
        "request_id": request.work_request.request_id,
        "method_id": request.method_id,
        "case_id": request.item["case_id"],
        "work_envelope": request.item["work_envelope"],
        "terminal_status": status,
        "raw_terminal": terminal,
        "raw_ledger_last_record_digest": replay.last_record_digest,
        "raw_work_total": asdict(replay.work_total),
        "raw_work_operation_units": dict(sorted(operation_units.items())),
        "candidate_energy_evaluations": operation_units.get(
            "candidate-energy-evaluation", 0
        ),
        "source_energy_evaluations": operation_units.get(
            "source-energy-evaluation", 0
        ),
        "verifier_work_total": verifier_ledger.total,
        "verifier_round_receipt_digests": [
            value.to_dict()["receipt_digest"] for value in verifier_receipts
        ],
        "outcome_checkpoint_digest": (
            None
            if outcome_checkpoint is None
            else outcome_checkpoint["checkpoint_digest"]
        ),
        "outcome": outcome_payload,
        "N_dense_expm": verifier_ledger.total["N_dense_expm"],
        "FCI_evaluations": 0,
        "performance_claim": "NOT_AUTHORIZED",
    }
    body["result_digest"] = _digest(body)
    return body


def _terminal_receipt(
    *,
    request: QueueV2NativeRequest,
    result: Mapping[str, Any],
    readiness_digest: str,
    runner_sha256: str,
    dispatch: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    body = {
        "schema": "v5-final.s11-v2-terminal-receipt.v1",
        "queue_item_id": request.item["queue_item_id"],
        "request_id": request.work_request.request_id,
        "terminal_status": result["terminal_status"],
        "result_digest": result["result_digest"],
        "queue_digest": request.queue_digest,
        "outcome_cap_digest": request.item["outcome_work_cap"]["cap_digest"],
        "verifier_cap_digest": request.item["verifier_componentwise_cap_digest"],
        "execution_readiness_digest": readiness_digest,
        "runner_sha256": runner_sha256,
        "dispatch_digest": None if dispatch is None else dispatch["dispatch_digest"],
        "environment_digest": (
            None
            if dispatch is None
            else dispatch["environment"]["frozen_environment_digest"]
        ),
        "kernel_bundle_digest": (
            None
            if dispatch is None
            else dispatch["source_binding"]["kernel_bundle_digest"]
        ),
        "adapter_sha256": (
            None
            if dispatch is None
            else dispatch["source_binding"]["adapter_sha256"]
        ),
        "N_dense_expm": result["N_dense_expm"],
        "FCI_evaluations": 0,
    }
    body["receipt_digest"] = _digest(body)
    return body


def _recover_existing(
    *,
    request: QueueV2NativeRequest,
    paths: Mapping[str, Path],
    verifier_ledger: CumulativeVerifierLedger,
    readiness_digest: str,
    dispatch: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    checkpoint_path = services._outcome_checkpoint_path(paths["raw"])
    checkpoint = (
        services._read_outcome_checkpoint(checkpoint_path, request.work_request)
        if checkpoint_path.is_file()
        else None
    )
    result = _result_artifact(
        request=request,
        raw_root=paths["raw"],
        verifier_ledger=verifier_ledger,
        outcome_checkpoint=checkpoint,
    )
    if paths["result"].exists():
        if _load(paths["result"]) != result:
            raise S11V2ExecutionRunnerError("existing result differs from recovery")
    else:
        paths["result"].parent.mkdir(parents=True, exist_ok=True)
        write_json_exclusive(paths["result"], result)
    receipt = _terminal_receipt(
        request=request,
        result=result,
        readiness_digest=readiness_digest,
        runner_sha256=_sha(Path(__file__)),
        dispatch=dispatch,
    )
    if paths["receipt"].exists():
        if _load(paths["receipt"]) != receipt:
            raise S11V2ExecutionRunnerError("existing receipt differs from recovery")
    else:
        paths["receipt"].parent.mkdir(parents=True, exist_ok=True)
        write_json_exclusive(paths["receipt"], receipt)
    return result


def _execute_authorized_item(
    *,
    adapter: QueueV2NativeAdapter,
    request: QueueV2NativeRequest,
    production_root: Path,
    readiness_digest: str,
    dispatch: Mapping[str, Any] | None = None,
    retry_authorization: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute after the public gate has established authorization."""

    queue_index = _queue_index(adapter, str(request.item["queue_item_id"]))
    paths = _item_paths(production_root, queue_index, request)
    verifier_ledger = CumulativeVerifierLedger(
        paths["verifier"], cap=request.item["verifier_componentwise_cap"]
    )
    checkpoint_path = services._outcome_checkpoint_path(paths["raw"])
    runner = None
    if paths["raw"].exists():
        replay = replay_raw_ledger(
            paths["raw"],
            request=request.work_request,
            cap=request.outcome_cap,
            require_terminal=False,
        )
        if replay.terminal is None:
            if checkpoint_path.is_file():
                runner = ParentNativePersistentRunner.open(
                    paths["raw"],
                    request=request.work_request,
                    cap=request.outcome_cap,
                )
                checkpoint = services._read_outcome_checkpoint(
                    checkpoint_path, request.work_request
                )
                services._terminalize_checkpoint(runner, checkpoint)
            elif replay.active_attempt_id is not None:
                raise S11V2ExecutionRunnerError(
                    "active item lacks outcome checkpoint; explicit retry audit required"
                )
            else:
                if retry_authorization is None:
                    raise S11V2ExecutionRunnerError(
                        "rolled-back item lacks additive retry authorization"
                    )
                _audit_retry_authorization(
                    request, str(replay.records[-1]["record_digest"])
                )
                preflight_development_binding_v1(
                    str(request.execution_item_v4["queue_item_id"])
                )
                runner = ParentNativePersistentRunner.open(
                    paths["raw"],
                    request=request.work_request,
                    cap=request.outcome_cap,
                )
                runner.start_retry(
                    make_attempt_id(
                        request.work_request,
                        ordinal=2,
                        nonce="s11-v2-item002-authorized-retry-attempt-2",
                    )
                )
        else:
            return _recover_existing(
                request=request,
                paths=paths,
                verifier_ledger=verifier_ledger,
                readiness_digest=readiness_digest,
                dispatch=dispatch,
            )
        if checkpoint_path.is_file():
            return _recover_existing(
                request=request,
                paths=paths,
                verifier_ledger=verifier_ledger,
                readiness_digest=readiness_digest,
                dispatch=dispatch,
            )
    elif any(paths[key].exists() for key in ("result", "receipt")) or checkpoint_path.exists():
        raise S11V2ExecutionRunnerError("orphan result, receipt, or checkpoint exists")

    old_item = request.execution_item_v4
    if runner is None:
        preflight_development_binding_v1(str(old_item["queue_item_id"]))
        attempt_id = make_attempt_id(
            request.work_request,
            ordinal=1,
            nonce="s11-v2-frozen-production-attempt-1",
        )
        runner = ParentNativePersistentRunner.create(
            paths["raw"],
            request=request.work_request,
            cap=request.outcome_cap,
            attempt_id=attempt_id,
        )
    random.seed(int(old_item["RNG_identity"]["python_seed"]))
    np.random.seed(int(old_item["RNG_identity"]["numpy_seed"]))
    recorder = runner.resume_work_recorder()
    boundary = services.DurableWorkBoundary(runner, recorder)
    context = None
    source_snapshot = None
    snapshots = None
    checkpoint = None
    try:
        context = build_queue_bound_development_runtime_v1(
            str(old_item["queue_item_id"]), work_recorder=boundary
        )
        source_snapshot = context.runtime.snapshot()
        snapshots = services._component_snapshot_digest(context.runtime)
        binding = dict(old_item["candidate_work_binding"])
        binding_body = dict(binding)
        observed_binding_digest = binding_body.pop("binding_digest", None)
        if observed_binding_digest != _digest(binding_body):
            raise S11V2ExecutionRunnerError("candidate work binding digest differs")
        context.runtime.metadata["candidate_work_binding"] = binding
        prepared, prepared_request = prepare_initial_executor_v1(
            adapter=adapter,
            request=request,
            context=context,
            verifier_ledger=verifier_ledger,
        )
        projected = WorkDelta(
            optimizer_starts=(
                0 if request.method_id == "immutable-ceo-star-source" else 1
            )
        )
        adapter.precheck_outcome_release(
            prepared_request, recorder=recorder, projected=projected
        )
        algorithm = context._actual_algorithm
        if algorithm.molecule.fci_energy is not None or algorithm.molecule.ccsd_energy is not None:
            raise S11V2ExecutionRunnerError("FCI/CCSD leaked into production runtime")
        executor_services = services.ParentNativeExecutionServices(
            item=old_item,
            plan=adapter.execution_plan,
            runner=runner,
            boundary=boundary,
            algorithm=algorithm,
        )
        with _queue_v2_dynamic_scope(
            queue_item=request.item,
            verifier_ledger=verifier_ledger,
            boundary=boundary,
            maximum_rounds=int(old_item["maximum_rounds"]),
        ):
            outcome = prepared.execute(executor_services)
        outcome_payload = {
            "queue_item_id": request.item["queue_item_id"],
            "method_id": request.method_id,
            "case_id": request.item["case_id"],
            "work_envelope": request.item["work_envelope"],
            "result": outcome,
            "work_total": asdict(boundary.total),
            "verifier_work_total": verifier_ledger.total,
            "telemetry": boundary.telemetry,
        }
        checkpoint = services._outcome_checkpoint(
            request.work_request, outcome_payload
        )
        write_json_exclusive(checkpoint_path, checkpoint)
        services._terminalize_checkpoint(runner, checkpoint)
    except (ComponentwiseCapRejected, VerifierComponentwiseCapRejected) as error:
        if not any(event.operation == "cap-rejection" for event in recorder.events):
            _record_verifier_cap_rejection(boundary, str(error))
        outcome_payload = {
            "queue_item_id": request.item["queue_item_id"],
            "terminal_status": "CAP_REJECTED",
            "work_total": asdict(boundary.total),
            "verifier_work_total": verifier_ledger.total,
            "telemetry": boundary.telemetry,
        }
        checkpoint = services._outcome_checkpoint(
            request.work_request, outcome_payload
        )
        write_json_exclusive(checkpoint_path, checkpoint)
        services._terminalize_checkpoint(runner, checkpoint)
    except BaseException as error:
        if checkpoint_path.is_file():
            raise S11V2ExecutionRunnerError(
                "outcome checkpoint exists; recover without repeating work"
            ) from error
        runner.persist_new_work_events(recorder.events)
        failed_primitive_exists = any(
            event.outcome == "failed" for event in recorder.events
        )
        if snapshots is None:
            seed = _digest(
                {
                    "StatePreparationID": request.item["source_identity"][
                        "StatePreparationID"
                    ],
                    "source_checkpoint_digest": request.item["source_identity"][
                        "source_checkpoint_digest"
                    ],
                }
            )
            snapshots = {
                name: seed
                for name in (
                    "ansatz",
                    "parameters",
                    "optimizer_inverse_hessian",
                    "resources",
                    "ledger_transaction",
                )
            }
        after = snapshots
        if context is not None and source_snapshot is not None:
            context.runtime.restore(source_snapshot)
            after = services._component_snapshot_digest(context.runtime)
        rollback_reason = type(error).__name__
        if context is None:
            rollback_reason += ":NO_RUNTIME_CONTEXT_EXPOSED"
        runner.rollback_active_attempt(
            component_digests_before=snapshots,
            component_digests_after=after,
            reason=rollback_reason,
        )
        if not failed_primitive_exists:
            raise S11V2ExecutionRunnerError(
                "non-primitive engineering failure was rolled back; "
                "explicit additive incident audit is required before retry"
            ) from error
        runner.finish("KERNEL_FAILURE", rejection_reason=type(error).__name__)
    return _recover_existing(
        request=request,
        paths=paths,
        verifier_ledger=verifier_ledger,
        readiness_digest=readiness_digest,
        dispatch=dispatch,
    )


def _audit_readiness_v2() -> dict[str, Any]:
    if not READINESS_V2.is_file():
        raise S11V2ExecutionRunnerError("execution-readiness v4 GO is absent")
    artifact = _load(READINESS_V2)
    bindings = artifact.get("binding", {})
    sources = bindings.get("source_sha256", {})
    if (
        artifact.get("schema") != "v5-final.s11-v2-execution-readiness.v4"
        or artifact.get("decision") != READINESS_GO
        or not _embedded_digest(artifact, "readiness_digest")
        or not all(artifact.get("checks", {}).values())
        or artifact.get("blockers") != []
        or artifact.get("authorization", {}).get("candidate_energy")
        != "AUTHORIZED_ONLY_INSIDE_EXACT_QUEUE_V2_ITEM_CAPS"
        or bindings.get("queue_v2", {}).get("sha256") != _sha(QUEUE_V2)
        or bindings.get("outcome_cap_freeze", {}).get("sha256")
        != _sha(OUTCOME_CAP_FREEZE)
        or bindings.get("P7_v5", {}).get("sha256") != _sha(P7_V5)
        or bindings.get("environment", {}).get("sha256")
        != _sha(EXECUTION_ENVIRONMENT)
        or bindings.get("item000_incident", {}).get("sha256")
        != _sha(ITEM000_INCIDENT)
        or bindings.get("item002_incident", {}).get("sha256")
        != _sha(ITEM002_INCIDENT)
        or bindings.get("item002_retry_authorization", {}).get("sha256")
        != _sha(ITEM002_RETRY_AUTHORIZATION)
        or artifact.get("execution_start_index") != 2
        or artifact.get("retry_attempt_ordinal") != 2
        or artifact.get("accepted_predecessor_receipt_readiness_digests")
        != [
            "5ce843ca5d057594d490243055cd657086ea8a60275c41623ff7a9e4aee6d409",
            "85cce0cc03289753f146f7d2cb4cfd12789dfd9f156f6a8ca292a5daa404e355",
        ]
        or not sources
        or any(_sha(ROOT / path) != expected for path, expected in sources.items())
    ):
        raise S11V2ExecutionRunnerError("execution-readiness v2 is invalid")
    return artifact


def execute_queue_item_v1(
    queue_item_id: str, *, production_root: Path = DEFAULT_PRODUCTION_ROOT
) -> dict[str, Any]:
    """Public gate-bound entrypoint for exactly one frozen queue-v2 item."""

    audit_p7_v5(require_live=True)
    readiness = _audit_readiness_v2()
    adapter = QueueV2NativeAdapter()
    request = adapter.request(queue_item_id)
    prefix = _terminal_prefix(
        adapter=adapter,
        production_root=production_root,
        readiness_digest=str(readiness["readiness_digest"]),
        predecessor_readiness_digests=tuple(
            readiness.get("accepted_predecessor_receipt_readiness_digests", ())
        ),
    )
    queue_index = _queue_index(adapter, queue_item_id)
    if queue_index != len(prefix):
        raise S11V2ExecutionRunnerError(
            "requested item is not the unique next frozen queue item"
        )
    paths = _item_paths(production_root, queue_index, request)
    if paths["receipt"].exists():
        raise S11V2ExecutionRunnerError("next item already has a terminal receipt")
    retry_authorization = None
    if paths["raw"].exists():
        replay = replay_raw_ledger(
            paths["raw"],
            request=request.work_request,
            cap=request.outcome_cap,
            require_terminal=False,
        )
        if replay.terminal is None and replay.active_attempt_id is None:
            retry_authorization = _audit_retry_authorization(
                request, str(replay.records[-1]["record_digest"])
            )
    environment = _runtime_environment()
    source_binding = _source_binding(adapter, readiness)
    dispatch = _write_dispatch(
        adapter=adapter,
        request=request,
        paths=paths,
        queue_index=queue_index,
        readiness_digest=str(readiness["readiness_digest"]),
        environment=environment,
        source_binding=source_binding,
        retry_authorization=retry_authorization,
    )
    result = _execute_authorized_item(
        adapter=adapter,
        request=request,
        production_root=production_root,
        readiness_digest=str(readiness["readiness_digest"]),
        dispatch=dispatch,
        retry_authorization=retry_authorization,
    )
    receipts = _terminal_prefix(
        adapter=adapter,
        production_root=production_root,
        readiness_digest=str(readiness["readiness_digest"]),
        predecessor_readiness_digests=tuple(
            readiness.get("accepted_predecessor_receipt_readiness_digests", ())
        ),
    )
    _write_progress(
        adapter=adapter,
        production_root=production_root,
        receipts=receipts,
        readiness_digest=str(readiness["readiness_digest"]),
    )
    return result

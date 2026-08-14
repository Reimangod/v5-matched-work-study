"""Capacity-guarded, resumable execution of the frozen MB6-v4 calibration."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time
from typing import Any, Callable, Mapping

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .p0_capacity_success_v3 import REQUIRED_FREE_BYTES, RESERVE_BYTES
from .parent_native_execution_services import execute_frozen_item
from .parent_native_persistent_runner import (
    recover_terminal_result,
    replay_raw_ledger,
)
from .parent_native_work_accounting import (
    ParentNativeWorkRequest,
    work_cap_digest,
)
from .s0_successor import ROOT
from .s8_parent_native_production_gate_v2 import audit as audit_s8_v2
from .semantic_contract_v2 import WORK_COMPONENTS, WorkDelta


PLAN_PATH = (
    ROOT
    / "artifacts/v5-final/parent-native/mb6-v4/h2-h4-calibration-plan-v4.json"
)
GO_PATH = ROOT / "artifacts/v5-final/parent-native/s8-production-go-v2.json"
S9_DIR = ROOT / "artifacts/v5-final/parent-native/s9-h2-h4-calibration-v1"
READINESS_PATH = S9_DIR / "s9-runner-readiness-v1.json"
AUTHORIZATION_PATH = S9_DIR / "s9-execution-authorization-v1.json"
DISPATCH_DIR = S9_DIR / "dispatch"
RAW_DIR = S9_DIR / "raw-ledgers"
RESULT_DIR = S9_DIR / "item-results"
RECEIPT_DIR = S9_DIR / "item-receipts"
PROGRESS_DIR = S9_DIR / "progress"
COMPLETENESS_PATH = S9_DIR / "h2-h4-completeness-v1.json"
THRESHOLD_BYTES = REQUIRED_FREE_BYTES + RESERVE_BYTES
TERMINAL_STATUSES = {
    "ACCEPTED",
    "ALGORITHM_REJECTED",
    "CAP_REJECTED",
    "KERNEL_FAILURE",
}
RUNNER_SOURCES = tuple(
    ROOT / value
    for value in (
        "src/v5_final/s9_h2_h4_calibration_runner.py",
        "src/v5_final/parent_native_execution_services.py",
        "src/v5_final/parent_native_persistent_runner.py",
        "src/v5_final/parent_native_work_accounting.py",
        "src/v5_final/semantic_contract_v2.py",
        ".github/workflows/v5-release-gate.yml",
    )
)


class S9CalibrationError(RuntimeError):
    pass


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _git(*arguments: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(ROOT), *arguments], text=True
    ).strip()


def _digest_valid(value: Mapping[str, Any], field: str) -> bool:
    body = dict(value)
    observed = body.pop(field, None)
    return isinstance(observed, str) and observed == _digest(body)


def _canonical_json(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise S9CalibrationError(f"invalid JSON artifact: {path}") from error
    if raw != canonical_json_bytes(value):
        raise S9CalibrationError(f"noncanonical JSON artifact: {path}")
    if not isinstance(value, dict):
        raise S9CalibrationError(f"artifact is not an object: {path}")
    return value


def _plan() -> dict[str, Any]:
    plan = _canonical_json(PLAN_PATH)
    body = dict(plan)
    observed = body.pop("plan_digest", None)
    items = list(plan.get("items", ()))
    if (
        observed != _digest(body)
        or plan.get("schema") != "v5-final.mb6-h2-h4-calibration-plan.v4"
        or plan.get("frozen_item_count") != 36
        or len(items) != 36
        or len({item.get("queue_item_id") for item in items}) != 36
        or plan.get("candidate_energy_evaluations") != 0
        or any(item.get("terminal_status") != "NOT_STARTED" for item in items)
    ):
        raise S9CalibrationError("MB6-v4 plan integrity failed")
    for item in items:
        item_body = {key: value for key, value in item.items() if key != "queue_item_id"}
        if item["queue_item_id"] != "mb6-calibration-item-v4:" + _digest(item_body):
            raise S9CalibrationError("MB6-v4 item identity failed")
    return plan


def _go() -> dict[str, Any]:
    if not GO_PATH.is_file():
        raise S9CalibrationError("S8-v2 GO is absent")
    if not all(audit_s8_v2(require_current_capacity=True).values()):
        raise S9CalibrationError("S8-v2 GO audit failed")
    gate = _canonical_json(GO_PATH)
    if (
        gate.get("decision") != "GO_H2_H4_CALIBRATION_ONLY"
        or gate.get("plan_digest") != _plan()["plan_digest"]
        or gate.get("authorization", {}).get("H2_H4_execution")
        != "AUTHORIZED_FROZEN_MB6_V4_PLAN_ONLY"
        or gate.get("authorization", {}).get("development_queue_execution")
        != "NOT_AUTHORIZED"
    ):
        raise S9CalibrationError("S8-v2 GO scope is invalid")
    return gate


def _capacity_observation(free_bytes: int) -> dict[str, Any]:
    if isinstance(free_bytes, bool) or not isinstance(free_bytes, int) or free_bytes < 0:
        raise S9CalibrationError("capacity observation is invalid")
    return {
        "filesystem_available_bytes": free_bytes,
        "required_study_bytes": REQUIRED_FREE_BYTES,
        "mandatory_reserve_bytes": RESERVE_BYTES,
        "execution_threshold_bytes": THRESHOLD_BYTES,
        "passed": free_bytes >= THRESHOLD_BYTES,
    }


def _current_capacity() -> dict[str, Any]:
    return _capacity_observation(shutil.disk_usage(ROOT).free)


def _item_key(index: int, item: Mapping[str, Any]) -> str:
    suffix = str(item["queue_item_id"]).split(":", 1)[-1]
    if len(suffix) != 64 or any(value not in "0123456789abcdef" for value in suffix):
        raise S9CalibrationError("queue item digest suffix is invalid")
    return f"{index:03d}-{suffix}"


def _request(plan: Mapping[str, Any], item: Mapping[str, Any]) -> tuple[ParentNativeWorkRequest, WorkDelta]:
    cap = WorkDelta(**dict(item["componentwise_work_cap"]))
    if work_cap_digest(cap) != item["work_cap_digest"]:
        raise S9CalibrationError("queue item work cap digest differs")
    request = ParentNativeWorkRequest(
        queue_item_id=str(item["queue_item_id"]),
        method_id=str(item["method_id"]),
        case_id=str(item["case_id"]),
        state_preparation_id=str(item["StatePreparationID"]),
        problem_id=str(item["ProblemID"]),
        hamiltonian_digest=str(item["Hamiltonian_digest"]),
        source_checkpoint_digest=str(item["source_checkpoint_digest"]),
        frozen_queue_digest=str(plan["plan_digest"]),
        work_cap_digest=str(item["work_cap_digest"]),
    )
    return request, cap


def build_readiness() -> dict[str, Any]:
    if _git("status", "--porcelain"):
        raise S9CalibrationError("readiness capture requires a clean worktree")
    plan = _plan()
    gate = _go()
    capacity = _current_capacity()
    checks = {
        "S8_v2_GO_valid": True,
        "capacity_currently_passes_with_5GiB_reserve": capacity["passed"],
        "exact_frozen_36_item_plan": len(plan["items"]) == 36,
        "candidate_energy_zero_at_runner_freeze": plan["candidate_energy_evaluations"]
        == 0
        and gate["candidate_molecular_energy_evaluations_before_GO"] == 0,
        "development_and_performance_not_authorized": gate["authorization"][
            "development_queue_execution"
        ]
        == "NOT_AUTHORIZED"
        and gate["authorization"]["performance_claim"] == "NOT_AUTHORIZED",
        "no_S9_output_exists": not S9_DIR.exists(),
    }
    if not all(checks.values()):
        raise S9CalibrationError(
            "S9 readiness failed: "
            + ", ".join(name for name, passed in checks.items() if not passed)
        )
    artifact = {
        "schema": "v5-final.s9-h2-h4-runner-readiness.v1",
        "stage": "S9_FROZEN_QUEUE_RUNNER_READINESS",
        "status": "PASS_OUTCOME_FREE_RUNNER_READY",
        "decision": "READY_AWAITING_EXACT_CI_FOR_S9_EXECUTION_AUTHORIZATION",
        "validated_runner_commit": _git("rev-parse", "HEAD"),
        "plan": {
            "path": str(PLAN_PATH.relative_to(ROOT)),
            "sha256": _sha(PLAN_PATH),
            "plan_digest": plan["plan_digest"],
            "item_count": 36,
        },
        "S8_v2_GO": {
            "path": str(GO_PATH.relative_to(ROOT)),
            "sha256": _sha(GO_PATH),
            "gate_digest": gate["gate_digest"],
        },
        "runner_source_manifest": [
            {"path": str(path.relative_to(ROOT)), "sha256": _sha(path)}
            for path in RUNNER_SOURCES
        ],
        "capacity_at_freeze": capacity,
        "checks": checks,
        "candidate_molecular_energy_evaluations": 0,
        "authorization": {
            "S9_execution_authorization_capture": "AUTHORIZED_AFTER_EXACT_CI",
            "H2_H4_execution": "NOT_AUTHORIZED_BY_READINESS_ALONE",
            "development_queue_execution": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "academic_boundary": (
            "This readiness record is outcome-free. It freezes only the durable "
            "orchestration and audit path for the already frozen MB6-v4 queue."
        ),
    }
    artifact["readiness_digest"] = _digest(artifact)
    return artifact


def audit_readiness() -> dict[str, bool]:
    artifact = _canonical_json(READINESS_PATH)
    plan = _plan()
    gate = _go()
    checks = {
        "readiness_digest_valid": _digest_valid(artifact, "readiness_digest"),
        "schema_and_decision_exact": artifact.get("schema")
        == "v5-final.s9-h2-h4-runner-readiness.v1"
        and artifact.get("decision")
        == "READY_AWAITING_EXACT_CI_FOR_S9_EXECUTION_AUTHORIZATION",
        "captured_checks_passed": all(artifact.get("checks", {}).values()),
        "plan_unchanged": artifact["plan"]["sha256"] == _sha(PLAN_PATH)
        and artifact["plan"]["plan_digest"] == plan["plan_digest"],
        "S8_v2_GO_unchanged": artifact["S8_v2_GO"]["sha256"] == _sha(GO_PATH)
        and artifact["S8_v2_GO"]["gate_digest"] == gate["gate_digest"],
        "runner_sources_unchanged": all(
            _sha(ROOT / item["path"]) == item["sha256"]
            for item in artifact["runner_source_manifest"]
        ),
        "runner_commit_is_ancestor": subprocess.run(
            [
                "git",
                "-C",
                str(ROOT),
                "merge-base",
                "--is-ancestor",
                artifact["validated_runner_commit"],
                "HEAD",
            ],
            check=False,
        ).returncode
        == 0,
        "candidate_energy_was_zero_at_freeze": artifact[
            "candidate_molecular_energy_evaluations"
        ]
        == 0,
        "development_and_claims_blocked": artifact["authorization"][
            "development_queue_execution"
        ]
        == "NOT_AUTHORIZED"
        and artifact["authorization"]["performance_claim"] == "NOT_AUTHORIZED",
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S9CalibrationError("S9 readiness audit failed: " + ", ".join(failures))
    return checks


def _validate_readiness_ci(evidence: Mapping[str, Any]) -> dict[str, bool]:
    readiness_commit = _git("rev-parse", "HEAD")
    return {
        "schema": evidence.get("schema")
        == "v5-final.external-s9-readiness-exact-ci-evidence.v1",
        "head_sha_exact": evidence.get("head_sha") == readiness_commit,
        "conclusion_success": evidence.get("conclusion") == "success",
        "release_gate_job_success": evidence.get("release_gate_job_conclusion")
        == "success",
        "attested_commit_exact": evidence.get("attested_commit") == readiness_commit,
        "S9_report_schema_exact": evidence.get("report_schema")
        == "v5-final.s9-h2-h4-ci-audit.v1",
        "readiness_audit_passed": evidence.get("readiness_audit_passed") is True,
        "run_id_positive": isinstance(evidence.get("run_id"), int)
        and evidence["run_id"] > 0,
        "attestation_sha256_valid": isinstance(
            evidence.get("attestation_sha256"), str
        )
        and len(evidence["attestation_sha256"]) == 64,
    }


def build_authorization(ci_evidence: Mapping[str, Any]) -> dict[str, Any]:
    if _git("status", "--porcelain"):
        raise S9CalibrationError("authorization capture requires a clean worktree")
    readiness_checks = audit_readiness()
    capacity = _current_capacity()
    ci_checks = _validate_readiness_ci(ci_evidence)
    checks = {
        "readiness_audit_passed": all(readiness_checks.values()),
        "readiness_exact_CI_passed": all(ci_checks.values()),
        "capacity_currently_passes_with_5GiB_reserve": capacity["passed"],
        "no_calibration_output_started": not any(
            path.exists()
            for path in (DISPATCH_DIR, RAW_DIR, RESULT_DIR, RECEIPT_DIR, PROGRESS_DIR)
        ),
    }
    if not all(checks.values()):
        raise S9CalibrationError(
            "S9 authorization failed: "
            + ", ".join(name for name, passed in checks.items() if not passed)
        )
    readiness = _canonical_json(READINESS_PATH)
    artifact = {
        "schema": "v5-final.s9-h2-h4-execution-authorization.v1",
        "stage": "S9_FROZEN_MB6_V4_EXECUTION_AUTHORIZATION",
        "status": "PASS_OUTCOME_FREE_EXECUTION_AUTHORIZATION",
        "decision": "GO_S9_FROZEN_MB6_V4_H2_H4_ONLY",
        "authorized_readiness_commit": _git("rev-parse", "HEAD"),
        "readiness": {
            "path": str(READINESS_PATH.relative_to(ROOT)),
            "sha256": _sha(READINESS_PATH),
            "readiness_digest": readiness["readiness_digest"],
        },
        "exact_CI_evidence": dict(ci_evidence),
        "exact_CI_checks": ci_checks,
        "capacity_at_authorization": capacity,
        "checks": checks,
        "candidate_molecular_energy_evaluations_before_authorization": 0,
        "authorization": {
            "H2_H4_execution": "AUTHORIZED_EXACT_FROZEN_MB6_V4_ORDER_ONLY",
            "H2_H4_item_count": 36,
            "capacity_recheck_before_and_after_each_item": True,
            "development_queue_execution": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "academic_boundary": (
            "Only execution and integrity analysis of the frozen 36 calibration "
            "items is authorized. Outcomes cannot alter order, methods, caps, or policy."
        ),
    }
    artifact["authorization_digest"] = _digest(artifact)
    return artifact


def audit_authorization() -> dict[str, bool]:
    readiness_checks = audit_readiness()
    artifact = _canonical_json(AUTHORIZATION_PATH)
    readiness = _canonical_json(READINESS_PATH)
    checks = {
        "authorization_digest_valid": _digest_valid(
            artifact, "authorization_digest"
        ),
        "schema_and_decision_exact": artifact.get("schema")
        == "v5-final.s9-h2-h4-execution-authorization.v1"
        and artifact.get("decision") == "GO_S9_FROZEN_MB6_V4_H2_H4_ONLY",
        "readiness_still_valid": all(readiness_checks.values()),
        "readiness_bound_exactly": artifact["readiness"]["sha256"]
        == _sha(READINESS_PATH)
        and artifact["readiness"]["readiness_digest"]
        == readiness["readiness_digest"],
        "exact_CI_checks_passed": all(artifact["exact_CI_checks"].values()),
        "captured_checks_passed": all(artifact["checks"].values()),
        "authorized_commit_is_ancestor": subprocess.run(
            [
                "git",
                "-C",
                str(ROOT),
                "merge-base",
                "--is-ancestor",
                artifact["authorized_readiness_commit"],
                "HEAD",
            ],
            check=False,
        ).returncode
        == 0,
        "authorization_scope_exact": artifact["authorization"]["H2_H4_execution"]
        == "AUTHORIZED_EXACT_FROZEN_MB6_V4_ORDER_ONLY"
        and artifact["authorization"]["development_queue_execution"]
        == "NOT_AUTHORIZED"
        and artifact["authorization"]["performance_claim"] == "NOT_AUTHORIZED",
        "capacity_currently_passes": _current_capacity()["passed"],
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S9CalibrationError(
            "S9 execution authorization audit failed: " + ", ".join(failures)
        )
    return checks


def _read_result(path: Path) -> dict[str, Any]:
    result = _canonical_json(path)
    if not _digest_valid(result, "artifact_digest"):
        raise S9CalibrationError("item result artifact digest is invalid")
    return result


def _event_operation_counts(state: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in state.work_events:
        counts[event.operation] = counts.get(event.operation, 0) + int(event.units)
    return dict(sorted(counts.items()))


def _receipt_for(
    *,
    plan: Mapping[str, Any],
    item: Mapping[str, Any],
    index: int,
    dispatch: Mapping[str, Any],
    capacity_before_resume: Mapping[str, Any],
    capacity_after: Mapping[str, Any],
    orchestrator_elapsed_seconds: float,
    result: Mapping[str, Any],
) -> dict[str, Any]:
    key = _item_key(index, item)
    request, cap = _request(plan, item)
    raw_root = RAW_DIR / key
    state = replay_raw_ledger(
        raw_root, request=request, cap=cap, require_terminal=True
    )
    recovered = recover_terminal_result(raw_root, request=request, cap=cap)
    terminal = dict(state.terminal or {})
    if terminal.get("terminal_status") not in TERMINAL_STATUSES:
        raise S9CalibrationError("item terminal status is invalid")
    result_terminal = result.get("recovered", {}).get("terminal")
    if result_terminal != terminal:
        raise S9CalibrationError("item result and raw terminal differ")
    operation_counts = _event_operation_counts(state)
    outcome = result.get("outcome", {})
    telemetry = outcome.get("telemetry", []) if isinstance(outcome, dict) else []
    receipt = {
        "schema": "v5-final.s9-h2-h4-item-receipt.v1",
        "queue_index": index,
        "queue_item_id": item["queue_item_id"],
        "case_id": item["case_id"],
        "method_id": item["method_id"],
        "work_envelope": item["work_envelope"],
        "plan_digest": plan["plan_digest"],
        "dispatch_digest": dispatch["dispatch_digest"],
        "raw_ledger_relative_path": str(raw_root.relative_to(ROOT)),
        "raw_terminal_record_digest": state.records[-1]["record_digest"],
        "result_relative_path": str((RESULT_DIR / f"{key}.json").relative_to(ROOT)),
        "result_sha256": _sha(RESULT_DIR / f"{key}.json"),
        "result_artifact_digest": result["artifact_digest"],
        "terminal_status": terminal["terminal_status"],
        "work_total": asdict(state.work_total),
        "work_operation_units": operation_counts,
        "candidate_energy_evaluations": operation_counts.get(
            "candidate-energy-evaluation", 0
        ),
        "source_energy_evaluations": operation_counts.get(
            "source-energy-evaluation", 0
        ),
        "kernel_telemetry_elapsed_seconds": sum(
            float(value["elapsed_seconds"])
            for value in telemetry
            if isinstance(value, dict) and "elapsed_seconds" in value
        ),
        "method_wall_time_seconds": (
            outcome.get("result", {}).get("wall_time_seconds")
            if isinstance(outcome, dict) and isinstance(outcome.get("result"), dict)
            else None
        ),
        "orchestrator_elapsed_seconds": float(orchestrator_elapsed_seconds),
        "capacity_before_dispatch": dispatch["capacity_before_dispatch"],
        "capacity_before_resume_or_execution": dict(capacity_before_resume),
        "capacity_after_terminal": dict(capacity_after),
    }
    receipt["receipt_digest"] = _digest(receipt)
    return receipt


def _validate_receipt(
    plan: Mapping[str, Any], item: Mapping[str, Any], index: int
) -> dict[str, Any]:
    key = _item_key(index, item)
    receipt = _canonical_json(RECEIPT_DIR / f"{key}.json")
    if (
        not _digest_valid(receipt, "receipt_digest")
        or receipt.get("queue_index") != index
        or receipt.get("queue_item_id") != item["queue_item_id"]
        or receipt.get("plan_digest") != plan["plan_digest"]
        or receipt.get("result_sha256") != _sha(RESULT_DIR / f"{key}.json")
    ):
        raise S9CalibrationError("item receipt binding is invalid")
    result = _read_result(RESULT_DIR / f"{key}.json")
    if receipt["result_artifact_digest"] != result["artifact_digest"]:
        raise S9CalibrationError("receipt result digest differs")
    request, cap = _request(plan, item)
    state = replay_raw_ledger(
        RAW_DIR / key, request=request, cap=cap, require_terminal=True
    )
    if (
        receipt["raw_terminal_record_digest"] != state.records[-1]["record_digest"]
        or receipt["terminal_status"] != state.terminal["terminal_status"]
        or receipt["work_total"] != asdict(state.work_total)
        or receipt["work_operation_units"] != _event_operation_counts(state)
    ):
        raise S9CalibrationError("receipt differs from raw-ledger reconstruction")
    return receipt


def _directory_names(path: Path) -> set[str]:
    if not path.exists():
        return set()
    if not path.is_dir() or path.is_symlink():
        raise S9CalibrationError(f"unsafe S9 output directory: {path}")
    return {value.name for value in path.iterdir()}


def _completed_receipts(
    plan: Mapping[str, Any],
    *,
    allow_inflight: bool,
    require_progress: bool = True,
) -> list[dict[str, Any]]:
    items = list(plan["items"])
    receipt_names = _directory_names(RECEIPT_DIR)
    completed: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        name = f"{_item_key(index, item)}.json"
        if name not in receipt_names:
            break
        completed.append(_validate_receipt(plan, item, index))
    expected_receipts = {
        f"{_item_key(index, items[index])}.json" for index in range(len(completed))
    }
    if receipt_names != expected_receipts:
        raise S9CalibrationError("receipts are not an exact frozen-order prefix")
    completed_keys = {
        _item_key(index, items[index]) for index in range(len(completed))
    }
    next_key = (
        _item_key(len(completed), items[len(completed)])
        if allow_inflight and len(completed) < len(items)
        else None
    )
    allowed_keys = completed_keys | ({next_key} if next_key is not None else set())
    for directory in (DISPATCH_DIR, RESULT_DIR):
        names = _directory_names(directory)
        if not names.issubset({f"{key}.json" for key in allowed_keys}):
            raise S9CalibrationError(f"orphan S9 artifact in {directory}")
    raw_names = _directory_names(RAW_DIR)
    allowed_raw = allowed_keys | {f"{key}.outcome.json" for key in allowed_keys}
    if not raw_names.issubset(allowed_raw):
        raise S9CalibrationError("orphan raw ledger or outcome checkpoint")
    progress_names = _directory_names(PROGRESS_DIR)
    expected_progress = {f"{value:03d}.json" for value in range(1, len(completed) + 1)}
    if (
        require_progress
        and progress_names != expected_progress
        or not require_progress
        and not progress_names.issubset(expected_progress)
    ):
        raise S9CalibrationError("progress snapshots are missing or orphaned")
    return completed


def _progress_snapshot(plan: Mapping[str, Any], receipts: list[Mapping[str, Any]]) -> dict[str, Any]:
    totals = {component: 0 for component in WORK_COMPONENTS}
    terminal_counts = {status: 0 for status in sorted(TERMINAL_STATUSES)}
    for receipt in receipts:
        terminal_counts[receipt["terminal_status"]] += 1
        for component in WORK_COMPONENTS:
            totals[component] += int(receipt["work_total"][component])
    complete = len(receipts) == len(plan["items"])
    snapshot = {
        "schema": "v5-final.s9-h2-h4-progress.v1",
        "plan_digest": plan["plan_digest"],
        "expected_item_count": len(plan["items"]),
        "completed_terminal_count": len(receipts),
        "completed_queue_item_ids": [value["queue_item_id"] for value in receipts],
        "receipt_digests": [value["receipt_digest"] for value in receipts],
        "terminal_status_counts": terminal_counts,
        "aggregate_work_total": totals,
        "candidate_energy_evaluations": sum(
            int(value["candidate_energy_evaluations"]) for value in receipts
        ),
        "all_post_item_capacity_checks_passed": all(
            value["capacity_after_terminal"]["passed"] for value in receipts
        ),
        "complete": complete,
        "authorization": {
            "development_queue_execution": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
    }
    snapshot["progress_digest"] = _digest(snapshot)
    return snapshot


def _ensure_progress_snapshots(
    plan: Mapping[str, Any], receipts: list[Mapping[str, Any]]
) -> None:
    for count in range(1, len(receipts) + 1):
        expected = _progress_snapshot(plan, receipts[:count])
        path = PROGRESS_DIR / f"{count:03d}.json"
        if path.exists():
            if _canonical_json(path) != expected:
                raise S9CalibrationError("existing progress snapshot differs")
        else:
            write_json_exclusive(path, expected)


def audit_progress(*, allow_inflight: bool = False) -> dict[str, Any]:
    plan = _plan()
    authorization_checks = audit_authorization() if AUTHORIZATION_PATH.exists() else {}
    if not READINESS_PATH.exists():
        completed: list[dict[str, Any]] = []
    else:
        audit_readiness()
        completed = _completed_receipts(plan, allow_inflight=allow_inflight)
    progress = _progress_snapshot(plan, completed)
    checks = {
        "readiness_valid_if_present": not READINESS_PATH.exists()
        or all(audit_readiness().values()),
        "authorization_valid_if_present": not AUTHORIZATION_PATH.exists()
        or all(authorization_checks.values()),
        "completed_items_form_exact_prefix": progress["completed_terminal_count"]
        == len(completed),
        "candidate_energy_reconstructed_from_raw_events": progress[
            "candidate_energy_evaluations"
        ]
        == sum(value["candidate_energy_evaluations"] for value in completed),
        "development_and_performance_blocked": progress["authorization"][
            "development_queue_execution"
        ]
        == "NOT_AUTHORIZED"
        and progress["authorization"]["performance_claim"] == "NOT_AUTHORIZED",
    }
    if not all(checks.values()):
        raise S9CalibrationError("S9 progress audit failed")
    return {"checks": checks, "progress": progress}


def build_ci_audit() -> dict[str, Any]:
    plan = _plan()
    gate = _go()
    readiness_checks = audit_readiness() if READINESS_PATH.exists() else {}
    authorization_checks = (
        audit_authorization() if AUTHORIZATION_PATH.exists() else {}
    )
    progress_report = audit_progress(allow_inflight=False)
    progress = progress_report["progress"]
    checks = {
        "S8_v2_GO_valid": gate["decision"] == "GO_H2_H4_CALIBRATION_ONLY",
        "frozen_plan_exact": len(plan["items"]) == 36,
        "readiness_valid_if_present": not READINESS_PATH.exists()
        or all(readiness_checks.values()),
        "authorization_valid_if_present": not AUTHORIZATION_PATH.exists()
        or all(authorization_checks.values()),
        "progress_integrity": all(progress_report["checks"].values()),
        "development_and_performance_not_authorized": progress["authorization"][
            "development_queue_execution"
        ]
        == "NOT_AUTHORIZED"
        and progress["authorization"]["performance_claim"] == "NOT_AUTHORIZED",
    }
    if not all(checks.values()):
        raise S9CalibrationError("S9 CI audit failed")
    result = {
        "schema": "v5-final.s9-h2-h4-ci-audit.v1",
        "validated_exact_commit": _git("rev-parse", "HEAD"),
        "status": "PASS_S9_INTEGRITY",
        "decision": (
            "S9_IMPLEMENTATION_ONLY_EXECUTION_NOT_AUTHORIZED"
            if not READINESS_PATH.exists()
            else (
                "READY_AWAITING_S9_EXECUTION_AUTHORIZATION"
                if not AUTHORIZATION_PATH.exists()
                else "S9_FROZEN_EXECUTION_AUTHORIZATION_VALID"
            )
        ),
        "readiness_audit": readiness_checks,
        "authorization_audit": authorization_checks,
        "progress": progress,
        "checks": checks,
        "candidate_molecular_energy_evaluations": progress[
            "candidate_energy_evaluations"
        ],
        "authorization": {
            "H2_H4_execution": (
                "AUTHORIZED_BY_COMMITTED_S9_ARTIFACT"
                if AUTHORIZATION_PATH.exists()
                else "NOT_AUTHORIZED"
            ),
            "development_queue_execution": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
    }
    result["audit_digest"] = _digest(result)
    return result


def _write_dispatch(
    plan: Mapping[str, Any], item: Mapping[str, Any], index: int
) -> dict[str, Any]:
    key = _item_key(index, item)
    path = DISPATCH_DIR / f"{key}.json"
    if path.exists():
        dispatch = _canonical_json(path)
        if (
            not _digest_valid(dispatch, "dispatch_digest")
            or dispatch.get("queue_index") != index
            or dispatch.get("queue_item_id") != item["queue_item_id"]
            or dispatch.get("plan_digest") != plan["plan_digest"]
            or dispatch.get("authorization_sha256") != _sha(AUTHORIZATION_PATH)
            or dispatch.get("capacity_before_dispatch", {}).get("passed") is not True
        ):
            raise S9CalibrationError("existing dispatch record is invalid")
        return dispatch
    capacity = _current_capacity()
    dispatch = {
        "schema": "v5-final.s9-h2-h4-item-dispatch.v1",
        "queue_index": index,
        "queue_item_id": item["queue_item_id"],
        "case_id": item["case_id"],
        "method_id": item["method_id"],
        "work_envelope": item["work_envelope"],
        "plan_digest": plan["plan_digest"],
        "authorization_sha256": _sha(AUTHORIZATION_PATH),
        "capacity_before_dispatch": capacity,
    }
    dispatch["dispatch_digest"] = _digest(dispatch)
    write_json_exclusive(path, dispatch)
    if not capacity["passed"]:
        raise S9CalibrationError("capacity failed before item dispatch")
    return dispatch


def _kernel_failure_result(
    plan: Mapping[str, Any], item: Mapping[str, Any], index: int, error: BaseException
) -> dict[str, Any]:
    key = _item_key(index, item)
    request, cap = _request(plan, item)
    recovered = recover_terminal_result(RAW_DIR / key, request=request, cap=cap)
    if recovered["terminal"]["terminal_status"] != "KERNEL_FAILURE":
        raise S9CalibrationError("raised item lacks a durable kernel-failure terminal")
    artifact = {
        "schema": "v5-final.parent-native-item-result.v1",
        "request": request.payload() | {"request_id": request.request_id},
        "outcome": {
            "queue_item_id": item["queue_item_id"],
            "terminal_status": "KERNEL_FAILURE",
            "exception_type": type(error).__name__,
            "performance_evidence": False,
        },
        "outcome_checkpoint_digest": None,
        "recovered": recovered,
    }
    artifact["artifact_digest"] = _digest(artifact)
    output = RESULT_DIR / f"{key}.json"
    if output.exists():
        if _canonical_json(output) != artifact:
            raise S9CalibrationError("existing kernel-failure result differs")
    else:
        write_json_exclusive(output, artifact)
    return artifact


def _run_item(
    plan: Mapping[str, Any], item: Mapping[str, Any], index: int
) -> dict[str, Any]:
    key = _item_key(index, item)
    dispatch = _write_dispatch(plan, item, index)
    capacity_before = _current_capacity()
    if not capacity_before["passed"]:
        raise S9CalibrationError("capacity failed before item execution or recovery")
    started = time.perf_counter()
    execution_error: BaseException | None = None
    try:
        result = execute_frozen_item(
            plan=plan,
            item=item,
            raw_ledger_root=RAW_DIR / key,
            result_output=RESULT_DIR / f"{key}.json",
        )
    except BaseException as error:
        execution_error = error
        result = _kernel_failure_result(plan, item, index, error)
    elapsed = time.perf_counter() - started
    capacity_after = _current_capacity()
    receipt = _receipt_for(
        plan=plan,
        item=item,
        index=index,
        dispatch=dispatch,
        capacity_before_resume=capacity_before,
        capacity_after=capacity_after,
        orchestrator_elapsed_seconds=elapsed,
        result=result,
    )
    write_json_exclusive(RECEIPT_DIR / f"{key}.json", receipt)
    completed = _completed_receipts(
        plan, allow_inflight=False, require_progress=False
    )
    _ensure_progress_snapshots(plan, completed)
    if execution_error is not None:
        raise S9CalibrationError(
            f"kernel failure terminalized at frozen item {index}; queue stopped"
        ) from execution_error
    if not capacity_after["passed"]:
        raise S9CalibrationError(
            f"capacity fell below threshold after frozen item {index}; queue stopped"
        )
    return receipt


def run_calibration(*, max_items: int | None = None) -> dict[str, Any]:
    if max_items is not None and (
        isinstance(max_items, bool) or not isinstance(max_items, int) or max_items < 1
    ):
        raise S9CalibrationError("max-items must be a positive integer")
    audit_authorization()
    plan = _plan()
    for directory in (DISPATCH_DIR, RAW_DIR, RESULT_DIR, RECEIPT_DIR, PROGRESS_DIR):
        directory.mkdir(parents=True, exist_ok=True)
    completed = _completed_receipts(
        plan, allow_inflight=True, require_progress=False
    )
    _ensure_progress_snapshots(plan, completed)
    if completed and not completed[-1]["capacity_after_terminal"]["passed"]:
        raise S9CalibrationError("prior item exhausted safe capacity; resume forbidden")
    limit = len(plan["items"]) if max_items is None else min(
        len(plan["items"]), len(completed) + max_items
    )
    for index in range(len(completed), limit):
        _run_item(plan, plan["items"][index], index)
    report = audit_progress(allow_inflight=False)
    if report["progress"]["complete"] and not COMPLETENESS_PATH.exists():
        completeness = {
            "schema": "v5-final.s9-h2-h4-completeness.v1",
            "plan_digest": plan["plan_digest"],
            "expected_item_count": 36,
            "progress": report["progress"],
            "checks": {
                "all_36_unique_terminals": report["progress"][
                    "completed_terminal_count"
                ]
                == 36,
                "all_post_item_capacity_checks_passed": report["progress"][
                    "all_post_item_capacity_checks_passed"
                ],
                "development_not_authorized": True,
            },
            "authorization": {
                "S10_calibration_integrity_analysis": "AUTHORIZED",
                "development_queue_execution": "NOT_AUTHORIZED",
                "performance_claim": "NOT_AUTHORIZED",
            },
        }
        completeness["completeness_digest"] = _digest(completeness)
        write_json_exclusive(COMPLETENESS_PATH, completeness)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-readiness", action="store_true")
    parser.add_argument("--write-authorization", action="store_true")
    parser.add_argument("--ci-evidence", type=Path)
    parser.add_argument("--ci-audit-output", type=Path)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--max-items", type=int)
    args = parser.parse_args()
    if args.write_readiness:
        artifact = build_readiness()
        S9_DIR.mkdir(parents=True, exist_ok=False)
        write_json_exclusive(READINESS_PATH, artifact)
        print(READINESS_PATH)
        return
    if args.write_authorization:
        if args.ci_evidence is None:
            raise S9CalibrationError("authorization requires exact-CI evidence")
        write_json_exclusive(
            AUTHORIZATION_PATH, build_authorization(_json(args.ci_evidence))
        )
        print(AUTHORIZATION_PATH)
        return
    if args.ci_audit_output is not None:
        write_json_exclusive(args.ci_audit_output, build_ci_audit())
        print(args.ci_audit_output)
        return
    if args.run:
        print(json.dumps(run_calibration(max_items=args.max_items), sort_keys=True))
        return
    print(json.dumps(build_ci_audit(), sort_keys=True))


if __name__ == "__main__":
    main()

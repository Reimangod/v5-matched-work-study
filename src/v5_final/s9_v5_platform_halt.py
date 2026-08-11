"""Audit and freeze the fail-closed S9-v5 runtime-platform halt."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Mapping

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from . import s9_h2_h4_calibration_runner as v1
from . import s9_h2_h4_calibration_runner_v5 as v5
from .s0_successor import ROOT


S9_V5_DIR = ROOT / "artifacts/v5-final/parent-native/s9-h2-h4-calibration-v5"
PLAN_PATH = (
    ROOT
    / "artifacts/v5-final/parent-native/mb6-v4/h2-h4-calibration-plan-v4.json"
)
ENVIRONMENT_PATH = (
    ROOT
    / "artifacts/v5-final/parent-native/mb6-v3/execution-environment-v3.json"
)
HALT_PATH = S9_V5_DIR / "s9-v5-runtime-platform-halt-v1.json"
FAILED_ITEM_KEY = (
    "000-536bd9cab01a1fe9762310e82533b4d30ee88e8a26ea010489af621b740cf402"
)
FAILED_RECEIPT_PATH = S9_V5_DIR / "item-receipts" / f"{FAILED_ITEM_KEY}.json"
FAILED_RESULT_PATH = S9_V5_DIR / "item-results" / f"{FAILED_ITEM_KEY}.json"
FAILED_PROGRESS_PATH = S9_V5_DIR / "progress/001.json"
FAILED_RAW_DIR = S9_V5_DIR / "raw-ledgers" / FAILED_ITEM_KEY
FAILED_KERNEL_EVENT_PATH = FAILED_RAW_DIR / "00000002-kernel-event.json"
FAILED_ROLLBACK_PATH = FAILED_RAW_DIR / "00000003-attempt-rollback.json"
FAILED_TERMINAL_PATH = FAILED_RAW_DIR / "00000004-terminal.json"


class S9V5PlatformHaltError(RuntimeError):
    pass


def _json(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise S9V5PlatformHaltError(f"invalid JSON artifact: {path}") from error
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise S9V5PlatformHaltError(f"noncanonical JSON artifact: {path}")
    return value


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _digest_valid(value: Mapping[str, Any], field: str) -> bool:
    body = dict(value)
    observed = body.pop(field, None)
    return isinstance(observed, str) and observed == _digest(body)


def _git(*arguments: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(ROOT), *arguments], text=True
    ).strip()


def _is_ancestor(commit: str) -> bool:
    return (
        subprocess.run(
            ["git", "-C", str(ROOT), "merge-base", "--is-ancestor", commit, "HEAD"],
            check=False,
        ).returncode
        == 0
    )


def audit_failure_state() -> dict[str, Any]:
    plan = _json(PLAN_PATH)
    environment = _json(ENVIRONMENT_PATH)
    with v5._v5_scope():
        completed = v1._completed_receipts(
            plan, allow_inflight=False, require_progress=True
        )
        reconstructed = v1._progress_snapshot(plan, completed)
    recorded = _json(FAILED_PROGRESS_PATH)
    receipt = _json(FAILED_RECEIPT_PATH)
    result = _json(FAILED_RESULT_PATH)
    kernel_event = _json(FAILED_KERNEL_EVENT_PATH)
    rollback = _json(FAILED_ROLLBACK_PATH)
    terminal = _json(FAILED_TERMINAL_PATH)
    next_dispatches = list((S9_V5_DIR / "dispatch").glob("001-*.json"))
    zero_work = {
        "candidate_generations": 0,
        "energy_evaluations": 0,
        "gradient_component_equivalents": 0,
        "gradient_vector_evaluations": 0,
        "hvp_evaluations": 0,
        "optimizer_iterations": 0,
        "optimizer_starts": 0,
        "resource_recounts": 0,
        "rewrite_verifications": 1,
        "search_states": 0,
        "statevector_recomputations": 0,
    }
    checks = {
        "frozen_plan_exact": len(plan["items"]) == 36
        and plan["plan_digest"]
        == "6f16721fb1156386bfedcc3daf23b75a8b70eb4e4ec6246ef09d078493c3345a",
        "frozen_runtime_exact": environment["runtime"]
        == {
            "byte_order": "little",
            "machine": "arm64",
            "python_implementation": "cpython",
            "python_version": "3.10.19",
            "system": "darwin",
        },
        "exact_one_item_prefix_valid": len(completed) == 1
        and completed[0]["queue_index"] == 0
        and completed[0]["queue_item_id"] == plan["items"][0]["queue_item_id"],
        "recorded_progress_reconstructs_exactly": recorded == reconstructed,
        "incomplete_queue_exact": reconstructed["completed_terminal_count"] == 1
        and reconstructed["expected_item_count"] == 36
        and reconstructed["complete"] is False,
        "terminal_counts_exact": reconstructed["terminal_status_counts"]
        == {
            "ACCEPTED": 0,
            "ALGORITHM_REJECTED": 0,
            "CAP_REJECTED": 0,
            "KERNEL_FAILURE": 1,
        },
        "candidate_energy_zero": reconstructed["candidate_energy_evaluations"] == 0
        and receipt["candidate_energy_evaluations"] == 0,
        "failed_result_exact": result["outcome"]
        == {
            "exception_type": "QueueBoundRuntimeError",
            "performance_evidence": False,
            "queue_item_id": receipt["queue_item_id"],
            "terminal_status": "KERNEL_FAILURE",
        },
        "pre_candidate_work_exact": receipt["work_total"] == zero_work
        and terminal["payload"]["work_total"] == zero_work,
        "platform_preflight_event_exact": kernel_event["kind"] == "kernel-event"
        and kernel_event["payload"]["operation"] == "rewrite-verification"
        and kernel_event["payload"]["outcome"] == "failed"
        and kernel_event["payload"]["evidence"]
        == {
            "exception_type": "ParentNativeExecutionError",
            "original_exception_type": "QueueBoundRuntimeError",
            "phase": "execution-integrity-validation",
        },
        "rollback_and_terminal_exact": rollback["kind"] == "attempt-rollback"
        and rollback["payload"]["reason"] == "QueueBoundRuntimeError"
        and terminal["kind"] == "terminal"
        and terminal["payload"]["terminal_status"] == "KERNEL_FAILURE"
        and terminal["payload"]["rejection_reason"] == "QueueBoundRuntimeError",
        "all_capacity_checks_passed": receipt[
            "capacity_before_resume_or_execution"
        ]["passed"]
        is True
        and receipt["capacity_before_dispatch"]["passed"] is True
        and receipt["capacity_after_terminal"]["passed"] is True,
        "no_next_item_dispatched": next_dispatches == [],
        "development_and_performance_blocked": reconstructed["authorization"][
            "development_queue_execution"
        ]
        == "NOT_AUTHORIZED"
        and reconstructed["authorization"]["performance_claim"]
        == "NOT_AUTHORIZED",
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S9V5PlatformHaltError(
            "S9-v5 platform failure audit failed: " + ", ".join(failures)
        )
    return {
        "checks": checks,
        "plan": plan,
        "environment": environment,
        "progress": reconstructed,
        "receipt": receipt,
        "result": result,
        "kernel_event": kernel_event,
        "rollback": rollback,
        "terminal": terminal,
    }


def _validate_ci_report(
    report_path: Path, *, failure_commit: str
) -> tuple[dict[str, Any], dict[str, bool]]:
    report = _json(report_path)
    progress = report.get("progress", {})
    checks = {
        "validated_failure_commit_exact": report.get("validated_exact_commit")
        == failure_commit,
        "decision_halts_namespace": report.get("decision")
        == "NO_GO_S9_V5_NAMESPACE_HALTED",
        "one_kernel_failure_exact": progress.get("completed_terminal_count") == 1
        and progress.get("terminal_status_counts", {}).get("KERNEL_FAILURE") == 1,
        "candidate_energy_zero": report.get(
            "candidate_molecular_energy_evaluations"
        )
        == 0,
        "namespace_halted": report.get("namespace_halted") is True,
        "checks_passed": all(report.get("checks", {}).values())
        and all(report.get("v5_checks", {}).values()),
        "downstream_blocks_exact": report.get("authorization", {}).get(
            "H2_H4_execution"
        )
        == "NOT_AUTHORIZED"
        and report.get("authorization", {}).get("development_queue_execution")
        == "NOT_AUTHORIZED"
        and report.get("authorization", {}).get("performance_claim")
        == "NOT_AUTHORIZED",
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S9V5PlatformHaltError(
            "S9-v5 exact-CI report failed: " + ", ".join(failures)
        )
    return report, checks


def build_halt(
    ci_report_path: Path, *, run_id: int, job_id: int, run_url: str
) -> dict[str, Any]:
    if _git("status", "--porcelain"):
        raise S9V5PlatformHaltError("halt capture requires a clean worktree")
    if run_id < 1 or job_id < 1 or not run_url.startswith("https://github.com/"):
        raise S9V5PlatformHaltError("invalid external CI identifiers")
    state = audit_failure_state()
    failure_commit = _git(
        "log", "-1", "--format=%H", "--", str(FAILED_RECEIPT_PATH.relative_to(ROOT))
    )
    report, ci_checks = _validate_ci_report(
        ci_report_path, failure_commit=failure_commit
    )
    artifact = {
        "schema": "v5-final.s9-v5-runtime-platform-halt.v1",
        "stage": "S9_V5_FAIL_CLOSED_RUNTIME_PLATFORM_HALT",
        "status": "VERIFIED_PRE_CANDIDATE_RUNTIME_PLATFORM_MISMATCH",
        "decision": "NO_GO_S9_V5_RUNTIME_PLATFORM_PRECONDITION",
        "validated_halt_commit": _git("rev-parse", "HEAD"),
        "observed_failure": {
            "artifact_commit": failure_commit,
            "queue_index": 0,
            "queue_item_id": state["receipt"]["queue_item_id"],
            "terminal_status": "KERNEL_FAILURE",
            "exception_type": "QueueBoundRuntimeError",
            "failure_message": "runtime platform differs from frozen environment",
            "candidate_molecular_energy_evaluations_in_v5": 0,
            "completed_terminal_count": 1,
            "expected_item_count": 36,
            "receipt_path": str(FAILED_RECEIPT_PATH.relative_to(ROOT)),
            "receipt_sha256": _sha(FAILED_RECEIPT_PATH),
            "kernel_event_path": str(FAILED_KERNEL_EVENT_PATH.relative_to(ROOT)),
            "kernel_event_sha256": _sha(FAILED_KERNEL_EVENT_PATH),
            "terminal_path": str(FAILED_TERMINAL_PATH.relative_to(ROOT)),
            "terminal_sha256": _sha(FAILED_TERMINAL_PATH),
        },
        "exact_CI_evidence": {
            "run_id": run_id,
            "job_id": job_id,
            "run_url": run_url,
            "validated_exact_commit": report["validated_exact_commit"],
            "report_sha256": _sha(ci_report_path),
            "checks": ci_checks,
        },
        "checks": state["checks"],
        "scientific_interpretation": {
            "failure_class": "INFRASTRUCTURE_RUNTIME_PLATFORM_MISMATCH",
            "molecular_candidate_energy_evaluated": False,
            "performance_evidence": False,
            "performance_comparison_permitted": False,
            "exclusion_reason": (
                "The namespace failed during execution-integrity validation before its "
                "first candidate energy. The terminal is infrastructure evidence only."
            ),
        },
        "remediation_contract": {
            "preserve_s9_v5_artifacts_byte_for_byte": True,
            "fresh_namespace": "s9-h2-h4-calibration-v6",
            "reuse_exact_plan_digest": state["plan"]["plan_digest"],
            "rerun_all_36_items_from_index_zero": True,
            "uniform_implementation_required": True,
            "required_runtime": state["environment"]["runtime"],
            "required_external_thread_environment": state["environment"][
                "required_threads"
            ],
            "runtime_and_capacity_preflight_before_any_output": True,
            "minimum_available_bytes": 23_890_755_584,
            "every_item_capacity_pre_and_post_check_required": True,
            "any_kernel_failure_permanently_halts_namespace": True,
        },
        "authorization": {
            "S9_v5_further_execution": "NOT_AUTHORIZED",
            "S9_v6_outcome_free_implementation_and_tests": "AUTHORIZED",
            "S9_v6_molecular_execution": "NOT_AUTHORIZED",
            "development_queue_execution": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
    }
    artifact["halt_digest"] = _digest(artifact)
    return artifact


def audit_halt() -> dict[str, bool]:
    state = audit_failure_state()
    artifact = _json(HALT_PATH)
    observed = artifact.get("observed_failure", {})
    contract = artifact.get("remediation_contract", {})
    authorization = artifact.get("authorization", {})
    checks = {
        "halt_digest_valid": _digest_valid(artifact, "halt_digest"),
        "schema_and_decision_exact": artifact.get("schema")
        == "v5-final.s9-v5-runtime-platform-halt.v1"
        and artifact.get("decision")
        == "NO_GO_S9_V5_RUNTIME_PLATFORM_PRECONDITION",
        "captured_failure_checks_passed": all(artifact.get("checks", {}).values()),
        "failure_state_still_exact": all(state["checks"].values()),
        "failure_artifacts_bound": observed.get("receipt_sha256")
        == _sha(FAILED_RECEIPT_PATH)
        and observed.get("kernel_event_sha256")
        == _sha(FAILED_KERNEL_EVENT_PATH)
        and observed.get("terminal_sha256") == _sha(FAILED_TERMINAL_PATH),
        "failure_commit_is_ancestor": _is_ancestor(observed["artifact_commit"]),
        "halt_commit_is_ancestor": _is_ancestor(artifact["validated_halt_commit"]),
        "exact_CI_checks_passed": all(
            artifact.get("exact_CI_evidence", {}).get("checks", {}).values()
        ),
        "fresh_exact_runtime_rerun_required": contract.get("fresh_namespace")
        == "s9-h2-h4-calibration-v6"
        and contract.get("rerun_all_36_items_from_index_zero") is True
        and contract.get("required_runtime") == state["environment"]["runtime"],
        "capacity_contract_preserved": contract.get("minimum_available_bytes")
        == 23_890_755_584
        and contract.get("every_item_capacity_pre_and_post_check_required") is True,
        "v5_and_downstream_blocked": authorization.get("S9_v5_further_execution")
        == "NOT_AUTHORIZED"
        and authorization.get("S9_v6_molecular_execution") == "NOT_AUTHORIZED"
        and authorization.get("development_queue_execution") == "NOT_AUTHORIZED"
        and authorization.get("performance_claim") == "NOT_AUTHORIZED",
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S9V5PlatformHaltError(
            "S9-v5 platform halt audit failed: " + ", ".join(failures)
        )
    return checks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--ci-report", type=Path)
    parser.add_argument("--run-id", type=int)
    parser.add_argument("--job-id", type=int)
    parser.add_argument("--run-url")
    args = parser.parse_args()
    if args.freeze:
        if (
            args.ci_report is None
            or args.run_id is None
            or args.job_id is None
            or args.run_url is None
        ):
            raise S9V5PlatformHaltError(
                "--freeze requires --ci-report, --run-id, --job-id, and --run-url"
            )
        write_json_exclusive(
            HALT_PATH,
            build_halt(
                args.ci_report,
                run_id=args.run_id,
                job_id=args.job_id,
                run_url=args.run_url,
            ),
        )
        print(HALT_PATH)
        return
    if HALT_PATH.exists():
        print(json.dumps(audit_halt(), sort_keys=True))
    else:
        print(json.dumps(audit_failure_state()["checks"], sort_keys=True))


if __name__ == "__main__":
    main()

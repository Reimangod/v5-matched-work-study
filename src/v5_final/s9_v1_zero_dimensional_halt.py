"""Audit and freeze the fail-closed S9-v1 zero-dimensional boundary halt."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Mapping

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .s0_successor import ROOT
from .s9_h2_h4_calibration_runner import (
    audit_authorization,
    audit_readiness,
    build_ci_audit,
)


S9_V1_DIR = ROOT / "artifacts/v5-final/parent-native/s9-h2-h4-calibration-v1"
PLAN_PATH = (
    ROOT
    / "artifacts/v5-final/parent-native/mb6-v4/h2-h4-calibration-plan-v4.json"
)
HALT_PATH = S9_V1_DIR / "s9-v1-zero-dimensional-boundary-halt-v1.json"
FAILED_QUEUE_INDEX = 2
FAILED_ITEM_KEY = (
    "002-8ab221bc079c720edce6012509565b1c343572d8de919c97606a8b065a141281"
)
FAILED_RESULT_PATH = S9_V1_DIR / "item-results" / f"{FAILED_ITEM_KEY}.json"
FAILED_RECEIPT_PATH = S9_V1_DIR / "item-receipts" / f"{FAILED_ITEM_KEY}.json"
FAILED_RAW_DIR = S9_V1_DIR / "raw-ledgers" / FAILED_ITEM_KEY
FAILED_TERMINAL_PATH = FAILED_RAW_DIR / "00000012-terminal.json"
FAILED_ROLLBACK_PATH = FAILED_RAW_DIR / "00000011-attempt-rollback.json"
NEXT_DISPATCH_PREFIX = "003-"


class S9V1HaltError(RuntimeError):
    pass


def _json(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise S9V1HaltError(f"invalid JSON artifact: {path}") from error
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise S9V1HaltError(f"noncanonical JSON artifact: {path}")
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
    """Reconstruct the observed failure without interpreting it as performance."""

    report = build_ci_audit()
    plan = _json(PLAN_PATH)
    result = _json(FAILED_RESULT_PATH)
    receipt = _json(FAILED_RECEIPT_PATH)
    terminal = _json(FAILED_TERMINAL_PATH)
    rollback = _json(FAILED_ROLLBACK_PATH)
    progress = report["progress"]
    next_dispatches = sorted(
        path.name
        for path in (S9_V1_DIR / "dispatch").glob(f"{NEXT_DISPATCH_PREFIX}*.json")
    )
    checks = {
        "v1_readiness_still_valid": all(audit_readiness().values()),
        "v1_authorization_still_valid": all(audit_authorization().values()),
        "frozen_plan_still_exact": report["checks"]["frozen_plan_exact"]
        and plan["plan_digest"] == progress["plan_digest"],
        "exact_three_item_prefix_preserved": progress["completed_terminal_count"]
        == 3
        and progress["expected_item_count"] == 36
        and progress["completed_queue_item_ids"]
        == [item["queue_item_id"] for item in plan["items"][:3]],
        "terminal_counts_exact": progress["terminal_status_counts"]
        == {
            "ACCEPTED": 2,
            "ALGORITHM_REJECTED": 0,
            "CAP_REJECTED": 0,
            "KERNEL_FAILURE": 1,
        },
        "candidate_energy_reconstructed_as_three": report[
            "candidate_molecular_energy_evaluations"
        ]
        == progress["candidate_energy_evaluations"]
        == 3,
        "failed_item_identity_exact": receipt["queue_index"] == FAILED_QUEUE_INDEX
        and receipt["queue_item_id"] == plan["items"][FAILED_QUEUE_INDEX][
            "queue_item_id"
        ]
        and receipt["method_id"] == "structural-magnitude-pruning",
        "failed_item_terminal_exact": receipt["terminal_status"]
        == "KERNEL_FAILURE"
        and result["outcome"]
        == {
            "exception_type": "ParentNativeWorkError",
            "performance_evidence": False,
            "queue_item_id": receipt["queue_item_id"],
            "terminal_status": "KERNEL_FAILURE",
        },
        "rollback_precedes_terminal": rollback["sequence"] == 11
        and rollback["kind"] == "attempt-rollback"
        and terminal["sequence"] == 12
        and terminal["kind"] == "terminal"
        and terminal["payload"]["terminal_status"] == "KERNEL_FAILURE"
        and terminal["payload"]["rejection_reason"] == "ParentNativeWorkError",
        "failed_work_preserved": receipt["candidate_energy_evaluations"] == 1
        and terminal["payload"]["work_total"]["candidate_generations"] == 1
        and terminal["payload"]["work_total"]["energy_evaluations"] == 1
        and terminal["payload"]["work_total"]["optimizer_starts"] == 1,
        "post_terminal_capacity_passed": receipt["capacity_after_terminal"][
            "passed"
        ]
        is True,
        "no_later_item_dispatched": next_dispatches == [],
        "development_and_performance_still_blocked": report["authorization"][
            "development_queue_execution"
        ]
        == "NOT_AUTHORIZED"
        and report["authorization"]["performance_claim"] == "NOT_AUTHORIZED",
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S9V1HaltError(
            "S9-v1 failure-state audit failed: " + ", ".join(failures)
        )
    return {
        "checks": checks,
        "report": report,
        "plan": plan,
        "result": result,
        "receipt": receipt,
        "terminal": terminal,
        "rollback": rollback,
    }


def _validate_exact_ci(
    report_path: Path,
    *,
    run_id: int,
    job_id: int,
    run_url: str,
) -> tuple[dict[str, Any], dict[str, bool]]:
    report = _json(report_path)
    head = _git("rev-parse", "HEAD")
    checks = {
        "validated_commit_exact": report.get("validated_exact_commit") == head,
        "report_schema_exact": report.get("schema")
        == "v5-final.s9-h2-h4-ci-audit.v1",
        "report_status_pass": report.get("status") == "PASS_S9_INTEGRITY",
        "report_checks_passed": all(report.get("checks", {}).values()),
        "authorization_checks_passed": all(
            report.get("authorization_audit", {}).values()
        ),
        "three_terminals_exact": report.get("progress", {}).get(
            "completed_terminal_count"
        )
        == 3,
        "one_kernel_failure_exact": report.get("progress", {}).get(
            "terminal_status_counts", {}
        ).get("KERNEL_FAILURE")
        == 1,
        "candidate_energy_exact": report.get(
            "candidate_molecular_energy_evaluations"
        )
        == 3,
        "external_identifiers_positive": isinstance(run_id, int)
        and run_id > 0
        and isinstance(job_id, int)
        and job_id > 0,
        "run_url_https": run_url.startswith("https://github.com/"),
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S9V1HaltError("exact-CI evidence failed: " + ", ".join(failures))
    return report, checks


def build_halt(
    ci_report_path: Path,
    *,
    run_id: int,
    job_id: int,
    run_url: str,
) -> dict[str, Any]:
    if _git("status", "--porcelain"):
        raise S9V1HaltError("halt capture requires a clean worktree")
    state = audit_failure_state()
    ci_report, ci_checks = _validate_exact_ci(
        ci_report_path, run_id=run_id, job_id=job_id, run_url=run_url
    )
    failure_commit = _git(
        "log", "-1", "--format=%H", "--", str(FAILED_RESULT_PATH.relative_to(ROOT))
    )
    artifact = {
        "schema": "v5-final.s9-v1-zero-dimensional-boundary-halt.v1",
        "stage": "S9_V1_FAIL_CLOSED_HALT",
        "status": "VERIFIED_INFRASTRUCTURE_KERNEL_FAILURE",
        "decision": "NO_GO_S9_V1_ZERO_DIMENSIONAL_OPTIMIZER_BOUNDARY",
        "validated_halt_commit": _git("rev-parse", "HEAD"),
        "observed_failure": {
            "artifact_commit": failure_commit,
            "queue_index": FAILED_QUEUE_INDEX,
            "queue_item_id": state["receipt"]["queue_item_id"],
            "case_id": state["receipt"]["case_id"],
            "method_id": state["receipt"]["method_id"],
            "terminal_status": "KERNEL_FAILURE",
            "exception_type": "ParentNativeWorkError",
            "candidate_molecular_energy_evaluations_in_v1": 3,
            "completed_terminal_count": 3,
            "expected_item_count": 36,
            "result_path": str(FAILED_RESULT_PATH.relative_to(ROOT)),
            "result_sha256": _sha(FAILED_RESULT_PATH),
            "receipt_path": str(FAILED_RECEIPT_PATH.relative_to(ROOT)),
            "receipt_sha256": _sha(FAILED_RECEIPT_PATH),
            "raw_terminal_path": str(FAILED_TERMINAL_PATH.relative_to(ROOT)),
            "raw_terminal_sha256": _sha(FAILED_TERMINAL_PATH),
        },
        "exact_CI_evidence": {
            "run_id": run_id,
            "job_id": job_id,
            "run_url": run_url,
            "validated_exact_commit": ci_report["validated_exact_commit"],
            "report_sha256": _sha(ci_report_path),
            "checks": ci_checks,
        },
        "checks": state["checks"],
        "scientific_interpretation": {
            "failure_class": "INFRASTRUCTURE_METHOD_NATIVE_BOUNDARY_MISMATCH",
            "performance_evidence": False,
            "performance_comparison_permitted": False,
            "exclusion_reason": (
                "The run stopped before a complete, implementation-uniform 36-item "
                "calibration existed. The three v1 terminals are integrity evidence only."
            ),
            "outcome_use_restriction": (
                "Observed energies and acceptance outcomes must not alter the frozen plan, "
                "order, work caps, ranking, or acceptance policy."
            ),
        },
        "remediation_contract": {
            "preserve_s9_v1_artifacts_byte_for_byte": True,
            "fresh_namespace": "s9-h2-h4-calibration-v2",
            "reuse_exact_plan_digest": state["plan"]["plan_digest"],
            "rerun_all_36_items_from_index_zero": True,
            "uniform_implementation_required": True,
            "zero_dimensional_target_semantics": {
                "trigger": "target parameter dimension equals zero",
                "optimizer_starts": 1,
                "candidate_energy_evaluations": 1,
                "full_gradient_evaluations": 0,
                "optimizer_iterations": 0,
                "result_shape": "x=(), jac=(), inverse_hessian=(0,0)",
                "acceptance_policy": "UNCHANGED_FROZEN_POLICY",
            },
        },
        "authorization": {
            "S9_v1_further_execution": "NOT_AUTHORIZED",
            "S9_v2_outcome_free_implementation_and_tests": "AUTHORIZED",
            "S9_v2_molecular_execution": "NOT_AUTHORIZED",
            "development_queue_execution": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
    }
    artifact["halt_digest"] = _digest(artifact)
    return artifact


def audit_halt() -> dict[str, bool]:
    state = audit_failure_state()
    artifact = _json(HALT_PATH)
    checks = {
        "halt_digest_valid": _digest_valid(artifact, "halt_digest"),
        "schema_and_decision_exact": artifact.get("schema")
        == "v5-final.s9-v1-zero-dimensional-boundary-halt.v1"
        and artifact.get("decision")
        == "NO_GO_S9_V1_ZERO_DIMENSIONAL_OPTIMIZER_BOUNDARY",
        "captured_failure_checks_passed": all(artifact.get("checks", {}).values()),
        "failure_state_still_exact": all(state["checks"].values()),
        "failure_artifacts_bound": artifact["observed_failure"]["result_sha256"]
        == _sha(FAILED_RESULT_PATH)
        and artifact["observed_failure"]["receipt_sha256"]
        == _sha(FAILED_RECEIPT_PATH)
        and artifact["observed_failure"]["raw_terminal_sha256"]
        == _sha(FAILED_TERMINAL_PATH),
        "failure_commit_is_ancestor": _is_ancestor(
            artifact["observed_failure"]["artifact_commit"]
        ),
        "halt_commit_is_ancestor": _is_ancestor(artifact["validated_halt_commit"]),
        "exact_CI_checks_passed": all(
            artifact["exact_CI_evidence"]["checks"].values()
        ),
        "fresh_uniform_rerun_required": artifact["remediation_contract"][
            "rerun_all_36_items_from_index_zero"
        ]
        is True
        and artifact["remediation_contract"]["uniform_implementation_required"]
        is True,
        "v1_and_downstream_execution_blocked": artifact["authorization"][
            "S9_v1_further_execution"
        ]
        == "NOT_AUTHORIZED"
        and artifact["authorization"]["S9_v2_molecular_execution"]
        == "NOT_AUTHORIZED"
        and artifact["authorization"]["development_queue_execution"]
        == "NOT_AUTHORIZED"
        and artifact["authorization"]["performance_claim"] == "NOT_AUTHORIZED",
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S9V1HaltError("S9-v1 halt audit failed: " + ", ".join(failures))
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
            raise S9V1HaltError(
                "--freeze requires --ci-report, --run-id, --job-id, and --run-url"
            )
        artifact = build_halt(
            args.ci_report,
            run_id=args.run_id,
            job_id=args.job_id,
            run_url=args.run_url,
        )
        write_json_exclusive(HALT_PATH, artifact)
        print(json.dumps(artifact, sort_keys=True))
        return
    if HALT_PATH.exists():
        print(json.dumps({"checks": audit_halt()}, sort_keys=True))
    else:
        state = audit_failure_state()
        print(json.dumps({"checks": state["checks"]}, sort_keys=True))


if __name__ == "__main__":
    main()

"""Audit and freeze the fail-closed S9-v3 post-terminal capacity halt."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Mapping

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from . import s9_h2_h4_calibration_runner as v1
from . import s9_h2_h4_calibration_runner_v3 as v3
from .s0_successor import ROOT


S9_V3_DIR = ROOT / "artifacts/v5-final/parent-native/s9-h2-h4-calibration-v3"
PLAN_PATH = (
    ROOT
    / "artifacts/v5-final/parent-native/mb6-v4/h2-h4-calibration-plan-v4.json"
)
HALT_PATH = S9_V3_DIR / "s9-v3-post-terminal-capacity-halt-v1.json"
FAILED_QUEUE_INDEX = 22
COMPLETED_TERMINAL_COUNT = 23
FAILED_ITEM_KEY = (
    "022-5d5cbe453079f38c2587cf5e6be1682f7f118b332b318490f209e17c45916a93"
)
FAILED_RECEIPT_PATH = S9_V3_DIR / "item-receipts" / f"{FAILED_ITEM_KEY}.json"
FAILED_PROGRESS_PATH = S9_V3_DIR / "progress/023.json"
NEXT_DISPATCH_PREFIX = "023-"


class S9V3CapacityHaltError(RuntimeError):
    pass


def _json(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise S9V3CapacityHaltError(f"invalid JSON artifact: {path}") from error
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise S9V3CapacityHaltError(f"noncanonical JSON artifact: {path}")
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
    """Reconstruct the v3 capacity halt without consulting current free space."""

    plan = _json(PLAN_PATH)
    with v3._v3_scope():
        completed = v1._completed_receipts(
            plan, allow_inflight=False, require_progress=True
        )
        reconstructed = v1._progress_snapshot(plan, completed)
    recorded = _json(FAILED_PROGRESS_PATH)
    receipt = _json(FAILED_RECEIPT_PATH)
    prior = completed[:-1]
    next_dispatches = sorted(
        path.name
        for path in (S9_V3_DIR / "dispatch").glob(f"{NEXT_DISPATCH_PREFIX}*.json")
    )
    before_resume = receipt["capacity_before_resume_or_execution"]
    before_dispatch = receipt["capacity_before_dispatch"]
    after_terminal = receipt["capacity_after_terminal"]
    checks = {
        "frozen_plan_exact": len(plan["items"]) == 36
        and plan["plan_digest"]
        == "6f16721fb1156386bfedcc3daf23b75a8b70eb4e4ec6246ef09d078493c3345a",
        "exact_23_item_prefix_valid": len(completed) == COMPLETED_TERMINAL_COUNT
        and [value["queue_index"] for value in completed]
        == list(range(COMPLETED_TERMINAL_COUNT)),
        "recorded_progress_reconstructs_exactly": recorded == reconstructed,
        "incomplete_queue_exact": reconstructed["expected_item_count"] == 36
        and reconstructed["completed_terminal_count"] == COMPLETED_TERMINAL_COUNT
        and reconstructed["complete"] is False,
        "terminal_counts_exact": reconstructed["terminal_status_counts"]
        == {
            "ACCEPTED": 8,
            "ALGORITHM_REJECTED": 15,
            "CAP_REJECTED": 0,
            "KERNEL_FAILURE": 0,
        },
        "candidate_energy_reconstructed_exact": reconstructed[
            "candidate_energy_evaluations"
        ]
        == 40,
        "failed_item_identity_exact": receipt["queue_index"] == FAILED_QUEUE_INDEX
        and receipt["queue_item_id"]
        == plan["items"][FAILED_QUEUE_INDEX]["queue_item_id"]
        and receipt["terminal_status"] == "ALGORITHM_REJECTED",
        "capacity_passed_before_item": before_resume["passed"] is True
        and before_dispatch["passed"] is True,
        "capacity_failed_after_terminal": after_terminal["passed"] is False
        and after_terminal["filesystem_available_bytes"]
        < after_terminal["execution_threshold_bytes"],
        "capacity_contract_unchanged": before_resume["execution_threshold_bytes"]
        == before_dispatch["execution_threshold_bytes"]
        == after_terminal["execution_threshold_bytes"]
        == 23_890_755_584
        and after_terminal["required_study_bytes"] == 18_522_046_464
        and after_terminal["mandatory_reserve_bytes"] == 5_368_709_120,
        "all_prior_post_terminal_capacity_checks_passed": all(
            value["capacity_after_terminal"]["passed"] is True for value in prior
        ),
        "aggregate_post_terminal_capacity_check_failed": reconstructed[
            "all_post_item_capacity_checks_passed"
        ]
        is False,
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
        raise S9V3CapacityHaltError(
            "S9-v3 capacity failure-state audit failed: " + ", ".join(failures)
        )
    return {
        "checks": checks,
        "plan": plan,
        "completed": completed,
        "progress": reconstructed,
        "receipt": receipt,
    }


def _validate_exact_ci(
    report_path: Path,
    *,
    failure_commit: str,
    run_id: int,
    job_id: int,
    run_url: str,
) -> tuple[dict[str, Any], dict[str, bool]]:
    report = _json(report_path)
    progress = report.get("progress", {})
    checks = {
        "validated_failure_commit_exact": report.get("validated_exact_commit")
        == failure_commit,
        "report_schema_exact": report.get("schema")
        == "v5-final.s9-h2-h4-ci-audit.v1",
        "report_status_pass": report.get("status") == "PASS_S9_INTEGRITY",
        "report_checks_passed": all(report.get("checks", {}).values()),
        "v3_checks_passed": all(report.get("v3_checks", {}).values()),
        "exact_incomplete_prefix": progress.get("completed_terminal_count")
        == COMPLETED_TERMINAL_COUNT
        and progress.get("expected_item_count") == 36
        and progress.get("complete") is False,
        "post_terminal_capacity_failure_exact": progress.get(
            "all_post_item_capacity_checks_passed"
        )
        is False,
        "terminal_counts_exact": progress.get("terminal_status_counts")
        == {
            "ACCEPTED": 8,
            "ALGORITHM_REJECTED": 15,
            "CAP_REJECTED": 0,
            "KERNEL_FAILURE": 0,
        },
        "candidate_energy_exact": report.get(
            "candidate_molecular_energy_evaluations"
        )
        == 40,
        "downstream_blocks_exact": report.get("authorization", {}).get(
            "development_queue_execution"
        )
        == "NOT_AUTHORIZED"
        and report.get("authorization", {}).get("performance_claim")
        == "NOT_AUTHORIZED",
        "external_identifiers_positive": isinstance(run_id, int)
        and run_id > 0
        and isinstance(job_id, int)
        and job_id > 0,
        "run_url_https": run_url.startswith("https://github.com/"),
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S9V3CapacityHaltError(
            "exact-CI evidence failed: " + ", ".join(failures)
        )
    return report, checks


def build_halt(
    ci_report_path: Path,
    *,
    run_id: int,
    job_id: int,
    run_url: str,
) -> dict[str, Any]:
    if _git("status", "--porcelain"):
        raise S9V3CapacityHaltError("halt capture requires a clean worktree")
    state = audit_failure_state()
    failure_commit = _git(
        "log", "-1", "--format=%H", "--", str(FAILED_RECEIPT_PATH.relative_to(ROOT))
    )
    ci_report, ci_checks = _validate_exact_ci(
        ci_report_path,
        failure_commit=failure_commit,
        run_id=run_id,
        job_id=job_id,
        run_url=run_url,
    )
    receipt = state["receipt"]
    artifact = {
        "schema": "v5-final.s9-v3-post-terminal-capacity-halt.v1",
        "stage": "S9_V3_FAIL_CLOSED_CAPACITY_HALT",
        "status": "VERIFIED_POST_TERMINAL_CAPACITY_PRECONDITION_FAILURE",
        "decision": "NO_GO_S9_V3_POST_TERMINAL_CAPACITY_PRECONDITION",
        "validated_halt_commit": _git("rev-parse", "HEAD"),
        "observed_failure": {
            "artifact_commit": failure_commit,
            "queue_index": FAILED_QUEUE_INDEX,
            "queue_item_id": receipt["queue_item_id"],
            "case_id": receipt["case_id"],
            "method_id": receipt["method_id"],
            "terminal_status": receipt["terminal_status"],
            "candidate_molecular_energy_evaluations_in_v3": state["progress"][
                "candidate_energy_evaluations"
            ],
            "completed_terminal_count": COMPLETED_TERMINAL_COUNT,
            "expected_item_count": 36,
            "all_post_item_capacity_checks_passed": False,
            "receipt_path": str(FAILED_RECEIPT_PATH.relative_to(ROOT)),
            "receipt_sha256": _sha(FAILED_RECEIPT_PATH),
            "progress_path": str(FAILED_PROGRESS_PATH.relative_to(ROOT)),
            "progress_sha256": _sha(FAILED_PROGRESS_PATH),
            "capacity_before_resume_or_execution": receipt[
                "capacity_before_resume_or_execution"
            ],
            "capacity_before_dispatch": receipt["capacity_before_dispatch"],
            "capacity_after_terminal": receipt["capacity_after_terminal"],
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
            "failure_class": "INFRASTRUCTURE_POST_TERMINAL_CAPACITY_PRECONDITION",
            "molecular_candidate_energy_evaluations_observed": 40,
            "uniform_36_item_calibration_complete": False,
            "performance_evidence": False,
            "performance_comparison_permitted": False,
            "exclusion_reason": (
                "The frozen calibration stopped after 23 of 36 terminals. Its partial "
                "outcomes cannot support calibration selection or method comparison."
            ),
            "outcome_use_restriction": (
                "The partial outcomes cannot alter the frozen plan, order, work caps, "
                "methods, ranking, acceptance policy, or the v4 remediation design."
            ),
        },
        "remediation_contract": {
            "preserve_s9_v3_artifacts_byte_for_byte": True,
            "fresh_namespace": "s9-h2-h4-calibration-v4",
            "reuse_exact_plan_digest": state["plan"]["plan_digest"],
            "rerun_all_36_items_from_index_zero": True,
            "uniform_implementation_required": True,
            "required_external_thread_environment": {
                "MKL_NUM_THREADS": "2",
                "OMP_NUM_THREADS": "2",
                "OPENBLAS_NUM_THREADS": "2",
            },
            "environment_preflight_before_any_output_publication": True,
            "current_capacity_preflight_before_any_output_publication": True,
            "every_item_capacity_pre_and_post_check_required": True,
            "any_kernel_failure_permanently_halts_namespace": True,
            "any_failed_post_terminal_capacity_check_permanently_halts_namespace": True,
        },
        "authorization": {
            "S9_v3_further_execution": "NOT_AUTHORIZED",
            "S9_v4_outcome_free_implementation_and_tests": "AUTHORIZED",
            "S9_v4_molecular_execution": "NOT_AUTHORIZED",
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
        == "v5-final.s9-v3-post-terminal-capacity-halt.v1"
        and artifact.get("decision")
        == "NO_GO_S9_V3_POST_TERMINAL_CAPACITY_PRECONDITION",
        "captured_failure_checks_passed": all(artifact.get("checks", {}).values()),
        "failure_state_still_exact": all(state["checks"].values()),
        "failure_artifacts_bound": observed.get("receipt_sha256")
        == _sha(FAILED_RECEIPT_PATH)
        and observed.get("progress_sha256") == _sha(FAILED_PROGRESS_PATH),
        "failure_commit_is_ancestor": _is_ancestor(observed["artifact_commit"]),
        "halt_commit_is_ancestor": _is_ancestor(artifact["validated_halt_commit"]),
        "exact_CI_checks_passed": all(
            artifact.get("exact_CI_evidence", {}).get("checks", {}).values()
        ),
        "fresh_uniform_rerun_required": contract.get(
            "rerun_all_36_items_from_index_zero"
        )
        is True
        and contract.get("uniform_implementation_required") is True
        and contract.get("reuse_exact_plan_digest")
        == state["plan"]["plan_digest"],
        "capacity_fail_closed_contract_exact": contract.get(
            "current_capacity_preflight_before_any_output_publication"
        )
        is True
        and contract.get("every_item_capacity_pre_and_post_check_required") is True
        and contract.get(
            "any_failed_post_terminal_capacity_check_permanently_halts_namespace"
        )
        is True,
        "v3_and_downstream_execution_blocked": authorization.get(
            "S9_v3_further_execution"
        )
        == "NOT_AUTHORIZED"
        and authorization.get("S9_v4_molecular_execution") == "NOT_AUTHORIZED"
        and authorization.get("development_queue_execution") == "NOT_AUTHORIZED"
        and authorization.get("performance_claim") == "NOT_AUTHORIZED",
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S9V3CapacityHaltError(
            "S9-v3 capacity halt audit failed: " + ", ".join(failures)
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
            raise S9V3CapacityHaltError(
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
        print(json.dumps(audit_halt(), sort_keys=True))
    else:
        print(json.dumps(audit_failure_state()["checks"], sort_keys=True))


if __name__ == "__main__":
    main()

"""Audit and freeze the outcome-free S9-v4 preauthorization halt."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Mapping

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .s0_successor import ROOT


S9_V4_DIR = ROOT / "artifacts/v5-final/parent-native/s9-h2-h4-calibration-v4"
READINESS_PATH = S9_V4_DIR / "s9-runner-readiness-v4.json"
AUTHORIZATION_PATH = S9_V4_DIR / "s9-execution-authorization-v4.json"
HALT_PATH = S9_V4_DIR / "s9-v4-preauthorization-halt-v1.json"
PLAN_PATH = (
    ROOT
    / "artifacts/v5-final/parent-native/mb6-v4/h2-h4-calibration-plan-v4.json"
)
V4_WORKFLOW_PATH = ".github/workflows/v5-s9-v4-github-runner-gate.yml"
BASE_RUNNER_PATH = "src/v5_final/s9_h2_h4_calibration_runner.py"


class S9V4PreauthorizationHaltError(RuntimeError):
    pass


def _json(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise S9V4PreauthorizationHaltError(
            f"invalid JSON artifact: {path}"
        ) from error
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise S9V4PreauthorizationHaltError(f"noncanonical JSON artifact: {path}")
    return value


def _sha_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _sha(path: Path) -> str:
    return _sha_bytes(path.read_bytes())


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _digest_valid(value: Mapping[str, Any], field: str) -> bool:
    body = dict(value)
    observed = body.pop(field, None)
    return isinstance(observed, str) and observed == _digest(body)


def _git_text(*arguments: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(ROOT), *arguments], text=True
    ).strip()


def _git_bytes(*arguments: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(ROOT), *arguments])


def _is_ancestor(commit: str) -> bool:
    return (
        subprocess.run(
            ["git", "-C", str(ROOT), "merge-base", "--is-ancestor", commit, "HEAD"],
            check=False,
        ).returncode
        == 0
    )


def audit_failure_state() -> dict[str, Any]:
    """Reconstruct the v4 evidence-schema failure from frozen Git blobs."""

    readiness = _json(READINESS_PATH)
    plan = _json(PLAN_PATH)
    readiness_commit = readiness["validated_runner_commit"]
    source_manifest = readiness["runner_source_manifest"]
    historical_source_hashes = {
        entry["path"]: _sha_bytes(
            _git_bytes("show", f"{readiness_commit}:{entry['path']}")
        )
        for entry in source_manifest
    }
    workflow = _git_bytes("show", f"{readiness_commit}:{V4_WORKFLOW_PATH}").decode()
    base_runner = _git_bytes(
        "show", f"{readiness_commit}:{BASE_RUNNER_PATH}"
    ).decode()
    output_paths = [
        S9_V4_DIR / name
        for name in ("dispatch", "raw-ledgers", "item-results", "item-receipts", "progress")
    ]
    checks = {
        "readiness_digest_valid": _digest_valid(readiness, "readiness_digest"),
        "readiness_status_exact": readiness.get("status")
        == "PASS_OUTCOME_FREE_RUNNER_READY"
        and readiness.get("decision")
        == "READY_AWAITING_EXACT_CI_FOR_S9_EXECUTION_AUTHORIZATION",
        "readiness_candidate_zero": readiness.get(
            "candidate_molecular_energy_evaluations"
        )
        == 0,
        "readiness_did_not_authorize_execution": readiness.get(
            "authorization", {}
        ).get("H2_H4_execution")
        == "NOT_AUTHORIZED_BY_READINESS_ALONE",
        "readiness_checks_passed": all(readiness.get("checks", {}).values())
        and all(readiness.get("venue_preflight", {}).values()),
        "readiness_commit_is_ancestor": _is_ancestor(readiness_commit),
        "historical_runner_sources_exact": all(
            historical_source_hashes.get(entry["path"]) == entry["sha256"]
            for entry in source_manifest
        ),
        "frozen_plan_exact": readiness["plan"]["plan_digest"]
        == plan["plan_digest"]
        == "6f16721fb1156386bfedcc3daf23b75a8b70eb4e4ec6246ef09d078493c3345a",
        "authorization_absent": not AUTHORIZATION_PATH.exists(),
        "molecular_outputs_absent": not any(path.exists() for path in output_paths),
        "workflow_passed_wrong_evidence_schema": (
            '--ci-evidence "$RUNNER_TEMP/s9-v4-release-gate-report.json"'
            in workflow
            and "v5-final.s9-h2-h4-ci-audit.v1" in base_runner
            and "v5-final.external-s9-readiness-exact-ci-evidence.v1" in base_runner
        ),
        "development_and_performance_blocked": readiness["authorization"][
            "development_queue_execution"
        ]
        == "NOT_AUTHORIZED"
        and readiness["authorization"]["performance_claim"] == "NOT_AUTHORIZED",
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S9V4PreauthorizationHaltError(
            "S9-v4 preauthorization failure audit failed: " + ", ".join(failures)
        )
    return {
        "checks": checks,
        "readiness": readiness,
        "plan": plan,
        "readiness_commit": readiness_commit,
        "historical_source_hashes": historical_source_hashes,
    }


def build_halt(*, run_id: int, job_id: int, run_url: str) -> dict[str, Any]:
    if _git_text("status", "--porcelain"):
        raise S9V4PreauthorizationHaltError(
            "halt capture requires a clean worktree"
        )
    if run_id < 1 or job_id < 1 or not run_url.startswith("https://github.com/"):
        raise S9V4PreauthorizationHaltError("invalid external CI identifiers")
    state = audit_failure_state()
    artifact = {
        "schema": "v5-final.s9-v4-preauthorization-halt.v1",
        "stage": "S9_V4_FAIL_CLOSED_PREAUTHORIZATION_HALT",
        "status": "VERIFIED_READINESS_CI_EVIDENCE_SCHEMA_MISMATCH",
        "decision": "NO_GO_S9_V4_PREAUTHORIZATION_EVIDENCE_SCHEMA",
        "validated_halt_commit": _git_text("rev-parse", "HEAD"),
        "observed_failure": {
            "readiness_commit": state["readiness_commit"],
            "readiness_path": str(READINESS_PATH.relative_to(ROOT)),
            "readiness_sha256": _sha(READINESS_PATH),
            "readiness_digest": state["readiness"]["readiness_digest"],
            "candidate_molecular_energy_evaluations_in_v4": 0,
            "completed_terminal_count": 0,
            "expected_item_count": 36,
            "authorization_artifact_created": False,
            "failure_message": (
                "S9 authorization failed: readiness_exact_CI_passed"
            ),
            "failure_mechanism": (
                "The v4 workflow supplied the ordinary S9 CI audit report where the "
                "authorization builder required the dedicated external readiness-CI "
                "evidence schema."
            ),
        },
        "exact_CI_evidence": {
            "run_id": run_id,
            "job_id": job_id,
            "run_url": run_url,
            "head_sha": _git_text("rev-parse", "HEAD"),
            "boundary_audit_step_conclusion": "success",
            "proposal_step_conclusion": "failure",
            "job_conclusion": "failure",
        },
        "checks": state["checks"],
        "scientific_interpretation": {
            "failure_class": "INFRASTRUCTURE_PREAUTHORIZATION_EVIDENCE_SCHEMA",
            "molecular_candidate_energy_evaluated": False,
            "uniform_36_item_calibration_started": False,
            "performance_evidence": False,
            "performance_comparison_permitted": False,
            "outcome_use_restriction": (
                "No v4 molecular outcome exists. Historical v1-v3 outcomes cannot "
                "alter the fresh remediation design, plan, order, methods, or caps."
            ),
        },
        "remediation_contract": {
            "preserve_s9_v4_readiness_byte_for_byte": True,
            "fresh_namespace": "s9-h2-h4-calibration-v5",
            "reuse_exact_plan_digest": state["plan"]["plan_digest"],
            "rerun_all_36_items_from_index_zero": True,
            "uniform_implementation_required": True,
            "dedicated_external_readiness_CI_evidence_schema_required": True,
            "authorization_must_be_built_only_after_exact_gate_success": True,
            "molecular_execution_requires_separate_frozen_authorization": True,
            "github_single_job_execution_venue_required": True,
        },
        "authorization": {
            "S9_v4_further_execution": "NOT_AUTHORIZED",
            "S9_v5_outcome_free_implementation_and_tests": "AUTHORIZED",
            "S9_v5_molecular_execution": "NOT_AUTHORIZED",
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
        == "v5-final.s9-v4-preauthorization-halt.v1"
        and artifact.get("decision")
        == "NO_GO_S9_V4_PREAUTHORIZATION_EVIDENCE_SCHEMA",
        "captured_failure_checks_passed": all(artifact.get("checks", {}).values()),
        "failure_state_still_exact": all(state["checks"].values()),
        "readiness_bound_exactly": observed.get("readiness_sha256")
        == _sha(READINESS_PATH)
        and observed.get("readiness_digest")
        == state["readiness"]["readiness_digest"],
        "halt_commit_is_ancestor": _is_ancestor(artifact["validated_halt_commit"]),
        "fresh_uniform_v5_required": contract.get("fresh_namespace")
        == "s9-h2-h4-calibration-v5"
        and contract.get("rerun_all_36_items_from_index_zero") is True
        and contract.get("uniform_implementation_required") is True,
        "evidence_handoff_remediated": contract.get(
            "dedicated_external_readiness_CI_evidence_schema_required"
        )
        is True
        and contract.get(
            "authorization_must_be_built_only_after_exact_gate_success"
        )
        is True,
        "v4_and_downstream_blocked": authorization.get("S9_v4_further_execution")
        == "NOT_AUTHORIZED"
        and authorization.get("S9_v5_molecular_execution") == "NOT_AUTHORIZED"
        and authorization.get("development_queue_execution") == "NOT_AUTHORIZED"
        and authorization.get("performance_claim") == "NOT_AUTHORIZED",
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S9V4PreauthorizationHaltError(
            "S9-v4 preauthorization halt audit failed: " + ", ".join(failures)
        )
    return checks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--run-id", type=int)
    parser.add_argument("--job-id", type=int)
    parser.add_argument("--run-url")
    args = parser.parse_args()
    if args.freeze:
        if args.run_id is None or args.job_id is None or args.run_url is None:
            raise S9V4PreauthorizationHaltError(
                "--freeze requires --run-id, --job-id, and --run-url"
            )
        write_json_exclusive(
            HALT_PATH,
            build_halt(
                run_id=args.run_id, job_id=args.job_id, run_url=args.run_url
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

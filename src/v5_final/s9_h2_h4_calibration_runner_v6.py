"""S9-v6 local Darwin/arm64 execution with static external-CI attestation.

GitHub-hosted runners cannot satisfy the frozen Darwin/arm64 runtime and disk
contract.  This namespace therefore separates an outcome-free, platform-neutral
static CI audit from a fail-closed local execution preflight.  No molecular
output is created by readiness or authorization capture.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import threading
from typing import Any, Iterator, Mapping

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from . import s9_h2_h4_calibration_runner as v1
from .parent_native_zero_dimensional_v2 import execute_frozen_item_v2
from .s0_successor import ROOT
from .s9_v5_platform_halt import HALT_PATH, audit_halt


S9_V6_DIR = ROOT / "artifacts/v5-final/parent-native/s9-h2-h4-calibration-v6"
READINESS_PATH = S9_V6_DIR / "s9-runner-readiness-v6.json"
AUTHORIZATION_PATH = S9_V6_DIR / "s9-execution-authorization-v6.json"
DISPATCH_DIR = S9_V6_DIR / "dispatch"
RAW_DIR = S9_V6_DIR / "raw-ledgers"
RESULT_DIR = S9_V6_DIR / "item-results"
RECEIPT_DIR = S9_V6_DIR / "item-receipts"
PROGRESS_DIR = S9_V6_DIR / "progress"
COMPLETENESS_PATH = S9_V6_DIR / "h2-h4-completeness-v6.json"
RUN_NAMESPACE = "s9-h2-h4-calibration-v6"
EXECUTION_VENUE = "repository-owner-local-darwin-arm64-single-process"
ENVIRONMENT_PATH = (
    ROOT
    / "artifacts/v5-final/parent-native/mb6-v3/execution-environment-v3.json"
)
OWNER_FREEZE_PATH = (
    ROOT / "artifacts/v5-final/method-native/mb4-2-owner-protocol-freeze-v1.json"
)
OWNER = "Reimangod"
OWNER_CONTINUATION_DIRECTIVE = (
    "終わるまで続けて行って。常に学術的な価値を保てているかとシステム"
    "エンジニアリング的な安全性が保ててるかを確認しながら進めて。続けて。"
)
RUNNER_SOURCES = tuple(
    ROOT / value
    for value in (
        "src/v5_final/s9_h2_h4_calibration_runner_v6.py",
        "src/v5_final/parent_native_zero_dimensional_v2.py",
        "src/v5_final/s9_v5_platform_halt.py",
        "src/v5_final/s9_h2_h4_calibration_runner.py",
        "src/v5_final/parent_native_execution_services.py",
        "src/v5_final/parent_native_persistent_runner.py",
        "src/v5_final/parent_native_work_accounting.py",
        "src/v5_final/semantic_contract_v2.py",
        "tests/test_v5_final_s9_h2_h4_calibration_runner_v6.py",
        ".github/workflows/v5-s9-v6-local-darwin-gate.yml",
    )
)


class S9V6CalibrationError(v1.S9CalibrationError):
    pass


def _json(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise S9V6CalibrationError(f"invalid JSON artifact: {path}") from error
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise S9V6CalibrationError(f"noncanonical JSON artifact: {path}")
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


def _halt() -> dict[str, Any]:
    checks = audit_halt()
    if not all(checks.values()):
        raise S9V6CalibrationError("S9-v5 runtime-platform halt is not valid")
    return _json(HALT_PATH)


def _environment_contract() -> tuple[dict[str, str], dict[str, str]]:
    environment = _json(ENVIRONMENT_PATH)
    halt = _halt()
    runtime = dict(environment["runtime"])
    threads = dict(environment["required_threads"])
    expected_runtime = {
        "byte_order": "little",
        "machine": "arm64",
        "python_implementation": "cpython",
        "python_version": "3.10.19",
        "system": "darwin",
    }
    expected_threads = {
        "MKL_NUM_THREADS": "2",
        "OMP_NUM_THREADS": "2",
        "OPENBLAS_NUM_THREADS": "2",
    }
    contract = halt["remediation_contract"]
    if (
        runtime != expected_runtime
        or threads != expected_threads
        or contract["required_runtime"] != runtime
        or contract["required_external_thread_environment"] != threads
        or contract["fresh_namespace"] != RUN_NAMESPACE
        or contract["minimum_available_bytes"] != v1.THRESHOLD_BYTES
    ):
        raise S9V6CalibrationError("frozen v6 environment contract is not exact")
    return runtime, threads


def _runtime_observation() -> dict[str, str]:
    return {
        "byte_order": sys.byteorder,
        "machine": platform.machine().lower(),
        "python_implementation": platform.python_implementation().lower(),
        "python_version": platform.python_version(),
        "system": platform.system().lower(),
    }


def observe_local_preflight() -> dict[str, Any]:
    runtime, threads = _environment_contract()
    observed_runtime = _runtime_observation()
    observed_threads = {name: os.environ.get(name) for name in threads}
    capacity = v1._current_capacity()
    checks = {
        "runtime_exact": observed_runtime == runtime,
        "thread_environment_exact": observed_threads == threads,
        "capacity_with_mandatory_reserve_passed": capacity["passed"] is True,
        "execution_threshold_exact": capacity["execution_threshold_bytes"]
        == 23_890_755_584,
        "single_process_local_venue_exact": os.environ.get(
            "V5_S9_V6_EXECUTION_VENUE"
        )
        == EXECUTION_VENUE,
    }
    return {
        "required_runtime": runtime,
        "observed_runtime": observed_runtime,
        "required_threads": threads,
        "observed_threads": observed_threads,
        "capacity": capacity,
        "checks": checks,
    }


def _require_local_preflight() -> dict[str, Any]:
    preflight = observe_local_preflight()
    failures = [name for name, passed in preflight["checks"].items() if not passed]
    if failures:
        raise S9V6CalibrationError(
            "v6 local preflight failed before output publication: "
            + ", ".join(failures)
        )
    return preflight


_LOCK = threading.RLock()
_PATH_OVERRIDES = {
    "S9_DIR": S9_V6_DIR,
    "READINESS_PATH": READINESS_PATH,
    "AUTHORIZATION_PATH": AUTHORIZATION_PATH,
    "DISPATCH_DIR": DISPATCH_DIR,
    "RAW_DIR": RAW_DIR,
    "RESULT_DIR": RESULT_DIR,
    "RECEIPT_DIR": RECEIPT_DIR,
    "PROGRESS_DIR": PROGRESS_DIR,
    "COMPLETENESS_PATH": COMPLETENESS_PATH,
    "RUNNER_SOURCES": RUNNER_SOURCES,
    "execute_frozen_item": execute_frozen_item_v2,
}


@contextmanager
def _v6_scope() -> Iterator[None]:
    with _LOCK:
        overrides = {
            **_PATH_OVERRIDES,
            "audit_readiness": _readiness_bridge,
            "audit_authorization": _authorization_bridge,
        }
        previous = {name: getattr(v1, name) for name in overrides}
        try:
            for name, value in overrides.items():
                setattr(v1, name, value)
            yield
        finally:
            for name, value in previous.items():
                setattr(v1, name, value)


def _static_gate() -> tuple[dict[str, Any], dict[str, Any], dict[str, bool]]:
    plan = v1._plan()
    gate = _json(v1.GO_PATH)
    checks = {
        "gate_digest_valid": _digest_valid(gate, "gate_digest"),
        "gate_decision_exact": gate.get("decision")
        == "GO_H2_H4_CALIBRATION_ONLY",
        "plan_digest_bound": gate.get("plan_digest") == plan["plan_digest"],
        "h2_h4_scope_exact": gate.get("authorization", {}).get("H2_H4_execution")
        == "AUTHORIZED_FROZEN_MB6_V4_PLAN_ONLY",
        "development_and_performance_blocked": gate.get("authorization", {}).get(
            "development_queue_execution"
        )
        == "NOT_AUTHORIZED"
        and gate.get("authorization", {}).get("performance_claim")
        == "NOT_AUTHORIZED",
    }
    if not all(checks.values()):
        raise S9V6CalibrationError("static S8-v2 gate binding failed")
    return plan, gate, checks


def _outputs_started() -> bool:
    return any(
        path.exists()
        for path in (DISPATCH_DIR, RAW_DIR, RESULT_DIR, RECEIPT_DIR, PROGRESS_DIR)
    )


def _remediation_binding(halt: Mapping[str, Any]) -> dict[str, Any]:
    runtime, threads = _environment_contract()
    return {
        "S9_v5_runtime_platform_halt": {
            "path": str(HALT_PATH.relative_to(ROOT)),
            "sha256": _sha(HALT_PATH),
            "halt_digest": halt["halt_digest"],
        },
        "run_namespace": RUN_NAMESPACE,
        "execution_venue": EXECUTION_VENUE,
        "reuse_exact_plan_digest": halt["remediation_contract"][
            "reuse_exact_plan_digest"
        ],
        "rerun_all_36_items_from_index_zero": True,
        "uniform_implementation_required": True,
        "required_runtime": runtime,
        "required_external_thread_environment": threads,
        "runtime_thread_capacity_preflight_before_any_output": True,
        "minimum_available_bytes": v1.THRESHOLD_BYTES,
        "every_item_capacity_pre_and_post_check_required": True,
        "any_kernel_or_post_capacity_failure_permanently_halts_namespace": True,
        "external_CI_is_static_and_never_executes_molecular_kernel": True,
        "historical_candidate_molecular_energy_evaluations": {
            "S9_v1": 3,
            "S9_v2": 0,
            "S9_v3": 40,
            "S9_v4": 0,
            "S9_v5": 0,
        },
        "historical_results_used_for_v6_design_or_selection": False,
        "historical_results_are_v6_performance_evidence": False,
    }


def build_readiness() -> dict[str, Any]:
    if _git("status", "--porcelain"):
        raise S9V6CalibrationError("readiness capture requires a clean worktree")
    halt = _halt()
    preflight = _require_local_preflight()
    plan, gate, gate_checks = _static_gate()
    if _outputs_started() or S9_V6_DIR.exists():
        raise S9V6CalibrationError("v6 readiness requires a fresh namespace")
    checks = {
        "v5_halt_valid": True,
        "static_gate_valid": all(gate_checks.values()),
        "local_preflight_passed": all(preflight["checks"].values()),
        "exact_frozen_36_item_plan": len(plan["items"]) == 36,
        "candidate_energy_zero_at_freeze": plan["candidate_energy_evaluations"]
        == 0,
        "fresh_namespace_has_no_output": True,
        "development_and_performance_blocked": gate["authorization"][
            "development_queue_execution"
        ]
        == "NOT_AUTHORIZED"
        and gate["authorization"]["performance_claim"] == "NOT_AUTHORIZED",
    }
    if not all(checks.values()):
        raise S9V6CalibrationError("v6 readiness checks failed")
    artifact = {
        "schema": "v5-final.s9-v6-local-runner-readiness.v1",
        "stage": "S9_V6_LOCAL_DARWIN_ARM64_RUNNER_READINESS",
        "status": "PASS_OUTCOME_FREE_LOCAL_RUNNER_READY",
        "decision": "READY_AWAITING_STATIC_EXACT_CI_AND_OWNER_AUTHORIZATION",
        "validated_runner_commit": _git("rev-parse", "HEAD"),
        "plan": {
            "path": str(v1.PLAN_PATH.relative_to(ROOT)),
            "sha256": _sha(v1.PLAN_PATH),
            "plan_digest": plan["plan_digest"],
            "item_count": 36,
        },
        "S8_v2_GO": {
            "path": str(v1.GO_PATH.relative_to(ROOT)),
            "sha256": _sha(v1.GO_PATH),
            "gate_digest": gate["gate_digest"],
        },
        "runner_source_manifest": [
            {"path": str(path.relative_to(ROOT)), "sha256": _sha(path)}
            for path in RUNNER_SOURCES
        ],
        "remediation": _remediation_binding(halt),
        "local_preflight_at_freeze": preflight,
        "checks": checks,
        "candidate_molecular_energy_evaluations": 0,
        "authorization": {
            "S9_v6_owner_authorization_capture": (
                "AUTHORIZED_AFTER_STATIC_EXACT_CI"
            ),
            "H2_H4_execution": "NOT_AUTHORIZED_BY_READINESS_ALONE",
            "development_queue_execution": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "academic_boundary": (
            "This outcome-free record freezes the unchanged 36-item runner only. "
            "GitHub CI may audit source and artifact integrity but cannot execute the "
            "Darwin/arm64 molecular kernel. No outcome is inspected or created here."
        ),
    }
    artifact["readiness_digest"] = _digest(artifact)
    return artifact


def audit_readiness() -> dict[str, bool]:
    halt = _halt()
    plan, gate, gate_checks = _static_gate()
    artifact = _json(READINESS_PATH)
    remediation = artifact.get("remediation", {})
    captured_preflight = artifact.get("local_preflight_at_freeze", {})
    checks = {
        "readiness_digest_valid": _digest_valid(artifact, "readiness_digest"),
        "schema_and_decision_exact": artifact.get("schema")
        == "v5-final.s9-v6-local-runner-readiness.v1"
        and artifact.get("decision")
        == "READY_AWAITING_STATIC_EXACT_CI_AND_OWNER_AUTHORIZATION",
        "captured_checks_passed": all(artifact.get("checks", {}).values()),
        "static_gate_valid": all(gate_checks.values()),
        "plan_unchanged": artifact["plan"]["sha256"] == _sha(v1.PLAN_PATH)
        and artifact["plan"]["plan_digest"] == plan["plan_digest"],
        "S8_v2_GO_unchanged": artifact["S8_v2_GO"]["sha256"]
        == _sha(v1.GO_PATH)
        and artifact["S8_v2_GO"]["gate_digest"] == gate["gate_digest"],
        "runner_sources_unchanged": all(
            _sha(ROOT / item["path"]) == item["sha256"]
            for item in artifact["runner_source_manifest"]
        ),
        "runner_commit_is_ancestor": _is_ancestor(
            artifact["validated_runner_commit"]
        ),
        "v5_halt_bound": remediation.get("S9_v5_runtime_platform_halt", {}).get(
            "sha256"
        )
        == _sha(HALT_PATH)
        and remediation.get("S9_v5_runtime_platform_halt", {}).get("halt_digest")
        == halt["halt_digest"],
        "fresh_exact_rerun_contract": remediation.get("run_namespace")
        == RUN_NAMESPACE
        and remediation.get("rerun_all_36_items_from_index_zero") is True
        and remediation.get("reuse_exact_plan_digest") == plan["plan_digest"],
        "captured_local_preflight_exact": all(
            captured_preflight.get("checks", {}).values()
        )
        and captured_preflight.get("required_runtime")
        == remediation.get("required_runtime")
        and captured_preflight.get("observed_runtime")
        == remediation.get("required_runtime")
        and captured_preflight.get("capacity", {}).get("passed") is True,
        "static_CI_never_executes_kernel": remediation.get(
            "external_CI_is_static_and_never_executes_molecular_kernel"
        )
        is True,
        "historical_outcomes_excluded": remediation.get(
            "historical_results_used_for_v6_design_or_selection"
        )
        is False
        and remediation.get("historical_results_are_v6_performance_evidence")
        is False,
        "zero_outcome_and_downstream_blocks": artifact.get(
            "candidate_molecular_energy_evaluations"
        )
        == 0
        and artifact.get("authorization", {}).get("H2_H4_execution")
        == "NOT_AUTHORIZED_BY_READINESS_ALONE"
        and artifact.get("authorization", {}).get("development_queue_execution")
        == "NOT_AUTHORIZED"
        and artifact.get("authorization", {}).get("performance_claim")
        == "NOT_AUTHORIZED",
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S9V6CalibrationError(
            "S9-v6 readiness audit failed: " + ", ".join(failures)
        )
    return checks


def _readiness_bridge() -> dict[str, bool]:
    return audit_readiness()


def build_readiness_ci_evidence(
    report: Mapping[str, Any], *, run_id: int, job_id: int, run_url: str,
    report_sha256: str
) -> dict[str, Any]:
    if _git("status", "--porcelain"):
        raise S9V6CalibrationError("CI evidence capture requires a clean worktree")
    head = _git("rev-parse", "HEAD")
    readiness_checks = audit_readiness()
    progress = report.get("progress", {})
    checks = {
        "run_and_job_ids_positive": run_id > 0 and job_id > 0,
        "run_url_exact_repository": run_url.startswith(
            "https://github.com/Reimangod/v5-matched-work-study/actions/runs/"
        ),
        "report_sha256_valid": len(report_sha256) == 64,
        "report_schema_exact": report.get("schema")
        == "v5-final.s9-v6-static-ci-audit.v1",
        "report_commit_exact": report.get("validated_exact_commit") == head,
        "report_decision_exact": report.get("decision")
        == "READY_AWAITING_S9_V6_OWNER_AUTHORIZATION",
        "readiness_audit_passed": all(readiness_checks.values())
        and all(report.get("readiness_audit", {}).values()),
        "report_checks_passed": all(report.get("checks", {}).values()),
        "zero_outcome_boundary": progress.get("completed_terminal_count") == 0
        and report.get("candidate_molecular_energy_evaluations") == 0,
        "downstream_blocks_exact": report.get("authorization", {}).get(
            "development_queue_execution"
        )
        == "NOT_AUTHORIZED"
        and report.get("authorization", {}).get("performance_claim")
        == "NOT_AUTHORIZED",
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S9V6CalibrationError(
            "v6 static exact-CI evidence failed: " + ", ".join(failures)
        )
    return {
        "schema": "v5-final.external-s9-v6-static-readiness-ci-evidence.v1",
        "attested_commit": head,
        "run_id": run_id,
        "job_id": job_id,
        "run_url": run_url,
        "conclusion": "success",
        "report_schema": report["schema"],
        "report_sha256": report_sha256,
        "capture_phase": "OUTCOME_FREE_STATIC_READINESS_BEFORE_OWNER_AUTHORIZATION",
        "candidate_molecular_energy_evaluations": 0,
        "checks": checks,
    }


def _validate_readiness_ci_evidence(
    evidence: Mapping[str, Any], *, readiness_commit: str
) -> dict[str, bool]:
    return {
        "schema_exact": evidence.get("schema")
        == "v5-final.external-s9-v6-static-readiness-ci-evidence.v1",
        "attested_commit_exact": evidence.get("attested_commit")
        == readiness_commit,
        "conclusion_success": evidence.get("conclusion") == "success",
        "run_and_job_ids_positive": isinstance(evidence.get("run_id"), int)
        and evidence["run_id"] > 0
        and isinstance(evidence.get("job_id"), int)
        and evidence["job_id"] > 0,
        "report_schema_exact": evidence.get("report_schema")
        == "v5-final.s9-v6-static-ci-audit.v1",
        "report_sha256_valid": isinstance(evidence.get("report_sha256"), str)
        and len(evidence["report_sha256"]) == 64,
        "zero_outcome_boundary": evidence.get(
            "candidate_molecular_energy_evaluations"
        )
        == 0,
        "captured_checks_passed": all(evidence.get("checks", {}).values()),
    }


def build_authorization(ci_evidence: Mapping[str, Any]) -> dict[str, Any]:
    if _git("status", "--porcelain"):
        raise S9V6CalibrationError("authorization capture requires a clean worktree")
    halt = _halt()
    readiness_checks = audit_readiness()
    preflight = _require_local_preflight()
    plan, _, gate_checks = _static_gate()
    readiness_commit = _git("rev-parse", "HEAD")
    ci_checks = _validate_readiness_ci_evidence(
        ci_evidence, readiness_commit=readiness_commit
    )
    if _outputs_started():
        raise S9V6CalibrationError("authorization requires zero v6 execution output")
    owner_freeze = _json(OWNER_FREEZE_PATH)
    owner_directive_digest = _digest({"directive": OWNER_CONTINUATION_DIRECTIVE})
    checks = {
        "v5_halt_valid": True,
        "readiness_audit_passed": all(readiness_checks.values()),
        "static_gate_valid": all(gate_checks.values()),
        "static_exact_CI_passed": all(ci_checks.values()),
        "current_local_preflight_passed": all(preflight["checks"].values()),
        "no_v6_execution_output": True,
        "candidate_energy_zero_before_authorization": True,
        "owner_identity_bound": owner_freeze.get("governance", {}).get(
            "repository_owner"
        )
        == OWNER,
    }
    if not all(checks.values()):
        raise S9V6CalibrationError("v6 authorization checks failed")
    readiness = _json(READINESS_PATH)
    artifact = {
        "schema": "v5-final.s9-v6-local-owner-execution-authorization.v1",
        "stage": "S9_V6_LOCAL_DARWIN_ARM64_EXECUTION_AUTHORIZATION",
        "status": "PASS_OUTCOME_FREE_OWNER_EXECUTION_AUTHORIZATION",
        "decision": "GO_S9_V6_EXACT_FROZEN_MB6_V4_H2_H4_ONLY",
        "authorized_readiness_commit": readiness_commit,
        "readiness": {
            "path": str(READINESS_PATH.relative_to(ROOT)),
            "sha256": _sha(READINESS_PATH),
            "readiness_digest": readiness["readiness_digest"],
        },
        "S9_v5_halt": {
            "path": str(HALT_PATH.relative_to(ROOT)),
            "sha256": _sha(HALT_PATH),
            "halt_digest": halt["halt_digest"],
        },
        "owner_governance": {
            "repository_owner": OWNER,
            "prior_owner_freeze_path": str(OWNER_FREEZE_PATH.relative_to(ROOT)),
            "prior_owner_freeze_sha256": _sha(OWNER_FREEZE_PATH),
            "continuation_directive": OWNER_CONTINUATION_DIRECTIVE,
            "continuation_directive_digest": owner_directive_digest,
            "basis": (
                "Repository-owner continuation of the already frozen, outcome-blind "
                "S8-v2 calibration scope; this is governance authorization, not "
                "scientific outcome evidence."
            ),
        },
        "static_exact_CI_evidence": dict(ci_evidence),
        "static_exact_CI_checks": ci_checks,
        "local_preflight_at_authorization": preflight,
        "plan_digest": plan["plan_digest"],
        "checks": checks,
        "candidate_molecular_energy_evaluations_before_authorization": 0,
        "authorization": {
            "H2_H4_execution": "AUTHORIZED_EXACT_V6_FROZEN_ORDER_ONLY",
            "H2_H4_item_count": 36,
            "start_index": 0,
            "single_process_local_execution": True,
            "runtime_thread_capacity_recheck_before_any_output": True,
            "capacity_recheck_before_and_after_each_item": True,
            "development_queue_execution": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "academic_boundary": (
            "Only the unchanged 36-item H2/H4 calibration is authorized. Outcomes "
            "cannot alter order, methods, work caps, runtime contract, or policy. "
            "Development execution and every performance claim remain forbidden."
        ),
    }
    artifact["authorization_digest"] = _digest(artifact)
    return artifact


def audit_authorization(*, require_current_preflight: bool = False) -> dict[str, bool]:
    readiness_checks = audit_readiness()
    artifact = _json(AUTHORIZATION_PATH)
    readiness = _json(READINESS_PATH)
    halt = _halt()
    ci_checks = _validate_readiness_ci_evidence(
        artifact.get("static_exact_CI_evidence", {}),
        readiness_commit=artifact["authorized_readiness_commit"],
    )
    owner = artifact.get("owner_governance", {})
    authorization = artifact.get("authorization", {})
    checks = {
        "authorization_digest_valid": _digest_valid(
            artifact, "authorization_digest"
        ),
        "schema_and_decision_exact": artifact.get("schema")
        == "v5-final.s9-v6-local-owner-execution-authorization.v1"
        and artifact.get("decision")
        == "GO_S9_V6_EXACT_FROZEN_MB6_V4_H2_H4_ONLY",
        "readiness_still_valid": all(readiness_checks.values()),
        "readiness_bound_exactly": artifact["readiness"]["sha256"]
        == _sha(READINESS_PATH)
        and artifact["readiness"]["readiness_digest"]
        == readiness["readiness_digest"],
        "v5_halt_bound_exactly": artifact["S9_v5_halt"]["sha256"]
        == _sha(HALT_PATH)
        and artifact["S9_v5_halt"]["halt_digest"] == halt["halt_digest"],
        "static_exact_CI_checks_passed": all(ci_checks.values())
        and all(artifact.get("static_exact_CI_checks", {}).values()),
        "captured_checks_passed": all(artifact.get("checks", {}).values()),
        "authorized_commit_is_ancestor": _is_ancestor(
            artifact["authorized_readiness_commit"]
        ),
        "owner_governance_bound": owner.get("repository_owner") == OWNER
        and owner.get("prior_owner_freeze_sha256") == _sha(OWNER_FREEZE_PATH)
        and owner.get("continuation_directive_digest")
        == _digest({"directive": OWNER_CONTINUATION_DIRECTIVE}),
        "authorization_scope_exact": authorization.get("H2_H4_execution")
        == "AUTHORIZED_EXACT_V6_FROZEN_ORDER_ONLY"
        and authorization.get("H2_H4_item_count") == 36
        and authorization.get("start_index") == 0
        and authorization.get("development_queue_execution") == "NOT_AUTHORIZED"
        and authorization.get("performance_claim") == "NOT_AUTHORIZED",
        "current_preflight_passed_if_required": not require_current_preflight
        or all(_require_local_preflight()["checks"].values()),
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S9V6CalibrationError(
            "S9-v6 authorization audit failed: " + ", ".join(failures)
        )
    return checks


def _authorization_bridge() -> dict[str, bool]:
    return audit_authorization(require_current_preflight=True)


def _failure_receipts() -> tuple[list[str], list[str]]:
    if not RECEIPT_DIR.exists():
        return [], []
    kernel: list[str] = []
    capacity: list[str] = []
    for path in sorted(RECEIPT_DIR.glob("*.json")):
        receipt = _json(path)
        if receipt.get("terminal_status") == "KERNEL_FAILURE":
            kernel.append(path.name)
        if receipt.get("capacity_after_terminal", {}).get("passed") is False:
            capacity.append(path.name)
    return kernel, capacity


def _require_resumable_namespace() -> None:
    kernel, capacity = _failure_receipts()
    if kernel or capacity:
        raise S9V6CalibrationError(
            "S9-v6 namespace permanently halted: kernel="
            + ",".join(kernel)
            + "; capacity="
            + ",".join(capacity)
        )


def _progress() -> dict[str, Any]:
    plan = v1._plan()
    if not READINESS_PATH.exists():
        if _outputs_started():
            raise S9V6CalibrationError("v6 output exists before readiness")
        receipts: list[dict[str, Any]] = []
    else:
        with _v6_scope():
            receipts = v1._completed_receipts(
                plan, allow_inflight=False, require_progress=True
            )
    return v1._progress_snapshot(plan, receipts)


def build_static_audit() -> dict[str, Any]:
    halt = _halt()
    plan, _, gate_checks = _static_gate()
    readiness_checks = audit_readiness() if READINESS_PATH.exists() else {}
    authorization_checks = (
        audit_authorization(require_current_preflight=False)
        if AUTHORIZATION_PATH.exists()
        else {}
    )
    progress = _progress()
    kernel_failures = progress["terminal_status_counts"]["KERNEL_FAILURE"]
    capacity_passed = progress["all_post_item_capacity_checks_passed"]
    completed = progress["completed_terminal_count"]
    namespace_halted = completed > 0 and (
        kernel_failures > 0 or not capacity_passed
    )
    completeness_valid = True
    if COMPLETENESS_PATH.exists():
        completeness = _json(COMPLETENESS_PATH)
        completeness_valid = (
            _digest_valid(completeness, "completeness_digest")
            and completeness.get("plan_digest") == plan["plan_digest"]
            and completeness.get("expected_item_count") == 36
            and completeness.get("progress") == progress
            and all(completeness.get("checks", {}).values())
        )
    checks = {
        "v5_halt_valid": all(audit_halt().values()),
        "static_gate_valid": all(gate_checks.values()),
        "frozen_plan_exact": len(plan["items"]) == 36,
        "readiness_valid_if_present": not READINESS_PATH.exists()
        or all(readiness_checks.values()),
        "authorization_valid_if_present": not AUTHORIZATION_PATH.exists()
        or all(authorization_checks.values()),
        "authorization_precedes_any_execution": completed == 0
        or AUTHORIZATION_PATH.exists(),
        "exact_prefix_integrity": len(progress["completed_queue_item_ids"])
        == completed,
        "completeness_valid_if_present": completeness_valid,
        "complete_only_at_36": progress["complete"] is (completed == 36),
        "namespace_halt_policy_exact": (
            not namespace_halted
            and kernel_failures == 0
            and capacity_passed is True
        )
        or namespace_halted,
        "development_and_performance_blocked": progress["authorization"][
            "development_queue_execution"
        ]
        == "NOT_AUTHORIZED"
        and progress["authorization"]["performance_claim"] == "NOT_AUTHORIZED",
        "historical_results_excluded": halt["scientific_interpretation"][
            "performance_evidence"
        ]
        is False,
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S9V6CalibrationError(
            "S9-v6 static CI audit failed: " + ", ".join(failures)
        )
    if namespace_halted:
        decision = "NO_GO_S9_V6_NAMESPACE_HALTED"
    elif progress["complete"]:
        decision = "S9_V6_CALIBRATION_COMPLETE_AWAITING_S10_INTEGRITY"
    elif AUTHORIZATION_PATH.exists():
        decision = "S9_V6_AUTHORIZED_AWAITING_LOCAL_EXECUTION"
    elif READINESS_PATH.exists():
        decision = "READY_AWAITING_S9_V6_OWNER_AUTHORIZATION"
    else:
        decision = "S9_V6_IMPLEMENTATION_ONLY_EXECUTION_NOT_AUTHORIZED"
    report = {
        "schema": "v5-final.s9-v6-static-ci-audit.v1",
        "validated_exact_commit": _git("rev-parse", "HEAD"),
        "status": "PASS_S9_V6_STATIC_INTEGRITY",
        "decision": decision,
        "run_namespace": RUN_NAMESPACE,
        "execution_venue": EXECUTION_VENUE,
        "S9_v5_halt": {
            "path": str(HALT_PATH.relative_to(ROOT)),
            "sha256": _sha(HALT_PATH),
            "halt_digest": halt["halt_digest"],
        },
        "readiness_audit": readiness_checks,
        "authorization_audit": authorization_checks,
        "progress": progress,
        "namespace_halted": namespace_halted,
        "checks": checks,
        "candidate_molecular_energy_evaluations": progress[
            "candidate_energy_evaluations"
        ],
        "authorization": {
            "H2_H4_execution": (
                "AUTHORIZED_BY_COMMITTED_V6_ARTIFACT"
                if AUTHORIZATION_PATH.exists() and not namespace_halted
                else "NOT_AUTHORIZED"
            ),
            "development_queue_execution": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
    }
    report["audit_digest"] = _digest(report)
    return report


def run_calibration(*, max_items: int | None = None) -> dict[str, Any]:
    _halt()
    _require_local_preflight()
    audit_authorization(require_current_preflight=True)
    _require_resumable_namespace()
    with _v6_scope():
        return v1.run_calibration(max_items=max_items)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-readiness", action="store_true")
    parser.add_argument("--write-readiness-ci-evidence", action="store_true")
    parser.add_argument("--write-authorization", action="store_true")
    parser.add_argument("--ci-report", type=Path)
    parser.add_argument("--ci-evidence-output", type=Path)
    parser.add_argument("--ci-evidence", type=Path)
    parser.add_argument("--run-id", type=int)
    parser.add_argument("--job-id", type=int)
    parser.add_argument("--run-url")
    parser.add_argument("--static-audit-output", type=Path)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--max-items", type=int)
    args = parser.parse_args()
    if args.write_readiness:
        artifact = build_readiness()
        S9_V6_DIR.mkdir(parents=True, exist_ok=False)
        write_json_exclusive(READINESS_PATH, artifact)
        print(READINESS_PATH)
        return
    if args.write_readiness_ci_evidence:
        if (
            args.ci_report is None
            or args.ci_evidence_output is None
            or args.run_id is None
            or args.job_id is None
            or args.run_url is None
        ):
            raise S9V6CalibrationError(
                "CI evidence requires report, output, run-id, job-id, and run-url"
            )
        write_json_exclusive(
            args.ci_evidence_output,
            build_readiness_ci_evidence(
                _json(args.ci_report),
                run_id=args.run_id,
                job_id=args.job_id,
                run_url=args.run_url,
                report_sha256=_sha(args.ci_report),
            ),
        )
        print(args.ci_evidence_output)
        return
    if args.write_authorization:
        if args.ci_evidence is None:
            raise S9V6CalibrationError("authorization requires static exact-CI evidence")
        write_json_exclusive(
            AUTHORIZATION_PATH, build_authorization(_json(args.ci_evidence))
        )
        print(AUTHORIZATION_PATH)
        return
    if args.static_audit_output is not None:
        write_json_exclusive(args.static_audit_output, build_static_audit())
        print(args.static_audit_output)
        return
    if args.run:
        print(json.dumps(run_calibration(max_items=args.max_items), sort_keys=True))
        return
    print(json.dumps(build_static_audit(), sort_keys=True))


if __name__ == "__main__":
    main()

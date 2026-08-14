"""Persistent, fail-closed runner for the frozen S11 development successor.

Static CI attests repository and artifact integrity without running molecular
kernels.  Candidate execution is released only by a separate repository-owner
authorization artifact after an exact-CI report and a local Darwin/arm64,
single-thread, capacity-reserved preflight.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import threading
import time
from typing import Any, Iterator, Mapping

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from . import s9_h2_h4_calibration_runner as core
from .parent_native_development_execution_v1 import execute_development_item_v1
from .parent_native_development_runtime_factory_v1 import ENVIRONMENT_PATH, PLAN_PATH
from .s0_successor import ROOT
from .s11_development_successor_v1 import (
    FREEZE_OUTPUT,
    LEDGER_OUTPUT,
    audit_static as audit_freeze_static,
)


EXECUTION_DIR = (
    ROOT / "artifacts/v5-final/parent-native/s11-development-execution-v1"
)
READINESS_PATH = EXECUTION_DIR / "s11-runner-readiness-v1.json"
AUTHORIZATION_PATH = EXECUTION_DIR / "s11-execution-authorization-v1.json"
DISPATCH_DIR = EXECUTION_DIR / "dispatch"
RAW_DIR = EXECUTION_DIR / "raw-ledgers"
RESULT_DIR = EXECUTION_DIR / "item-results"
RECEIPT_DIR = EXECUTION_DIR / "item-receipts"
PROGRESS_DIR = EXECUTION_DIR / "progress"
COMPLETENESS_PATH = EXECUTION_DIR / "development-completeness-v1.json"
RUN_NAMESPACE = "s11-development-execution-v1"
EXECUTION_VENUE = "repository-owner-local-darwin-arm64-single-process"
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
        "src/v5_final/s11_development_runner_v1.py",
        "src/v5_final/s11_development_successor_v1.py",
        "src/v5_final/parent_native_development_execution_v1.py",
        "src/v5_final/parent_native_development_runtime_factory_v1.py",
        "src/v5_final/parent_native_execution_services.py",
        "src/v5_final/parent_native_persistent_runner.py",
        "src/v5_final/parent_native_work_accounting.py",
        "src/v5_final/semantic_contract_v2.py",
        "src/v5_final/s9_h2_h4_calibration_runner.py",
        "tests/test_v5_final_s11_development_runner_v1.py",
        ".github/workflows/v5-s11-development-successor-gate.yml",
    )
)
PREFLIGHT_CHECK_KEYS = frozenset(
    {
        "runtime_exact",
        "thread_environment_exact",
        "capacity_with_mandatory_reserve_passed",
        "execution_threshold_exact",
        "single_process_local_venue_exact",
    }
)
READINESS_CHECK_KEYS = frozenset(
    {
        "freeze_static_audit_passed",
        "local_preflight_passed",
        "exact_frozen_90_item_plan",
        "candidate_energy_zero_at_freeze",
        "fresh_namespace_has_no_output",
        "freeze_execution_and_claims_blocked",
    }
)
READINESS_AUDIT_CHECK_KEYS = frozenset(
    {
        "readiness_digest_valid",
        "schema_and_decision_exact",
        "captured_checks_passed",
        "plan_unchanged",
        "freeze_unchanged",
        "empty_ledger_root_unchanged",
        "runner_source_manifest_exact",
        "runner_sources_unchanged",
        "runner_commit_is_ancestor",
        "captured_local_preflight_exact",
        "zero_outcome_and_claim_boundary",
    }
)
STATIC_AUDIT_CHECK_KEYS = frozenset(
    {
        "freeze_static_audit_passed",
        "frozen_plan_exact",
        "readiness_valid_if_present",
        "authorization_valid_if_present",
        "authorization_precedes_any_execution",
        "exact_prefix_integrity",
        "completeness_valid_if_present",
        "complete_only_at_90",
        "namespace_halt_policy_exact",
        "FCI_not_reported_during_development",
        "performance_claim_blocked",
        "freeze_was_zero_outcome",
    }
)
CI_EVIDENCE_CHECK_KEYS = frozenset(
    {
        "run_and_job_ids_positive",
        "run_url_exact_repository",
        "report_sha256_valid",
        "report_sha256_exact",
        "report_schema_exact",
        "report_commit_exact",
        "report_decision_exact",
        "readiness_audit_passed",
        "report_checks_passed",
        "zero_outcome_boundary",
        "claims_and_FCI_blocked",
    }
)
AUTHORIZATION_CHECK_KEYS = frozenset(
    {
        "freeze_static_audit_passed",
        "readiness_audit_passed",
        "static_exact_CI_passed",
        "current_local_preflight_passed",
        "no_S11_execution_output",
        "candidate_energy_zero_before_authorization",
        "owner_identity_bound",
    }
)
COMPLETENESS_CHECK_KEYS = frozenset(
    {
        "all_90_unique_terminals",
        "every_and_only_frozen_item_terminal",
        "raw_ledgers_reconstructed",
        "no_kernel_failure",
        "all_post_item_capacity_checks_passed",
        "candidate_energy_reconstructed_from_raw_events",
        "FCI_not_reported_during_development",
        "performance_claim_not_made",
    }
)


class S11DevelopmentRunnerError(core.S9CalibrationError):
    pass


def _json(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise S11DevelopmentRunnerError(f"invalid JSON artifact: {path}") from error
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise S11DevelopmentRunnerError(f"noncanonical JSON artifact: {path}")
    return value


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _digest_valid(value: Mapping[str, Any], field: str) -> bool:
    body = dict(value)
    observed = body.pop(field, None)
    return isinstance(observed, str) and observed == _digest(body)


def _exact_true_checks(value: Any, expected: frozenset[str]) -> bool:
    return (
        isinstance(value, Mapping)
        and frozenset(value) == expected
        and all(item is True for item in value.values())
    )


def _capacity_record_valid(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    expected_keys = {
        "filesystem_available_bytes",
        "required_study_bytes",
        "mandatory_reserve_bytes",
        "execution_threshold_bytes",
        "passed",
    }
    if set(value) != expected_keys:
        return False
    available = value["filesystem_available_bytes"]
    required = value["required_study_bytes"]
    reserve = value["mandatory_reserve_bytes"]
    threshold = value["execution_threshold_bytes"]
    if any(
        isinstance(item, bool) or not isinstance(item, int) or item < 0
        for item in (available, required, reserve, threshold)
    ):
        return False
    return (
        required == core.REQUIRED_FREE_BYTES
        and reserve == core.RESERVE_BYTES
        and threshold == required + reserve == 23_890_755_584
        and value["passed"] is (available >= threshold)
    )


def _runner_source_manifest_valid(value: Any) -> bool:
    if not isinstance(value, list):
        return False
    expected_paths = [str(path.relative_to(ROOT)) for path in RUNNER_SOURCES]
    return (
        len(value) == len(expected_paths)
        and [item.get("path") if isinstance(item, Mapping) else None for item in value]
        == expected_paths
        and all(
            isinstance(item, Mapping)
            and set(item) == {"path", "sha256"}
            and isinstance(item["sha256"], str)
            and len(item["sha256"]) == 64
            and all(character in "0123456789abcdef" for character in item["sha256"])
            for item in value
        )
    )


def _git(*arguments: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(ROOT), *arguments], text=True
    ).strip()


def _last_commit_for(path: Path) -> str:
    return _git("log", "-1", "--format=%H", "--", str(path.relative_to(ROOT)))


def _is_ancestor(commit: str) -> bool:
    return (
        subprocess.run(
            ["git", "-C", str(ROOT), "merge-base", "--is-ancestor", commit, "HEAD"],
            check=False,
        ).returncode
        == 0
    )


def _plan() -> dict[str, Any]:
    if not all(audit_freeze_static().values()):
        raise S11DevelopmentRunnerError("S11 outcome-blind freeze audit failed")
    plan = _json(PLAN_PATH)
    items = list(plan.get("items", ()))
    if (
        not _digest_valid(plan, "plan_digest")
        or plan.get("schema") != "v5-final.s11-development-plan.v4"
        or plan.get("frozen_item_count") != 90
        or len(items) != 90
        or len({item.get("queue_item_id") for item in items}) != 90
        or plan.get("candidate_energy_evaluations") != 0
        or any(item.get("terminal_status") != "NOT_STARTED" for item in items)
    ):
        raise S11DevelopmentRunnerError("S11 frozen plan integrity failed")
    for item in items:
        body = {key: value for key, value in item.items() if key != "queue_item_id"}
        if item["queue_item_id"] != "development-queue-item-v4:" + _digest(body):
            raise S11DevelopmentRunnerError("S11 queue item identity failed")
    return plan


def _freeze() -> dict[str, Any]:
    checks = audit_freeze_static()
    freeze = _json(FREEZE_OUTPUT)
    authorization = freeze.get("authorization", {})
    if (
        not all(checks.values())
        or not _digest_valid(freeze, "freeze_digest")
        or freeze.get("decision") != "READY_FOR_S11_STATIC_EXACT_CI_ONLY"
        or freeze.get("candidate_molecular_energy_evaluations") != 0
        or authorization.get("development_execution") != "NOT_AUTHORIZED"
        or authorization.get("performance_claim") != "NOT_AUTHORIZED"
        or authorization.get("FCI_reporting")
        != "NOT_AUTHORIZED_UNTIL_ALL_90_TERMINAL"
    ):
        raise S11DevelopmentRunnerError("S11 freeze boundary is invalid")
    return freeze


def _environment_contract() -> tuple[dict[str, str], dict[str, str]]:
    environment = _json(ENVIRONMENT_PATH)
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
        "MKL_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
    }
    if (
        not _digest_valid(environment, "environment_digest")
        or runtime != expected_runtime
        or threads != expected_threads
    ):
        raise S11DevelopmentRunnerError("S11 frozen environment contract is not exact")
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
    capacity = core._current_capacity()
    checks = {
        "runtime_exact": observed_runtime == runtime,
        "thread_environment_exact": observed_threads == threads,
        "capacity_with_mandatory_reserve_passed": capacity["passed"] is True,
        "execution_threshold_exact": capacity["execution_threshold_bytes"]
        == 23_890_755_584,
        "single_process_local_venue_exact": os.environ.get(
            "V5_S11_EXECUTION_VENUE"
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
        raise S11DevelopmentRunnerError(
            "S11 local preflight failed before output publication: "
            + ", ".join(failures)
        )
    return preflight


def _outputs_started() -> bool:
    return COMPLETENESS_PATH.exists() or any(
        path.exists()
        for path in (DISPATCH_DIR, RAW_DIR, RESULT_DIR, RECEIPT_DIR, PROGRESS_DIR)
    )


def build_readiness() -> dict[str, Any]:
    if _git("status", "--porcelain"):
        raise S11DevelopmentRunnerError("readiness capture requires a clean worktree")
    if EXECUTION_DIR.exists():
        raise S11DevelopmentRunnerError("readiness requires a fresh S11 namespace")
    plan = _plan()
    freeze = _freeze()
    preflight = _require_local_preflight()
    checks = {
        "freeze_static_audit_passed": True,
        "local_preflight_passed": all(preflight["checks"].values()),
        "exact_frozen_90_item_plan": len(plan["items"]) == 90,
        "candidate_energy_zero_at_freeze": plan["candidate_energy_evaluations"] == 0,
        "fresh_namespace_has_no_output": True,
        "freeze_execution_and_claims_blocked": freeze["authorization"][
            "development_execution"
        ]
        == "NOT_AUTHORIZED"
        and freeze["authorization"]["performance_claim"] == "NOT_AUTHORIZED",
    }
    if not _exact_true_checks(checks, READINESS_CHECK_KEYS):
        raise S11DevelopmentRunnerError("S11 readiness checks failed")
    artifact = {
        "schema": "v5-final.s11-local-runner-readiness.v1",
        "stage": "S11_LOCAL_DARWIN_ARM64_RUNNER_READINESS",
        "status": "PASS_OUTCOME_FREE_LOCAL_RUNNER_READY",
        "decision": "READY_AWAITING_STATIC_EXACT_CI_AND_OWNER_AUTHORIZATION",
        "validated_runner_commit": _git("rev-parse", "HEAD"),
        "plan": {
            "path": str(PLAN_PATH.relative_to(ROOT)),
            "sha256": _sha(PLAN_PATH),
            "plan_digest": plan["plan_digest"],
            "item_count": 90,
        },
        "freeze": {
            "path": str(FREEZE_OUTPUT.relative_to(ROOT)),
            "sha256": _sha(FREEZE_OUTPUT),
            "freeze_digest": freeze["freeze_digest"],
        },
        "empty_ledger_root": {
            "path": str(LEDGER_OUTPUT.relative_to(ROOT)),
            "sha256": _sha(LEDGER_OUTPUT),
        },
        "runner_source_manifest": [
            {"path": str(path.relative_to(ROOT)), "sha256": _sha(path)}
            for path in RUNNER_SOURCES
        ],
        "local_preflight_at_freeze": preflight,
        "checks": checks,
        "candidate_molecular_energy_evaluations": 0,
        "authorization": {
            "development_execution": "NOT_AUTHORIZED_BY_READINESS_ALONE",
            "performance_claim": "NOT_AUTHORIZED",
            "FCI_reporting": "NOT_AUTHORIZED_UNTIL_ALL_90_TERMINAL",
            "release": "NOT_AUTHORIZED",
        },
        "academic_boundary": (
            "This record freezes only the local persistent runner. Static CI may "
            "audit exact source and artifact integrity but cannot run molecular "
            "kernels. No candidate outcome or FCI value is created or inspected."
        ),
    }
    artifact["readiness_digest"] = _digest(artifact)
    return artifact


def audit_readiness() -> dict[str, bool]:
    plan = _plan()
    freeze = _freeze()
    artifact = _json(READINESS_PATH)
    captured = artifact.get("local_preflight_at_freeze", {})
    manifest = artifact.get("runner_source_manifest")
    checks = {
        "readiness_digest_valid": _digest_valid(artifact, "readiness_digest"),
        "schema_and_decision_exact": artifact.get("schema")
        == "v5-final.s11-local-runner-readiness.v1"
        and artifact.get("decision")
        == "READY_AWAITING_STATIC_EXACT_CI_AND_OWNER_AUTHORIZATION",
        "captured_checks_passed": _exact_true_checks(
            artifact.get("checks"), READINESS_CHECK_KEYS
        ),
        "plan_unchanged": artifact["plan"]["sha256"] == _sha(PLAN_PATH)
        and artifact["plan"]["plan_digest"] == plan["plan_digest"]
        and artifact["plan"]["item_count"] == 90,
        "freeze_unchanged": artifact["freeze"]["sha256"] == _sha(FREEZE_OUTPUT)
        and artifact["freeze"]["freeze_digest"] == freeze["freeze_digest"],
        "empty_ledger_root_unchanged": artifact["empty_ledger_root"]["sha256"]
        == _sha(LEDGER_OUTPUT),
        "runner_source_manifest_exact": _runner_source_manifest_valid(manifest),
        "runner_sources_unchanged": _runner_source_manifest_valid(manifest) and all(
            _sha(ROOT / item["path"]) == item["sha256"]
            for item in manifest
        ),
        "runner_commit_is_ancestor": _is_ancestor(
            artifact["validated_runner_commit"]
        ),
        "captured_local_preflight_exact": all(captured.get("checks", {}).values())
        and frozenset(captured.get("checks", {})) == PREFLIGHT_CHECK_KEYS
        and captured.get("required_runtime") == captured.get("observed_runtime")
        and captured.get("required_threads") == captured.get("observed_threads")
        and _capacity_record_valid(captured.get("capacity"))
        and captured.get("capacity", {}).get("passed") is True,
        "zero_outcome_and_claim_boundary": artifact.get(
            "candidate_molecular_energy_evaluations"
        )
        == 0
        and artifact.get("authorization", {}).get("development_execution")
        == "NOT_AUTHORIZED_BY_READINESS_ALONE"
        and artifact.get("authorization", {}).get("performance_claim")
        == "NOT_AUTHORIZED"
        and artifact.get("authorization", {}).get("FCI_reporting")
        == "NOT_AUTHORIZED_UNTIL_ALL_90_TERMINAL",
    }
    if frozenset(checks) != READINESS_AUDIT_CHECK_KEYS:
        raise S11DevelopmentRunnerError("S11 readiness audit check set drifted")
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S11DevelopmentRunnerError(
            "S11 readiness audit failed: " + ", ".join(failures)
        )
    return checks


def build_readiness_ci_evidence(
    report: Mapping[str, Any], *, run_id: int, job_id: int, run_url: str,
    report_sha256: str
) -> dict[str, Any]:
    if _git("status", "--porcelain"):
        raise S11DevelopmentRunnerError("CI evidence capture requires a clean worktree")
    head = _git("rev-parse", "HEAD")
    readiness_checks = audit_readiness()
    progress = report.get("progress", {})
    checks = {
        "run_and_job_ids_positive": run_id > 0 and job_id > 0,
        "run_url_exact_repository": run_url
        == (
            "https://github.com/Reimangod/v5-matched-work-study/actions/runs/"
            + str(run_id)
        ),
        "report_sha256_valid": len(report_sha256) == 64
        and all(value in "0123456789abcdef" for value in report_sha256),
        "report_sha256_exact": report_sha256 == _digest(report),
        "report_schema_exact": report.get("schema")
        == "v5-final.s11-static-ci-audit.v1",
        "report_commit_exact": report.get("validated_exact_commit") == head,
        "report_decision_exact": report.get("decision")
        == "READY_AWAITING_S11_OWNER_AUTHORIZATION",
        "readiness_audit_passed": frozenset(readiness_checks)
        == READINESS_AUDIT_CHECK_KEYS
        and all(readiness_checks.values())
        and _exact_true_checks(
            report.get("readiness_audit"), READINESS_AUDIT_CHECK_KEYS
        ),
        "report_checks_passed": _exact_true_checks(
            report.get("checks"), STATIC_AUDIT_CHECK_KEYS
        )
        and _digest_valid(report, "audit_digest"),
        "zero_outcome_boundary": progress.get("completed_terminal_count") == 0
        and report.get("candidate_molecular_energy_evaluations") == 0,
        "claims_and_FCI_blocked": report.get("authorization", {}).get(
            "performance_claim"
        )
        == "NOT_AUTHORIZED"
        and report.get("authorization", {}).get("FCI_reporting")
        == "NOT_AUTHORIZED_UNTIL_ALL_90_TERMINAL",
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S11DevelopmentRunnerError(
            "S11 static exact-CI evidence failed: " + ", ".join(failures)
        )
    return {
        "schema": "v5-final.external-s11-static-readiness-ci-evidence.v1",
        "attested_commit": head,
        "run_id": run_id,
        "job_id": job_id,
        "run_url": run_url,
        "conclusion": "success",
        "report_schema": report["schema"],
        "report_sha256": report_sha256,
        "static_report": dict(report),
        "capture_phase": "OUTCOME_FREE_STATIC_READINESS_BEFORE_OWNER_AUTHORIZATION",
        "candidate_molecular_energy_evaluations": 0,
        "checks": checks,
    }


def _validate_readiness_ci_evidence(
    evidence: Mapping[str, Any], *, readiness_commit: str
) -> dict[str, bool]:
    report_sha = evidence.get("report_sha256")
    report = evidence.get("static_report")
    report_is_mapping = isinstance(report, Mapping)
    report_progress = report.get("progress", {}) if report_is_mapping else {}
    run_id = evidence.get("run_id")
    expected_run_url = (
        "https://github.com/Reimangod/v5-matched-work-study/actions/runs/"
        + str(run_id)
    )
    return {
        "schema_exact": evidence.get("schema")
        == "v5-final.external-s11-static-readiness-ci-evidence.v1",
        "attested_commit_exact": evidence.get("attested_commit")
        == readiness_commit,
        "conclusion_success": evidence.get("conclusion") == "success",
        "run_and_job_ids_positive": isinstance(evidence.get("run_id"), int)
        and evidence["run_id"] > 0
        and isinstance(evidence.get("job_id"), int)
        and evidence["job_id"] > 0,
        "run_url_exact": evidence.get("run_url") == expected_run_url,
        "capture_phase_exact": evidence.get("capture_phase")
        == "OUTCOME_FREE_STATIC_READINESS_BEFORE_OWNER_AUTHORIZATION",
        "report_schema_exact": evidence.get("report_schema")
        == "v5-final.s11-static-ci-audit.v1"
        and report_is_mapping
        and report.get("schema") == evidence.get("report_schema"),
        "report_sha256_valid": isinstance(report_sha, str)
        and len(report_sha) == 64
        and all(value in "0123456789abcdef" for value in report_sha),
        "embedded_report_digest_exact": report_is_mapping
        and report_sha == _digest(report),
        "report_commit_and_decision_exact": report_is_mapping
        and report.get("validated_exact_commit") == readiness_commit
        and report.get("decision") == "READY_AWAITING_S11_OWNER_AUTHORIZATION"
        and report.get("status") == "PASS_S11_STATIC_INTEGRITY"
        and report.get("run_namespace") == RUN_NAMESPACE
        and report.get("execution_venue") == EXECUTION_VENUE
        and report.get("namespace_halted") is False,
        "report_audits_exact": report_is_mapping
        and _digest_valid(report, "audit_digest")
        and _exact_true_checks(
            report.get("readiness_audit"), READINESS_AUDIT_CHECK_KEYS
        )
        and _exact_true_checks(report.get("checks"), STATIC_AUDIT_CHECK_KEYS),
        "report_zero_outcome_boundary": report_progress.get(
            "expected_item_count"
        )
        == 90
        and report_progress.get("completed_terminal_count") == 0
        and report_progress.get("candidate_energy_evaluations") == 0
        and report_progress.get("FCI_reporting_performed") is False
        and report.get("candidate_molecular_energy_evaluations") == 0
        and report.get("authorization", {}).get("performance_claim")
        == "NOT_AUTHORIZED"
        and report.get("authorization", {}).get("FCI_reporting")
        == "NOT_AUTHORIZED_UNTIL_ALL_90_TERMINAL",
        "zero_outcome_boundary": evidence.get(
            "candidate_molecular_energy_evaluations"
        )
        == 0,
        "captured_checks_passed": _exact_true_checks(
            evidence.get("checks"), CI_EVIDENCE_CHECK_KEYS
        ),
    }


def build_authorization(ci_evidence: Mapping[str, Any]) -> dict[str, Any]:
    if _git("status", "--porcelain"):
        raise S11DevelopmentRunnerError("authorization capture requires a clean worktree")
    readiness_checks = audit_readiness()
    preflight = _require_local_preflight()
    plan = _plan()
    freeze = _freeze()
    readiness_commit = _git("rev-parse", "HEAD")
    ci_checks = _validate_readiness_ci_evidence(
        ci_evidence, readiness_commit=readiness_commit
    )
    if _outputs_started():
        raise S11DevelopmentRunnerError(
            "authorization requires zero S11 execution output"
        )
    owner_freeze = _json(OWNER_FREEZE_PATH)
    if (
        owner_freeze.get("schema")
        != "v5-final.method-native.mb4-2-owner-protocol-freeze.v1"
        or owner_freeze.get("decision")
        != "GO_MB5_OUTCOME_FREE_EXECUTOR_IMPLEMENTATION_ONLY"
        or not _digest_valid(owner_freeze, "freeze_digest")
    ):
        raise S11DevelopmentRunnerError("prior repository-owner freeze is invalid")
    owner_directive_digest = _digest({"directive": OWNER_CONTINUATION_DIRECTIVE})
    checks = {
        "freeze_static_audit_passed": True,
        "readiness_audit_passed": all(readiness_checks.values()),
        "static_exact_CI_passed": all(ci_checks.values()),
        "current_local_preflight_passed": all(preflight["checks"].values()),
        "no_S11_execution_output": True,
        "candidate_energy_zero_before_authorization": True,
        "owner_identity_bound": owner_freeze.get("governance", {}).get(
            "repository_owner"
        )
        == OWNER,
    }
    if not _exact_true_checks(checks, AUTHORIZATION_CHECK_KEYS):
        raise S11DevelopmentRunnerError("S11 authorization checks failed")
    readiness = _json(READINESS_PATH)
    artifact = {
        "schema": "v5-final.s11-development-local-owner-execution-authorization.v1",
        "stage": "S11_LOCAL_DARWIN_ARM64_DEVELOPMENT_EXECUTION_AUTHORIZATION",
        "status": "PASS_OUTCOME_FREE_OWNER_EXECUTION_AUTHORIZATION",
        "decision": "GO_S11_EXACT_FROZEN_90_ITEM_DEVELOPMENT_ONLY",
        "authorized_readiness_commit": readiness_commit,
        "readiness": {
            "path": str(READINESS_PATH.relative_to(ROOT)),
            "sha256": _sha(READINESS_PATH),
            "readiness_digest": readiness["readiness_digest"],
        },
        "freeze": {
            "path": str(FREEZE_OUTPUT.relative_to(ROOT)),
            "sha256": _sha(FREEZE_OUTPUT),
            "freeze_digest": freeze["freeze_digest"],
        },
        "owner_governance": {
            "repository_owner": OWNER,
            "prior_owner_freeze_path": str(OWNER_FREEZE_PATH.relative_to(ROOT)),
            "prior_owner_freeze_sha256": _sha(OWNER_FREEZE_PATH),
            "continuation_directive": OWNER_CONTINUATION_DIRECTIVE,
            "continuation_directive_digest": owner_directive_digest,
            "basis": (
                "Repository-owner continuation of the already frozen, outcome-blind "
                "S11 development scope; governance authorization is not outcome evidence."
            ),
        },
        "static_exact_CI_evidence": dict(ci_evidence),
        "static_exact_CI_checks": ci_checks,
        "local_preflight_at_authorization": preflight,
        "plan_digest": plan["plan_digest"],
        "checks": checks,
        "candidate_molecular_energy_evaluations_before_authorization": 0,
        "authorization": {
            "development_execution": "AUTHORIZED_EXACT_FROZEN_90_ITEM_ORDER_ONLY",
            "development_item_count": 90,
            "start_index": 0,
            "single_process_local_execution": True,
            "runtime_thread_capacity_recheck_before_any_output": True,
            "capacity_recheck_before_and_after_each_item": True,
            "performance_claim": "NOT_AUTHORIZED",
            "FCI_reporting": "NOT_AUTHORIZED_UNTIL_ALL_90_TERMINAL",
            "release": "NOT_AUTHORIZED",
        },
        "academic_boundary": (
            "Only the exact frozen 90-item known-development order is authorized. "
            "Outcomes cannot change cases, methods, caps, rounds, thresholds, RNG, "
            "or order. FCI reporting and every performance claim remain forbidden."
        ),
    }
    artifact["authorization_digest"] = _digest(artifact)
    return artifact


def audit_authorization(*, require_current_preflight: bool = False) -> dict[str, bool]:
    readiness_checks = audit_readiness()
    artifact = _json(AUTHORIZATION_PATH)
    readiness = _json(READINESS_PATH)
    freeze = _freeze()
    ci_checks = _validate_readiness_ci_evidence(
        artifact.get("static_exact_CI_evidence", {}),
        readiness_commit=artifact["authorized_readiness_commit"],
    )
    owner = artifact.get("owner_governance", {})
    authorization = artifact.get("authorization", {})
    captured_preflight = artifact.get("local_preflight_at_authorization", {})
    checks = {
        "authorization_digest_valid": _digest_valid(
            artifact, "authorization_digest"
        ),
        "schema_and_decision_exact": artifact.get("schema")
        == "v5-final.s11-development-local-owner-execution-authorization.v1"
        and artifact.get("decision")
        == "GO_S11_EXACT_FROZEN_90_ITEM_DEVELOPMENT_ONLY",
        "readiness_still_valid": all(readiness_checks.values()),
        "readiness_bound_exactly": artifact["readiness"]["sha256"]
        == _sha(READINESS_PATH)
        and artifact["readiness"]["readiness_digest"]
        == readiness["readiness_digest"],
        "freeze_bound_exactly": artifact["freeze"]["sha256"]
        == _sha(FREEZE_OUTPUT)
        and artifact["freeze"]["freeze_digest"] == freeze["freeze_digest"],
        "plan_digest_exact": artifact.get("plan_digest") == _plan()["plan_digest"],
        "static_exact_CI_checks_passed": all(ci_checks.values())
        and all(artifact.get("static_exact_CI_checks", {}).values()),
        "captured_checks_passed": _exact_true_checks(
            artifact.get("checks"), AUTHORIZATION_CHECK_KEYS
        ),
        "captured_preflight_exact": isinstance(captured_preflight, Mapping)
        and _exact_true_checks(
            captured_preflight.get("checks"), PREFLIGHT_CHECK_KEYS
        )
        and captured_preflight.get("required_runtime")
        == captured_preflight.get("observed_runtime")
        and captured_preflight.get("required_threads")
        == captured_preflight.get("observed_threads")
        and _capacity_record_valid(captured_preflight.get("capacity"))
        and captured_preflight.get("capacity", {}).get("passed") is True,
        "authorized_commit_is_ancestor": _is_ancestor(
            artifact["authorized_readiness_commit"]
        ),
        "authorized_commit_is_exact_readiness_artifact_commit": artifact[
            "authorized_readiness_commit"
        ]
        == _last_commit_for(READINESS_PATH),
        "owner_governance_bound": owner.get("repository_owner") == OWNER
        and owner.get("prior_owner_freeze_path")
        == str(OWNER_FREEZE_PATH.relative_to(ROOT))
        and owner.get("prior_owner_freeze_sha256") == _sha(OWNER_FREEZE_PATH)
        and owner.get("continuation_directive") == OWNER_CONTINUATION_DIRECTIVE
        and owner.get("continuation_directive_digest")
        == _digest({"directive": OWNER_CONTINUATION_DIRECTIVE}),
        "authorization_scope_exact": authorization.get("development_execution")
        == "AUTHORIZED_EXACT_FROZEN_90_ITEM_ORDER_ONLY"
        and authorization.get("development_item_count") == 90
        and authorization.get("start_index") == 0
        and authorization.get("single_process_local_execution") is True
        and authorization.get("runtime_thread_capacity_recheck_before_any_output")
        is True
        and authorization.get("capacity_recheck_before_and_after_each_item") is True
        and authorization.get("performance_claim") == "NOT_AUTHORIZED"
        and authorization.get("FCI_reporting")
        == "NOT_AUTHORIZED_UNTIL_ALL_90_TERMINAL",
        "release_blocked": authorization.get("release") == "NOT_AUTHORIZED",
        "zero_outcome_before_authorization": artifact.get(
            "candidate_molecular_energy_evaluations_before_authorization"
        )
        == 0,
        "current_preflight_passed_if_required": not require_current_preflight
        or all(_require_local_preflight()["checks"].values()),
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S11DevelopmentRunnerError(
            "S11 authorization audit failed: " + ", ".join(failures)
        )
    return checks


def _event_operation_counts(state: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in state.work_events:
        counts[event.operation] = counts.get(event.operation, 0) + int(event.units)
    return dict(sorted(counts.items()))


def _receipt_for(
    *, plan: Mapping[str, Any], item: Mapping[str, Any], index: int,
    dispatch: Mapping[str, Any], capacity_before_resume: Mapping[str, Any],
    capacity_after: Mapping[str, Any], orchestrator_elapsed_seconds: float,
    result: Mapping[str, Any]
) -> dict[str, Any]:
    key = core._item_key(index, item)
    request, cap = core._request(plan, item)
    raw_root = RAW_DIR / key
    state = core.replay_raw_ledger(
        raw_root, request=request, cap=cap, require_terminal=True
    )
    terminal = dict(state.terminal or {})
    if terminal.get("terminal_status") not in core.TERMINAL_STATUSES:
        raise S11DevelopmentRunnerError("S11 item terminal status is invalid")
    if result.get("recovered", {}).get("terminal") != terminal:
        raise S11DevelopmentRunnerError("S11 result and raw terminal differ")
    operation_counts = _event_operation_counts(state)
    outcome = result.get("outcome", {})
    telemetry = outcome.get("telemetry", []) if isinstance(outcome, dict) else []
    receipt = {
        "schema": "v5-final.s11-development-item-receipt.v1",
        "queue_index": index,
        "queue_item_id": item["queue_item_id"],
        "case_id": item["case_id"],
        "method_id": item["method_id"],
        "work_envelope": item["work_envelope"],
        "plan_digest": plan["plan_digest"],
        "freeze_sha256": _sha(FREEZE_OUTPUT),
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
        "FCI_reporting_performed": False,
        "performance_claim": False,
    }
    receipt["receipt_digest"] = _digest(receipt)
    return receipt


def _validate_receipt(
    plan: Mapping[str, Any], item: Mapping[str, Any], index: int
) -> dict[str, Any]:
    key = core._item_key(index, item)
    receipt = _json(RECEIPT_DIR / f"{key}.json")
    if (
        not _digest_valid(receipt, "receipt_digest")
        or receipt.get("schema") != "v5-final.s11-development-item-receipt.v1"
        or receipt.get("queue_index") != index
        or receipt.get("queue_item_id") != item["queue_item_id"]
        or receipt.get("case_id") != item["case_id"]
        or receipt.get("method_id") != item["method_id"]
        or receipt.get("work_envelope") != item["work_envelope"]
        or receipt.get("plan_digest") != plan["plan_digest"]
        or receipt.get("freeze_sha256") != _sha(FREEZE_OUTPUT)
        or receipt.get("result_sha256") != _sha(RESULT_DIR / f"{key}.json")
        or receipt.get("raw_ledger_relative_path")
        != str((RAW_DIR / key).relative_to(ROOT))
        or receipt.get("result_relative_path")
        != str((RESULT_DIR / f"{key}.json").relative_to(ROOT))
        or not _capacity_record_valid(receipt.get("capacity_before_dispatch"))
        or not _capacity_record_valid(
            receipt.get("capacity_before_resume_or_execution")
        )
        or not _capacity_record_valid(receipt.get("capacity_after_terminal"))
        or receipt.get("FCI_reporting_performed") is not False
        or receipt.get("performance_claim") is not False
    ):
        raise S11DevelopmentRunnerError("S11 item receipt binding is invalid")
    result = core._read_result(RESULT_DIR / f"{key}.json")
    if receipt["result_artifact_digest"] != result["artifact_digest"]:
        raise S11DevelopmentRunnerError("S11 receipt result digest differs")
    request, cap = core._request(plan, item)
    state = core.replay_raw_ledger(
        RAW_DIR / key, request=request, cap=cap, require_terminal=True
    )
    if (
        receipt["raw_terminal_record_digest"] != state.records[-1]["record_digest"]
        or receipt["terminal_status"] != state.terminal["terminal_status"]
        or receipt["work_total"] != asdict(state.work_total)
        or receipt["work_operation_units"] != _event_operation_counts(state)
        or receipt.get("candidate_energy_evaluations")
        != _event_operation_counts(state).get("candidate-energy-evaluation", 0)
        or receipt.get("source_energy_evaluations")
        != _event_operation_counts(state).get("source-energy-evaluation", 0)
    ):
        raise S11DevelopmentRunnerError(
            "S11 receipt differs from raw-ledger reconstruction"
        )
    return receipt


def _progress_snapshot(
    plan: Mapping[str, Any], receipts: list[Mapping[str, Any]]
) -> dict[str, Any]:
    totals = {component: 0 for component in core.WORK_COMPONENTS}
    terminal_counts = {status: 0 for status in sorted(core.TERMINAL_STATUSES)}
    for receipt in receipts:
        terminal_counts[receipt["terminal_status"]] += 1
        for component in core.WORK_COMPONENTS:
            totals[component] += int(receipt["work_total"][component])
    complete = len(receipts) == len(plan["items"])
    snapshot = {
        "schema": "v5-final.s11-development-progress.v1",
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
        "FCI_reporting_performed": False,
        "complete": complete,
        "authorization": {
            "development_execution": (
                "AUTHORIZED_BY_COMMITTED_S11_ARTIFACT"
                if AUTHORIZATION_PATH.exists()
                else "NOT_AUTHORIZED"
            ),
            "S12_post_outcome_analysis": (
                "AUTHORIZED_AFTER_ALL_90_TERMINAL" if complete else "NOT_AUTHORIZED"
            ),
            "FCI_reporting": (
                "AUTHORIZED_POST_TERMINAL_S12_ONLY"
                if complete
                else "NOT_AUTHORIZED_UNTIL_ALL_90_TERMINAL"
            ),
            "performance_claim": "NOT_AUTHORIZED",
            "release": "NOT_AUTHORIZED",
        },
    }
    snapshot["progress_digest"] = _digest(snapshot)
    return snapshot


def _write_dispatch(
    plan: Mapping[str, Any], item: Mapping[str, Any], index: int
) -> dict[str, Any]:
    key = core._item_key(index, item)
    path = DISPATCH_DIR / f"{key}.json"
    if path.exists():
        dispatch = _json(path)
        if (
            not _digest_valid(dispatch, "dispatch_digest")
            or dispatch.get("schema") != "v5-final.s11-development-item-dispatch.v1"
            or dispatch.get("queue_index") != index
            or dispatch.get("queue_item_id") != item["queue_item_id"]
            or dispatch.get("plan_digest") != plan["plan_digest"]
            or dispatch.get("authorization_sha256") != _sha(AUTHORIZATION_PATH)
            or not _capacity_record_valid(dispatch.get("capacity_before_dispatch"))
            or dispatch.get("capacity_before_dispatch", {}).get("passed") is not True
        ):
            raise S11DevelopmentRunnerError("existing S11 dispatch is invalid")
        return dispatch
    capacity = core._current_capacity()
    if not capacity["passed"]:
        raise S11DevelopmentRunnerError("capacity failed before S11 item dispatch")
    dispatch = {
        "schema": "v5-final.s11-development-item-dispatch.v1",
        "queue_index": index,
        "queue_item_id": item["queue_item_id"],
        "case_id": item["case_id"],
        "method_id": item["method_id"],
        "work_envelope": item["work_envelope"],
        "plan_digest": plan["plan_digest"],
        "freeze_sha256": _sha(FREEZE_OUTPUT),
        "authorization_sha256": _sha(AUTHORIZATION_PATH),
        "capacity_before_dispatch": capacity,
        "FCI_reporting_authorized": False,
        "performance_claim_authorized": False,
    }
    dispatch["dispatch_digest"] = _digest(dispatch)
    write_json_exclusive(path, dispatch)
    return dispatch


def _kernel_failure_result(
    plan: Mapping[str, Any], item: Mapping[str, Any], index: int,
    error: BaseException
) -> dict[str, Any]:
    key = core._item_key(index, item)
    request, cap = core._request(plan, item)
    recovered = core.recover_terminal_result(
        RAW_DIR / key, request=request, cap=cap
    )
    if recovered["terminal"]["terminal_status"] != "KERNEL_FAILURE":
        raise S11DevelopmentRunnerError(
            "raised S11 item lacks a durable kernel-failure terminal"
        )
    artifact = {
        "schema": "v5-final.parent-native-item-result.v1",
        "request": request.payload() | {"request_id": request.request_id},
        "outcome": {
            "queue_item_id": item["queue_item_id"],
            "terminal_status": "KERNEL_FAILURE",
            "exception_type": type(error).__name__,
            "FCI_reporting_performed": False,
            "performance_evidence": False,
        },
        "outcome_checkpoint_digest": None,
        "recovered": recovered,
    }
    artifact["artifact_digest"] = _digest(artifact)
    output = RESULT_DIR / f"{key}.json"
    if output.exists():
        if _json(output) != artifact:
            raise S11DevelopmentRunnerError(
                "existing S11 kernel-failure result differs"
            )
    else:
        write_json_exclusive(output, artifact)
    return artifact


def _readiness_bridge() -> dict[str, bool]:
    return audit_readiness()


def _authorization_bridge() -> dict[str, bool]:
    return audit_authorization(require_current_preflight=True)


_LOCK = threading.RLock()


@contextmanager
def _core_scope() -> Iterator[None]:
    overrides = {
        "S9_DIR": EXECUTION_DIR,
        "PLAN_PATH": PLAN_PATH,
        "READINESS_PATH": READINESS_PATH,
        "AUTHORIZATION_PATH": AUTHORIZATION_PATH,
        "DISPATCH_DIR": DISPATCH_DIR,
        "RAW_DIR": RAW_DIR,
        "RESULT_DIR": RESULT_DIR,
        "RECEIPT_DIR": RECEIPT_DIR,
        "PROGRESS_DIR": PROGRESS_DIR,
        "COMPLETENESS_PATH": COMPLETENESS_PATH,
        "RUNNER_SOURCES": RUNNER_SOURCES,
        "execute_frozen_item": execute_development_item_v1,
        "_plan": _plan,
        "audit_readiness": _readiness_bridge,
        "audit_authorization": _authorization_bridge,
        "_receipt_for": _receipt_for,
        "_validate_receipt": _validate_receipt,
        "_progress_snapshot": _progress_snapshot,
        "_write_dispatch": _write_dispatch,
        "_kernel_failure_result": _kernel_failure_result,
    }
    with _LOCK:
        previous = {name: getattr(core, name) for name in overrides}
        try:
            for name, value in overrides.items():
                setattr(core, name, value)
            yield
            changed = [
                name for name, value in overrides.items() if getattr(core, name) is not value
            ]
        finally:
            for name, value in previous.items():
                setattr(core, name, value)
        if changed:
            raise S11DevelopmentRunnerError(
                "S11 core execution scope changed unexpectedly: " + ", ".join(changed)
            )


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
        raise S11DevelopmentRunnerError(
            "S11 namespace permanently halted: kernel="
            + ",".join(kernel)
            + "; capacity="
            + ",".join(capacity)
        )


def _progress() -> dict[str, Any]:
    plan = _plan()
    if not READINESS_PATH.exists():
        if _outputs_started():
            raise S11DevelopmentRunnerError("S11 output exists before readiness")
        receipts: list[dict[str, Any]] = []
    else:
        with _core_scope():
            receipts = core._completed_receipts(
                plan, allow_inflight=False, require_progress=True
            )
    return _progress_snapshot(plan, receipts)


def audit_progress(*, allow_inflight: bool = False) -> dict[str, Any]:
    plan = _plan()
    readiness_checks = audit_readiness() if READINESS_PATH.exists() else {}
    authorization_checks = (
        audit_authorization(require_current_preflight=False)
        if AUTHORIZATION_PATH.exists()
        else {}
    )
    if not READINESS_PATH.exists():
        receipts: list[dict[str, Any]] = []
    else:
        with _core_scope():
            receipts = core._completed_receipts(
                plan, allow_inflight=allow_inflight, require_progress=True
            )
    progress = _progress_snapshot(plan, receipts)
    checks = {
        "readiness_valid_if_present": not READINESS_PATH.exists()
        or all(readiness_checks.values()),
        "authorization_valid_if_present": not AUTHORIZATION_PATH.exists()
        or all(authorization_checks.values()),
        "completed_items_form_exact_prefix": progress["completed_terminal_count"]
        == len(receipts),
        "candidate_energy_reconstructed_from_raw_events": progress[
            "candidate_energy_evaluations"
        ]
        == sum(value["candidate_energy_evaluations"] for value in receipts),
        "FCI_not_reported_during_development": progress["FCI_reporting_performed"]
        is False,
        "performance_claim_blocked": progress["authorization"][
            "performance_claim"
        ]
        == "NOT_AUTHORIZED",
    }
    if not all(checks.values()):
        raise S11DevelopmentRunnerError("S11 progress audit failed")
    return {"checks": checks, "progress": progress}


def build_static_audit() -> dict[str, Any]:
    plan = _plan()
    freeze = _freeze()
    readiness_checks = audit_readiness() if READINESS_PATH.exists() else {}
    authorization_checks = (
        audit_authorization(require_current_preflight=False)
        if AUTHORIZATION_PATH.exists()
        else {}
    )
    progress = _progress()
    completed = progress["completed_terminal_count"]
    kernel_failures = progress["terminal_status_counts"]["KERNEL_FAILURE"]
    capacity_passed = progress["all_post_item_capacity_checks_passed"]
    namespace_halted = completed > 0 and (
        kernel_failures > 0 or not capacity_passed
    )
    completeness_valid = True
    if COMPLETENESS_PATH.exists():
        completeness = _json(COMPLETENESS_PATH)
        completeness_valid = (
            _digest_valid(completeness, "completeness_digest")
            and completeness.get("schema")
            == "v5-final.s11-development-completeness.v1"
            and completeness.get("plan_digest") == plan["plan_digest"]
            and completeness.get("plan_sha256") == _sha(PLAN_PATH)
            and completeness.get("freeze_sha256") == _sha(FREEZE_OUTPUT)
            and completeness.get("expected_item_count") == 90
            and completeness.get("expected_queue_nonempty") is True
            and completeness.get("progress") == progress
            and progress.get("complete") is True
            and _exact_true_checks(
                completeness.get("checks"), COMPLETENESS_CHECK_KEYS
            )
        )
    checks = {
        "freeze_static_audit_passed": all(audit_freeze_static().values()),
        "frozen_plan_exact": len(plan["items"]) == 90,
        "readiness_valid_if_present": not READINESS_PATH.exists()
        or all(readiness_checks.values()),
        "authorization_valid_if_present": not AUTHORIZATION_PATH.exists()
        or all(authorization_checks.values()),
        "authorization_precedes_any_execution": completed == 0
        or AUTHORIZATION_PATH.exists(),
        "exact_prefix_integrity": len(progress["completed_queue_item_ids"])
        == completed,
        "completeness_valid_if_present": completeness_valid,
        "complete_only_at_90": progress["complete"] is (completed == 90),
        "namespace_halt_policy_exact": (
            not namespace_halted
            and kernel_failures == 0
            and capacity_passed is True
        )
        or namespace_halted,
        "FCI_not_reported_during_development": progress["FCI_reporting_performed"]
        is False,
        "performance_claim_blocked": progress["authorization"][
            "performance_claim"
        ]
        == "NOT_AUTHORIZED",
        "freeze_was_zero_outcome": freeze["candidate_molecular_energy_evaluations"]
        == 0,
    }
    if frozenset(checks) != STATIC_AUDIT_CHECK_KEYS:
        raise S11DevelopmentRunnerError("S11 static CI audit check set drifted")
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S11DevelopmentRunnerError(
            "S11 static CI audit failed: " + ", ".join(failures)
        )
    if namespace_halted:
        decision = "NO_GO_S11_NAMESPACE_HALTED"
    elif progress["complete"]:
        decision = "S11_DEVELOPMENT_COMPLETE_AWAITING_S12"
    elif AUTHORIZATION_PATH.exists():
        decision = "S11_AUTHORIZED_AWAITING_LOCAL_EXECUTION"
    elif READINESS_PATH.exists():
        decision = "READY_AWAITING_S11_OWNER_AUTHORIZATION"
    else:
        decision = "S11_FREEZE_VALID_EXECUTION_NOT_AUTHORIZED"
    report = {
        "schema": "v5-final.s11-static-ci-audit.v1",
        "validated_exact_commit": _git("rev-parse", "HEAD"),
        "status": "PASS_S11_STATIC_INTEGRITY",
        "decision": decision,
        "run_namespace": RUN_NAMESPACE,
        "execution_venue": EXECUTION_VENUE,
        "freeze": {
            "path": str(FREEZE_OUTPUT.relative_to(ROOT)),
            "sha256": _sha(FREEZE_OUTPUT),
            "freeze_digest": freeze["freeze_digest"],
        },
        "readiness_audit": readiness_checks,
        "authorization_audit": authorization_checks,
        "progress": progress,
        "namespace_halted": namespace_halted,
        "checks": checks,
        "candidate_molecular_energy_evaluations": progress[
            "candidate_energy_evaluations"
        ],
        "authorization": progress["authorization"],
    }
    report["audit_digest"] = _digest(report)
    return report


def run_development(*, max_items: int | None = None) -> dict[str, Any]:
    if max_items is not None and (
        isinstance(max_items, bool) or not isinstance(max_items, int) or max_items < 1
    ):
        raise S11DevelopmentRunnerError("max-items must be a positive integer")
    _require_local_preflight()
    audit_authorization(require_current_preflight=True)
    _require_resumable_namespace()
    plan = _plan()
    for directory in (DISPATCH_DIR, RAW_DIR, RESULT_DIR, RECEIPT_DIR, PROGRESS_DIR):
        directory.mkdir(parents=True, exist_ok=True)
    with _core_scope():
        completed = core._completed_receipts(
            plan, allow_inflight=True, require_progress=False
        )
        core._ensure_progress_snapshots(plan, completed)
        if completed and not completed[-1]["capacity_after_terminal"]["passed"]:
            raise S11DevelopmentRunnerError(
                "prior item exhausted safe capacity; resume forbidden"
            )
        limit = len(plan["items"]) if max_items is None else min(
            len(plan["items"]), len(completed) + max_items
        )
        for index in range(len(completed), limit):
            core._run_item(plan, plan["items"][index], index)
    report = audit_progress(allow_inflight=False)
    progress = report["progress"]
    if progress["complete"] and not COMPLETENESS_PATH.exists():
        completeness = {
            "schema": "v5-final.s11-development-completeness.v1",
            "plan_digest": plan["plan_digest"],
            "plan_sha256": _sha(PLAN_PATH),
            "freeze_sha256": _sha(FREEZE_OUTPUT),
            "authorization_sha256": _sha(AUTHORIZATION_PATH),
            "expected_queue_nonempty": True,
            "expected_item_count": 90,
            "progress": progress,
            "checks": {
                "all_90_unique_terminals": progress["completed_terminal_count"] == 90
                and len(set(progress["completed_queue_item_ids"])) == 90,
                "every_and_only_frozen_item_terminal": progress[
                    "completed_queue_item_ids"
                ]
                == [item["queue_item_id"] for item in plan["items"]],
                "raw_ledgers_reconstructed": True,
                "no_kernel_failure": progress["terminal_status_counts"][
                    "KERNEL_FAILURE"
                ]
                == 0,
                "all_post_item_capacity_checks_passed": progress[
                    "all_post_item_capacity_checks_passed"
                ],
                "candidate_energy_reconstructed_from_raw_events": report["checks"][
                    "candidate_energy_reconstructed_from_raw_events"
                ],
                "FCI_not_reported_during_development": progress[
                    "FCI_reporting_performed"
                ]
                is False,
                "performance_claim_not_made": progress["authorization"][
                    "performance_claim"
                ]
                == "NOT_AUTHORIZED",
            },
            "authorization": {
                "S12_post_outcome_integrity_analysis": "AUTHORIZED",
                "FCI_reporting": "AUTHORIZED_POST_TERMINAL_S12_ONLY",
                "performance_claim": "NOT_AUTHORIZED_PENDING_S12",
                "release": "NOT_AUTHORIZED_PENDING_S12",
            },
        }
        completeness["completeness_digest"] = _digest(completeness)
        write_json_exclusive(COMPLETENESS_PATH, completeness)
    return report


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
        EXECUTION_DIR.mkdir(parents=True, exist_ok=False)
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
            raise S11DevelopmentRunnerError(
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
            raise S11DevelopmentRunnerError(
                "authorization requires static exact-CI evidence"
            )
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
        print(json.dumps(run_development(max_items=args.max_items), sort_keys=True))
        return
    print(json.dumps(build_static_audit(), sort_keys=True))


if __name__ == "__main__":
    main()

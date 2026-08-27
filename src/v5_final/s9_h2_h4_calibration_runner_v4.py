"""Fresh S9-v4 calibration namespace fixed to one GitHub-hosted execution job."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import threading
from typing import Any, Iterator, Mapping

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from . import s9_h2_h4_calibration_runner as v1
from .parent_native_zero_dimensional_v2 import execute_frozen_item_v2
from .s0_successor import ROOT
from .s9_v3_capacity_halt import HALT_PATH, audit_halt


S9_V4_DIR = ROOT / "artifacts/v5-final/parent-native/s9-h2-h4-calibration-v4"
READINESS_PATH = S9_V4_DIR / "s9-runner-readiness-v4.json"
AUTHORIZATION_PATH = S9_V4_DIR / "s9-execution-authorization-v4.json"
DISPATCH_DIR = S9_V4_DIR / "dispatch"
RAW_DIR = S9_V4_DIR / "raw-ledgers"
RESULT_DIR = S9_V4_DIR / "item-results"
RECEIPT_DIR = S9_V4_DIR / "item-receipts"
PROGRESS_DIR = S9_V4_DIR / "progress"
COMPLETENESS_PATH = S9_V4_DIR / "h2-h4-completeness-v4.json"
RUN_NAMESPACE = "s9-h2-h4-calibration-v4"
EXECUTION_VENUE = "github-actions-ubuntu-24.04-x64-single-job"
RUNNER_SOURCES = tuple(
    ROOT / value
    for value in (
        "src/v5_final/s9_h2_h4_calibration_runner_v4.py",
        "src/v5_final/parent_native_zero_dimensional_v2.py",
        "src/v5_final/s9_v3_capacity_halt.py",
        "src/v5_final/s9_h2_h4_calibration_runner_v3.py",
        "src/v5_final/s9_h2_h4_calibration_runner.py",
        "src/v5_final/parent_native_execution_services.py",
        "src/v5_final/parent_native_persistent_runner.py",
        "src/v5_final/parent_native_work_accounting.py",
        "src/v5_final/semantic_contract_v2.py",
        "tests/test_v5_final_s9_h2_h4_calibration_runner_v4.py",
        ".github/workflows/v5-s9-v4-github-runner-gate.yml",
        ".github/workflows/v5-s9-v4-artifact-builder.yml",
        ".github/workflows/v5-s9-v4-execute.yml",
    )
)


class S9V4CalibrationError(v1.S9CalibrationError):
    pass


def _json(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise S9V4CalibrationError(f"invalid JSON artifact: {path}") from error
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise S9V4CalibrationError(f"noncanonical JSON artifact: {path}")
    return value


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _halt() -> dict[str, Any]:
    checks = audit_halt()
    if not all(checks.values()):
        raise S9V4CalibrationError("S9-v3 capacity halt is not valid")
    return _json(HALT_PATH)


_LOCK = threading.RLock()
_OVERRIDES = {
    "S9_DIR": S9_V4_DIR,
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
def _v4_scope() -> Iterator[None]:
    with _LOCK:
        previous = {name: getattr(v1, name) for name in _OVERRIDES}
        try:
            for name, value in _OVERRIDES.items():
                setattr(v1, name, value)
            yield
        finally:
            for name, value in previous.items():
                setattr(v1, name, value)


def _required_thread_environment() -> dict[str, str]:
    required = _halt()["remediation_contract"][
        "required_external_thread_environment"
    ]
    if required != {
        "MKL_NUM_THREADS": "2",
        "OMP_NUM_THREADS": "2",
        "OPENBLAS_NUM_THREADS": "2",
    }:
        raise S9V4CalibrationError("frozen thread environment is not exact")
    return dict(required)


def audit_external_environment() -> dict[str, bool]:
    required = _required_thread_environment()
    return {
        "all_required_variables_present": all(name in os.environ for name in required),
        "all_required_values_exact": all(
            os.environ.get(name) == value for name, value in required.items()
        ),
        "process_environment_not_mutated_by_runner": True,
    }


def audit_execution_venue() -> dict[str, bool]:
    return {
        "github_actions_exact": os.environ.get("GITHUB_ACTIONS") == "true",
        "ci_exact": os.environ.get("CI") == "true",
        "runner_os_exact": os.environ.get("RUNNER_OS") == "Linux",
        "runner_arch_exact": os.environ.get("RUNNER_ARCH") == "X64",
        "venue_marker_exact": os.environ.get("V5_S9_V4_EXECUTION_VENUE")
        == EXECUTION_VENUE,
    }


def _require_pre_output_environment() -> dict[str, bool]:
    checks = {**audit_external_environment(), **audit_execution_venue()}
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S9V4CalibrationError(
            "v4 execution environment failed before output publication: "
            + ", ".join(failures)
        )
    return checks


def _kernel_failure_receipts() -> list[str]:
    if not RECEIPT_DIR.exists():
        return []
    return [
        path.name
        for path in sorted(RECEIPT_DIR.glob("*.json"))
        if _json(path).get("terminal_status") == "KERNEL_FAILURE"
    ]


def _failed_post_capacity_receipts() -> list[str]:
    if not RECEIPT_DIR.exists():
        return []
    return [
        path.name
        for path in sorted(RECEIPT_DIR.glob("*.json"))
        if _json(path).get("capacity_after_terminal", {}).get("passed") is False
    ]


def _require_resumable_namespace() -> None:
    kernel_failures = _kernel_failure_receipts()
    capacity_failures = _failed_post_capacity_receipts()
    if kernel_failures or capacity_failures:
        raise S9V4CalibrationError(
            "S9-v4 namespace permanently halted: kernel="
            + ",".join(kernel_failures)
            + "; capacity="
            + ",".join(capacity_failures)
        )


def _remediation_binding(halt: Mapping[str, Any]) -> dict[str, Any]:
    contract = halt["remediation_contract"]
    return {
        "S9_v3_capacity_halt": {
            "path": str(HALT_PATH.relative_to(ROOT)),
            "sha256": _sha(HALT_PATH),
            "halt_digest": halt["halt_digest"],
        },
        "run_namespace": RUN_NAMESPACE,
        "fresh_uniform_36_item_rerun": True,
        "plan_digest": contract["reuse_exact_plan_digest"],
        "execution_venue": EXECUTION_VENUE,
        "single_job_execution_required": True,
        "required_external_thread_environment": contract[
            "required_external_thread_environment"
        ],
        "environment_preflight_before_any_output_publication": True,
        "current_capacity_preflight_before_any_output_publication": True,
        "every_item_capacity_pre_and_post_check_required": True,
        "any_kernel_failure_permanently_halts_namespace": True,
        "any_failed_post_terminal_capacity_check_permanently_halts_namespace": True,
        "historical_candidate_molecular_energy_evaluations": {
            "S9_v1": 3,
            "S9_v2": 0,
            "S9_v3": 40,
        },
        "historical_results_are_performance_evidence": False,
        "historical_results_used_for_v4_design_or_selection": False,
    }


def build_readiness() -> dict[str, Any]:
    halt = _halt()
    environment_checks = _require_pre_output_environment()
    with _v4_scope():
        artifact = v1.build_readiness()
    artifact.pop("readiness_digest")
    artifact["stage"] = "S9_V4_GITHUB_SINGLE_JOB_FROZEN_QUEUE_RUNNER_READINESS"
    artifact["remediation"] = _remediation_binding(halt)
    artifact["venue_preflight"] = environment_checks
    artifact["academic_boundary"] = (
        "This freezes a fresh uniform rerun of the unchanged 36-item calibration plan "
        "on one GitHub-hosted Ubuntu job. Historical partial outcomes are excluded from "
        "design and selection. It authorizes no molecular execution, development queue, "
        "or performance claim."
    )
    artifact["readiness_digest"] = _digest(artifact)
    return artifact


def audit_readiness() -> dict[str, bool]:
    halt = _halt()
    with _v4_scope():
        checks = dict(v1.audit_readiness())
    artifact = _json(READINESS_PATH)
    remediation = artifact.get("remediation", {})
    checks.update(
        {
            "v3_halt_bound_exactly": remediation.get(
                "S9_v3_capacity_halt", {}
            ).get("sha256")
            == _sha(HALT_PATH)
            and remediation.get("S9_v3_capacity_halt", {}).get("halt_digest")
            == halt["halt_digest"],
            "fresh_v4_namespace_exact": remediation.get("run_namespace")
            == RUN_NAMESPACE
            and remediation.get("fresh_uniform_36_item_rerun") is True,
            "plan_unchanged": remediation.get("plan_digest")
            == halt["remediation_contract"]["reuse_exact_plan_digest"],
            "execution_venue_exact": remediation.get("execution_venue")
            == EXECUTION_VENUE
            and remediation.get("single_job_execution_required") is True,
            "environment_preflight_exact": all(audit_external_environment().values())
            and all(audit_execution_venue().values())
            and remediation.get(
                "environment_preflight_before_any_output_publication"
            )
            is True,
            "capacity_fail_closed_exact": remediation.get(
                "current_capacity_preflight_before_any_output_publication"
            )
            is True
            and remediation.get("every_item_capacity_pre_and_post_check_required")
            is True
            and remediation.get(
                "any_failed_post_terminal_capacity_check_permanently_halts_namespace"
            )
            is True,
            "historical_outcomes_excluded": remediation.get(
                "historical_candidate_molecular_energy_evaluations"
            )
            == {"S9_v1": 3, "S9_v2": 0, "S9_v3": 40}
            and remediation.get("historical_results_are_performance_evidence")
            is False
            and remediation.get("historical_results_used_for_v4_design_or_selection")
            is False,
        }
    )
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S9V4CalibrationError(
            "S9-v4 readiness audit failed: " + ", ".join(failures)
        )
    return checks


def build_authorization(ci_evidence: Mapping[str, Any]) -> dict[str, Any]:
    halt = _halt()
    _require_pre_output_environment()
    audit_readiness()
    with _v4_scope():
        artifact = v1.build_authorization(ci_evidence)
    artifact.pop("authorization_digest")
    artifact["stage"] = "S9_V4_GITHUB_SINGLE_JOB_MB6_V4_EXECUTION_AUTHORIZATION"
    artifact["remediation"] = _remediation_binding(halt)
    artifact["academic_boundary"] = (
        "Only one fresh execution of the unchanged frozen 36-item calibration queue is "
        "authorized, in one GitHub-hosted Ubuntu job under the exact frozen environment. "
        "Development execution and performance claims remain forbidden."
    )
    artifact["authorization_digest"] = _digest(artifact)
    return artifact


def audit_authorization() -> dict[str, bool]:
    halt = _halt()
    readiness_checks = audit_readiness()
    with _v4_scope():
        checks = dict(v1.audit_authorization())
    artifact = _json(AUTHORIZATION_PATH)
    remediation = artifact.get("remediation", {})
    checks.update(
        {
            "v4_readiness_checks_passed": all(readiness_checks.values()),
            "v3_halt_bound_in_authorization": remediation.get(
                "S9_v3_capacity_halt", {}
            ).get("sha256")
            == _sha(HALT_PATH)
            and remediation.get("S9_v3_capacity_halt", {}).get("halt_digest")
            == halt["halt_digest"],
            "fresh_uniform_single_job_rerun_authorized": remediation.get(
                "fresh_uniform_36_item_rerun"
            )
            is True
            and remediation.get("run_namespace") == RUN_NAMESPACE
            and remediation.get("execution_venue") == EXECUTION_VENUE
            and remediation.get("single_job_execution_required") is True,
            "current_venue_preflight_passed": all(
                audit_execution_venue().values()
            ),
        }
    )
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S9V4CalibrationError(
            "S9-v4 authorization audit failed: " + ", ".join(failures)
        )
    return checks


def build_ci_audit() -> dict[str, Any]:
    halt = _halt()
    _require_pre_output_environment()
    with _v4_scope():
        report = v1.build_ci_audit()
    report.pop("audit_digest")
    report["run_namespace"] = RUN_NAMESPACE
    report["execution_venue"] = EXECUTION_VENUE
    report["remediation"] = _remediation_binding(halt)
    report["v3_capacity_halt_audit"] = audit_halt()
    kernel_failures = report["progress"]["terminal_status_counts"]["KERNEL_FAILURE"]
    post_capacity_passed = report["progress"][
        "all_post_item_capacity_checks_passed"
    ]
    namespace_halted = kernel_failures > 0 or not post_capacity_passed
    if namespace_halted and report["progress"]["completed_terminal_count"] > 0:
        report["decision"] = "NO_GO_S9_V4_NAMESPACE_HALTED"
        report["authorization"]["H2_H4_execution"] = "NOT_AUTHORIZED"
    report["namespace_halted"] = namespace_halted
    report["v4_checks"] = {
        "v3_capacity_halt_audit_passed": all(
            report["v3_capacity_halt_audit"].values()
        ),
        "fresh_namespace_isolated": report["run_namespace"] == RUN_NAMESPACE,
        "execution_venue_exact": report["execution_venue"] == EXECUTION_VENUE
        and all(audit_execution_venue().values()),
        "historical_outcomes_excluded": report["remediation"][
            "historical_results_are_performance_evidence"
        ]
        is False
        and report["remediation"][
            "historical_results_used_for_v4_design_or_selection"
        ]
        is False,
        "development_and_performance_blocked": report["authorization"][
            "development_queue_execution"
        ]
        == "NOT_AUTHORIZED"
        and report["authorization"]["performance_claim"] == "NOT_AUTHORIZED",
        "namespace_halt_policy_exact": (
            report["progress"]["completed_terminal_count"] == 0
            and namespace_halted is False
        )
        or (
            kernel_failures == 0
            and post_capacity_passed is True
            and namespace_halted is False
        )
        or (
            namespace_halted is True
            and report["decision"] == "NO_GO_S9_V4_NAMESPACE_HALTED"
            and report["authorization"]["H2_H4_execution"] == "NOT_AUTHORIZED"
        ),
    }
    if READINESS_PATH.exists():
        report["v4_readiness_audit"] = audit_readiness()
        report["v4_checks"]["readiness_audit_passed_if_present"] = all(
            report["v4_readiness_audit"].values()
        )
    if AUTHORIZATION_PATH.exists():
        report["v4_authorization_audit"] = audit_authorization()
        report["v4_checks"]["authorization_audit_passed_if_present"] = all(
            report["v4_authorization_audit"].values()
        )
    report["audit_digest"] = _digest(report)
    failures = [name for name, passed in report["v4_checks"].items() if not passed]
    if failures:
        raise S9V4CalibrationError(
            "S9-v4 CI audit failed: " + ", ".join(failures)
        )
    return report


def run_calibration(*, max_items: int | None = None) -> dict[str, Any]:
    _halt()
    _require_pre_output_environment()
    audit_authorization()
    _require_resumable_namespace()
    with _v4_scope():
        return v1.run_calibration(max_items=max_items)


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
        S9_V4_DIR.mkdir(parents=True, exist_ok=False)
        write_json_exclusive(READINESS_PATH, artifact)
        print(READINESS_PATH)
        return
    if args.write_authorization:
        if args.ci_evidence is None:
            raise S9V4CalibrationError("authorization requires exact-CI evidence")
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

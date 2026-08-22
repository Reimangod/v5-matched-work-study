"""Fresh S9-v3 calibration namespace with process-environment fail-closed gates."""

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
from .s9_v2_thread_environment_halt import HALT_PATH, audit_halt


S9_V3_DIR = ROOT / "artifacts/v5-final/parent-native/s9-h2-h4-calibration-v3"
READINESS_PATH = S9_V3_DIR / "s9-runner-readiness-v3.json"
AUTHORIZATION_PATH = S9_V3_DIR / "s9-execution-authorization-v3.json"
DISPATCH_DIR = S9_V3_DIR / "dispatch"
RAW_DIR = S9_V3_DIR / "raw-ledgers"
RESULT_DIR = S9_V3_DIR / "item-results"
RECEIPT_DIR = S9_V3_DIR / "item-receipts"
PROGRESS_DIR = S9_V3_DIR / "progress"
COMPLETENESS_PATH = S9_V3_DIR / "h2-h4-completeness-v3.json"
RUN_NAMESPACE = "s9-h2-h4-calibration-v3"
RUNNER_SOURCES = tuple(
    ROOT / value
    for value in (
        "src/v5_final/s9_h2_h4_calibration_runner_v3.py",
        "src/v5_final/parent_native_zero_dimensional_v2.py",
        "src/v5_final/s9_v2_thread_environment_halt.py",
        "src/v5_final/s9_h2_h4_calibration_runner_v2.py",
        "src/v5_final/s9_h2_h4_calibration_runner.py",
        "src/v5_final/parent_native_execution_services.py",
        "src/v5_final/parent_native_persistent_runner.py",
        "src/v5_final/parent_native_work_accounting.py",
        "src/v5_final/semantic_contract_v2.py",
        "tests/test_v5_final_s9_h2_h4_calibration_runner_v3.py",
        ".github/workflows/v5-s9-v3-environment-gate.yml",
    )
)


class S9V3CalibrationError(v1.S9CalibrationError):
    pass


def _json(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise S9V3CalibrationError(f"invalid JSON artifact: {path}") from error
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise S9V3CalibrationError(f"noncanonical JSON artifact: {path}")
    return value


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _halt() -> dict[str, Any]:
    checks = audit_halt()
    if not all(checks.values()):
        raise S9V3CalibrationError("S9-v2 halt is not valid")
    return _json(HALT_PATH)


_LOCK = threading.RLock()
_OVERRIDES = {
    "S9_DIR": S9_V3_DIR,
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
def _v3_scope() -> Iterator[None]:
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
    halt = _halt()
    required = halt["remediation_contract"]["required_external_thread_environment"]
    if required != {
        "MKL_NUM_THREADS": "2",
        "OMP_NUM_THREADS": "2",
        "OPENBLAS_NUM_THREADS": "2",
    }:
        raise S9V3CalibrationError("frozen thread environment is not exact")
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


def _require_external_environment() -> dict[str, bool]:
    checks = audit_external_environment()
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S9V3CalibrationError(
            "external thread environment preflight failed before output publication: "
            + ", ".join(failures)
        )
    return checks


def _kernel_failure_receipts(receipt_dir: Path = RECEIPT_DIR) -> list[str]:
    if not receipt_dir.exists():
        return []
    failures: list[str] = []
    for path in sorted(receipt_dir.glob("*.json")):
        receipt = _json(path)
        if receipt.get("terminal_status") == "KERNEL_FAILURE":
            failures.append(path.name)
    return failures


def _require_resumable_namespace() -> None:
    failures = _kernel_failure_receipts()
    if failures:
        raise S9V3CalibrationError(
            "S9-v3 namespace permanently halted by kernel failure: "
            + ", ".join(failures)
        )


def _remediation_binding(halt: Mapping[str, Any]) -> dict[str, Any]:
    contract = halt["remediation_contract"]
    return {
        "S9_v2_halt": {
            "path": str(HALT_PATH.relative_to(ROOT)),
            "sha256": _sha(HALT_PATH),
            "halt_digest": halt["halt_digest"],
        },
        "run_namespace": RUN_NAMESPACE,
        "fresh_uniform_36_item_rerun": True,
        "plan_digest": contract["reuse_exact_plan_digest"],
        "required_external_thread_environment": contract[
            "required_external_thread_environment"
        ],
        "environment_preflight_before_any_output_publication": True,
        "environment_values_mutated_inside_python_process": False,
        "any_kernel_failure_permanently_halts_namespace": True,
        "historical_v1_candidate_molecular_energy_evaluations": 3,
        "historical_v2_candidate_molecular_energy_evaluations": 0,
        "historical_v1_results_are_performance_evidence": False,
        "historical_v2_results_are_performance_evidence": False,
    }


def build_readiness() -> dict[str, Any]:
    halt = _halt()
    with _v3_scope():
        artifact = v1.build_readiness()
    artifact.pop("readiness_digest")
    artifact["stage"] = "S9_V3_ENVIRONMENT_GATED_FROZEN_QUEUE_RUNNER_READINESS"
    artifact["remediation"] = _remediation_binding(halt)
    artifact["academic_boundary"] = (
        "This freezes a fresh uniform rerun of the unchanged 36-item calibration plan. "
        "It requires the frozen thread environment before any output publication and "
        "permanently halts the namespace after any kernel failure. It authorizes no "
        "molecular execution, development queue, or performance claim."
    )
    artifact["readiness_digest"] = _digest(artifact)
    return artifact


def audit_readiness() -> dict[str, bool]:
    halt = _halt()
    with _v3_scope():
        checks = dict(v1.audit_readiness())
    artifact = _json(READINESS_PATH)
    remediation = artifact.get("remediation", {})
    checks.update(
        {
            "v2_halt_bound_exactly": remediation.get("S9_v2_halt", {}).get(
                "sha256"
            )
            == _sha(HALT_PATH)
            and remediation.get("S9_v2_halt", {}).get("halt_digest")
            == halt["halt_digest"],
            "fresh_v3_namespace_exact": remediation.get("run_namespace")
            == RUN_NAMESPACE
            and remediation.get("fresh_uniform_36_item_rerun") is True,
            "plan_unchanged": remediation.get("plan_digest")
            == halt["remediation_contract"]["reuse_exact_plan_digest"],
            "external_environment_contract_exact": remediation.get(
                "required_external_thread_environment"
            )
            == halt["remediation_contract"]["required_external_thread_environment"]
            and remediation.get(
                "environment_preflight_before_any_output_publication"
            )
            is True
            and remediation.get("environment_values_mutated_inside_python_process")
            is False,
            "kernel_failure_halt_contract_exact": remediation.get(
                "any_kernel_failure_permanently_halts_namespace"
            )
            is True,
            "historical_outcomes_excluded_from_performance": remediation.get(
                "historical_v1_results_are_performance_evidence"
            )
            is False
            and remediation.get("historical_v2_results_are_performance_evidence")
            is False,
        }
    )
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S9V3CalibrationError(
            "S9-v3 readiness audit failed: " + ", ".join(failures)
        )
    return checks


def build_authorization(ci_evidence: Mapping[str, Any]) -> dict[str, Any]:
    halt = _halt()
    audit_readiness()
    with _v3_scope():
        artifact = v1.build_authorization(ci_evidence)
    artifact.pop("authorization_digest")
    artifact["stage"] = "S9_V3_ENVIRONMENT_GATED_MB6_V4_EXECUTION_AUTHORIZATION"
    artifact["remediation"] = _remediation_binding(halt)
    artifact["academic_boundary"] = (
        "Only a fresh execution of the unchanged frozen 36-item calibration queue is "
        "authorized, under one implementation and the externally supplied exact frozen "
        "thread environment. Development execution and performance claims remain forbidden."
    )
    artifact["authorization_digest"] = _digest(artifact)
    return artifact


def audit_authorization() -> dict[str, bool]:
    halt = _halt()
    readiness_checks = audit_readiness()
    with _v3_scope():
        checks = dict(v1.audit_authorization())
    artifact = _json(AUTHORIZATION_PATH)
    remediation = artifact.get("remediation", {})
    checks.update(
        {
            "v3_readiness_checks_passed": all(readiness_checks.values()),
            "v2_halt_bound_in_authorization": remediation.get(
                "S9_v2_halt", {}
            ).get("sha256")
            == _sha(HALT_PATH)
            and remediation.get("S9_v2_halt", {}).get("halt_digest")
            == halt["halt_digest"],
            "fresh_uniform_rerun_authorized": remediation.get(
                "fresh_uniform_36_item_rerun"
            )
            is True
            and remediation.get("run_namespace") == RUN_NAMESPACE,
            "external_environment_gate_authorized": remediation.get(
                "environment_preflight_before_any_output_publication"
            )
            is True
            and remediation.get("environment_values_mutated_inside_python_process")
            is False,
            "kernel_failure_halt_authorized": remediation.get(
                "any_kernel_failure_permanently_halts_namespace"
            )
            is True,
        }
    )
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S9V3CalibrationError(
            "S9-v3 authorization audit failed: " + ", ".join(failures)
        )
    return checks


def build_ci_audit() -> dict[str, Any]:
    halt = _halt()
    with _v3_scope():
        report = v1.build_ci_audit()
    report.pop("audit_digest")
    report["run_namespace"] = RUN_NAMESPACE
    report["remediation"] = _remediation_binding(halt)
    report["v2_halt_audit"] = audit_halt()
    kernel_failures = report["progress"]["terminal_status_counts"]["KERNEL_FAILURE"]
    namespace_halted = kernel_failures > 0
    if namespace_halted:
        report["decision"] = "NO_GO_S9_V3_KERNEL_FAILURE_NAMESPACE_HALTED"
        report["authorization"]["H2_H4_execution"] = "NOT_AUTHORIZED"
    report["namespace_halted"] = namespace_halted
    report["v3_checks"] = {
        "v2_halt_audit_passed": all(report["v2_halt_audit"].values()),
        "fresh_namespace_isolated": report["remediation"]["run_namespace"]
        == RUN_NAMESPACE,
        "historical_results_not_performance_evidence": report["remediation"][
            "historical_v1_results_are_performance_evidence"
        ]
        is False
        and report["remediation"][
            "historical_v2_results_are_performance_evidence"
        ]
        is False,
        "development_and_performance_blocked": report["authorization"][
            "development_queue_execution"
        ]
        == "NOT_AUTHORIZED"
        and report["authorization"]["performance_claim"] == "NOT_AUTHORIZED",
        "kernel_failure_policy_exact": (
            kernel_failures == 0 and namespace_halted is False
        )
        or (
            kernel_failures > 0
            and namespace_halted is True
            and report["decision"]
            == "NO_GO_S9_V3_KERNEL_FAILURE_NAMESPACE_HALTED"
            and report["authorization"]["H2_H4_execution"] == "NOT_AUTHORIZED"
        ),
    }
    if READINESS_PATH.exists():
        report["v3_readiness_audit"] = audit_readiness()
        report["v3_checks"]["readiness_audit_passed_if_present"] = all(
            report["v3_readiness_audit"].values()
        )
    if AUTHORIZATION_PATH.exists():
        report["v3_authorization_audit"] = audit_authorization()
        report["v3_checks"]["authorization_audit_passed_if_present"] = all(
            report["v3_authorization_audit"].values()
        )
    report["audit_digest"] = _digest(report)
    failures = [name for name, passed in report["v3_checks"].items() if not passed]
    if failures:
        raise S9V3CalibrationError(
            "S9-v3 CI audit failed: " + ", ".join(failures)
        )
    return report


def run_calibration(*, max_items: int | None = None) -> dict[str, Any]:
    _halt()
    audit_authorization()
    _require_external_environment()
    _require_resumable_namespace()
    with _v3_scope():
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
        S9_V3_DIR.mkdir(parents=True, exist_ok=False)
        write_json_exclusive(READINESS_PATH, artifact)
        print(READINESS_PATH)
        return
    if args.write_authorization:
        if args.ci_evidence is None:
            raise S9V3CalibrationError("authorization requires exact-CI evidence")
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

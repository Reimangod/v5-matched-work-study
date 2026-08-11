"""Isolated S9-v2 rerun using the additive zero-dimensional remediation."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import threading
from typing import Any, Iterator, Mapping

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from . import s9_h2_h4_calibration_runner as v1
from .parent_native_zero_dimensional_v2 import execute_frozen_item_v2
from .s0_successor import ROOT
from .s9_v1_zero_dimensional_halt import HALT_PATH, audit_halt


S9_V2_DIR = ROOT / "artifacts/v5-final/parent-native/s9-h2-h4-calibration-v2"
READINESS_PATH = S9_V2_DIR / "s9-runner-readiness-v2.json"
AUTHORIZATION_PATH = S9_V2_DIR / "s9-execution-authorization-v2.json"
DISPATCH_DIR = S9_V2_DIR / "dispatch"
RAW_DIR = S9_V2_DIR / "raw-ledgers"
RESULT_DIR = S9_V2_DIR / "item-results"
RECEIPT_DIR = S9_V2_DIR / "item-receipts"
PROGRESS_DIR = S9_V2_DIR / "progress"
COMPLETENESS_PATH = S9_V2_DIR / "h2-h4-completeness-v2.json"
RUNNER_SOURCES = tuple(
    ROOT / value
    for value in (
        "src/v5_final/s9_h2_h4_calibration_runner_v2.py",
        "src/v5_final/parent_native_zero_dimensional_v2.py",
        "src/v5_final/s9_v1_zero_dimensional_halt.py",
        "src/v5_final/s9_h2_h4_calibration_runner.py",
        "src/v5_final/parent_native_execution_services.py",
        "src/v5_final/parent_native_persistent_runner.py",
        "src/v5_final/parent_native_work_accounting.py",
        "src/v5_final/semantic_contract_v2.py",
        "tests/test_v5_final_s9_h2_h4_calibration_runner.py",
        ".github/workflows/v5-s9-v2-remediation-gate.yml",
    )
)
RUN_NAMESPACE = "s9-h2-h4-calibration-v2"


class S9V2CalibrationError(v1.S9CalibrationError):
    pass


def _json(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise S9V2CalibrationError(f"invalid JSON artifact: {path}") from error
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise S9V2CalibrationError(f"noncanonical JSON artifact: {path}")
    return value


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _halt() -> dict[str, Any]:
    checks = audit_halt()
    if not all(checks.values()):
        raise S9V2CalibrationError("S9-v1 halt is not valid")
    return _json(HALT_PATH)


_LOCK = threading.RLock()
_OVERRIDES = {
    "S9_DIR": S9_V2_DIR,
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
_ORIGINALS = {name: getattr(v1, name) for name in _OVERRIDES}


@contextmanager
def _v2_scope() -> Iterator[None]:
    """Rebind the frozen orchestration to an isolated namespace and executor."""

    with _LOCK:
        changed = [
            name
            for name, original in _ORIGINALS.items()
            if getattr(v1, name) is not original
        ]
        if changed:
            raise S9V2CalibrationError(
                "unexpected S9-v1 orchestration override: " + ", ".join(changed)
            )
        for name, replacement in _OVERRIDES.items():
            setattr(v1, name, replacement)
        try:
            yield
        finally:
            corrupted = [
                name
                for name, replacement in _OVERRIDES.items()
                if getattr(v1, name) is not replacement
            ]
            for name, original in _ORIGINALS.items():
                setattr(v1, name, original)
            if corrupted:
                raise S9V2CalibrationError(
                    "S9-v2 orchestration override changed in scope: "
                    + ", ".join(corrupted)
                )


def _remediation_binding(halt: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "run_namespace": RUN_NAMESPACE,
        "S9_v1_halt": {
            "path": str(HALT_PATH.relative_to(ROOT)),
            "sha256": _sha(HALT_PATH),
            "halt_digest": halt["halt_digest"],
            "decision": halt["decision"],
        },
        "historical_v1_candidate_molecular_energy_evaluations": halt[
            "observed_failure"
        ]["candidate_molecular_energy_evaluations_in_v1"],
        "v1_results_are_performance_evidence": False,
        "fresh_uniform_36_item_rerun": True,
        "zero_dimensional_target_semantics": halt["remediation_contract"][
            "zero_dimensional_target_semantics"
        ],
    }


def build_readiness() -> dict[str, Any]:
    halt = _halt()
    with _v2_scope():
        artifact = v1.build_readiness()
    artifact.pop("readiness_digest")
    artifact["stage"] = "S9_V2_REMEDIATED_FROZEN_QUEUE_RUNNER_READINESS"
    artifact["remediation"] = _remediation_binding(halt)
    artifact["academic_boundary"] = (
        "This outcome-free readiness binds the shape-only zero-dimensional "
        "compatibility rule and a fresh, implementation-uniform rerun of the exact "
        "MB6-v4 36-item queue. It does not authorize molecular execution."
    )
    artifact["readiness_digest"] = _digest(artifact)
    return artifact


def audit_readiness() -> dict[str, bool]:
    halt = _halt()
    with _v2_scope():
        checks = dict(v1.audit_readiness())
    artifact = _json(READINESS_PATH)
    remediation = artifact.get("remediation", {})
    checks.update(
        {
            "v1_halt_bound_exactly": remediation.get("S9_v1_halt", {}).get(
                "sha256"
            )
            == _sha(HALT_PATH)
            and remediation.get("S9_v1_halt", {}).get("halt_digest")
            == halt["halt_digest"],
            "fresh_v2_namespace_exact": remediation.get("run_namespace")
            == RUN_NAMESPACE
            and remediation.get("fresh_uniform_36_item_rerun") is True,
            "v1_outcomes_excluded_from_performance": remediation.get(
                "v1_results_are_performance_evidence"
            )
            is False
            and remediation.get(
                "historical_v1_candidate_molecular_energy_evaluations"
            )
            == 3,
            "zero_dimensional_contract_exact": remediation.get(
                "zero_dimensional_target_semantics"
            )
            == halt["remediation_contract"]["zero_dimensional_target_semantics"],
        }
    )
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S9V2CalibrationError(
            "S9-v2 readiness audit failed: " + ", ".join(failures)
        )
    return checks


def build_authorization(ci_evidence: Mapping[str, Any]) -> dict[str, Any]:
    halt = _halt()
    audit_readiness()
    with _v2_scope():
        artifact = v1.build_authorization(ci_evidence)
    artifact.pop("authorization_digest")
    artifact["stage"] = "S9_V2_REMEDIATED_MB6_V4_EXECUTION_AUTHORIZATION"
    artifact["remediation"] = _remediation_binding(halt)
    artifact["academic_boundary"] = (
        "Only a fresh execution of the unchanged frozen 36-item calibration queue "
        "under one uniform remediated implementation is authorized. Development "
        "execution and performance claims remain forbidden."
    )
    artifact["authorization_digest"] = _digest(artifact)
    return artifact


def audit_authorization() -> dict[str, bool]:
    halt = _halt()
    readiness_checks = audit_readiness()
    with _v2_scope():
        checks = dict(v1.audit_authorization())
    artifact = _json(AUTHORIZATION_PATH)
    remediation = artifact.get("remediation", {})
    checks.update(
        {
            "v2_readiness_checks_passed": all(readiness_checks.values()),
            "v1_halt_bound_in_authorization": remediation.get(
                "S9_v1_halt", {}
            ).get("sha256")
            == _sha(HALT_PATH)
            and remediation.get("S9_v1_halt", {}).get("halt_digest")
            == halt["halt_digest"],
            "fresh_uniform_rerun_authorized": remediation.get(
                "fresh_uniform_36_item_rerun"
            )
            is True
            and remediation.get("run_namespace") == RUN_NAMESPACE,
            "historical_v1_work_disclosed": remediation.get(
                "historical_v1_candidate_molecular_energy_evaluations"
            )
            == 3,
        }
    )
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S9V2CalibrationError(
            "S9-v2 authorization audit failed: " + ", ".join(failures)
        )
    return checks


def build_ci_audit() -> dict[str, Any]:
    halt = _halt()
    with _v2_scope():
        report = v1.build_ci_audit()
    report.pop("audit_digest")
    report["run_namespace"] = RUN_NAMESPACE
    report["remediation"] = _remediation_binding(halt)
    report["halt_audit"] = audit_halt()
    report["v2_checks"] = {
        "halt_audit_passed": all(report["halt_audit"].values()),
        "fresh_namespace_isolated": report["remediation"]["run_namespace"]
        == RUN_NAMESPACE,
        "historical_v1_work_disclosed": report["remediation"][
            "historical_v1_candidate_molecular_energy_evaluations"
        ]
        == 3,
        "v1_results_not_performance_evidence": report["remediation"][
            "v1_results_are_performance_evidence"
        ]
        is False,
        "development_and_performance_blocked": report["authorization"][
            "development_queue_execution"
        ]
        == "NOT_AUTHORIZED"
        and report["authorization"]["performance_claim"] == "NOT_AUTHORIZED",
    }
    if READINESS_PATH.exists():
        report["v2_readiness_audit"] = audit_readiness()
        report["v2_checks"]["readiness_audit_passed_if_present"] = all(
            report["v2_readiness_audit"].values()
        )
    if AUTHORIZATION_PATH.exists():
        report["v2_authorization_audit"] = audit_authorization()
        report["v2_checks"]["authorization_audit_passed_if_present"] = all(
            report["v2_authorization_audit"].values()
        )
    report["audit_digest"] = _digest(report)
    failures = [
        name for name, passed in report["v2_checks"].items() if not passed
    ]
    if failures:
        raise S9V2CalibrationError(
            "S9-v2 CI audit failed: " + ", ".join(failures)
        )
    return report


def run_calibration(*, max_items: int | None = None) -> dict[str, Any]:
    _halt()
    audit_authorization()
    with _v2_scope():
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
        S9_V2_DIR.mkdir(parents=True, exist_ok=False)
        write_json_exclusive(READINESS_PATH, artifact)
        print(READINESS_PATH)
        return
    if args.write_authorization:
        if args.ci_evidence is None:
            raise S9V2CalibrationError("authorization requires exact-CI evidence")
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

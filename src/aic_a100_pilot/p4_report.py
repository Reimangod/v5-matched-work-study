"""Publish and evaluate the complete P4 same-node benchmark evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from v5_matched_work.atomic_artifacts import write_bytes_exclusive

from .benchmark import CURRENT_ORDER, SYNTHETIC_QUBITS
from .common import (
    ARTIFACT_ROOT,
    ROOT,
    A100PilotError,
    embedded_digest_valid,
    load_json,
    publish,
    sha256_file,
)
from .p4_contract import CONTRACT
from .p4_contract_correction import CORRECTION


P4 = ARTIFACT_ROOT / "p4-same-node-benchmark"
RAW = P4 / "raw"
REPORT = P4 / "same-node-route-benchmark-report-v1.json"


def _read_result(source: Path, name: str) -> tuple[Path, dict[str, Any]]:
    path = source / f"{name}.json"
    value = load_json(path)
    if not embedded_digest_valid(value, "record_digest"):
        raise A100PilotError(f"invalid benchmark record digest: {name}")
    if value.get("candidate_molecular_energy_evaluations") != 0:
        raise A100PilotError(f"candidate outcome entered benchmark: {name}")
    if value.get("optimizer_runs") != 0 or value.get("FCI_evaluations") != 0:
        raise A100PilotError(f"optimizer or FCI entered benchmark: {name}")
    measurement = value.get("measurement", {})
    if int(measurement.get("warmup_repetitions", -1)) != 1:
        raise A100PilotError(f"wrong warmup count: {name}")
    if int(measurement.get("measured_repetitions", -1)) != 5:
        raise A100PilotError(f"wrong measured count: {name}")
    if len(measurement.get("cpu_seconds", [])) != 5 or len(
        measurement.get("gpu_seconds", [])
    ) != 5:
        raise A100PilotError(f"incomplete raw timings: {name}")
    return path, value


def publish_report(source: Path) -> dict[str, Any]:
    contract = load_json(CONTRACT)
    correction = load_json(CORRECTION)
    if not embedded_digest_valid(contract, "contract_digest"):
        raise A100PilotError("P4 contract digest is invalid")
    if contract["status"] != "GO_P4_EXECUTION":
        raise A100PilotError("P4 contract did not authorize execution")
    if not embedded_digest_valid(correction, "correction_digest"):
        raise A100PilotError("P4 correction digest is invalid")
    if REPORT.exists():
        raise A100PilotError("P4 report already exists")
    raw_preexisted = RAW.exists()
    RAW.mkdir(parents=True, exist_ok=True)
    current: list[dict[str, Any]] = []
    synthetic: list[dict[str, Any]] = []
    try:
        for alias in CURRENT_ORDER:
            name = f"current-{alias}"
            path, value = _read_result(source, name)
            if value.get("benchmark_kind") != "CURRENT_FROZEN_SOURCE":
                raise A100PilotError(f"wrong current benchmark kind: {alias}")
            if value.get("alias") != alias:
                raise A100PilotError(f"wrong current alias: {alias}")
            destination = RAW / f"{name}.json"
            if destination.exists():
                if destination.read_bytes() != path.read_bytes():
                    raise A100PilotError(f"existing raw timing differs: {name}")
            else:
                write_bytes_exclusive(destination, path.read_bytes())
            measurement = value["measurement"]
            current.append(
                {
                    "alias": alias,
                    "case_id": value["case_id"],
                    "qubit_count": int(value["qubit_count"]),
                    "path": destination.relative_to(ROOT).as_posix(),
                    "sha256": sha256_file(destination),
                    "record_digest": value["record_digest"],
                    "slurm_job_id": int(value["hardware"]["slurm_job_id"]),
                    "cpu_median_seconds": float(measurement["cpu_median_seconds"]),
                    "gpu_median_seconds": float(measurement["gpu_median_seconds"]),
                    "speedup_cpu_over_gpu": float(
                        measurement["speedup_cpu_over_gpu"]
                    ),
                    "checks": dict(measurement["checks"]),
                    "route_counters": dict(measurement["measured_route_counters"]),
                }
            )
        for qubits in SYNTHETIC_QUBITS:
            name = f"synthetic-{qubits}"
            path, value = _read_result(source, name)
            if value.get("benchmark_kind") != "SYNTHETIC_DIAGNOSTIC":
                raise A100PilotError(f"wrong synthetic benchmark kind: {qubits}")
            if int(value.get("qubit_count", -1)) != qubits:
                raise A100PilotError(f"wrong synthetic qubit count: {qubits}")
            if value.get("scientific_scope") != (
                "DIAGNOSTIC_ONLY_CANNOT_OVERRIDE_CURRENT_SYSTEM_GATE"
            ):
                raise A100PilotError(f"synthetic scope changed: {qubits}")
            destination = RAW / f"{name}.json"
            if destination.exists():
                if destination.read_bytes() != path.read_bytes():
                    raise A100PilotError(f"existing raw timing differs: {name}")
            else:
                write_bytes_exclusive(destination, path.read_bytes())
            measurement = value["measurement"]
            synthetic.append(
                {
                    "qubit_count": qubits,
                    "path": destination.relative_to(ROOT).as_posix(),
                    "sha256": sha256_file(destination),
                    "record_digest": value["record_digest"],
                    "slurm_job_id": int(value["hardware"]["slurm_job_id"]),
                    "cpu_median_seconds": float(measurement["cpu_median_seconds"]),
                    "gpu_median_seconds": float(measurement["gpu_median_seconds"]),
                    "speedup_cpu_over_gpu": float(
                        measurement["speedup_cpu_over_gpu"]
                    ),
                    "checks": dict(measurement["checks"]),
                    "scope": value["scientific_scope"],
                }
            )
    except Exception:
        if not raw_preexisted:
            for path in RAW.glob("*"):
                path.unlink()
            RAW.rmdir()
        raise

    threshold = float(
        correction["corrected_interpretation"][
            "minimum_target_speedup_cpu_over_gpu"
        ]
    )
    target_aliases = correction["corrected_interpretation"][
        "production_target_aliases"
    ]
    numerical_and_route_pass = all(
        all(case["checks"].values()) for case in current + synthetic
    )
    target_source_route_speed_pass = all(
        case["speedup_cpu_over_gpu"] >= threshold
        for case in current
        if case["alias"] in target_aliases
    )
    if not numerical_and_route_pass:
        status = "NO_GO_A100_SOURCE_ROUTE_NUMERICAL_OR_ROUTE_FAILURE"
    elif not target_source_route_speed_pass:
        status = "NO_GO_A100_SOURCE_ROUTE_TARGET_SPEED_PRECHECK"
    else:
        status = "GO_P3_PRODUCTION_OBJECTIVE_BINDING_AND_DECISION_PARITY"
    body = {
        "schema": "aic-a100-pilot.p4-same-node-route-benchmark-report.v1",
        "status": status,
        "evidence_binding": {
            "P4_contract_digest": contract["contract_digest"],
            "P4_contract_correction_digest": correction["correction_digest"],
            **dict(contract["evidence_binding"]),
        },
        "current_system_results": current,
        "synthetic_diagnostic_results": synthetic,
        "decision": {
            "minimum_speedup_cpu_over_gpu": threshold,
            "measurement_scope": "SOURCE_ROUTE_DIAGNOSTIC_ONLY",
            "production_target_aliases": target_aliases,
            "H2_role": "POSITIVE_CONTROL_AND_LAUNCH_OVERHEAD_DIAGNOSTIC",
            "numerical_and_route_pass": numerical_and_route_pass,
            "all_target_source_routes_meet_speed_precheck": target_source_route_speed_pass,
            "synthetic_can_override_current_failure": False,
            "production_adoption_decision_authorized": False,
        },
        "pre_timing_engineering_incident": {
            "jobs": [1978, 1979, 1980, 1981, 1982, 1983, 1984, 1985],
            "classification": "NVIDIA_SMI_MANAGEMENT_SCOPE_MISTAKEN_FOR_CUDA_ALLOCATION_SCOPE",
            "persisted_timing_records": 0,
            "candidate_outcomes": 0,
            "remediation": (
                "The rerun separately requires one Slurm selector, one "
                "CUDA_VISIBLE_DEVICES selector and cuDeviceGetCount=1, while "
                "retaining the node-management inventory count as context."
            ),
            "decision_rule_changed": False,
        },
        "scientific_boundary": {
            "authorized_claim": (
                "Measured same-node source-route timings as a diagnostic precheck only."
            ),
            "candidate_terminal_decision_parity": "NOT_EXECUTED",
            "candidate_molecular_energy_evaluations": 0,
            "optimizer_runs": 0,
            "FCI_evaluations": 0,
            "Measurement_Cost_claim": "NOT_AUTHORIZED",
            "V5_performance_claim": "NOT_AUTHORIZED",
        },
        "successor_authorization": {
            "production_GPU_objective_binding": (
                "AUTHORIZED"
                if status == "GO_P3_PRODUCTION_OBJECTIVE_BINDING_AND_DECISION_PARITY"
                else "NOT_AUTHORIZED"
            ),
            "P3_candidate_decision_parity": "PENDING_PRODUCTION_BINDING",
            "P4_complete_item_end_to_end_gate": "NOT_AUTHORIZED_PENDING_PARITY",
            "P5_limited_scientific_pilot": "NOT_AUTHORIZED",
            "existing_90_item_execution": "UNCHANGED_NOT_AUTHORIZED_BY_A100_PILOT",
        },
    }
    return publish(REPORT, body, "report_digest")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--publish", action="store_true")
    arguments = parser.parse_args()
    if not arguments.publish:
        raise RuntimeError("select --publish")
    print(json.dumps(publish_report(arguments.source), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

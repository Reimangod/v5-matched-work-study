"""Publish the bounded optimizer-objective parity prefix and terminal failure."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from v5_matched_work.atomic_artifacts import write_bytes_exclusive

from .common import (
    ARTIFACT_ROOT,
    ROOT,
    A100PilotError,
    embedded_digest_valid,
    load_json,
    publish,
    sha256_file,
)
from .objective_incident import INCIDENT
from .p3_objective_contract import CONTRACT


ROOT_OUT = ARTIFACT_ROOT / "p3-objective-parity"
CASES = ROOT_OUT / "cases"
REPORT = ROOT_OUT / "production-objective-parity-report-v1.json"
EXECUTED_ORDER = ("h2", "h4", "lih")
UNEXECUTED = ("h6", "beh2")


def publish_report(source: Path) -> dict[str, Any]:
    contract = load_json(CONTRACT)
    incident = load_json(INCIDENT)
    if not embedded_digest_valid(contract, "contract_digest"):
        raise A100PilotError("P3 objective contract digest is invalid")
    if not embedded_digest_valid(incident, "incident_digest"):
        raise A100PilotError("H2 incident digest is invalid")
    if CASES.exists() or REPORT.exists():
        raise A100PilotError("P3 objective report already exists")
    by_alias = {
        case["alias"]: case for case in contract["selection_policy"]["cases"]
    }
    CASES.mkdir(parents=True, exist_ok=False)
    results: list[dict[str, Any]] = []
    totals = {
        route: {name: 0 for name in contract_route_names()}
        for route in ("cpu", "gpu")
    }
    try:
        for alias in EXECUTED_ORDER:
            source_path = source / f"{alias}.json"
            value = load_json(source_path)
            if not embedded_digest_valid(value, "record_digest"):
                raise A100PilotError(f"objective record digest is invalid: {alias}")
            if value.get("alias") != alias:
                raise A100PilotError(f"objective alias differs: {alias}")
            if value.get("candidate_id") != by_alias[alias]["candidate_id"]:
                raise A100PilotError(f"objective candidate differs: {alias}")
            if value["scientific_boundary"]["FCI_evaluations"] != 0:
                raise A100PilotError(f"FCI entered objective parity: {alias}")
            expected_status = "FAIL" if alias == "lih" else "PASS"
            if value.get("status") != expected_status:
                raise A100PilotError(f"unexpected objective status: {alias}")
            destination = CASES / f"{alias}.json"
            write_bytes_exclusive(destination, source_path.read_bytes())
            for route in ("cpu", "gpu"):
                for name, count in value["route_counters"][route].items():
                    totals[route][name] += int(count)
            frozen_optimizer = by_alias[alias]["frozen_CPU_optimizer_terminal"]
            results.append(
                {
                    "alias": alias,
                    "case_id": value["case_id"],
                    "candidate_id": value["candidate_id"],
                    "reference_class": value["reference_class"],
                    "path": destination.relative_to(ROOT).as_posix(),
                    "sha256": sha256_file(destination),
                    "record_digest": value["record_digest"],
                    "slurm_job_id": int(value["hardware"]["slurm_job_id"]),
                    "status": value["status"],
                    "checks": dict(value["checks"]),
                    "differences": dict(value["differences"]),
                    "CPU_terminal_decision": value["cpu"]["terminal_decision"],
                    "GPU_terminal_decision": value["gpu"]["terminal_decision"],
                    "same_AIC_CPU_GPU_optimizer_terminal_exact": value[
                        "optimizer_terminal_exact_fields_equal"
                    ],
                    "AIC_CPU_matches_frozen_optimizer_terminal_exact": value["cpu"][
                        "optimizer_terminal"
                    ]
                    == frozen_optimizer,
                    "wall_time_seconds": dict(value["wall_time_seconds"]),
                }
            )
    except Exception:
        for path in CASES.glob("*"):
            path.unlink()
        CASES.rmdir()
        raise

    lih = next(value for value in results if value["alias"] == "lih")
    if [name for name, passed in lih["checks"].items() if not passed] != [
        "gradient",
        "state",
    ]:
        raise A100PilotError("LiH failure set differs from audited numerical nonparity")
    body = {
        "schema": "aic-a100-pilot.p3-production-objective-parity-report.v1",
        "status": "NO_GO_A100_NUMERICAL_NONPARITY",
        "evidence_binding": {
            "P3_objective_contract_digest": contract["contract_digest"],
            "H2_serialization_incident_digest": incident["incident_digest"],
        },
        "executed_prefix": list(EXECUTED_ORDER),
        "unexecuted_after_first_scientific_failure": list(UNEXECUTED),
        "case_results": results,
        "terminal_failure": {
            "alias": "lih",
            "failed_registered_checks": ["gradient", "state"],
            "phase_aligned_state_error": lih["differences"][
                "phase_aligned_independent_state"
            ],
            "state_error_threshold": contract["parity_requirements"][
                "state_error_max"
            ],
            "max_gradient_component_error": lih["differences"][
                "max_gradient_component"
            ],
            "gradient_error_threshold": contract["parity_requirements"][
                "max_gradient_component_error"
            ],
            "energy_error_hartree": lih["differences"]["energy_hartree"],
            "energy_error_threshold_hartree": contract["parity_requirements"][
                "energy_error_hartree_max"
            ],
            "CPU_GPU_terminal_decision_remained_equal": (
                lih["CPU_terminal_decision"] == lih["GPU_terminal_decision"]
            ),
            "reason_for_no_go": (
                "Equal final accept/reject decisions do not override preregistered "
                "state and gradient tolerances."
            ),
        },
        "route_counters_persisted_results": totals,
        "work_disclosure": {
            "persisted_paired_CPU_candidate_outcomes": 3,
            "persisted_GPU_candidate_outcomes": 3,
            "failed_H2_serialization_attempt_CPU_computation": 1,
            "failed_H2_serialization_attempt_GPU_computation": 1,
            "total_CPU_candidate_computations_including_retry": 4,
            "total_GPU_candidate_computations_including_retry": 4,
            "FCI_evaluations": 0,
        },
        "cross_environment_observation": {
            "AIC_CPU_GPU_optimizer_terminal_exact_by_case": {
                result["alias"]: result[
                    "same_AIC_CPU_GPU_optimizer_terminal_exact"
                ]
                for result in results
            },
            "AIC_CPU_frozen_historical_optimizer_terminal_exact_by_case": {
                result["alias"]: result[
                    "AIC_CPU_matches_frozen_optimizer_terminal_exact"
                ]
                for result in results
            },
            "interpretation": (
                "AIC CPU versus frozen macOS optimizer-path drift is reported "
                "separately from GPU-induced same-node drift."
            ),
        },
        "successor_authorization": {
            "h6_objective_parity": "NOT_AUTHORIZED",
            "beh2_objective_parity": "NOT_AUTHORIZED",
            "P4_complete_item_end_to_end_gate": "NOT_AUTHORIZED",
            "P5_limited_scientific_pilot": "NOT_AUTHORIZED",
            "P6_formal_decision": "AUTHORIZED_NO_GO_ONLY",
            "existing_90_item_execution": "UNCHANGED",
        },
        "scientific_boundary": {
            "authorized_claim": (
                "The tested hybrid A100-energy/CPU-gradient optimizer route failed "
                "the frozen LiH state and gradient parity tolerances."
            ),
            "A100_speedup_claim_for_complete_items": "NOT_AUTHORIZED",
            "Measurement_Cost_claim": "NOT_AUTHORIZED",
            "V5_performance_claim": "NOT_AUTHORIZED",
        },
    }
    return publish(REPORT, body, "report_digest")


def contract_route_names() -> tuple[str, ...]:
    return (
        "N_gpu_statevector",
        "N_gpu_energy",
        "N_gpu_gradient_component",
        "N_cpu_statevector",
        "N_cpu_energy",
        "N_cpu_gradient_component",
        "N_cpu_fallback",
    )


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

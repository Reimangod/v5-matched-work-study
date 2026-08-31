"""Terminal decision for the unified CPU/A100 trajectory experiment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .common import (
    ARTIFACT_ROOT,
    ROOT,
    embedded_digest_valid,
    load_json,
    publish,
    sha256_file,
)
from .unified_route_contract import CONTRACT, TERMINAL_NO_GO


H2_RESULT = ARTIFACT_ROOT / "p3-unified-route-v4/results/h2.json"
H4_RESULT = ARTIFACT_ROOT / "p3-unified-route-v4/results/h4.json"
H2_PREPARATION = (
    ARTIFACT_ROOT / "p3-unified-route-v4/preparation-manifests/h2.json"
)
H4_PREPARATION = (
    ARTIFACT_ROOT / "p3-unified-route-v4/preparation-manifests/h4.json"
)
DECISION = (
    ARTIFACT_ROOT
    / "p6-unified-route-decision/unified-route-terminal-no-go-v1.json"
)


def _binding(path: Path, field: str) -> dict[str, str]:
    value = load_json(path)
    if not embedded_digest_valid(value, field):
        raise RuntimeError(f"invalid evidence digest: {path}")
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": sha256_file(path),
        field: str(value[field]),
    }


def decision_body() -> dict[str, Any]:
    contract = load_json(CONTRACT)
    h2 = load_json(H2_RESULT)
    h4 = load_json(H4_RESULT)
    old_no_go = load_json(TERMINAL_NO_GO)
    if not embedded_digest_valid(contract, "contract_digest"):
        raise RuntimeError("unified-route v4 contract digest is invalid")
    if h2["status"] != "PASS" or h4["status"] != "FAIL":
        raise RuntimeError("unified-route executed prefix is not PASS then FAIL")
    if h2["contract_digest"] != contract["contract_digest"]:
        raise RuntimeError("H2 result contract differs")
    if h4["contract_digest"] != contract["contract_digest"]:
        raise RuntimeError("H4 result contract differs")
    if not embedded_digest_valid(old_no_go, "decision_digest"):
        raise RuntimeError("historical hybrid No-Go digest is invalid")
    failed_checks = sorted(
        key for key, passed in h4["checks"].items() if not bool(passed)
    )
    if not failed_checks:
        raise RuntimeError("H4 has no registered failed checks")
    return {
        "schema": "aic-a100-pilot.unified-route-terminal-decision.v1",
        "status": "NO_GO_A100_UNIFIED_ROUTE_H4_TRAJECTORY_NONPARITY",
        "contract_binding": _binding(CONTRACT, "contract_digest"),
        "immutable_historical_hybrid_no_go": {
            **_binding(TERMINAL_NO_GO, "decision_digest"),
            "modified": False,
        },
        "executed_prefix": ["h2", "h4"],
        "case_evidence": {
            "h2": {
                "result": _binding(H2_RESULT, "record_digest"),
                "preparation": _binding(H2_PREPARATION, "manifest_digest"),
                "status": "PASS",
            },
            "h4": {
                "result": _binding(H4_RESULT, "record_digest"),
                "preparation": _binding(H4_PREPARATION, "manifest_digest"),
                "status": "FAIL",
            },
        },
        "terminal_failure": {
            "alias": "h4",
            "failed_registered_checks": failed_checks,
            "observed": {
                **h4["terminal_differences"],
                "trajectory_length_cpu": h4["trajectory"]["length_cpu"],
                "trajectory_length_gpu": h4["trajectory"]["length_gpu"],
                "CPU_optimizer": h4["cpu"]["optimizer_terminal"],
                "GPU_optimizer": h4["gpu"]["optimizer_terminal"],
                "CPU_route_counters": h4["route_counters"]["cpu"],
                "GPU_route_counters": h4["route_counters"]["gpu"],
            },
            "frozen_thresholds": contract["parity_requirements"],
            "same_device_repeat_determinism": h4["checks"][
                "same_device_repeat_determinism"
            ],
            "CPU_fallback_count": h4["route_counters"]["gpu"][
                "N_cpu_fallback"
            ],
            "energy_decision_and_resources_still_matched": all(
                h4["checks"][key]
                for key in ("terminal_energy", "terminal_decision", "resources_exact")
            ),
        },
        "interpretation": {
            "observation": (
                "The registered unified external route and deterministic host "
                "reduction did not produce a parity-equivalent H4 BFGS trajectory."
            ),
            "bounded_inference_not_proof": (
                "Small cross-device statevector differences were amplified by the "
                "five-point finite-difference gradient, inverse-Hessian updates, and "
                "line search, ending in different optimizer status and work counts."
            ),
            "not_claimed": (
                "This does not establish that A100 simulation is generally invalid "
                "or that no alternative pre-registered optimizer can match CPU."
            ),
        },
        "slurm_evidence": {
            "job_id": 2007,
            "state": "FAILED",
            "exit_code": "2:0",
            "elapsed": "00:00:43",
            "start": "2026-08-31T07:04:22",
            "end": "2026-08-31T07:05:05",
            "remote_log_relative_path": "repo/slurm-2007.out",
            "remote_log_sha256": (
                "1904ecc613b0dcba944d6c3f28f116ac9c75957f089e26d910cdff27c523a3d2"
            ),
            "remote_log_size_bytes": 35092,
        },
        "stopped_by_frozen_gate": {
            "unexecuted_cases": ["lih", "h6", "beh2"],
            "LiH_parity": "NOT_EXECUTED_NOT_AUTHORIZED_AFTER_H4_FAILURE",
            "H6_BeH2": "NOT_EXECUTED_NOT_AUTHORIZED",
            "complete_item_end_to_end_timing": "NOT_EXECUTED_NOT_AUTHORIZED",
        },
        "scientific_boundaries": {
            "paired_CPU_candidate_attempts": 2,
            "paired_GPU_candidate_attempts": 2,
            "FCI_evaluations": 0,
            "production_dense_exponentials": 0,
            "existing_90_item_execution": "UNCHANGED",
            "post_outcome_tolerance_change": False,
            "V5_performance_claim": "NOT_AUTHORIZED",
            "Measurement_Cost_claim": "NOT_AUTHORIZED",
            "A100_speedup_claim": "NOT_AUTHORIZED",
        },
        "authorized_claim": (
            "Under the frozen v4 unified-route protocol, H2 passed but H4 failed "
            "registered optimizer-trajectory, gradient, state, and terminal-status "
            "parity; execution stopped before LiH and before timing."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--publish", action="store_true")
    arguments = parser.parse_args()
    if not arguments.publish:
        raise RuntimeError("select --publish")
    print(json.dumps(publish(DECISION, decision_body(), "decision_digest"), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

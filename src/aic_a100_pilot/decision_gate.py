"""Terminal fail-closed decision gate for the A100 pilot."""

from __future__ import annotations

import argparse
import json
from typing import Any

from .common import ARTIFACT_ROOT, embedded_digest_valid, load_json, publish
from .environment import PREFLIGHT
from .p0_baseline import PROTOCOL, REFERENCE


P6 = ARTIFACT_ROOT / "p6-decision"
DECISION = P6 / "a100-pilot-terminal-decision-v1.json"


def decision_body() -> dict[str, Any]:
    protocol = load_json(PROTOCOL)
    reference = load_json(REFERENCE)
    preflight = load_json(PREFLIGHT)
    if not embedded_digest_valid(protocol, "protocol_digest"):
        raise RuntimeError("P0 protocol digest is invalid")
    if not embedded_digest_valid(reference, "reference_digest"):
        raise RuntimeError("P0 reference digest is invalid")
    if not embedded_digest_valid(preflight, "preflight_digest"):
        raise RuntimeError("P1 preflight digest is invalid")
    if preflight["status"] != "NO_GO_A100_OPERATIONAL_INSTABILITY":
        raise RuntimeError("this terminal gate only accepts the recorded P1 No-Go")
    return {
        "schema": "aic-a100-pilot.terminal-decision.v1",
        "status": "NO_GO_A100_OPERATIONAL_INSTABILITY",
        "terminal_phase": "P6_FORMAL_DECISION_AFTER_P1_STOP",
        "evidence_binding": {
            "P0_protocol_digest": protocol["protocol_digest"],
            "P0_reference_digest": reference["reference_digest"],
            "P1_preflight_digest": preflight["preflight_digest"],
        },
        "phase_status": {
            "P0_LOCAL_CPU_REFERENCE": "GO",
            "P1_AIC_PREFLIGHT": "NO_GO",
            "P2_GPU_ENVIRONMENT_AND_SMOKE": "NOT_STARTED_NOT_AUTHORIZED",
            "P3_SCIENTIFIC_PARITY": "NOT_STARTED_NOT_AUTHORIZED",
            "P4_SAME_NODE_MICROBENCHMARK": "NOT_STARTED_NOT_AUTHORIZED",
            "P5_LIMITED_SCIENTIFIC_PILOT": "NOT_STARTED_NOT_AUTHORIZED",
            "P6_FORMAL_DECISION": "TERMINAL",
        },
        "decision_rationale": (
            "No Slurm A100 allocation was obtained in either of two valid one-GPU "
            "attempts. P2 cannot certify an actual GPU route, so later parity, "
            "benchmark, and scientific phases are fail-closed."
        ),
        "hardware_observation": {
            "cluster_inventory": "dgx-a100 / gpu:a100:6",
            "allocated_A100_model": None,
            "CUDA_version": None,
            "NVIDIA_driver_version": None,
            "reason_null": "No compute allocation was obtained.",
        },
        "route_counters": dict(preflight["route_counters"]),
        "parity_table": [],
        "parity_table_status": "NOT_EXECUTED",
        "speedup_table": [],
        "speedup_table_status": "NOT_EXECUTED",
        "slurm_job_ids": [
            attempt["slurm_job_id"] for attempt in preflight["allocation_attempts"]
        ],
        "rollback": dict(preflight["cleanup"]),
        "scientific_boundaries": {
            "candidate_molecular_energy_evaluations": 0,
            "FCI_evaluations": 0,
            "existing_90_item_study_changed": False,
            "A100_performance_claim": "NOT_AUTHORIZED",
            "CPU_GPU_parity_claim": "NOT_AUTHORIZED",
            "Measurement_Cost_claim": "NOT_AUTHORIZED",
            "engineering_negative_result_scope": (
                "AIC allocation availability at this audited time only; not A100 speed "
                "or numerical suitability."
            ),
        },
        "safe_reentry_conditions": [
            "A one-GPU Slurm job starts on gpu-interactive or gpu-short.",
            "The allocated job reports exactly one visible NVIDIA A100 via nvidia-smi.",
            "The P0 protocol, reference bundle, protected S11/S12 artifacts, and pinned "
            "Qiskit generation remain unchanged.",
            "Resume at P1 successor evidence; do not skip directly to P2 or reuse an "
            "unregistered interactive outcome.",
        ],
    }


def publish_decision() -> dict[str, Any]:
    return publish(DECISION, decision_body(), "decision_digest")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--publish", action="store_true")
    arguments = parser.parse_args()
    if not arguments.publish:
        raise RuntimeError("select --publish")
    print(json.dumps(publish_decision(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

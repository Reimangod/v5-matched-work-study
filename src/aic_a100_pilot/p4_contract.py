"""Outcome-blind execution contract for the P4 same-node benchmark."""

from __future__ import annotations

import argparse
import json
from typing import Any

from .common import ARTIFACT_ROOT, embedded_digest_valid, load_json, publish
from .p0_baseline import PROTOCOL
from .p3_report import REPORT


P4 = ARTIFACT_ROOT / "p4-same-node-benchmark"
CONTRACT = P4 / "benchmark-contract-v1.json"


def contract_body() -> dict[str, Any]:
    protocol = load_json(PROTOCOL)
    parity = load_json(REPORT)
    if not embedded_digest_valid(protocol, "protocol_digest"):
        raise RuntimeError("P0 protocol digest is invalid")
    if not embedded_digest_valid(parity, "report_digest"):
        raise RuntimeError("P3 report digest is invalid")
    if parity["status"] != "GO_P4_SOURCE_ROUTE_SPEED_GATE":
        raise RuntimeError("P3 did not authorize P4")
    policy = protocol["benchmark_policy"]
    return {
        "schema": "aic-a100-pilot.p4-benchmark-contract.v1",
        "status": "GO_P4_EXECUTION",
        "frozen_before_timing_outcomes": True,
        "evidence_binding": {
            "P0_protocol_digest": protocol["protocol_digest"],
            "P3_source_parity_report_digest": parity["report_digest"],
        },
        "current_system_cases": list(protocol["case_order"]),
        "route": {
            "name": "SOURCE_STATEVECTOR_PLUS_SPARSE_ENERGY",
            "cpu": "Qiskit Statevector.evolve plus host sparse expectation",
            "gpu": "Aer GPU statevector plus transfer and host sparse expectation",
            "same_AIC_node_required": True,
            "molecular_setup_timed": False,
            "candidate_catalog_timed": False,
            "optimizer_timed": False,
            "FCI_timed": False,
        },
        "sampling": {
            "warmup_repetitions": max(1, int(policy["warmup_repetitions_min"])),
            "measured_repetitions": int(policy["measured_repetitions"]),
            "order": "CPU_FIRST_ON_EVEN_REPETITIONS_GPU_FIRST_ON_ODD",
            "summary": "MEDIAN_WALL_SECONDS_PER_ROUTE",
        },
        "decision_rule": {
            "minimum_speedup_cpu_over_gpu": float(
                policy["current_system_end_to_end_speedup_min"]
            ),
            "current_case_rule": "EVERY_CURRENT_CASE_MUST_MEET_MINIMUM",
            "reason": (
                "The P0 field specifies a current-system minimum. The conservative "
                "outcome-blind interpretation is applied independently to every "
                "registered current case; no favorable aggregation is selected "
                "after observing timings."
            ),
            "numerical_parity_required": True,
            "explicit_GPU_metadata_required": True,
            "CPU_fallback_allowed": False,
            "go": "GO_P3_CANDIDATE_DECISION_PARITY",
            "no_go": "NO_GO_A100_NO_CURRENT_SYSTEM_END_TO_END_SPEEDUP",
        },
        "synthetic_diagnostics": {
            "qubits": list(policy["synthetic_scaling_qubits"]),
            "can_override_current_case_failure": False,
            "scientific_scope": "DIAGNOSTIC_SCALING_ONLY",
        },
        "scientific_boundary": {
            "candidate_molecular_energy_evaluations": 0,
            "optimizer_runs": 0,
            "FCI_evaluations": 0,
            "P5_limited_scientific_pilot": "NOT_AUTHORIZED",
            "V5_performance_claim": "NOT_AUTHORIZED",
        },
    }


def publish_contract() -> dict[str, Any]:
    return publish(CONTRACT, contract_body(), "contract_digest")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--publish", action="store_true")
    arguments = parser.parse_args()
    if not arguments.publish:
        raise RuntimeError("select --publish")
    print(json.dumps(publish_contract(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

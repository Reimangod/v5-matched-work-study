"""Additive correction of P4 prerequisite and target-case interpretation."""

from __future__ import annotations

import argparse
import json
from typing import Any

from .common import ARTIFACT_ROOT, ROOT, embedded_digest_valid, load_json, publish, sha256_file
from .p4_contract import CONTRACT


CORRECTION = ARTIFACT_ROOT / "p4-same-node-benchmark/benchmark-contract-correction-v2.json"
PRIMARY_PLAN = ROOT / "docs/AIC_A100_PILOT_PLAN.md"


def correction_body() -> dict[str, Any]:
    prior = load_json(CONTRACT)
    if not embedded_digest_valid(prior, "contract_digest"):
        raise RuntimeError("P4 v1 contract digest is invalid")
    return {
        "schema": "aic-a100-pilot.p4-benchmark-contract-correction.v2",
        "status": "CORRECTED_TO_SOURCE_ROUTE_DIAGNOSTIC_PENDING_PRODUCTION_BINDING",
        "supersedes_without_mutation": {
            "path": CONTRACT.relative_to(ROOT).as_posix(),
            "contract_digest": prior["contract_digest"],
            "raw_timings_retained": True,
        },
        "authority": {
            "path": PRIMARY_PLAN.relative_to(ROOT).as_posix(),
            "sha256": sha256_file(PRIMARY_PLAN),
            "frozen_before_A100_timing_outcomes": True,
            "outcome_values_used_to_choose_correction": False,
        },
        "audit_findings": [
            {
                "class": "MISSING_PRODUCTION_OBJECTIVE_BINDING_PREREQUISITE",
                "primary_plan_requirement": (
                    "P2 requires the optimizer's actual energy objective to be GPU-bound "
                    "before the P4 end-to-end benchmark."
                ),
                "observed_scope": (
                    "The completed runs measured source statevector propagation plus "
                    "host sparse expectation only."
                ),
                "effect": "P4 adoption and terminal decisions are not authorized.",
            },
            {
                "class": "H2_INCORRECTLY_INCLUDED_IN_PRODUCTION_SPEED_GATE",
                "primary_plan_requirement": (
                    "P4 target molecular cases are H4, LiH, H6 and BeH2; H2 is a P3 "
                    "positive-control case."
                ),
                "effect": (
                    "H2 timing remains a launch-overhead diagnostic and cannot decide "
                    "current 12--14-qubit production adoption."
                ),
            },
        ],
        "corrected_interpretation": {
            "completed_measurement_scope": "SOURCE_ROUTE_DIAGNOSTIC_ONLY",
            "production_target_aliases": ["h4", "lih", "h6", "beh2"],
            "positive_control_not_in_production_speed_gate": ["h2"],
            "minimum_target_speedup_cpu_over_gpu": 1.2,
            "synthetic_scaling_can_override_molecular_evidence": False,
            "threshold_changed": False,
            "parity_tolerance_changed": False,
        },
        "successor_authorization": {
            "publish_source_route_diagnostic": "AUTHORIZED",
            "implement_production_GPU_objective_binding": "AUTHORIZED",
            "candidate_and_optimizer_terminal_parity": "PENDING_BINDING",
            "P4_complete_item_end_to_end_gate": "NOT_AUTHORIZED_PENDING_PARITY",
            "P5_limited_scientific_pilot": "NOT_AUTHORIZED",
            "existing_90_item_execution": "UNCHANGED",
        },
        "scientific_boundary": {
            "candidate_molecular_energy_evaluations": 0,
            "optimizer_runs": 0,
            "FCI_evaluations": 0,
            "terminal_A100_adoption_decision": "NOT_AUTHORIZED",
            "V5_performance_claim": "NOT_AUTHORIZED",
        },
    }


def publish_correction() -> dict[str, Any]:
    return publish(CORRECTION, correction_body(), "correction_digest")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--publish", action="store_true")
    arguments = parser.parse_args()
    if not arguments.publish:
        raise RuntimeError("select --publish")
    print(json.dumps(publish_correction(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

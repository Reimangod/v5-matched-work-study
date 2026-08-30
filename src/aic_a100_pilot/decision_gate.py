"""Terminal fail-closed decision gate for the A100 pilot."""

from __future__ import annotations

import argparse
import json
from typing import Any

from .common import ARTIFACT_ROOT, embedded_digest_valid, load_json, publish
from .environment import PREFLIGHT
from .p0_baseline import CANDIDATE_REFERENCE, PROTOCOL, REFERENCE


P6 = ARTIFACT_ROOT / "p6-decision"
DECISION = P6 / "a100-pilot-terminal-decision-v1.json"
DECISION_V2 = P6 / "a100-pilot-terminal-decision-v2.json"


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


def reference_complete_decision_body() -> dict[str, Any]:
    prior = load_json(DECISION)
    supplement = load_json(CANDIDATE_REFERENCE)
    if not embedded_digest_valid(prior, "decision_digest"):
        raise RuntimeError("P6 v1 decision digest is invalid")
    if not embedded_digest_valid(supplement, "supplement_digest"):
        raise RuntimeError("P0 candidate supplement digest is invalid")
    if prior["status"] != "NO_GO_A100_OPERATIONAL_INSTABILITY":
        raise RuntimeError("P6 v1 is not the expected operational No-Go")
    if supplement["provenance_policy"]["P1_decision_changed"] is not False:
        raise RuntimeError("candidate supplement attempted to change the P1 decision")
    return {
        "schema": "aic-a100-pilot.terminal-decision.v2",
        "status": "NO_GO_A100_OPERATIONAL_INSTABILITY",
        "terminal_phase": "P6_FORMAL_DECISION_WITH_COMPLETE_P0_REFERENCE_CONTRACT",
        "supersedes_without_mutation": {
            "path": DECISION.relative_to(ARTIFACT_ROOT.parent.parent).as_posix(),
            "decision_digest": prior["decision_digest"],
            "status_unchanged": True,
        },
        "evidence_binding": {
            **dict(prior["evidence_binding"]),
            "P0_candidate_reference_supplement_digest": supplement[
                "supplement_digest"
            ],
        },
        "P0_reference_contract": {
            "status": "COMPLETE_BY_ADDITIVE_SUPPLEMENT",
            "five_source_state_references": len(supplement["cases"]),
            "exact_terminal_references_available": sum(
                case["exact_candidate_terminal_reference"]["availability"]
                == "AVAILABLE_FROZEN_HISTORICAL_CPU_RESULT"
                for case in supplement["cases"]
            ),
            "exact_class_absent_from_source_catalog": sum(
                case["exact_candidate_terminal_reference"]["availability"]
                == "NO_EXACT_CANDIDATE_IN_SOURCE_CATALOG"
                for case in supplement["cases"]
            ),
            "approximate_terminal_references_available": sum(
                case["approximate_candidate_terminal_reference"]["availability"]
                == "AVAILABLE_FROZEN_HISTORICAL_CPU_RESULT"
                for case in supplement["cases"]
            ),
            "new_candidate_energy_evaluations": supplement["provenance_policy"][
                "new_candidate_energy_evaluations"
            ],
            "new_optimizer_runs": supplement["provenance_policy"][
                "new_optimizer_runs"
            ],
            "new_FCI_evaluations": supplement["provenance_policy"][
                "new_FCI_evaluations"
            ],
        },
        "phase_status": dict(prior["phase_status"]),
        "decision_rationale": prior["decision_rationale"],
        "hardware_observation": dict(prior["hardware_observation"]),
        "route_counters": dict(prior["route_counters"]),
        "parity_table": list(prior["parity_table"]),
        "parity_table_status": prior["parity_table_status"],
        "speedup_table": list(prior["speedup_table"]),
        "speedup_table_status": prior["speedup_table_status"],
        "slurm_job_ids": list(prior["slurm_job_ids"]),
        "rollback": dict(prior["rollback"]),
        "scientific_boundaries": dict(prior["scientific_boundaries"]),
        "safe_reentry_conditions": list(prior["safe_reentry_conditions"]),
    }


def publish_reference_complete_decision() -> dict[str, Any]:
    return publish(DECISION_V2, reference_complete_decision_body(), "decision_digest")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--publish-reference-complete-v2", action="store_true")
    arguments = parser.parse_args()
    if arguments.publish == arguments.publish_reference_complete_v2:
        raise RuntimeError("select exactly one publication action")
    value = (
        publish_decision()
        if arguments.publish
        else publish_reference_complete_decision()
    )
    print(json.dumps(value, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

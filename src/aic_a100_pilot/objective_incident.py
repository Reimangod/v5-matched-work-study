"""Record the post-kernel H2 evidence-serialization incident and bounded retry."""

from __future__ import annotations

import argparse
import json
from typing import Any

from .common import ARTIFACT_ROOT, embedded_digest_valid, load_json, publish
from .p3_objective_contract import CONTRACT


INCIDENT = ARTIFACT_ROOT / "p3-objective-parity/h2-serialization-incident-v1.json"


def incident_body() -> dict[str, Any]:
    contract = load_json(CONTRACT)
    if not embedded_digest_valid(contract, "contract_digest"):
        raise RuntimeError("P3 objective contract digest is invalid")
    return {
        "schema": "aic-a100-pilot.p3-objective-serialization-incident.v1",
        "status": "RETRY_AUTHORIZED_SAME_FROZEN_H2_ONLY",
        "P3_objective_contract_digest": contract["contract_digest"],
        "slurm_job": {
            "job_id": 1994,
            "state": "FAILED",
            "elapsed_seconds": 5,
            "exit_code": "1:0",
        },
        "failure": {
            "class": "POST_KERNEL_CPU_INDEPENDENT_STATE_EVIDENCE_KEY_ERROR",
            "cause": (
                "The production CPU helper validates but does not return the "
                "independent statevector. The pilot attempted to read that absent "
                "return key after both paired computations."
            ),
            "scientific_nonparity_observed": False,
            "raw_result_JSON_persisted": False,
            "candidate_values_printed_to_log": False,
            "partial_result_used": False,
        },
        "work_disclosure": {
            "paired_CPU_candidate_computation_reached": True,
            "GPU_candidate_computation_reached": True,
            "candidate_outcome_records_persisted": 0,
            "FCI_evaluations": 0,
        },
        "remediation": {
            "capture_counted_CPU_independent_state_inside_the_existing_helper_call": True,
            "repeat_CPU_run_for_counter_reconciliation": False,
            "candidate_selection_changed": False,
            "optimizer_changed": False,
            "tolerance_changed": False,
            "same_item_retry_only": "h2",
        },
        "successor_authorization": {
            "h2_same_candidate_retry": "AUTHORIZED_ADDITIVE_RETRY",
            "h4_and_later": "NOT_AUTHORIZED_PENDING_H2_SUCCESS",
            "P4_end_to_end": "NOT_AUTHORIZED",
            "P5": "NOT_AUTHORIZED",
        },
    }


def publish_incident() -> dict[str, Any]:
    return publish(INCIDENT, incident_body(), "incident_digest")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--publish", action="store_true")
    arguments = parser.parse_args()
    if not arguments.publish:
        raise RuntimeError("select --publish")
    print(json.dumps(publish_incident(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

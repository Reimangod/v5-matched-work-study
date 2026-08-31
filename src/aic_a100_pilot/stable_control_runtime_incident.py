"""Immutable audit of the stable-control v1 job-2015 accounting incident."""

from __future__ import annotations

import argparse
import json
from typing import Any

from .common import (
    ARTIFACT_ROOT,
    ROOT,
    embedded_digest_valid,
    load_json,
    publish,
    sha256_file,
)
from .stable_control_contract import CONTRACT


INCIDENT = (
    ARTIFACT_ROOT
    / "p7-unified-stable-v1/incidents/job-2015-runtime-accounting-v1.json"
)
H2_RESULT = ARTIFACT_ROOT / "p7-unified-stable-v1/results/h2.json"


def incident_body() -> dict[str, Any]:
    contract = load_json(CONTRACT)
    h2_result = load_json(H2_RESULT)
    if not embedded_digest_valid(contract, "contract_digest"):
        raise RuntimeError("stable-control v1 contract digest is invalid")
    if not embedded_digest_valid(h2_result, "record_digest"):
        raise RuntimeError("stable-control v1 H2 digest is invalid")
    return {
        "schema": "aic-a100-pilot.stable-control-runtime-incident.v1",
        "status": "NO_GO_A100_STABLE_CONTROL_V1_RUNTIME_ACCOUNTING_MISMATCH",
        "contract_binding": {
            "path": CONTRACT.relative_to(ROOT).as_posix(),
            "sha256": sha256_file(CONTRACT),
            "contract_digest": contract["contract_digest"],
        },
        "prior_h2_result": {
            "path": H2_RESULT.relative_to(ROOT).as_posix(),
            "sha256": sha256_file(H2_RESULT),
            "record_digest": h2_result["record_digest"],
            "interpretation": (
                "engineering sanity passed, but the zero-dimensional optimizer "
                "branch returned before the inherited accounting assertion"
            ),
        },
        "slurm": {
            "source_git_head": "63ed3952029c124c68d46f63244cfcf98fb6eb53",
            "h2_job": {
                "job_id": 2012,
                "state": "COMPLETED",
                "exit_code": "0:0",
                "elapsed": "00:00:08",
            },
            "cancelled_prestart_reroute_job": {
                "job_id": 2014,
                "state": "CANCELLED",
                "elapsed": "00:00:00",
            },
            "failed_h4_job": {
                "job_id": 2015,
                "partition": "gpu-short",
                "state": "FAILED",
                "exit_code": "1:0",
                "elapsed": "00:00:15",
                "start": "2026-08-31T16:03:20+09:00",
                "end": "2026-08-31T16:03:35+09:00",
                "remote_log_relative_path": "repo/slurm-2015.out",
                "remote_log_sha256": (
                    "c9546abcca86a7f7013f344d0b561eb1f0e8411f0199ecc58674d8b5bf11fcec"
                ),
                "remote_log_size_bytes": 2626,
            },
            "dependency_cancelled_jobs": [
                {"job_id": 2016, "alias": "lih", "state": "CANCELLED"},
                {"job_id": 2017, "alias": "h6", "state": "CANCELLED"},
                {"job_id": 2018, "alias": "beh2", "state": "CANCELLED"},
            ],
        },
        "h4_preparation": {
            "manifest_digest": (
                "afb0e8627688a1329680199edb82e82e5f576f3504476d6ea7111dc7b1ba9064"
            ),
            "bundle_sha256": (
                "bc71737d0597bfc464ffc6fabda3d733943d047dd6fbef2c679e2e5644367845"
            ),
            "bundle_size_bytes": 146051,
            "scope": "SOURCE_PREPARATION_ONLY",
            "candidate_outcomes_in_preparation_process": 0,
            "warning": (
                "the preparation counters do not describe the later numerical "
                "process that failed"
            ),
        },
        "failure": {
            "stage": "after CPU BFGS and before GPU BFGS",
            "exception": "aic_a100_pilot.common.A100PilotError",
            "message": (
                "unified optimizer accounting differs: optimizer-objective-energy "
                "was false while optimizer-start, optimizer-iteration, and "
                "full-gradient-evaluation were true"
            ),
            "cause": {
                "stable_control_v1_recorded": "optimizer-objective-raw-energy",
                "inherited_optimizer_required": "optimizer-objective-energy",
                "classification": "OUTCOME_INDEPENDENT_EVENT_NAME_MISMATCH",
            },
        },
        "outcome_boundary": {
            "H4_CPU_determinism_probe_reached": True,
            "H4_GPU_determinism_probe_reached": True,
            "H4_CPU_optimizer_computation_reached": True,
            "H4_CPU_optimizer_values_persisted": False,
            "H4_CPU_optimizer_values_printed_to_log": False,
            "H4_GPU_optimizer_computation_reached": False,
            "H4_result_JSON_persisted": False,
            "LiH_H6_BeH2_candidate_outcomes": 0,
            "FCI_evaluations": 0,
            "existing_90_item_execution": "UNCHANGED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "preservation": {
            "v1_contract_modified": False,
            "v1_H2_result_modified": False,
            "v1_H4_preparation_deleted_or_modified": False,
            "remote_job_log_deleted_or_modified": False,
            "v1_namespace_retry_authorized": False,
        },
        "authorized_successor": {
            "kind": "ADDITIVE_STABLE_CONTROL_V2",
            "allowed_changes": [
                "make the optimizer objective event name agree with the frozen accounting contract",
                "validate accounting for zero- and nonzero-dimensional optimization",
                "persist exclusive attempt-start and failure-incident evidence",
                "use a new preparation and result namespace",
            ],
            "scientific_numerics_change": False,
            "candidate_or_threshold_change": False,
            "case_order": ["h2", "h4", "lih", "h6", "beh2"],
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

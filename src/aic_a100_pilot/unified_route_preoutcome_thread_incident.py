"""Immutable audit of the job-2005 pre-outcome thread-contract incident."""

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


CONTRACT_V3 = (
    ARTIFACT_ROOT
    / "p3-unified-route-v3/unified-route-trajectory-contract-v3.json"
)
INCIDENT = (
    ARTIFACT_ROOT
    / "p3-unified-route-v3/thread-preflight-incident-job2005-v1.json"
)


def incident_body() -> dict[str, Any]:
    contract = load_json(CONTRACT_V3)
    if not embedded_digest_valid(contract, "contract_digest"):
        raise RuntimeError("unified-route v3 contract digest is invalid")
    return {
        "schema": "aic-a100-pilot.unified-route-thread-incident.v1",
        "status": "PRE_OUTCOME_ENGINEERING_INCIDENT_H2_SOURCE_THREAD_CONTRACT",
        "contract_binding": {
            "path": CONTRACT_V3.relative_to(ROOT).as_posix(),
            "sha256": sha256_file(CONTRACT_V3),
            "contract_digest": contract["contract_digest"],
        },
        "job": {
            "slurm_job_id": 2005,
            "git_head": "d27754fa28fd9b9053a0dd60cc45bbec7aa9f086",
            "state": "FAILED",
            "exit_code": "1:0",
            "elapsed": "00:00:03",
            "start": "2026-08-31T06:51:27",
            "end": "2026-08-31T06:51:30",
            "remote_log_relative_path": "repo/slurm-2005.out",
            "remote_log_sha256": (
                "3f3b1ddad19d33f6f11da8e9a011b8d4cbd84533a4dd6e61bd108f2f51bc136f"
            ),
            "remote_log_size_bytes": 1682,
        },
        "failure": {
            "stage": "historical source runtime preflight before candidate preparation",
            "exception": "QueueBoundRuntimeError",
            "message": "thread environment differs from frozen environment",
            "cause": (
                "H2 source reconstruction requires its historical two-thread "
                "environment, while v3 set the process environment to one thread "
                "before reconstruction"
            ),
        },
        "outcome_boundary": {
            "case_output_files": 0,
            "candidate_states": 0,
            "candidate_energy_evaluations": 0,
            "candidate_gradient_evaluations": 0,
            "optimizer_runs": 0,
            "FCI_evaluations": 0,
            "H2_parity_result": "NOT_OBSERVED",
            "H4_LiH_H6_BeH2": "NOT_AUTHORIZED_NOT_EXECUTED",
            "complete_item_timing": "NOT_AUTHORIZED_NOT_EXECUTED",
        },
        "preservation": {
            "remote_log_deleted_or_modified": False,
            "v1_v2_v3_contracts_modified": False,
            "historical_hybrid_No_Go_modified": False,
        },
        "authorized_successor": (
            "freeze a v4 contract that reconstructs each source under its immutable "
            "historical thread environment, then enforces and records a one-thread "
            "limit for the numerical CPU/GPU parity route"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--publish", action="store_true")
    arguments = parser.parse_args()
    if not arguments.publish:
        raise RuntimeError("select --publish")
    print(json.dumps(publish(INCIDENT, incident_body(), "incident_digest"), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

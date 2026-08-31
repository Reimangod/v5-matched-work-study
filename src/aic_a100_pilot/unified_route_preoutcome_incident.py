"""Immutable audit of the job-2004 pre-outcome metadata incident."""

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


CONTRACT_V2 = (
    ARTIFACT_ROOT
    / "p3-unified-route-v2/unified-route-trajectory-contract-v2.json"
)
INCIDENT = (
    ARTIFACT_ROOT
    / "p3-unified-route-v2/runtime-metadata-incident-job2004-v1.json"
)


def incident_body() -> dict[str, Any]:
    contract = load_json(CONTRACT_V2)
    if not embedded_digest_valid(contract, "contract_digest"):
        raise RuntimeError("unified-route v2 contract digest is invalid")
    return {
        "schema": "aic-a100-pilot.unified-route-preoutcome-incident.v1",
        "status": "PRE_OUTCOME_ENGINEERING_INCIDENT_QISKIT_METADATA_UNAVAILABLE",
        "contract_binding": {
            "path": CONTRACT_V2.relative_to(ROOT).as_posix(),
            "sha256": sha256_file(CONTRACT_V2),
            "contract_digest": contract["contract_digest"],
        },
        "job": {
            "slurm_job_id": 2004,
            "git_head": "56ae2bf68f5dd6fe6b7ffb165070acc03afed466",
            "state": "FAILED",
            "exit_code": "1:0",
            "elapsed": "00:00:02",
            "start": "2026-08-31T06:47:49",
            "end": "2026-08-31T06:47:51",
            "remote_log_relative_path": "repo/slurm-2004.out",
            "remote_log_sha256": (
                "428ce1a32c48d158a17734669caa3df820f63e7c0c98eb33d6fa44998a015599"
            ),
            "remote_log_size_bytes": 1833,
        },
        "failure": {
            "stage": "runtime identity before predecessor and case preparation",
            "exception": "importlib.metadata.PackageNotFoundError",
            "missing_distribution_name": "qiskit",
            "cause": (
                "the importable pinned Qiskit installation exposes its package "
                "version through a different distribution/module identity"
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
            "v1_contract_modified": False,
            "v2_contract_modified": False,
            "historical_hybrid_No_Go_modified": False,
        },
        "authorized_successor": (
            "freeze an additive v3 contract using import-aware software version "
            "resolution before retrying H2"
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

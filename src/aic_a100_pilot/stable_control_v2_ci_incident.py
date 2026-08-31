"""Pre-outcome audit of the first stable-control v2 GitHub CI attempt."""

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
from .stable_control_v2_contract import CONTRACT


INCIDENT = (
    ARTIFACT_ROOT
    / "p8-unified-stable-v2/incidents/github-ci-run-33383518953-v1.json"
)
CORRECTED_WORKFLOW = (
    ROOT / ".github/workflows/aic-a100-stable-control-v2-runtime-gate.yml"
)
RETRY_GATE = (
    ARTIFACT_ROOT
    / "p8-unified-stable-v2/ci-runtime-successor-gate-v1.json"
)


def incident_body() -> dict[str, Any]:
    contract = load_json(CONTRACT)
    if not embedded_digest_valid(contract, "contract_digest"):
        raise RuntimeError("stable-control v2 contract digest is invalid")
    return {
        "schema": "aic-a100-pilot.stable-control-v2-ci-incident.v1",
        "status": "PRE_OUTCOME_CI_ENVIRONMENT_INCIDENT_MISSING_NUMPY",
        "contract_binding": {
            "path": CONTRACT.relative_to(ROOT).as_posix(),
            "sha256": sha256_file(CONTRACT),
            "contract_digest": contract["contract_digest"],
        },
        "github_actions": {
            "run_id": 33383518953,
            "job_id": 99460907869,
            "head_sha": "b6c8e28703469b06ab8469e6cd865b309daa8b6f",
            "workflow": "AIC A100 stable-control v2 gate",
            "conclusion": "failure",
            "url": (
                "https://github.com/Reimangod/v5-matched-work-study/"
                "actions/runs/33383518953"
            ),
        },
        "failure": {
            "stage": "pytest collection before any test body",
            "exception": "ModuleNotFoundError: No module named 'numpy'",
            "cause": (
                "the root project test extra installs pytest/jsonschema but does "
                "not declare the pinned scientific NumPy/SciPy runtime"
            ),
            "scientific_code_executed": False,
            "test_assertion_reached": False,
        },
        "outcome_boundary": {
            "candidate_state_preparations": 0,
            "candidate_energy_evaluations": 0,
            "candidate_gradient_evaluations": 0,
            "optimizer_runs": 0,
            "FCI_evaluations": 0,
            "AIC_jobs_submitted_after_v2_freeze": 0,
            "existing_90_item_execution": "UNCHANGED",
        },
        "preservation": {
            "stable_control_v2_contract_modified": False,
            "stable_control_v2_runtime_sources_modified": False,
            "failed_workflow_modified": False,
        },
        "authorized_successor": {
            "scope": "CI_ENVIRONMENT_RETRY_ONLY",
            "use_parent_pinned_lock": True,
            "scientific_dependency_version_change": False,
            "AIC_execution_before_corrected_CI_success": "NOT_AUTHORIZED",
        },
    }


def retry_gate_body() -> dict[str, Any]:
    incident = load_json(INCIDENT)
    contract = load_json(CONTRACT)
    if not embedded_digest_valid(incident, "incident_digest"):
        raise RuntimeError("stable-control v2 CI incident digest is invalid")
    if not embedded_digest_valid(contract, "contract_digest"):
        raise RuntimeError("stable-control v2 contract digest is invalid")
    return {
        "schema": "aic-a100-pilot.stable-control-v2-ci-successor-gate.v1",
        "status": "GO_CORRECTED_CI_RETRY_ONLY",
        "contract_digest": contract["contract_digest"],
        "incident_digest": incident["incident_digest"],
        "corrected_workflow": {
            "path": CORRECTED_WORKFLOW.relative_to(ROOT).as_posix(),
            "sha256": sha256_file(CORRECTED_WORKFLOW),
            "pinned_python": "3.10.19",
            "pinned_uv": "0.9.8",
            "dependency_source": "provenance/dvg-obs-ceo/uv.lock",
            "uv_frozen": True,
        },
        "authorization": {
            "corrected_exact_commit_CI": "AUTHORIZED",
            "AIC_H2": "NOT_AUTHORIZED_UNTIL_CORRECTED_CI_SUCCESS",
            "AIC_H4_LiH_H6_BeH2": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--publish-incident", action="store_true")
    parser.add_argument("--publish-retry-gate", action="store_true")
    arguments = parser.parse_args()
    if arguments.publish_incident == arguments.publish_retry_gate:
        raise RuntimeError("select exactly one publication")
    if arguments.publish_incident:
        result = publish(INCIDENT, incident_body(), "incident_digest")
    else:
        result = publish(RETRY_GATE, retry_gate_body(), "gate_digest")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

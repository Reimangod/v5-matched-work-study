"""Immutable closure of the stable-control v2 H6 parity failure."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from v5_matched_work.atomic_artifacts import write_bytes_exclusive

from .common import (
    ARTIFACT_ROOT,
    ROOT,
    embedded_digest_valid,
    load_json,
    publish,
    sha256_file,
)
from .stable_control_v2_contract import CONTRACT


H6_RESULT = (
    ARTIFACT_ROOT
    / "p8-unified-stable-v2/terminal-evidence/h6-result-v2.json"
)
NO_GO = (
    ARTIFACT_ROOT
    / "p8-unified-stable-v2/incidents/h6-parity-no-go-v1.json"
)
EXPECTED_H6_RESULT_SHA256 = (
    "3dba7413f6816a78244f86e9dbb954cd2629918e343e350d2011efa4ac0decbf"
)
EXPECTED_H6_START_SHA256 = (
    "abe45832885574bfb14d6affc99205e0af5ac8a238cbe594081a606ef25974ba"
)
EXPECTED_H6_PREPARATION_SHA256 = (
    "c243a7a2c0101503366686d73fce213a2a7e0e9985d9d9026b5d2f06e5044c1e"
)
EXPECTED_H6_LOG_SHA256 = (
    "ea633cf5e1b0f668bc967bb64e4a99416d405915fbf1f0823e7443c9fcefc3d8"
)
EXPECTED_FAILED_CHECKS = {
    "optimizer_control_codes",
    "terminal_decision",
    "terminal_state",
    "trajectory_iteration_parity",
}


def validate_h6_result(path: Path = H6_RESULT) -> dict[str, Any]:
    if sha256_file(path) != EXPECTED_H6_RESULT_SHA256:
        raise RuntimeError("stable-control v2 H6 result SHA-256 differs")
    result = load_json(path)
    if not embedded_digest_valid(result, "record_digest"):
        raise RuntimeError("stable-control v2 H6 record digest is invalid")
    failed = {key for key, value in result["checks"].items() if not value}
    expected = {
        "schema": "aic-a100-pilot.stable-control-trajectory-case.v2",
        "status": "FAIL",
        "alias": "h6",
        "candidate_id": (
            "candidate-v1:96e910655d1cb7144517ad76edf203d400b95adb7810a358e9859b683144cebe"
        ),
    }
    if any(result.get(key) != value for key, value in expected.items()):
        raise RuntimeError("stable-control v2 H6 terminal identity differs")
    if failed != EXPECTED_FAILED_CHECKS:
        raise RuntimeError(f"stable-control v2 H6 failed checks differ: {failed}")
    boundary = result["scientific_boundary"]
    if boundary["FCI_evaluations"] != 0:
        raise RuntimeError("unexpected H6 FCI evaluation")
    if boundary["existing_90_item_execution"] != "UNCHANGED":
        raise RuntimeError("H6 result changed the existing 90-item execution")
    if result["route_counters"]["gpu"]["N_cpu_fallback"] != 0:
        raise RuntimeError("H6 GPU route used a CPU fallback")
    return result


def import_h6_result(source: Path) -> Path:
    payload = source.read_bytes()
    import hashlib

    if hashlib.sha256(payload).hexdigest() != EXPECTED_H6_RESULT_SHA256:
        raise RuntimeError("refusing to import an unregistered H6 result")
    parsed = json.loads(payload.decode("utf-8"))
    if not isinstance(parsed, dict) or not embedded_digest_valid(
        parsed, "record_digest"
    ):
        raise RuntimeError("refusing to import malformed H6 evidence")
    write_bytes_exclusive(H6_RESULT, payload)
    validate_h6_result(H6_RESULT)
    return H6_RESULT


def no_go_body() -> dict[str, Any]:
    contract = load_json(CONTRACT)
    result = validate_h6_result()
    if not embedded_digest_valid(contract, "contract_digest"):
        raise RuntimeError("stable-control v2 contract digest is invalid")
    cpu = result["cpu"]
    gpu = result["gpu"]
    return {
        "schema": "aic-a100-pilot.stable-control-v2-h6-no-go.v1",
        "status": "NO_GO_A100_STABLE_CONTROL_V2_H6_PARITY",
        "contract_binding": {
            "path": CONTRACT.relative_to(ROOT).as_posix(),
            "sha256": sha256_file(CONTRACT),
            "contract_digest": contract["contract_digest"],
        },
        "h6_result": {
            "path": H6_RESULT.relative_to(ROOT).as_posix(),
            "sha256": sha256_file(H6_RESULT),
            "record_digest": result["record_digest"],
            "failed_registered_checks": sorted(EXPECTED_FAILED_CHECKS),
        },
        "remote_evidence": {
            "attempt_start_sha256": EXPECTED_H6_START_SHA256,
            "preparation_manifest_sha256": EXPECTED_H6_PREPARATION_SHA256,
            "slurm_log_sha256": EXPECTED_H6_LOG_SHA256,
            "slurm_job": {
                "job_id": 2033,
                "state": "FAILED",
                "exit_code": "2:0",
                "elapsed": "02:40:54",
                "start": "2026-08-31T19:50:58+09:00",
                "end": "2026-08-31T22:31:52+09:00",
            },
            "dependent_BeH2_job": {
                "job_id": 2035,
                "state": "CANCELLED",
                "elapsed": "00:00:00",
            },
        },
        "scientific_interpretation": {
            "engineering_exception": False,
            "CPU_GPU_terminal_control_energy_difference_hartree": result[
                "terminal_differences"
            ]["control_energy_hartree"],
            "CPU_GPU_terminal_gradient_max_abs": result[
                "terminal_differences"
            ]["control_gradient_max_abs"],
            "CPU_GPU_terminal_state_max_abs": result[
                "terminal_differences"
            ]["phase_aligned_state_max_abs"],
            "CPU_terminal_decision": cpu["terminal_decision"],
            "GPU_terminal_decision": gpu["terminal_decision"],
            "frozen_historical_CPU_terminal_decision": "ACCEPTED",
            "CPU_optimizer_status": cpu["optimizer_terminal"],
            "GPU_optimizer_status": gpu["optimizer_terminal"],
            "cause_boundary": (
                "The paired stable-control route did not reproduce the frozen "
                "historical CPU optimizer terminal.  This is not evidence of "
                "an A100 hardware failure or of a V5 performance result."
            ),
        },
        "preservation": {
            "v2_contract_modified": False,
            "v2_H2_H4_LiH_results_modified": False,
            "H6_same_namespace_retry": "NOT_AUTHORIZED",
            "threshold_relaxation": "NOT_AUTHORIZED",
            "BeH2_production_continuation": "NOT_AUTHORIZED",
            "existing_90_item_execution": "UNCHANGED",
            "FCI_evaluations": 0,
            "performance_claim": "NOT_AUTHORIZED",
        },
        "authorized_successor": {
            "scope": "ONE_BEH2_POST_FAILURE_DIAGNOSTIC_ONLY",
            "purpose": (
                "Determine whether the registered v2 numerical parity failure "
                "is H6-specific without treating BeH2 as an independent "
                "confirmation or production-adoption result."
            ),
            "H6_retry": "NOT_AUTHORIZED",
            "BeH2_single_diagnostic": "AUTHORIZED_AFTER_NEW_CONTRACT_AND_CI",
            "numerics_candidate_optimizer_and_threshold_changes": False,
            "timing": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
    }


def publish_no_go() -> dict[str, Any]:
    return publish(NO_GO, no_go_body(), "incident_digest")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--import-result", type=Path)
    parser.add_argument("--publish-no-go", action="store_true")
    arguments = parser.parse_args()
    if (arguments.import_result is None) == (not arguments.publish_no_go):
        raise RuntimeError("select exactly one operation")
    if arguments.import_result is not None:
        result: Any = {"imported": str(import_h6_result(arguments.import_result))}
    else:
        result = publish_no_go()
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

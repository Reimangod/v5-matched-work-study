"""Immutable closure of the stable-control v2 BeH2 diagnostic."""

from __future__ import annotations

import argparse
import hashlib
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
from .p3_objective_contract import CONTRACT as OBJECTIVE_CONTRACT
from .stable_control_v2_h6_no_go import NO_GO as H6_NO_GO
from .stable_control_v2_postfailure_contract import CONTRACT


BEH2_RESULT = (
    ARTIFACT_ROOT
    / "p9-stable-control-v2-postfailure-diagnostic/terminal-evidence/beh2-result-v1.json"
)
TERMINAL_DECISION = (
    ARTIFACT_ROOT
    / "p9-stable-control-v2-postfailure-diagnostic/terminal-decision/postfailure-diagnostic-no-go-v1.json"
)
EXPECTED_BEH2_RESULT_SHA256 = (
    "3bf2845a93e016ac8f95f25f2e8daa400e11939a9629785a3451fe134d347f30"
)
EXPECTED_BEH2_START_SHA256 = (
    "d0022e305a3a0e36db340633471a42461bc75d1320fee58da7b7041510f6f0c8"
)
EXPECTED_BEH2_PREPARATION_SHA256 = (
    "0ca5afa82f2089c496bfaf0c563af650bbdd68ae1a47320ba504941a4ed58081"
)
EXPECTED_BEH2_BUNDLE_SHA256 = (
    "53b7030dd08d0e023019fcad1c3fd2d8de755c5cc03428ed900d809f9a2616a1"
)
EXPECTED_BEH2_LOG_SHA256 = (
    "09555f3e3a445c89fdfd582caa5b699f52455e7f5312e8e795a4ee95fb33670c"
)
EXPECTED_FAILED_CHECKS = {"terminal_decision"}


def _beh2_specification() -> dict[str, Any]:
    objective = load_json(OBJECTIVE_CONTRACT)
    if not embedded_digest_valid(objective, "contract_digest"):
        raise RuntimeError("objective contract digest is invalid")
    matches = [
        case
        for case in objective["selection_policy"]["cases"]
        if case["alias"] == "beh2"
    ]
    if len(matches) != 1:
        raise RuntimeError("BeH2 objective specification is not unique")
    return matches[0]


def validate_beh2_result(path: Path = BEH2_RESULT) -> dict[str, Any]:
    if sha256_file(path) != EXPECTED_BEH2_RESULT_SHA256:
        raise RuntimeError("stable-control v2 BeH2 result SHA-256 differs")
    result = load_json(path)
    if not embedded_digest_valid(result, "record_digest"):
        raise RuntimeError("stable-control v2 BeH2 record digest is invalid")
    expected = {
        "schema": (
            "aic-a100-pilot.stable-control-v2-postfailure-diagnostic-case.v1"
        ),
        "status": "DIAGNOSTIC_FAIL",
        "alias": "beh2",
        "case_id": "beh2-3.0",
        "candidate_id": (
            "candidate-v1:f0f345e2a538a1ea9175b163b0091321911ccce650e2656ef8fe9cd3d8f8c1d1"
        ),
    }
    if any(result.get(key) != value for key, value in expected.items()):
        raise RuntimeError("stable-control v2 BeH2 terminal identity differs")
    failed = {key for key, passed in result["checks"].items() if not passed}
    if failed != EXPECTED_FAILED_CHECKS:
        raise RuntimeError(f"stable-control v2 BeH2 failed checks differ: {failed}")
    if result["route_counters"]["cpu"]["N_cpu_fallback"] != 0:
        raise RuntimeError("BeH2 CPU route recorded an unexpected fallback")
    if result["route_counters"]["gpu"]["N_cpu_fallback"] != 0:
        raise RuntimeError("BeH2 GPU route used a CPU fallback")
    boundary = result["scientific_boundary"]
    if boundary["FCI_evaluations"] != 0:
        raise RuntimeError("unexpected BeH2 FCI evaluation")
    if boundary["existing_90_item_execution"] != "UNCHANGED":
        raise RuntimeError("BeH2 diagnostic changed the 90-item execution")
    if result["execution_policy"]["threshold_or_numerics_changed"]:
        raise RuntimeError("BeH2 diagnostic reports a numerical protocol change")
    return result


def import_beh2_result(source: Path) -> Path:
    payload = source.read_bytes()
    if hashlib.sha256(payload).hexdigest() != EXPECTED_BEH2_RESULT_SHA256:
        raise RuntimeError("refusing to import an unregistered BeH2 result")
    parsed = json.loads(payload.decode("utf-8"))
    if not isinstance(parsed, dict) or not embedded_digest_valid(
        parsed, "record_digest"
    ):
        raise RuntimeError("refusing to import malformed BeH2 evidence")
    write_bytes_exclusive(BEH2_RESULT, payload)
    validate_beh2_result(BEH2_RESULT)
    return BEH2_RESULT


def terminal_decision_body() -> dict[str, Any]:
    contract = load_json(CONTRACT)
    h6_no_go = load_json(H6_NO_GO)
    result = validate_beh2_result()
    specification = _beh2_specification()
    if not embedded_digest_valid(contract, "contract_digest"):
        raise RuntimeError("post-failure contract digest is invalid")
    if not embedded_digest_valid(h6_no_go, "incident_digest"):
        raise RuntimeError("H6 No-Go digest is invalid")
    cpu = result["cpu"]
    gpu = result["gpu"]
    return {
        "schema": "aic-a100-pilot.stable-control-v2-postfailure-decision.v1",
        "status": "NO_GO_A100_STABLE_CONTROL_V2_HISTORICAL_OPTIMIZER_SEMANTICS",
        "contract_binding": {
            "path": CONTRACT.relative_to(ROOT).as_posix(),
            "sha256": sha256_file(CONTRACT),
            "contract_digest": contract["contract_digest"],
        },
        "H6_no_go_binding": {
            "path": H6_NO_GO.relative_to(ROOT).as_posix(),
            "sha256": sha256_file(H6_NO_GO),
            "incident_digest": h6_no_go["incident_digest"],
        },
        "BeH2_result": {
            "path": BEH2_RESULT.relative_to(ROOT).as_posix(),
            "sha256": sha256_file(BEH2_RESULT),
            "record_digest": result["record_digest"],
            "failed_registered_checks": sorted(EXPECTED_FAILED_CHECKS),
        },
        "remote_evidence": {
            "attempt_start_sha256": EXPECTED_BEH2_START_SHA256,
            "preparation_manifest_sha256": EXPECTED_BEH2_PREPARATION_SHA256,
            "preparation_bundle_sha256": EXPECTED_BEH2_BUNDLE_SHA256,
            "slurm_log_sha256": EXPECTED_BEH2_LOG_SHA256,
            "slurm_job": {
                "job_id": 2042,
                "state": "FAILED",
                "exit_code": "2:0",
                "elapsed": "01:08:54",
                "start": "2026-09-01T02:00:42+09:00",
                "end": "2026-09-01T03:09:36+09:00",
                "node": "dgx-a100",
            },
        },
        "observed_BeH2_diagnostic": {
            "engineering_exception": False,
            "CPU_GPU_terminal_control_energy_difference_hartree": result[
                "terminal_differences"
            ]["control_energy_hartree"],
            "CPU_GPU_terminal_gradient_max_abs": result[
                "terminal_differences"
            ]["control_gradient_max_abs"],
            "CPU_GPU_terminal_state_max_abs": result["terminal_differences"][
                "phase_aligned_state_max_abs"
            ],
            "CPU_terminal_decision": cpu["terminal_decision"],
            "GPU_terminal_decision": gpu["terminal_decision"],
            "frozen_historical_CPU_terminal_decision": specification[
                "frozen_CPU_terminal_decision"
            ],
            "CPU_optimizer_status": cpu["optimizer_terminal"],
            "GPU_optimizer_status": gpu["optimizer_terminal"],
            "frozen_historical_CPU_optimizer_status": specification[
                "frozen_CPU_optimizer_terminal"
            ],
            "CPU_gradient_infinity_norm": cpu["gradient_infinity_norm"],
            "GPU_gradient_infinity_norm": gpu["gradient_infinity_norm"],
            "CPU_rejection_reasons": cpu["acceptance_rejection_reasons"],
            "GPU_rejection_reasons": gpu["acceptance_rejection_reasons"],
            "CPU_GPU_resource_vector_exact": cpu["resources"] == gpu["resources"],
            "CPU_GPU_optimizer_terminal_exact": (
                cpu["optimizer_terminal"] == gpu["optimizer_terminal"]
            ),
        },
        "scientific_interpretation": {
            "observed_scope": (
                "Under the frozen stable-control v2 route, paired CPU and A100 "
                "agree for the BeH2 candidate but both fail to reproduce the "
                "frozen historical CPU optimizer terminal decision."
            ),
            "cross_case_observation": (
                "H6 and BeH2 both show historical optimizer-terminal semantic "
                "non-reproduction. The BeH2 observation is inconsistent with "
                "an A100-only numerical discrepancy for this case."
            ),
            "not_supported": [
                "A100 hardware failure",
                "A100 production adoption",
                "A100 complete-item speedup",
                "V5 performance superiority or inferiority",
                "BeH2 independent confirmation",
            ],
        },
        "preservation": {
            "BeH2_attempts": 1,
            "BeH2_retry": "NOT_AUTHORIZED_NOT_PERFORMED",
            "H6_retry": "NOT_AUTHORIZED_NOT_PERFORMED",
            "threshold_or_numerics_changed": False,
            "contract_modified_after_outcome": False,
            "H6_No_Go_modified": False,
            "existing_90_item_execution": "UNCHANGED",
            "FCI_evaluations": 0,
            "performance_claim": "NOT_AUTHORIZED",
        },
        "authorized_successor": {
            "scope": "HISTORICAL_CPU_SEMANTICS_ROOT_CAUSE_ANALYSIS_ONLY",
            "allowed": [
                "reconstruct the exact historical CPU objective and optimizer path",
                "compare historical and stable-control numerical primitives outcome-free",
                "freeze a new bounded remediation before any retry",
            ],
            "not_authorized": [
                "H6 or BeH2 retry under the current contract",
                "threshold relaxation",
                "A100 production execution",
                "complete-item timing",
                "V5 performance claims",
            ],
        },
    }


def publish_terminal_decision() -> dict[str, Any]:
    return publish(
        TERMINAL_DECISION,
        terminal_decision_body(),
        "decision_digest",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--import-result", type=Path)
    parser.add_argument("--publish-decision", action="store_true")
    arguments = parser.parse_args()
    if (arguments.import_result is None) == (not arguments.publish_decision):
        raise RuntimeError("select exactly one operation")
    if arguments.import_result is not None:
        value: Any = {
            "imported": str(import_beh2_result(arguments.import_result))
        }
    else:
        value = publish_terminal_decision()
    print(json.dumps(value, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

"""Frozen authorization for one BeH2 diagnostic after the H6 v2 No-Go."""

from __future__ import annotations

import argparse
import copy
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
from .stable_control_v2_contract import CONTRACT as V2_CONTRACT
from .stable_control_v2_h6_no_go import H6_RESULT, NO_GO


V1_CONTRACT = (
    ARTIFACT_ROOT
    / "p9-stable-control-v2-postfailure-diagnostic/beh2-contract-v1.json"
)
CONTRACT = (
    ARTIFACT_ROOT
    / "p9-stable-control-v2-postfailure-diagnostic/beh2-contract-v2.json"
)
SOURCE_PATHS = (
    ROOT / "src/aic_a100_pilot/stable_control_v2_postfailure_route.py",
    ROOT / "scripts/aic/a100_stable_control_v2_beh2_diagnostic.sbatch",
)
VALIDATION_PATHS = (
    ROOT / "tests/test_aic_a100_stable_control_v2_postfailure.py",
    ROOT
    / ".github/workflows/aic-a100-stable-control-v2-postfailure-gate.yml",
)


def _binding(path, digest_field: str) -> dict[str, str]:
    value = load_json(path)
    if not embedded_digest_valid(value, digest_field):
        raise RuntimeError(f"invalid predecessor digest: {path}")
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": sha256_file(path),
        digest_field: value[digest_field],
    }


def contract_body() -> dict[str, Any]:
    v2 = load_json(V2_CONTRACT)
    no_go = load_json(NO_GO)
    h6 = load_json(H6_RESULT)
    if not embedded_digest_valid(v2, "contract_digest"):
        raise RuntimeError("stable-control v2 contract digest is invalid")
    if not embedded_digest_valid(no_go, "incident_digest"):
        raise RuntimeError("H6 No-Go digest is invalid")
    if not embedded_digest_valid(h6, "record_digest"):
        raise RuntimeError("H6 result digest is invalid")
    if no_go["status"] != "NO_GO_A100_STABLE_CONTROL_V2_H6_PARITY":
        raise RuntimeError("H6 No-Go status differs")
    v1 = load_json(V1_CONTRACT)
    if not embedded_digest_valid(v1, "contract_digest"):
        raise RuntimeError("post-failure v1 contract digest is invalid")
    missing = [
        path for path in (*SOURCE_PATHS, *VALIDATION_PATHS) if not path.is_file()
    ]
    if missing:
        raise RuntimeError(f"post-failure diagnostic is incomplete: {missing}")
    return {
        "schema": "aic-a100-pilot.stable-control-v2-postfailure-contract.v2",
        "status": "GO_ONE_BEH2_POST_FAILURE_DIAGNOSTIC_ONLY",
        "frozen_before_BeH2_diagnostic_outcome": True,
        "supersedes_before_outcome_without_mutation": {
            "path": V1_CONTRACT.relative_to(ROOT).as_posix(),
            "sha256": sha256_file(V1_CONTRACT),
            "contract_digest": v1["contract_digest"],
            "reason": (
                "The diagnostic relabel/restoration test was added after the "
                "v1 validation binding. No BeH2 preparation, state, energy, "
                "gradient, optimizer, or outcome had been executed."
            ),
            "BeH2_candidate_outcomes_before_v2_freeze": 0,
        },
        "predecessor_binding": {
            "stable_control_v2_contract": _binding(
                V2_CONTRACT, "contract_digest"
            ),
            "H6_terminal_result": _binding(H6_RESULT, "record_digest"),
            "H6_no_go": _binding(NO_GO, "incident_digest"),
        },
        "execution_scope": {
            "alias": "beh2",
            "case_id": "beh2-3.0",
            "maximum_attempts": 1,
            "new_namespace": "p9-stable-control-v2-postfailure-diagnostic",
            "H6_retry": "NOT_AUTHORIZED",
            "H2_H4_LiH_reexecution": "NOT_AUTHORIZED",
            "reason": (
                "The BeH2 observation is diagnostic characterization after an "
                "observed H6 failure; it is not independent confirmation."
            ),
        },
        "unchanged_numerical_contract": {
            "route_contract": copy.deepcopy(v2["route_contract"]),
            "optimizer_contract": copy.deepcopy(v2["optimizer_contract"]),
            "parity_requirements": copy.deepcopy(v2["parity_requirements"]),
            "candidate_changed": False,
            "ansatz_changed": False,
            "optimizer_changed": False,
            "control_quantization_changed": False,
            "threshold_changed": False,
            "molecular_source_changed": False,
        },
        "source_binding": {
            path.relative_to(ROOT).as_posix(): sha256_file(path)
            for path in SOURCE_PATHS
        },
        "validation_binding": {
            path.relative_to(ROOT).as_posix(): sha256_file(path)
            for path in VALIDATION_PATHS
        },
        "required_terminal_prefix": {
            "h2": "PASS",
            "h4": "PASS",
            "lih": "PASS",
            "h6": "FAIL_BOUND_TO_NO_GO",
        },
        "scientific_boundary": {
            "FCI_evaluations": 0,
            "existing_90_item_execution": "UNCHANGED",
            "candidate_attempt_timing": "NOT_RECORDED",
            "complete_item_speed_claim": "NOT_AUTHORIZED",
            "A100_production_adoption": "NOT_AUTHORIZED",
            "V5_performance_claim": "NOT_AUTHORIZED",
            "BeH2_independent_confirmation_claim": "NOT_AUTHORIZED",
        },
        "terminal_rule": {
            "persist_PASS_or_FAIL_without_retry": True,
            "threshold_relaxation_after_outcome": "NOT_AUTHORIZED",
            "successor_performance_execution": "NOT_AUTHORIZED",
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

"""Frozen additive successor to the stable-control v1 accounting incident."""

from __future__ import annotations

import argparse
import copy
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
from .stable_control_contract import CONTRACT as V1_CONTRACT
from .stable_control_runtime_incident import INCIDENT as V1_INCIDENT


CONTRACT = (
    ARTIFACT_ROOT
    / "p8-unified-stable-v2/stable-control-trajectory-contract-v2.json"
)
V1_H2_RESULT = ARTIFACT_ROOT / "p7-unified-stable-v1/results/h2.json"
SOURCE_PATHS = (
    ROOT / "src/aic_a100_pilot/stable_control_route.py",
    ROOT / "src/aic_a100_pilot/stable_control_v2_route.py",
    ROOT / "src/aic_a100_pilot/stable_control_v2_prepare.py",
    ROOT / "scripts/aic/a100_stable_control_v2_trajectory.sbatch",
)
VALIDATION_PATHS = (
    ROOT / "tests/test_aic_a100_stable_control.py",
    ROOT / "tests/test_aic_a100_stable_control_v2.py",
    ROOT / ".github/workflows/aic-a100-stable-control-v2-gate.yml",
)


def _binding(path: Path, *, digest_field: str) -> dict[str, str]:
    value = load_json(path)
    if not embedded_digest_valid(value, digest_field):
        raise RuntimeError(f"invalid evidence digest: {path}")
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": sha256_file(path),
        digest_field: str(value[digest_field]),
    }


def contract_body() -> dict[str, Any]:
    v1 = load_json(V1_CONTRACT)
    incident = load_json(V1_INCIDENT)
    h2 = load_json(V1_H2_RESULT)
    if not embedded_digest_valid(v1, "contract_digest"):
        raise RuntimeError("stable-control v1 contract digest is invalid")
    if not embedded_digest_valid(incident, "incident_digest"):
        raise RuntimeError("stable-control v1 incident digest is invalid")
    if not embedded_digest_valid(h2, "record_digest"):
        raise RuntimeError("stable-control v1 H2 result digest is invalid")
    if incident["status"] != (
        "NO_GO_A100_STABLE_CONTROL_V1_RUNTIME_ACCOUNTING_MISMATCH"
    ):
        raise RuntimeError("stable-control v1 incident status differs")
    missing = [
        path for path in (*SOURCE_PATHS, *VALIDATION_PATHS) if not path.is_file()
    ]
    if missing:
        raise RuntimeError(f"stable-control v2 implementation is incomplete: {missing}")

    route_contract = copy.deepcopy(v1["route_contract"])
    route_contract["optimizer_event_crosswalk"] = {
        "start": "optimizer-start",
        "iteration": "optimizer-iteration",
        "objective_energy": "optimizer-objective-energy",
        "full_gradient": "full-gradient-evaluation",
    }
    route_contract["optimizer_accounting_validation"] = (
        "REQUIRED_FOR_ZERO_AND_NONZERO_DIMENSIONS"
    )
    route_contract["failure_evidence"] = (
        "EXCLUSIVE_ATTEMPT_START_AND_EXCLUSIVE_INCIDENT_WITH_PARTIAL_COUNTERS"
    )
    route_contract["artifact_namespace"] = "p8-unified-stable-v2"

    scientific_boundary = copy.deepcopy(v1["scientific_boundary"])
    scientific_boundary["stable_control_v2_candidate_outcomes_before_freeze"] = 0

    return {
        "schema": "aic-a100-pilot.stable-control-trajectory-contract.v2",
        "status": "GO_BOUNDED_STABLE_CONTROL_V2_TRAJECTORY_CALIBRATION",
        "frozen_before_new_stable_control_v2_candidate_outcomes": True,
        "immutable_predecessor": {
            "preserved_without_mutation": True,
            "v1_contract": _binding(V1_CONTRACT, digest_field="contract_digest"),
            "v1_H2_result": _binding(V1_H2_RESULT, digest_field="record_digest"),
            "v1_runtime_incident": _binding(
                V1_INCIDENT, digest_field="incident_digest"
            ),
            "v1_terminal_status": incident["status"],
        },
        "remediation": {
            "classification": "OUTCOME_INDEPENDENT_ACCOUNTING_CORRECTION",
            "recorded_optimizer_objective_event": "optimizer-objective-energy",
            "registered_optimizer_objective_event": "optimizer-objective-energy",
            "zero_dimensional_accounting_is_checked": True,
            "nonzero_dimensional_accounting_is_checked": True,
            "attempt_start_is_persisted_before_numerical_execution": True,
            "exception_captures_partial_primitive_counters": True,
            "v1_namespace_reused": False,
        },
        "candidate_binding": {
            "selection_changed": False,
            "ansatz_changed": False,
            "rewrite_changed": False,
            "molecular_source_changed": False,
            "optimizer_changed": False,
            "tolerance_changed": False,
            "control_numerics_changed": False,
            "only_accounting_and_failure_durability_changed": True,
        },
        "source_binding": {
            path.relative_to(ROOT).as_posix(): sha256_file(path)
            for path in SOURCE_PATHS
        },
        "validation_binding": {
            path.relative_to(ROOT).as_posix(): sha256_file(path)
            for path in VALIDATION_PATHS
        },
        "route_contract": route_contract,
        "optimizer_contract": copy.deepcopy(v1["optimizer_contract"]),
        "sequential_gate": copy.deepcopy(v1["sequential_gate"]),
        "parity_requirements": copy.deepcopy(v1["parity_requirements"]),
        "timing_contract_if_and_only_if_all_parity_passes": copy.deepcopy(
            v1["timing_contract_if_and_only_if_all_parity_passes"]
        ),
        "scientific_boundary": scientific_boundary,
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

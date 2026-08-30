"""Publish the five-case P3 source-parity evidence atomically."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from v5_matched_work.atomic_artifacts import write_bytes_exclusive

from .common import (
    ARTIFACT_ROOT,
    ROOT,
    A100PilotError,
    embedded_digest_valid,
    load_json,
    publish,
    sha256_file,
)
from .gpu_smoke import SMOKE
from .p0_baseline import PROTOCOL
from .sparse_hamiltonian_bundle import MANIFEST_V2


P3 = ARTIFACT_ROOT / "p3-scientific-parity"
CASE_ROOT = P3 / "cases"
REPORT = P3 / "source-parity-report-v1.json"
CASE_ORDER = ("h2", "h4", "lih", "h6", "beh2")
FINAL_JOBS = {
    "h2": {"job_id": 1975, "elapsed_seconds": 5},
    "h4": {"job_id": 1976, "elapsed_seconds": 8},
    "lih": {"job_id": 1977, "elapsed_seconds": 57},
    "h6": {"job_id": 1973, "elapsed_seconds": 551},
    "beh2": {"job_id": 1974, "elapsed_seconds": 230},
}


def publish_report(source: Path) -> dict[str, Any]:
    protocol = load_json(PROTOCOL)
    smoke = load_json(SMOKE)
    sparse_bundle = load_json(MANIFEST_V2)
    if not embedded_digest_valid(protocol, "protocol_digest"):
        raise A100PilotError("P0 protocol digest is invalid")
    if not embedded_digest_valid(smoke, "smoke_digest"):
        raise A100PilotError("P2 smoke digest is invalid")
    if not embedded_digest_valid(sparse_bundle, "bundle_digest"):
        raise A100PilotError("P2 sparse transfer digest is invalid")
    if CASE_ROOT.exists() or REPORT.exists():
        raise A100PilotError("P3 report already exists")
    CASE_ROOT.mkdir(parents=True, exist_ok=False)
    cases: list[dict[str, Any]] = []
    totals = {name: 0 for name in protocol["route_counters"]}
    try:
        for alias in CASE_ORDER:
            source_path = source / f"{alias}.json"
            value = load_json(source_path)
            if value.get("alias") != alias or value.get("status") != "PASS":
                raise A100PilotError(f"P3 source result is not PASS: {alias}")
            if not all(value.get("checks", {}).values()):
                raise A100PilotError(f"P3 source checks are not all true: {alias}")
            if any(
                value.get(field) != expected
                for field, expected in (
                    ("candidate_molecular_energy_evaluations", 0),
                    ("optimizer_runs", 0),
                    ("FCI_evaluations", 0),
                )
            ):
                raise A100PilotError(f"forbidden P3 outcome work: {alias}")
            if value["candidate_catalog_policy"]["AIC_dynamic_rebuild_consumed"]:
                raise A100PilotError(f"dynamic AIC catalog was consumed: {alias}")
            destination = CASE_ROOT / f"{alias}.json"
            write_bytes_exclusive(destination, source_path.read_bytes())
            for name, count in value["route_counters"].items():
                totals[name] += int(count)
            cases.append(
                {
                    "alias": alias,
                    "case_id": value["case_id"],
                    "qubit_count": int(value["qubit_count"]),
                    "path": destination.relative_to(ROOT).as_posix(),
                    "sha256": sha256_file(destination),
                    "status": value["status"],
                    "errors": value["errors"],
                    "resources": value["resources"],
                    "candidate_catalog_policy": value["candidate_catalog_policy"],
                    "job": FINAL_JOBS[alias],
                }
            )
    except Exception:
        for path in CASE_ROOT.glob("*"):
            path.unlink()
        CASE_ROOT.rmdir()
        raise
    body = {
        "schema": "aic-a100-pilot.p3-source-parity-report.v1",
        "status": "GO_P4_SOURCE_ROUTE_SPEED_GATE",
        "evidence_binding": {
            "P0_protocol_digest": protocol["protocol_digest"],
            "P2_smoke_digest": smoke["smoke_digest"],
            "P2_sparse_Hamiltonian_bundle_digest": sparse_bundle["bundle_digest"],
            "pilot_implementation_head": "5c085dd1c64c4e61df5a4b19a8e49a01dc57b166",
        },
        "case_order": list(CASE_ORDER),
        "cases": cases,
        "all_source_parity_checks_passed": True,
        "route_counters": totals,
        "engineering_incidents_before_final_results": [
            {"jobs": [1960, 1962], "class": "EXPECTED_HEAD_ARGUMENT_MISMATCH", "outcomes": 0},
            {"job": 1961, "class": "PRODUCTION_RUNTIME_PLATFORM_GUARD", "outcomes": 0},
            {"job": 1963, "class": "DEPENDENCY_RESOLVER_DRIFT", "outcomes": 0},
            {"job": 1964, "class": "PYSCF_CLI_OUTPUT_COLLISION", "outcomes": 0},
            {"jobs": [1965, 1966], "class": "CROSS_PLATFORM_HAMILTONIAN_ASSEMBLY_DRIFT", "outcomes": 0},
            {"job": 1968, "class": "CROSS_PLATFORM_STATE_DIGEST_DRIFT", "outcomes": 0},
            {"job": 1969, "class": "MISSING_IMMUTABLE_BUDGET_METADATA", "outcomes": 0},
            {"job": 1972, "class": "CROSS_PLATFORM_CANDIDATE_ORDER_REBUILD_DRIFT", "outcomes": 0},
        ],
        "scientific_boundary": {
            "authorized_claim": (
                "The exact frozen source identities and physical resources were "
                "preserved, and all five source ansätze passed the registered "
                "CPU/A100 numerical tolerances."
            ),
            "candidate_terminal_decision_parity": "NOT_EXECUTED",
            "optimizer_parity": "NOT_EXECUTED",
            "candidate_molecular_energy_evaluations": 0,
            "optimizer_runs": 0,
            "FCI_evaluations": 0,
            "speedup_claim": "NOT_AUTHORIZED_PENDING_P4",
            "V5_performance_claim": "NOT_AUTHORIZED",
        },
        "successor_authorization": {
            "P4_same_node_source_route_benchmark": "AUTHORIZED",
            "P3_candidate_decision_parity": "DEFERRED_PENDING_P4_SPEED_GATE",
            "P5_limited_scientific_pilot": "NOT_AUTHORIZED",
        },
    }
    return publish(REPORT, body, "report_digest")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--publish", action="store_true")
    arguments = parser.parse_args()
    if not arguments.publish:
        raise RuntimeError("select --publish")
    print(json.dumps(publish_report(arguments.source), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

"""Freeze the corrected v2 development protocol after readiness has passed."""

from __future__ import annotations

import argparse
import hashlib
import json
from typing import Any

from .atomic_artifacts import canonical_json_bytes, write_json_exclusive
from .comparators import PRIMARY_METHODS
from .evidence_v2 import verify_historical_evidence
from .s0_common import ROOT, git, sha256
from .work_ledger import event_from_dict, reconstruct_candidate_energy_evaluations


CASES = ("lih-3.0", "h6-1.5", "h6-3.0", "beh2-3.0", "h4-1.5-known-development")
CAPS = ("LOW", "MEDIUM", "HIGH")
TAG = "v5-matched-work-s5-development-freeze-v2"


def _id(payload: Any) -> str:
    return "s6-queue-v2:" + hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def build() -> dict[str, Any]:
    readiness_path = ROOT / "artifacts/pre-s5/readiness-v2.json"
    readiness = json.loads(readiness_path.read_text())
    if readiness["decision"] != "READY_TO_FREEZE_S5_V2":
        raise RuntimeError("S5-v2 cannot freeze before readiness passes")
    s3 = json.loads((ROOT / "artifacts/s3/work-ledger-protocol-v2.json").read_text())
    zero_path = ROOT / readiness["zero_event_ledger"]
    zero = json.loads(zero_path.read_text())
    zero_count = reconstruct_candidate_energy_evaluations(event_from_dict(value) for value in zero["events"])
    queue = []
    for case in CASES:
        for cap in CAPS:
            for method in PRIMARY_METHODS:
                payload = {"case_id": case, "work_envelope": cap, "method_id": method}
                queue.append({"queue_item_id": _id(payload), **payload})
    result = {
        "schema": "v5-matched-work.s5-development-freeze.v2",
        "stage": "S5", "version": 2, "status": "FROZEN_PRE_OUTCOME",
        "supersedes_for_future_execution": "artifacts/s5/development-freeze-v1.json",
        "planned_annotated_tag": TAG,
        "pre_s5_readiness": {
            "path": str(readiness_path.relative_to(ROOT)),
            "sha256": sha256(readiness_path),
            "readiness_digest": readiness["readiness_digest"],
            "tag": "v5-matched-work-pre-s5-readiness-v2",
            "tag_commit": git(ROOT, "rev-parse", "v5-matched-work-pre-s5-readiness-v2^{}"),
        },
        "source_protocol": "artifacts/s2/stationary-source-protocol-v2.json",
        "source_selection_rule": (
            "Use registered byte-identical development checkpoints. All five scheduled sources, including "
            "H4 1.5, must pass pinned-implementation reconstruction and parameter-gradient infinity <=1e-8."
        ),
        "case_order": list(CASES), "work_envelope_order": list(CAPS),
        "method_order": list(PRIMARY_METHODS), "work_caps": s3["work_caps"],
        "work_cap_derivation": s3["cap_derivation"],
        "queue": queue,
        "queue_generation_rule": "case order × work-envelope order × method order; no outcome-based omission",
        "candidate_order": "frozen parent canonical semantic ID ordering; no exact/FCI/actual-energy field",
        "tie_break": "retain all nondominated points; canonical point ID is display-only",
        "optimizer": {"primary": "pinned parent BFGS", "maximum_iterations": 1000,
                      "gradient_tolerance": 1e-8, "fallback": "registered parent fallback only"},
        "tolerances": {"source_relative_energy_budget_hartree": 1e-4,
                       "parameter_stationarity_infinity": 1e-8,
                       "independent_energy_hartree": 1e-10,
                       "state_fidelity_minimum": 0.9999999999,
                       "constraint_residual_maximum": 1e-10,
                       "dominance_energy_hartree": 1e-12, "resource_tolerance": 0},
        "pareto": {"axes": ["energy_increase_hartree", "cnot_count", "cnot_depth", "total_depth", "parameter_count"],
                   "context_unit": "case_id + work_envelope", "all_accepted_points_primary": True},
        "failure_policy": {"rerun_only_documented_engineering_incident": True,
                           "threshold_optimizer_catalog_budget_change_after_outcome": False,
                           "partial_failed_rollback_no_candidate_preserved": True,
                           "next_queue_item_runs_after_scientific_failure": True},
        "go_gate": {"minimum_independent_contexts_full_v5_adds_point_absent_from_v4_1": 2,
                    "minimum_contexts_full_v5_adds_point_absent_without_rebuilding": 1},
        "no_go": ["V4.1 difference disappears after work matching",
                  "full V5 and without-rebuilding do not differ",
                  "positive is explained by same-structure reoptimization",
                  "unresolved certification failure or artifact corruption"],
        "fci_firewall": True, "paper_measurement_cost": None,
        "candidate_energy_evaluations_at_s5": {
            "value": zero_count,
            "derivation": "reconstructed from raw work events whose operation is candidate-energy-evaluation",
            "ledger_path": str(zero_path.relative_to(ROOT)),
            "ledger_digest": zero["ledger_digest"],
            "scope": "repository work-chain record only; not a claim about computations outside the repository",
        },
        "literature_ledger": [
            {"id": "ceo-adapt-vqe-star", "doi": "10.1038/s41534-025-01039-4", "status": "peer-reviewed", "use_now": True},
            {"id": "pruned-adapt-vqe", "doi": "10.1021/acs.jctc.5c00535", "status": "peer-reviewed", "use_now": False},
            {"id": "param-adapt-vqe", "doi": "10.1021/acs.jctc.6c00269",
             "title": "Constructing Compact ADAPT Unitary Coupled-Cluster Ansatz with Parameter-Based Criterion",
             "journal": "Journal of Chemical Theory and Computation", "status": "peer-reviewed-version-of-record",
             "published_online": "2026-05-13", "volume": 22, "issue": 10, "pages": "5090-5101",
             "primary_url": "https://pubs.acs.org/doi/10.1021/acs.jctc.6c00269",
             "verification_source": "ACS publication record", "verified_on": "2026-08-05", "use_now": False},
            {"id": "circuit-efficient-qeb-vqe", "doi": "10.1021/acs.jctc.5c00119", "status": "peer-reviewed", "use_now": False},
        ],
        "decision": "AUTHORIZED_S6_FROM_TAG_ONLY", "next_stage_authorized": "S6_AFTER_ANNOTATED_TAG",
        "claim_boundary": (
            "Pre-outcome development protocol only. Candidate-energy count is reconstructed only within the "
            "repository event chain. No matched-work performance claim."
        ),
    }
    result["freeze_digest"] = hashlib.sha256(canonical_json_bytes(result)).hexdigest()
    return result


def audit(value: dict[str, Any]) -> dict[str, Any]:
    readiness = json.loads((ROOT / value["pre_s5_readiness"]["path"]).read_text())
    literature = {item["id"]: item for item in value["literature_ledger"]}
    historical = verify_historical_evidence()
    checks = {
        "readiness_precedes_authorization": readiness["decision"] == "READY_TO_FREEZE_S5_V2",
        "queue_size_90": len(value["queue"]) == len(CASES) * len(CAPS) * len(PRIMARY_METHODS),
        "queue_unique": len({item["queue_item_id"] for item in value["queue"]}) == len(value["queue"]),
        "candidate_zero_reconstructed_from_raw_events": value["candidate_energy_evaluations_at_s5"]["value"] == 0,
        "six_comparators": tuple(value["method_order"]) == PRIMARY_METHODS,
        "h4_scheduled": "h4-1.5-known-development" in value["case_order"],
        "caps_fixed": set(value["work_caps"]) == set(CAPS),
        "fci_firewall": value["fci_firewall"] is True,
        "param_adapt_version_of_record_corrected": literature["param-adapt-vqe"]["status"] == "peer-reviewed-version-of-record",
        "historical_evidence_reverified_not_constant": historical["passed"] and all(historical["checks"].values()),
    }
    failures = [name for name, passed in checks.items() if not passed]
    result = {
        "schema": "v5-matched-work.s5-development-freeze-audit.v2",
        "stage": "S5", "passed": not failures, "checks": checks, "failed_checks": failures,
        "historical_evidence_reconstruction": historical,
        "freeze_digest": value["freeze_digest"],
        "claim_boundary": "Audit of a pre-outcome freeze; no candidate performance result.",
    }
    result["audit_digest"] = hashlib.sha256(canonical_json_bytes(result)).hexdigest()
    if failures:
        raise RuntimeError("S5-v2 audit failed: " + ", ".join(failures))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args(); freeze = build(); audit_value = audit(freeze)
    outputs = {
        ROOT / "artifacts/s5/development-freeze-v2.json": freeze,
        ROOT / "artifacts/s5/development-freeze-audit-v2.json": audit_value,
    }
    for path, value in outputs.items():
        if args.verify_only:
            if path.read_bytes() != canonical_json_bytes(value):
                raise RuntimeError(f"S5-v2 drift: {path}")
        else:
            write_json_exclusive(path, value)
    print(json.dumps({"decision": freeze["decision"], "queue": len(freeze["queue"]), "audit": audit_value["passed"]}, sort_keys=True))


if __name__ == "__main__":
    main()

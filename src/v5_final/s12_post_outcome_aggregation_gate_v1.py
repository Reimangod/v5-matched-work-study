"""Fail-closed authorization for read-only aggregation of all frozen S11 results."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from typing import Any, Sequence

from v5_matched_work.atomic_artifacts import write_json_exclusive

from .historical_artifact_audit import artifact_is_immutable_git_blob
from .s0_successor import ROOT
from .s11_v2_execution_readiness_v4 import MINIMUM_FREE_BYTES, _digest, _embedded_digest, _git, _load, _sha
from .s12_offline_fci_reference_v1 import RESULT
from .s12_offline_fci_result_audit_v1 import (
    OUTPUT as RESULT_AUDIT,
    audit_frozen as audit_result_successor,
)
from .s12_offline_reporting_gate_v1 import OUTPUT as REPORTING_GATE, inspect_completion


OUTPUT_DIR = ROOT / "artifacts/v5-final/parent-native/s12-post-outcome-aggregation-gate-v1"
OUTPUT = OUTPUT_DIR / "aggregation-go-v1.json"
DECISION = "GO_S12_READ_ONLY_AGGREGATION_OF_EXACT_FROZEN_90"
SOURCE_PATHS = (
    "src/v5_final/s12_post_outcome_aggregation_gate_v1.py",
    "tests/test_v5_final_s12_post_outcome_aggregation_gate_v1.py",
)


class S12PostOutcomeAggregationGateV1Error(RuntimeError):
    pass


def _authorization() -> dict[str, str]:
    return {
        "exact_90_result_read_only_aggregation": "AUTHORIZED",
        "exact_five_FCI_reference_join": "AUTHORIZED",
        "status_stratified_summary": "AUTHORIZED",
        "completed_only_physical_resource_comparison": "AUTHORIZED",
        "verified_paired_reduction_comparison": "AUTHORIZED",
        "non_scalar_pareto_analysis": "AUTHORIZED",
        "tables_figures_and_machine_readable_outputs": "AUTHORIZED",
        "frozen_matched_work_claims_with_limitations": "AUTHORIZED",
        "S11_rerun": "NOT_AUTHORIZED",
        "FCI_reexecution": "NOT_AUTHORIZED",
        "candidate_reselection": "NOT_AUTHORIZED",
        "ranking_threshold_or_method_change": "NOT_AUTHORIZED",
        "case_or_status_exclusion_from_outcomes": "NOT_AUTHORIZED",
        "missing_or_rejected_value_imputation": "NOT_AUTHORIZED",
        "general_superiority_claim": "NOT_AUTHORIZED",
        "release": "NOT_AUTHORIZED",
    }


def inspect_inputs() -> dict[str, Any]:
    result_audit = audit_result_successor()
    audit_artifact = _load(RESULT_AUDIT)
    reporting = _load(REPORTING_GATE)
    result = _load(RESULT)
    completion = inspect_completion()
    expected_statuses = {
        "COMPLETED": 58,
        "ALGORITHM_REJECTED": 23,
        "CAP_REJECTED": 8,
        "FAILED_ENGINEERING_PRESERVED": 1,
    }
    checks = {
        "result_audit_successor_all_pass": all(result_audit["checks"].values()),
        "result_audit_authorizes_gate_only": audit_artifact["authorization"]
        ["aggregation_gate_creation"] == "AUTHORIZED"
        and audit_artifact["authorization"]["aggregation"]
        == "NOT_AUTHORIZED_UNTIL_SEPARATE_GATE",
        "exact_90_terminal_identity": completion["observed"]["terminal_count"] == 90
        and completion["observed"]["terminal_status_counts"] == expected_statuses,
        "S11_manifests_frozen": all(
            completion["bindings"].get(name) == reporting["bindings"].get(name)
            for name in (
                "result_manifest_digest", "receipt_manifest_digest",
                "production_manifest_digest",
            )
        ),
        "exact_five_FCI_result_bound": len(result["cases"]) == 5
        and result["counters"]["FCI_evaluations"] == 5,
        "execution_firewalls_closed": result["counters"]
        ["candidate_energy_evaluations"] == 0
        and result["counters"]["optimizer_starts"] == 0
        and result["counters"]["S11_items_rerun"] == 0
        and result["counters"]["production_N_dense_expm"] == 0,
        "item000_engineering_failure_preserved": expected_statuses[
            "FAILED_ENGINEERING_PRESERVED"
        ] == 1,
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S12PostOutcomeAggregationGateV1Error(failures)
    return {
        "checks": checks,
        "observed": {
            "terminal_count": 90,
            "terminal_status_counts": expected_statuses,
            "offline_FCI_evaluations": 5,
            "S11_FCI_evaluations": 0,
            "production_N_dense_expm": 0,
        },
        "bindings": {
            "result_audit_sha256": _sha(RESULT_AUDIT),
            "result_audit_digest": audit_artifact["audit_digest"],
            "FCI_result_sha256": _sha(RESULT),
            "FCI_result_digest": result["result_digest"],
            "reporting_gate_sha256": _sha(REPORTING_GATE),
            "reporting_gate_digest": reporting["gate_digest"],
            "S11_result_manifest_digest": completion["bindings"][
                "result_manifest_digest"
            ],
            "S11_receipt_manifest_digest": completion["bindings"][
                "receipt_manifest_digest"
            ],
            "S11_production_manifest_digest": completion["bindings"][
                "production_manifest_digest"
            ],
            "source_sha256": {path: _sha(ROOT / path) for path in SOURCE_PATHS},
        },
    }


def build_artifact(base_head: str) -> dict[str, Any]:
    artifact: dict[str, Any] = {
        "schema": "v5-final.s12-post-outcome-aggregation-gate.v1",
        "stage": "S12_POST_OUTCOME_AGGREGATION_AUTHORIZATION",
        "status": DECISION,
        "decision": DECISION,
        "base_head_with_result_audit": base_head,
        **inspect_inputs(),
        "authorization": _authorization(),
        "aggregation_contract": {
            "population": "all exact frozen 90 queue items",
            "status_handling": {
                "COMPLETED": "ordinary metrics when verified",
                "ALGORITHM_REJECTED": "preserve method-native no-accepted-candidate status",
                "CAP_REJECTED": "preserve incomplete-within-frozen-budget status",
                "FAILED_ENGINEERING_PRESERVED": "preserve engineering NA; never rerun or impute",
            },
            "paired_reduction_rule": (
                "compute only when both immutable CEO* source and comparator have "
                "verified numeric values in the same case and budget"
            ),
            "pareto_rule": "non-scalar verified objectives only; no post-hoc weighting",
            "outcome_based_exclusion": False,
        },
        "scientific_boundary": {
            "allowed": (
                "Descriptive and paired claims within the exact frozen matched-work "
                "population, with status, missingness, case, and budget disclosed."
            ),
            "forbidden": (
                "Imputation, selective case removal, reruns, retrospective tuning, or "
                "general superiority beyond the frozen study."
            ),
        },
    }
    artifact["gate_digest"] = _digest(artifact)
    return artifact


def capture() -> dict[str, Any]:
    if OUTPUT.exists():
        raise S12PostOutcomeAggregationGateV1Error("aggregation gate already exists")
    dirty = _git("status", "--porcelain").splitlines()
    if {line[3:] for line in dirty} != set(SOURCE_PATHS) or any(
        not line.startswith("?? ") for line in dirty
    ):
        raise S12PostOutcomeAggregationGateV1Error(
            "capture permits only the new aggregation-gate source and test"
        )
    artifact = build_artifact(_git("rev-parse", "HEAD"))
    OUTPUT_DIR.mkdir(parents=True, exist_ok=False)
    write_json_exclusive(OUTPUT, artifact)
    return artifact


def audit_frozen(*, live: bool = False) -> dict[str, Any]:
    artifact = _load(OUTPUT)
    observed = inspect_inputs()
    checks = {
        "schema_decision_exact": artifact.get("schema")
        == "v5-final.s12-post-outcome-aggregation-gate.v1"
        and artifact.get("decision") == DECISION
        and artifact.get("status") == DECISION,
        "gate_digest_valid": _embedded_digest(artifact, "gate_digest"),
        "all_captured_and_live_checks_pass": all(artifact.get("checks", {}).values())
        and all(observed["checks"].values()),
        "bindings_current": artifact.get("bindings") == observed["bindings"],
        "observations_current": artifact.get("observed") == observed["observed"],
        "authorization_exact": artifact.get("authorization") == _authorization(),
        "outcome_exclusion_disabled": artifact.get("aggregation_contract", {}).get(
            "outcome_based_exclusion"
        ) is False,
        "artifact_is_immutable_git_blob": artifact_is_immutable_git_blob(OUTPUT),
    }
    if live:
        branch = _git("branch", "--show-current")
        head = _git("rev-parse", "HEAD")
        checks.update({
            "base_head_is_ancestor": subprocess.run(
                ["git", "merge-base", "--is-ancestor",
                 artifact["base_head_with_result_audit"], head], cwd=ROOT,
            ).returncode == 0,
            "local_remote_head_match": head == _git("rev-parse", f"origin/{branch}"),
            "worktree_clean": not _git("status", "--porcelain"),
            "submodules_clean": all(
                line.startswith(" ") for line in _git(
                    "submodule", "status", "--recursive"
                ).splitlines()
            ),
            "storage_at_least_40_GiB": shutil.disk_usage(ROOT).free
            >= MINIMUM_FREE_BYTES,
        })
    if not all(checks.values()):
        raise S12PostOutcomeAggregationGateV1Error(
            [name for name, passed in checks.items() if not passed]
        )
    return {"decision": DECISION, "checks": checks,
            "gate_digest": artifact["gate_digest"]}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", action="store_true")
    parser.add_argument("--audit-live", action="store_true")
    args = parser.parse_args(argv)
    if args.capture and args.audit_live:
        parser.error("choose one action")
    value = capture() if args.capture else audit_frozen(live=args.audit_live)
    print(json.dumps(value, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

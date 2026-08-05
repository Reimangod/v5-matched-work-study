"""Independent S1 correctness-baseline audit."""

from __future__ import annotations

import argparse
import hashlib
import json
from typing import Any

from jsonschema import Draft202012Validator

from .atomic_artifacts import canonical_json_bytes, write_json_exclusive
from .s0_common import PARENT, PARENT_COMMIT, ROOT, git, sha256
from .s1_correctness import accepted_pareto_frontier, risk_semantics, source_relative_budget


def _digest_without(record: dict[str, Any], field: str) -> str:
    payload = dict(record)
    payload.pop(field, None)
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def audit() -> dict[str, Any]:
    baseline_path = ROOT / "artifacts/s1/correctness-baseline-v1.json"
    schema_path = ROOT / "schemas/s1-correctness-baseline-v1.schema.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    schema_errors = list(Draft202012Validator(schema).iter_errors(baseline))
    s9 = json.loads((PARENT / "artifacts/v5/s9/summary-v1.json").read_text(encoding="utf-8"))
    s9_cases = {case["case_id"]: case for case in s9["cases"]}
    cases = baseline["cases"]
    checks = {
        "schema_valid": not schema_errors,
        "baseline_digest": baseline["baseline_digest"] == _digest_without(baseline, "baseline_digest"),
        "pinned_parent": git(PARENT, "rev-parse", "HEAD") == PARENT_COMMIT,
        "parent_tracked_clean": git(PARENT, "status", "--porcelain", "--untracked-files=no") == "",
        "immutable_input_hashes": all(
            sha256(PARENT / item["path"]) == item["sha256"] for item in baseline["immutable_inputs"]
        ),
        "historical_artifacts_unchanged": baseline["historical_artifacts_modified"] is False,
        "historical_raw_winners_replayed": all(
            case["historical_raw_winner"] == s9_cases[case["case_id"]]["v5_raw_winner"]
            for case in cases
        ),
        "frontiers_reconstructed": all(
            case["accepted_pareto_frontier"] == accepted_pareto_frontier(case["accepted_points"])
            for case in cases
        ),
        "frontier_case_coverage": {case["case_id"] for case in cases}
        == {"lih-3.0", "h6-1.5", "h6-3.0", "beh2-3.0"},
        "full_regression_passed": (
            baseline["historical_replay"]["full_regression"]["passed"] is True
            and baseline["historical_replay"]["full_regression"]["test_count"] == 509
        ),
        "release_audit_passed": (
            baseline["historical_replay"]["release_audit"]["passed"] is True
            and all(baseline["historical_replay"]["release_audit"]["checks"].values())
        ),
        "source_relative_budget": source_relative_budget(
            source_energy_hartree=-2.0,
            committed_energy_hartree=-1.99997,
            total_budget_hartree=0.0001,
        ) == 0.0000700000000001922,
        "zero_margin_not_risk_aware": risk_semantics(0.0) == "risk-neutral-zero-uncertainty-margin",
        "fci_firewall_declared": "exact/FCI reference forbidden online"
        in baseline["corrected_runtime_contract"]["energy_budget"],
        "endpoint_rank_inference_forbidden": baseline["corrected_runtime_contract"][
            "endpoint_inference_from_rank_forbidden"
        ]
        is True,
        "candidate_order_unchanged": baseline["corrected_runtime_contract"]["candidate_order_changed"] is False,
        "rollback_parent_immutable": (
            baseline["corrected_runtime_contract"]["failed_candidate_parent_commit_allowed"] is False
            and baseline["corrected_runtime_contract"]["rollback_and_parent_immutability_required"] is True
        ),
        "correctness_only_change": baseline["change_classification"][
            "outcome_independent_correctness_only"
        ]
        is True,
        "measurement_cost_null": baseline["paper_measurement_cost"] is None,
        "s2_authorized": baseline["decision"] == "GO_S2" and baseline["next_stage_authorized"] == "S2",
    }
    failures = [name for name, passed in checks.items() if not passed]
    result: dict[str, Any] = {
        "schema": "v5-matched-work.s1-correctness-audit.v1",
        "stage": "S1",
        "passed": not failures,
        "checks": checks,
        "failed_checks": failures,
        "schema_errors": [error.message for error in schema_errors],
        "baseline_sha256": sha256(baseline_path),
        "claim_boundary": "Correctness and historical replay audit only; no new molecular outcome.",
    }
    result["audit_digest"] = _digest_without(result, "audit_digest")
    if failures:
        raise RuntimeError("S1 audit failed: " + ", ".join(failures))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-only", action="store_true")
    arguments = parser.parse_args()
    output = ROOT / "artifacts/s1/correctness-audit-v1.json"
    result = audit()
    if arguments.verify_only:
        if output.read_bytes() != canonical_json_bytes(result):
            raise RuntimeError("committed S1 audit does not match reconstruction")
    else:
        write_json_exclusive(output, result)
    print(json.dumps({"passed": result["passed"], "checks": len(result["checks"])}, sort_keys=True))


if __name__ == "__main__":
    main()

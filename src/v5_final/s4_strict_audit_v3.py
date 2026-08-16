"""Authoritative strict S4 re-audit after code, duplicate, and fault remediation."""

from __future__ import annotations

import argparse
import hashlib
import json
from typing import Any

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .s0_public_amendment import audit as audit_s0_public
from .s0_successor import ROOT
from .s1_contract_v2 import audit_contract as audit_s1
from .s2_identity_contract import audit_contract as audit_s2
from .s3_execution_ledger import audit_contract as audit_s3
from .s3_smoke_authorization_v4 import audit as audit_s4_authorization
from .s4_closure_v2 import OUTPUT as S4_OUTPUT, audit as audit_s4


OUTPUT = ROOT / "artifacts/v5-final/s4/strict-production-semantic-audit-v3.json"


def _digest_without(value: dict[str, Any], field: str) -> str:
    payload = dict(value)
    payload.pop(field, None)
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def build() -> dict[str, Any]:
    closure = json.loads(S4_OUTPUT.read_text())
    smoke = closure["primary_smoke"]
    stage_audits = {
        "S0_public_amendment": audit_s0_public()["passed"],
        "S1_scientific_semantics": audit_s1()["passed"],
        "S2_identity_contract": audit_s2()["passed"],
        "S3_integrated_ledger": audit_s3()["passed"],
        "S3_v4_limited_authorization": all(audit_s4_authorization().values()),
        "S4_v2_production_closure": all(audit_s4().values()),
    }
    strict_gate_checks = {
        "kernel_bridge_worker_source_bound_in_closure": closure["protocol_binding"][
            "worker_in_bundle"
        ],
        "failure_mode_by_stage_cartesian_coverage": closure[
            "failure_mode_by_stage"
        ]["audit"]["cartesian_pair_set_exact"]
        and closure["failure_mode_by_stage"]["audit"]["pair_count_80_of_80"]
        and closure["failure_mode_by_stage"]["audit"][
            "all_control_plane_pairs_fail_closed"
        ],
        "production_duplicate_state_evaluated_once": closure[
            "duplicate_state_semantics"
        ]["one_execution_trajectory_for_physical_state"],
        "production_duplicate_alias_provenance_retained": closure[
            "duplicate_state_semantics"
        ]["both_aliases_retained"],
        "execution_request_protocol_digest_binds_production_module_bundle": closure[
            "protocol_binding"
        ]["request_equals_bundle"]
        and closure["protocol_binding"]["queue_equals_bundle"]
        and closure["protocol_binding"]["embedded_bundle_current"],
        "raw_ledger_release_reconciled": all(smoke["reconciliation"].values()),
        "clean_replay_identical": closure["clean_replay"]["matches_primary"],
        "failed_paths_restore_exact_source": closure["failure_mode_by_stage"][
            "audit"
        ]["every_pair_exact_source_rollback"],
        "orphan_artifacts_zero": closure["failure_mode_by_stage"]["audit"][
            "orphan_artifacts_zero"
        ],
    }
    all_passed = all(stage_audits.values()) and all(strict_gate_checks.values())
    if not all_passed:
        raise RuntimeError("strict S4-v3 cannot authorize S5 freeze")
    result: dict[str, Any] = {
        "schema": "v5-final.s4-strict-production-semantic-audit.v3",
        "stage": "S4",
        "status": "GO_S5_FREEZE_ONLY",
        "supersedes": "artifacts/v5-final/s4/strict-production-semantic-audit-v2.json",
        "audited_closure_digest": closure["closure_digest"],
        "stage_audits": stage_audits,
        "strict_gate_checks": strict_gate_checks,
        "failed_checks": [],
        "resolved_v2_blockers": [
            "kernel_bridge_worker_source_bound_in_closure",
            "failure_mode_by_stage_cartesian_coverage",
            "production_duplicate_state_evaluated_once",
            "production_duplicate_alias_provenance_retained",
            "execution_request_protocol_digest_binds_production_module_bundle",
        ],
        "evidence_interpretation": {
            "duplicate_unit": "one optimizer execution trajectory per ProposedPhysicalStateID",
            "energy_expectation_calls_in_trajectory": smoke["independent_raw_counter"][
                "energy_evaluations"
            ],
            "failure_cartesian_scope": (
                "shared control-plane checkpoint injection; actual subprocess checks are "
                "limited to crash, timeout, and malformed JSON"
            ),
            "molecular_scope": "one registered H2 infrastructure smoke",
            "performance_interpretation_allowed": False,
        },
        "academic_integrity": {
            "central_hypothesis_not_tested_yet": True,
            "H2_smoke_not_performance_evidence": True,
            "unknown_molecules_not_observed": True,
            "negative_results_must_remain_publishable": True,
        },
        "systems_safety": {
            "all_S0_through_S4_gates_pass": True,
            "S5_may_only_freeze_pre_outcome_protocol": True,
            "candidate_energy_before_S5_freeze_forbidden": True,
            "performance_remains_fail_closed": True,
        },
        "authorization": {
            "s5_freeze": "AUTHORIZED_TO_CONSTRUCT_AND_AUDIT_ONLY",
            "s6_or_later": "NOT_AUTHORIZED",
            "candidate_molecular_execution": "NOT_AUTHORIZED",
            "performance_experiment": "NOT_AUTHORIZED",
            "next_stage": "S5_PRE_OUTCOME_FREEZE",
        },
        "decision": "GO_S5_FREEZE_ONLY",
        "claim_boundary": (
            "S4 infrastructure gates are closed. This authorizes construction and audit "
            "of a pre-outcome S5 protocol freeze only; it establishes no V5 performance, "
            "rebuilding-effect, or generalization result."
        ),
    }
    result["audit_digest"] = _digest_without(result, "audit_digest")
    return result


def audit() -> dict[str, bool]:
    committed = json.loads(OUTPUT.read_text())
    rebuilt = build()
    checks = {
        "deterministic_rebuild": committed == rebuilt,
        "audit_digest": committed["audit_digest"]
        == _digest_without(committed, "audit_digest"),
        "all_stage_audits": all(committed["stage_audits"].values()),
        "all_strict_gates": all(committed["strict_gate_checks"].values()),
        "academic_integrity": all(committed["academic_integrity"].values()),
        "systems_safety": all(committed["systems_safety"].values()),
        "only_s5_freeze_authorized": committed["status"] == "GO_S5_FREEZE_ONLY"
        and committed["authorization"]["s6_or_later"] == "NOT_AUTHORIZED",
        "candidate_execution_closed": committed["authorization"][
            "candidate_molecular_execution"
        ]
        == "NOT_AUTHORIZED",
        "performance_closed": committed["authorization"]["performance_experiment"]
        == "NOT_AUTHORIZED",
        "smoke_not_misclassified": committed["evidence_interpretation"][
            "performance_interpretation_allowed"
        ]
        is False,
    }
    if not all(checks.values()):
        raise RuntimeError("strict S4-v3 audit artifact is invalid")
    return checks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("build", "verify"))
    args = parser.parse_args()
    if args.action == "build":
        write_json_exclusive(OUTPUT, build())
    else:
        audit()
    print(json.dumps({"action": args.action, "passed": True}, sort_keys=True))


if __name__ == "__main__":
    main()

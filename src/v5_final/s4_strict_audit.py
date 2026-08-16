"""Strict S4 audit that refuses to infer unobserved production guarantees."""

from __future__ import annotations

import argparse
import hashlib
import json
from typing import Any

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .release_audit import require_smoke
from .s0_successor import ROOT
from .s4_closure import OUTPUT as S4_OUTPUT, audit as audit_s4_claimed_closure


OUTPUT = ROOT / "artifacts/v5-final/s4/strict-production-semantic-audit-v2.json"


def _digest_without(value: dict[str, Any], field: str) -> str:
    payload = dict(value)
    payload.pop(field, None)
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def build() -> dict[str, Any]:
    closure = json.loads(S4_OUTPUT.read_text())
    smoke = closure["primary_smoke"]
    claimed_checks = audit_s4_claimed_closure()
    smoke_checks = require_smoke(smoke)
    module_paths = {item["path"] for item in closure["production_modules"]}
    observed = {
        "actual_pinned_CEO_H2_kernel": smoke["upstream"]["commit"]
        == "a3f89d03e6a03c89767d3cf8ee7657a57653dda0",
        "actual_energy_gradient_resource_execution": (
            smoke["independent_raw_counter"]["energy_evaluations"] > 0
            and smoke["independent_raw_counter"]["gradient_vector_evaluations"] > 0
            and smoke["independent_raw_counter"]["resource_recounts"] > 0
        ),
        "raw_ledger_release_reconciliation": all(smoke["reconciliation"].values()),
        "clean_replay_same_digest": closure["clean_replay"]["matches_primary"],
        "orphan_artifact_count_zero": closure["orphan_artifact_count"] == 0,
        "source_digest_rollback_contract": closure["failure_injection"][
            "all_failed_attempts_restore_source_digest"
        ],
        "performance_claim_absent": closure["authorization"]["performance_experiment"]
        == "NOT_AUTHORIZED",
        "claimed_closure_self_audit": all(claimed_checks.values())
        and all(smoke_checks.values()),
    }
    blockers = {
        "kernel_bridge_worker_source_bound_in_closure": (
            "src/v5_final/kernel_bridge_worker.py" in module_paths
        ),
        "failure_mode_by_stage_cartesian_coverage": False,
        "production_duplicate_state_evaluated_once": False,
        "production_duplicate_alias_provenance_retained": False,
        "execution_request_protocol_digest_binds_production_module_bundle": False,
    }
    result: dict[str, Any] = {
        "schema": "v5-final.s4-strict-production-semantic-audit.v2",
        "stage": "S4",
        "status": "NO_GO",
        "audited_closure_digest": closure["closure_digest"],
        "observed_passes": observed,
        "strict_gate_checks": blockers,
        "failed_checks": [name for name, passed in blockers.items() if not passed],
        "missing_evidence": {
            "failure_matrix": (
                "Current artifact proves one probe per failure class, not injection of "
                "every failure class at every production stage."
            ),
            "duplicate_path": (
                "S2 proves identity-index behavior synthetically, but the production "
                "executor smoke contains one intent and one physical state only."
            ),
            "code_binding": (
                "The closure module inventory omits kernel_bridge_worker.py and the "
                "ExecutionRequestID protocol digest binds authorization, not the full "
                "production module bundle."
            ),
        },
        "worker_diagnostic_binding": {
            "path": "src/v5_final/kernel_bridge_worker.py",
            "sha256": hashlib.sha256(
                (ROOT / "src/v5_final/kernel_bridge_worker.py").read_bytes()
            ).hexdigest(),
            "classification": "diagnostic only; absent from audited v1 closure inventory",
        },
        "authorization": {
            "s5_freeze": "NOT_AUTHORIZED",
            "performance_experiment": "NOT_AUTHORIZED",
            "next_stage": "S4_REMEDIATION",
        },
        "candidate_molecular_evidence": {
            "classification": "bounded H2 infrastructure smoke only",
            "performance_interpretation_allowed": False,
        },
        "decision": "NO_GO_S5_STRICT_S4_EVIDENCE_GAPS",
        "claim_boundary": (
            "The H2 smoke validates a substantial production path but does not yet "
            "close all S4 safety gates and provides no performance evidence."
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
        "observed_evidence_valid": all(committed["observed_passes"].values()),
        "strict_gaps_fail_closed": committed["status"] == "NO_GO"
        and bool(committed["failed_checks"]),
        "s5_closed": committed["authorization"]["s5_freeze"] == "NOT_AUTHORIZED",
        "performance_closed": committed["authorization"]["performance_experiment"]
        == "NOT_AUTHORIZED",
        "smoke_not_misclassified": committed["candidate_molecular_evidence"][
            "performance_interpretation_allowed"
        ]
        is False,
    }
    if not all(checks.values()):
        raise RuntimeError("strict S4 audit artifact is invalid")
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

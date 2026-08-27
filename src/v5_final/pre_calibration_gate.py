"""Authoritative fail-closed gate before any H2/H4 calibration outcome."""

from __future__ import annotations

import argparse
import hashlib
import json
from typing import Any

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .s0_successor import ROOT
from .s5_freeze import LEDGER_ROOT_OUTPUT, QUEUE_OUTPUT, audit_committed as audit_s5
from .s6_method_parity import audit as audit_s6
from .s7_s9_contract import audit as audit_s7_s9


OUTPUT = ROOT / "artifacts/v5-final/pre-calibration/authoritative-readiness-v1.json"


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def build() -> dict[str, Any]:
    queue = json.loads(QUEUE_OUTPUT.read_text())
    ledger_root = json.loads(LEDGER_ROOT_OUTPUT.read_text())
    established = {
        "S5_exact_queue_freeze": all(audit_s5().values()),
        "S6_method_planning_parity": all(audit_s6().values()),
        "S7_S9_outcome_blind_contracts": all(audit_s7_s9().values()),
        "development_queue_90_items": queue["expected_queue_count"] == 90,
        "development_candidate_energy_events_zero": ledger_root[
            "development_candidate_energy_evaluations"
        ]
        == 0
        and not ledger_root["segments"],
    }
    production_requirements = {
        "six_method_native_molecular_backend_entrypoints": False,
        "all_methods_emit_shared_live_semantic_events": False,
        "all_methods_raw_ledger_release_reconcile": False,
        "v4_1_joint_compression_parent_semantics_bound": False,
        "v5_sequential_parent_semantics_bound": False,
        "full_v5_post_commit_catalog_rebuild_observed": False,
        "no_rebuild_original_catalog_reuse_observed": False,
        "H2_H4_calibration_queue_frozen": False,
        "H2_H4_FCI_counterfactual_runtime_invariance": False,
    }
    failed = [name for name, passed in production_requirements.items() if not passed]
    result: dict[str, Any] = {
        "schema": "v5-final.pre-calibration-authoritative-readiness.v1",
        "stage": "PRE_CALIBRATION",
        "status": "NO_GO",
        "established_infrastructure": established,
        "production_requirements": production_requirements,
        "failed_requirements": failed,
        "why_no_proxy_execution": (
            "The six S6 controllers prove planning symmetry but do not yet execute the "
            "registered parent-native V4.1 and V5 algorithms. Replacing them with simplified "
            "drop-one proxies would change the scientific methods under comparison."
        ),
        "required_next_work": [
            "wrap each registered parent-native method in the shared production backend protocol",
            "emit semantic events at the actual counted kernel operations",
            "prove raw=ledger=release for every method on bounded H2/H4",
            "freeze an H2/H4 calibration queue before reading calibration outcomes",
            "run calibration once and freeze selected settings before development execution",
        ],
        "authorization": {
            "backend_integration_implementation": "AUTHORIZED",
            "H2_H4_candidate_execution": "NOT_AUTHORIZED",
            "development_queue_execution": "NOT_AUTHORIZED",
            "prospective_execution": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "academic_integrity": {
            "planning_controller_not_misclassified_as_method_backend": True,
            "synthetic_contract_not_misclassified_as_calibration": True,
            "historical_outcomes_not_used_to_fill_new_queue": True,
            "proxy_method_substitution_rejected": True,
            "negative_infrastructure_result_reported": True,
        },
        "systems_safety": {
            "candidate_execution_fail_closed": True,
            "frozen_development_queue_untouched": not ledger_root["segments"],
            "empty_ledger_not_complete": ledger_root["completeness"]["complete"]
            is False,
            "next_authority_narrowly_scoped": True,
        },
        "decision": "NO_GO_METHOD_NATIVE_PRODUCTION_BACKENDS",
        "claim_boundary": (
            "Infrastructure through S9 contracts is reproducible, but no calibration, "
            "matched-work comparison, V5 benefit, or molecular generalization result exists."
        ),
    }
    result["readiness_digest"] = _digest(result)
    return result


def audit() -> dict[str, bool]:
    committed = json.loads(OUTPUT.read_text())
    rebuilt = build()
    payload = dict(committed)
    observed = payload.pop("readiness_digest")
    checks = {
        "deterministic_rebuild": committed == rebuilt,
        "readiness_digest": observed == _digest(payload),
        "established_valid": all(committed["established_infrastructure"].values()),
        "missing_requirements_fail_closed": committed["status"] == "NO_GO"
        and set(committed["failed_requirements"])
        == {
            name
            for name, passed in committed["production_requirements"].items()
            if not passed
        },
        "academic_integrity": all(committed["academic_integrity"].values()),
        "systems_safety": all(committed["systems_safety"].values()),
        "all_experiments_closed": all(
            value == "NOT_AUTHORIZED"
            for name, value in committed["authorization"].items()
            if name != "backend_integration_implementation"
        ),
    }
    if not all(checks.values()):
        raise RuntimeError("pre-calibration readiness audit failed")
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

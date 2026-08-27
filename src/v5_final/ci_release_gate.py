"""Read-only CI release gate for the pre-calibration method-native branch."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .mb3_1_hardening_audit import audit as audit_mb3_1
from .mb3_1_hardening_v2_audit import audit as audit_mb3_1_v2
from .mb4_1_protocol_drafts import audit as audit_mb4_1
from .mb4_1_protocol_drafts_v2 import audit as audit_mb4_1_v2
from .mb4_2_owner_protocol_freeze import audit as audit_mb4_2
from .mb4_fail_closed import audit as audit_mb4
from .mb5_outcome_free_executor_audit import audit as audit_mb5
from .mb5_1_production_backend_audit import audit as audit_mb5_1
from .mb6_queue_freeze import FREEZE_OUTPUT as MB6_OUTPUT, audit as audit_mb6
from .mb7_pre_calibration_audit import OUTPUT as MB7_OUTPUT, audit as audit_mb7
from .infrastructure_no_go_release import OUTPUT as NO_GO_RELEASE_OUTPUT, audit as audit_no_go_release
from .p0_preexecution_audit import audit as audit_p0
from .pre_calibration_gate import audit as audit_pre_calibration
from .s0_documentation_amendment import audit as audit_documentation
from .s0_successor import ROOT, audit_manifest
from .s5_freeze import audit_committed as audit_s5


class CIReleaseGateError(RuntimeError):
    pass


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _artifact_inventory() -> list[dict[str, str]]:
    return [
        {
            "path": str(path.relative_to(ROOT)),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for path in sorted((ROOT / "artifacts/v5-final").rglob("*.json"))
    ]


def build() -> dict[str, Any]:
    queue_path = ROOT / "artifacts/v5-final/s5/development-queue-v3.json"
    ledger_path = ROOT / "artifacts/v5-final/s5/development-ledger-root-v3.json"
    draft_path = ROOT / "artifacts/v5-final/method-native/mb4-1-protocol-drafts-v2.json"
    freeze_path = ROOT / "artifacts/v5-final/method-native/mb4-2-owner-protocol-freeze-v1.json"
    mb5_path = ROOT / "artifacts/v5-final/method-native/mb5-outcome-free-executors-v1.json"
    mb5_1_path = ROOT / "artifacts/v5-final/method-native/mb5-1-production-backends-v3.json"
    p0_path = ROOT / "artifacts/v5-final/pre-execution/p0-capacity-no-go-v1.json"
    queue = json.loads(queue_path.read_text())
    ledger = json.loads(ledger_path.read_text())
    draft = json.loads(draft_path.read_text())
    freeze = json.loads(freeze_path.read_text())
    mb5 = json.loads(mb5_path.read_text())
    mb5_1 = json.loads(mb5_1_path.read_text())
    p0 = json.loads(p0_path.read_text())
    mb6 = json.loads(MB6_OUTPUT.read_text())
    mb7 = json.loads(MB7_OUTPUT.read_text())
    no_go_release = json.loads(NO_GO_RELEASE_OUTPUT.read_text())
    queue_artifacts = sorted(
        str(path.relative_to(ROOT))
        for path in (ROOT / "artifacts/v5-final").rglob("*queue*.json")
    )
    audits = {
        "s0": audit_manifest(require_clean=False)["checks"],
        "s0_documentation_amendment": audit_documentation(),
        "s5": audit_s5(),
        "pre_calibration": audit_pre_calibration(),
        "mb3_1": audit_mb3_1(),
        "mb3_1_v2": audit_mb3_1_v2(),
        "mb4": audit_mb4(),
        "mb4_1": audit_mb4_1(),
        "mb4_1_v2": audit_mb4_1_v2(),
        "mb4_2_owner_freeze": audit_mb4_2(),
        "mb5_outcome_free_executors": audit_mb5(),
        "p0_preexecution_capacity": audit_p0(),
        "mb5_1_production_backends": audit_mb5_1(),
        "mb6_outcome_blind_queue_freeze": audit_mb6(),
        "mb7_pre_calibration_no_go": audit_mb7(),
        "terminal_infrastructure_no_go_release": audit_no_go_release(),
    }
    checks = {
        "all_audits_pass": all(all(values.values()) for values in audits.values()),
        "development_queue_exactly_90": queue["expected_queue_count"] == 90
        and len(queue["items"]) == 90,
        "development_queue_90_not_started": sum(
            item["terminal_status"] == "NOT_STARTED" for item in queue["items"]
        )
        == 90,
        "completed_items_zero": ledger["completed_queue_item_ids"] == [],
        "segments_zero": ledger["segments"] == [],
        "development_candidate_energy_zero": ledger[
            "development_candidate_energy_evaluations"
        ]
        == 0,
        "only_registered_separate_queues_exist": queue_artifacts
        == [
            "artifacts/v5-final/mb6-v2/h2-h4-calibration-queue-v2.json",
            "artifacts/v5-final/mb6/h2-h4-calibration-queue-v1.json",
            "artifacts/v5-final/s5/development-queue-v3.json",
        ],
        "historical_h2_h4_absence_claims_preserved": freeze["H2_H4_queue_created"] is False
        and mb5["H2_H4_queue_created"] is False,
        "mb6_h2_h4_queue_frozen_not_executed": mb6["decision"]
        == "GO_MB7_PRE_CALIBRATION_AUDIT_ONLY"
        and mb6["authorization"]["H2_H4_execution"] == "NOT_AUTHORIZED",
        "mb7_no_go_is_fail_closed": mb7["decision"]
        == "NO_GO_MB7_UNRESOLVED_PRODUCTION_BINDING_AND_CAPACITY"
        and mb7["authorization"]["H2_H4_execution"] == "NOT_AUTHORIZED",
        "terminal_release_is_zero_outcome_no_go": no_go_release["decision"]
        == "NO_GO_V5_MATCHED_WORK_UNRESOLVED_INFRASTRUCTURE_V1"
        and no_go_release["candidate_molecular_energy_evaluations"] == 0,
        "molecular_candidate_energy_not_executed": freeze[
            "molecular_candidate_energy_executed"
        ]
        is False
        and mb5["molecular_candidate_energy_executed"] is False,
        "historical_mb4_1_remains_unchanged": draft["status"]
        == "NO_GO_AWAITING_INDEPENDENT_HUMAN_PROTOCOL_APPROVAL"
        and draft["approval_record"]
        == {
            "reviewer": None,
            "review_date": None,
            "decision": None,
            "approval_artifact": None,
            "approved_protocol_digests": [],
        },
        "owner_freeze_removes_human_gate": freeze["governance"]
        ["independent_human_approval_required"]
        is False
        and freeze["decision"] == "GO_MB5_OUTCOME_FREE_EXECUTOR_IMPLEMENTATION_ONLY",
        "six_outcome_free_executors_complete": mb5[
            "six_outcome_free_method_native_executors_implemented"
        ]
        is True
        and mb5["decision"] == "GO_MB6_QUEUE_FREEZE_ONLY",
        "production_molecular_execution_absent": mb5[
            "production_molecular_executor_execution"
        ]
        is False
        and all(
            result["molecular_kernel_calls"] == 0
            for result in mb5_1["dry_run_results"].values()
        ),
        "six_production_backends_bound_outcome_free": mb5_1["status"]
        == "PASS_OUTCOME_FREE_PRODUCTION_BACKEND_BINDING"
        and mb5_1["decision"] == "GO_MB6_OUTCOME_BLIND_QUEUE_FREEZE_ONLY",
        "p0_capacity_no_go_preserved": p0["status"]
        == "NO_GO_INSUFFICIENT_SAFE_DISK_CAPACITY"
        and p0["storage_policy"]["capacity_passed"] is False,
        "performance_not_authorized": mb5["authorization"]["performance_claim"]
        == "NOT_AUTHORIZED",
    }
    result = {
        "schema": "v5-final.ci-release-gate.v1",
        "status": (
            "PASS_TERMINAL_INFRASTRUCTURE_NO_GO"
            if all(checks.values())
            else "FAIL_CLOSED"
        ),
        "checks": checks,
        "audits": audits,
        "queue_artifacts": queue_artifacts,
        "artifact_inventory": _artifact_inventory(),
        "authorization": {
            "MB6_queue_freeze": "COMPLETE_FROZEN_NOT_EXECUTED",
            "MB7_pre_calibration_audit": "COMPLETE_NO_GO",
            "molecular_candidate_energy": "NOT_AUTHORIZED",
            "H2_H4_execution": "NOT_AUTHORIZED",
            "development_queue_execution": "NOT_AUTHORIZED",
            "six_production_molecular_executors": "IMPLEMENTED_BINDING_ONLY_NOT_EXECUTION_AUTHORIZED",
            "P0_capacity": "NO_GO_BLOCKS_ALL_MOLECULAR_EXECUTION",
            "performance_claim": "NOT_AUTHORIZED",
            "outcome_free_infrastructure_repair": "AUTHORIZED_WITH_VERSIONED_SUCCESSOR",
            "MB8_or_later": "NOT_AUTHORIZED",
            "terminal_release": "NO_GO_V5_MATCHED_WORK_UNRESOLVED_INFRASTRUCTURE_V1",
        },
        "decision": "NO_GO_V5_MATCHED_WORK_UNRESOLVED_INFRASTRUCTURE_V1",
    }
    result["report_digest"] = _digest(result)
    return result


def audit() -> dict[str, Any]:
    result = build()
    failures = [name for name, passed in result["checks"].items() if not passed]
    if failures:
        raise CIReleaseGateError("CI release gate failed: " + ", ".join(failures))
    expected_authorization = {
        "MB6_queue_freeze": "COMPLETE_FROZEN_NOT_EXECUTED",
        "MB7_pre_calibration_audit": "COMPLETE_NO_GO",
        "molecular_candidate_energy": "NOT_AUTHORIZED",
        "H2_H4_execution": "NOT_AUTHORIZED",
        "development_queue_execution": "NOT_AUTHORIZED",
        "six_production_molecular_executors": "IMPLEMENTED_BINDING_ONLY_NOT_EXECUTION_AUTHORIZED",
        "P0_capacity": "NO_GO_BLOCKS_ALL_MOLECULAR_EXECUTION",
        "performance_claim": "NOT_AUTHORIZED",
        "outcome_free_infrastructure_repair": "AUTHORIZED_WITH_VERSIONED_SUCCESSOR",
        "MB8_or_later": "NOT_AUTHORIZED",
        "terminal_release": "NO_GO_V5_MATCHED_WORK_UNRESOLVED_INFRASTRUCTURE_V1",
    }
    if result["authorization"] != expected_authorization:
        raise CIReleaseGateError("CI release gate authorization boundary drifted")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit()
    if args.output is not None:
        write_json_exclusive(args.output, result)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()

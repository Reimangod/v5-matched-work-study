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
    queue = json.loads(queue_path.read_text())
    ledger = json.loads(ledger_path.read_text())
    draft = json.loads(draft_path.read_text())
    freeze = json.loads(freeze_path.read_text())
    mb5 = json.loads(mb5_path.read_text())
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
        "only_development_queue_exists": queue_artifacts
        == ["artifacts/v5-final/s5/development-queue-v3.json"],
        "h2_h4_queue_not_created": freeze["H2_H4_queue_created"] is False
        and mb5["H2_H4_queue_created"] is False,
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
        is False,
        "performance_not_authorized": mb5["authorization"]["performance_claim"]
        == "NOT_AUTHORIZED",
    }
    result = {
        "schema": "v5-final.ci-release-gate.v1",
        "status": (
            "PASS_GO_MB6_QUEUE_FREEZE_ONLY" if all(checks.values()) else "FAIL_CLOSED"
        ),
        "checks": checks,
        "audits": audits,
        "queue_artifacts": queue_artifacts,
        "artifact_inventory": _artifact_inventory(),
        "authorization": {
            "MB6_queue_freeze": "AUTHORIZED_TO_CREATE_AND_AUDIT_FREEZE_ONLY",
            "molecular_candidate_energy": "NOT_AUTHORIZED",
            "H2_H4_execution": "NOT_AUTHORIZED",
            "development_queue_execution": "NOT_AUTHORIZED",
            "six_production_molecular_executors": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
            "MB7_or_later": "NOT_AUTHORIZED",
        },
        "decision": "GO_MB6_QUEUE_FREEZE_ONLY",
    }
    result["report_digest"] = _digest(result)
    return result


def audit() -> dict[str, Any]:
    result = build()
    failures = [name for name, passed in result["checks"].items() if not passed]
    if failures:
        raise CIReleaseGateError("CI release gate failed: " + ", ".join(failures))
    expected_authorization = {
        "MB6_queue_freeze": "AUTHORIZED_TO_CREATE_AND_AUDIT_FREEZE_ONLY",
        "molecular_candidate_energy": "NOT_AUTHORIZED",
        "H2_H4_execution": "NOT_AUTHORIZED",
        "development_queue_execution": "NOT_AUTHORIZED",
        "six_production_molecular_executors": "NOT_AUTHORIZED",
        "performance_claim": "NOT_AUTHORIZED",
        "MB7_or_later": "NOT_AUTHORIZED",
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

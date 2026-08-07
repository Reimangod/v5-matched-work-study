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
from .mb4_fail_closed import audit as audit_mb4
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
    draft_path = ROOT / "artifacts/v5-final/method-native/mb4-1-protocol-drafts-v1.json"
    queue = json.loads(queue_path.read_text())
    ledger = json.loads(ledger_path.read_text())
    draft = json.loads(draft_path.read_text())
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
        "h2_h4_queue_not_created": draft["H2_H4_calibration_queue_created"] is False,
        "molecular_candidate_energy_not_executed": draft[
            "molecular_candidate_energy_executed"
        ]
        is False,
        "mb4_1_unapproved": draft["status"]
        == "NO_GO_AWAITING_INDEPENDENT_HUMAN_PROTOCOL_APPROVAL"
        and draft["approval_record"]
        == {"reviewer": None, "approved_protocol_digests": [], "approval_artifact": None},
        "performance_not_authorized": draft["authorization"]["performance_claim"]
        == "NOT_AUTHORIZED",
    }
    result = {
        "schema": "v5-final.ci-release-gate.v1",
        "status": "PASS_NO_GO" if all(checks.values()) else "FAIL_CLOSED",
        "checks": checks,
        "audits": audits,
        "queue_artifacts": queue_artifacts,
        "artifact_inventory": _artifact_inventory(),
        "authorization": {
            "H2_H4_candidate_energy": "NOT_AUTHORIZED",
            "development_queue_execution": "NOT_AUTHORIZED",
            "six_production_molecular_executors": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "decision": "NO_GO_MB4_1_PROTOCOLS_PROPOSED_NOT_APPROVED",
    }
    result["report_digest"] = _digest(result)
    return result


def audit() -> dict[str, Any]:
    result = build()
    failures = [name for name, passed in result["checks"].items() if not passed]
    if failures:
        raise CIReleaseGateError("CI release gate failed: " + ", ".join(failures))
    if not all(value == "NOT_AUTHORIZED" for value in result["authorization"].values()):
        raise CIReleaseGateError("CI release gate found an open execution authorization")
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

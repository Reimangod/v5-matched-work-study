"""Latest additive CI gate for the v2 terminal release successor branch."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .infrastructure_no_go_release_v2 import audit as audit_release_v2
from .mb5_2_actual_binding_audit import audit as audit_mb5_2
from .mb6_queue_freeze_v2 import audit as audit_mb6_v2
from .mb7_pre_calibration_audit_v2 import audit as audit_mb7_v2
from .p0_capacity_success_v3 import REQUIRED_FREE_BYTES, ROOT, audit as audit_p0_v3


CALIBRATION_QUEUE = ROOT / "artifacts/v5-final/mb6-v2/h2-h4-calibration-queue-v2.json"
CALIBRATION_LEDGER = ROOT / "artifacts/v5-final/mb6-v2/h2-h4-calibration-ledger-root-v2.json"
DEVELOPMENT_QUEUE = ROOT / "artifacts/v5-final/s5/development-queue-v3.json"
DEVELOPMENT_LEDGER = ROOT / "artifacts/v5-final/s5/development-ledger-root-v3.json"
MB7_V2 = ROOT / "artifacts/v5-final/pre-calibration/mb7-pre-calibration-audit-v2.json"
RELEASE_V2 = ROOT / "artifacts/v5-final/release/v5-infrastructure-no-go-release-v2.json"


class CIReleaseGateV2Error(RuntimeError):
    pass


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def build() -> dict[str, Any]:
    calibration_queue = _json(CALIBRATION_QUEUE)
    calibration_ledger = _json(CALIBRATION_LEDGER)
    development_queue = _json(DEVELOPMENT_QUEUE)
    development_ledger = _json(DEVELOPMENT_LEDGER)
    mb7 = _json(MB7_V2)
    release = _json(RELEASE_V2)
    current_free = shutil.disk_usage(ROOT).free
    audits = {
        "p0_capacity_v3": audit_p0_v3(require_current_capacity=True),
        "MB5_2": audit_mb5_2(),
        "MB6_v2": audit_mb6_v2(),
        "MB7_v2": audit_mb7_v2(),
        "infrastructure_no_go_v2": audit_release_v2(),
    }
    checks = {
        "all_authoritative_audits_pass": all(all(values.values()) for values in audits.values()),
        "MB7_v2_decision_preserved": mb7["decision"] == "NO_GO_MB7_V2_UNRESOLVED_METHOD_NATIVE_PRODUCTION_SEMANTICS",
        "infrastructure_v2_decision_preserved": release["decision"] == "NO_GO_V5_MATCHED_WORK_INFRASTRUCTURE_V2",
        "calibration_queue_36_not_started": len(calibration_queue["items"]) == 36 and all(item["terminal_status"] == "NOT_STARTED" for item in calibration_queue["items"]),
        "calibration_ledger_empty": calibration_ledger["completed_queue_item_ids"] == [] and calibration_ledger["segments"] == [] and calibration_ledger["candidate_energy_evaluations"] == 0,
        "development_queue_90_not_started": development_queue["expected_queue_count"] == 90 and len(development_queue["items"]) == 90 and all(item["terminal_status"] == "NOT_STARTED" for item in development_queue["items"]),
        "development_ledger_empty": development_ledger["completed_queue_item_ids"] == [] and development_ledger["segments"] == [] and development_ledger["development_candidate_energy_evaluations"] == 0,
        "current_capacity_passed": current_free >= REQUIRED_FREE_BYTES,
    }
    result: dict[str, Any] = {
        "schema": "v5-final.ci-release-gate.v2",
        "status": "PASS_V2_SUCCESSOR_INFRASTRUCTURE_ONLY" if all(checks.values()) else "FAIL_CLOSED",
        "decision": "NO_GO_V5_MATCHED_WORK_INFRASTRUCTURE_V2",
        "checks": checks,
        "audits": audits,
        "current_capacity": {
            "available_bytes": current_free,
            "required_bytes": REQUIRED_FREE_BYTES,
            "passed": current_free >= REQUIRED_FREE_BYTES,
        },
        "queue_state": {
            "H2_H4": {"expected": 36, "terminal": 0, "candidate_energy": 0},
            "development": {"expected": 90, "terminal": 0, "candidate_energy": 0},
        },
        "authorization": {
            "outcome_free_parent_native_implementation": "AUTHORIZED",
            "molecular_candidate_energy": "NOT_AUTHORIZED",
            "H2_H4_execution": "NOT_AUTHORIZED",
            "development_queue_execution": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "academic_boundary": "This gate validates infrastructure state only and cannot support a performance claim.",
    }
    result["report_digest"] = _digest(result)
    return result


def audit() -> dict[str, Any]:
    result = build()
    failures = [name for name, passed in result["checks"].items() if not passed]
    if failures:
        raise CIReleaseGateV2Error("CI release gate v2 failed: " + ", ".join(failures))
    if result["decision"] != "NO_GO_V5_MATCHED_WORK_INFRASTRUCTURE_V2":
        raise CIReleaseGateV2Error("latest gate emitted a non-v2 successor decision")
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

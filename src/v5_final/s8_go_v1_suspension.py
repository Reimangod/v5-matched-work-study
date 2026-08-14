"""Additive suspension of S8-v1 before the first molecular outcome."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .s0_successor import ROOT


OUTPUT = ROOT / "artifacts/v5-final/parent-native/s8-production-go-v1-suspension.json"
GO_V1 = ROOT / "artifacts/v5-final/parent-native/s8-production-go-v1.json"
PLAN_V3 = ROOT / "artifacts/v5-final/parent-native/mb6-v3/h2-h4-calibration-plan-v3.json"
LEDGER_V3 = ROOT / "artifacts/v5-final/parent-native/mb6-v3/h2-h4-calibration-ledger-root-v3.json"
FACTORY_SOURCE = ROOT / "src/v5_final/parent_native_runtime_factory.py"


class S8GoV1SuspensionError(RuntimeError):
    pass


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def build() -> dict[str, Any]:
    go = _json(GO_V1)
    plan = _json(PLAN_V3)
    ledger = _json(LEDGER_V3)
    release_source = FACTORY_SOURCE.read_text()
    checks = {
        "S8_v1_previously_said_GO": go["decision"] == "GO_H2_H4_CALIBRATION_ONLY",
        "factory_queue_path_still_v2": (
            'h2-h4-calibration-queue-v2.json"' in release_source
        ),
        "factory_release_path_does_not_name_S8_v1": (
            'artifacts/v5-final/production/s8-h2-h4-production-go-v1.json"'
            in release_source
            and str(GO_V1.relative_to(ROOT)) not in release_source
        ),
        "factory_release_schema_is_legacy": "v5-final.s8-production-go-gate.v1"
        in release_source,
        "frozen_plan_is_v3": plan["schema"]
        == "v5-final.mb6-h2-h4-calibration-plan.v3"
        and all(
            item["queue_item_id"].startswith("mb6-calibration-item-v3:")
            for item in plan["items"]
        ),
        "no_calibration_started": all(
            item["terminal_status"] == "NOT_STARTED" for item in plan["items"]
        )
        and not ledger["raw_ledger_directories"]
        and not ledger["terminal_segments"],
        "candidate_energy_still_zero": plan["candidate_energy_evaluations"] == 0
        and ledger["candidate_energy_evaluations"] == 0,
    }
    if not all(checks.values()):
        raise S8GoV1SuspensionError("S8-v1 suspension evidence is incomplete")
    artifact = {
        "schema": "v5-final.s8-production-go-suspension.v1",
        "stage": "S8_PRE_FIRST_OUTCOME_GATE_REAUDIT",
        "status": "SUSPENDED_BEFORE_FIRST_MOLECULAR_OUTCOME",
        "decision": "SUSPEND_S8_V1_REMEDIATE_MB6_V3_RUNTIME_RELEASE",
        "superseded_GO": {
            "path": str(GO_V1.relative_to(ROOT)),
            "sha256": _sha(GO_V1),
            "unchanged": True,
        },
        "checks": checks,
        "blocker": (
            "The actual queue-bound runtime release still accepts only the MB6-v2 "
            "queue identity and a different legacy GO path/schema; S8-v1 did not "
            "behaviorally prove release of the frozen MB6-v3 plan."
        ),
        "authorization": {
            "successor_factory_and_gate_remediation": "AUTHORIZED_OUTCOME_FREE_ONLY",
            "molecular_candidate_energy": "NOT_AUTHORIZED",
            "H2_H4_execution": "NOT_AUTHORIZED",
            "development_queue_execution": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "candidate_molecular_energy_evaluations": 0,
        "academic_boundary": (
            "No molecular candidate energy or calibration result was observed before "
            "suspension, so the outcome-blind protocol remains intact."
        ),
    }
    artifact["suspension_digest"] = _digest(artifact)
    return artifact


def audit() -> dict[str, bool]:
    artifact = _json(OUTPUT)
    body = dict(artifact)
    observed = body.pop("suspension_digest", None)
    checks = {
        "suspension_digest_valid": observed == _digest(body),
        "evidence_rebuild_identical": artifact == build(),
        "H2_H4_blocked": artifact["authorization"]["H2_H4_execution"]
        == "NOT_AUTHORIZED",
        "candidate_energy_zero": artifact["candidate_molecular_energy_evaluations"] == 0,
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S8GoV1SuspensionError(
            "S8-v1 suspension audit failed: " + ", ".join(failures)
        )
    return checks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.output is None:
        print(json.dumps(audit(), sort_keys=True))
    else:
        write_json_exclusive(args.output, build())
        print(args.output)


if __name__ == "__main__":
    main()

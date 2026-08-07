"""Append-only S1-v2 correction separating resource and computation work."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from typing import Any

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from . import PROTOCOL_ID
from .s0_successor import ROOT
from .semantic_contract_v2 import RESOURCE_COMPONENTS, WORK_COMPONENTS, ResourceDelta, WorkDelta


def _digest_without(value: dict[str, Any], field: str) -> str:
    payload = dict(value)
    payload.pop(field, None)
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def build_contract() -> dict[str, Any]:
    example = {
        "event": "INDEPENDENT_ENERGY_RECOMPUTATION",
        "resource_delta": asdict(ResourceDelta()),
        "work_delta": asdict(WorkDelta(energy_evaluations=1)),
    }
    result: dict[str, Any] = {
        "schema": "v5-final.s1-scientific-semantic-contract.v2",
        "protocol_id": PROTOCOL_ID,
        "stage": "S1",
        "status": "CORRECTED_COMPLETE",
        "supersedes": "artifacts/v5-final/s1/scientific-semantic-contract-v1.json",
        "correction": (
            "resource_delta is restricted to signed circuit/architecture resource "
            "changes; computation consumption is restricted to nonnegative work_delta"
        ),
        "resource_components": list(RESOURCE_COMPONENTS),
        "work_components": list(WORK_COMPONENTS),
        "independent_energy_recomputation_example": example,
        "academic_integrity": {
            "physical_resource_change_not_conflated_with_computation": True,
            "evidence_work_cannot_disappear_when_state_is_unchanged": True,
        },
        "systems_safety": {
            "resource_and_work_fields_are_disjoint": not bool(
                set(RESOURCE_COMPONENTS) & set(WORK_COMPONENTS)
            ),
            "work_counters_nonnegative": True,
            "resource_changes_may_be_signed": True,
        },
        "authorization": {
            "next_stage": "S2",
            "performance_experiment": "NOT_AUTHORIZED",
            "candidate_molecular_energy_evaluation": "NOT_AUTHORIZED",
            "s5_freeze": "NOT_AUTHORIZED",
        },
        "claim_boundary": "Corrected S1 semantics only; no molecular execution or performance evidence.",
        "decision": "GO_S2_ONLY",
    }
    result["contract_digest"] = _digest_without(result, "contract_digest")
    return result


def audit_contract() -> dict[str, Any]:
    path = ROOT / "artifacts" / "v5-final" / "s1" / "scientific-semantic-contract-v2.json"
    committed = json.loads(path.read_text(encoding="utf-8"))
    checks = {
        "deterministic_rebuild": committed == build_contract(),
        "contract_digest": committed["contract_digest"]
        == _digest_without(committed, "contract_digest"),
        "resource_work_disjoint": not bool(
            set(committed["resource_components"]) & set(committed["work_components"])
        ),
        "example_resource_zero": not any(
            committed["independent_energy_recomputation_example"]["resource_delta"].values()
        ),
        "example_energy_work_one": committed["independent_energy_recomputation_example"][
            "work_delta"
        ]["energy_evaluations"]
        == 1,
        "academic_integrity_gate": all(committed["academic_integrity"].values()),
        "systems_safety_gate": all(committed["systems_safety"].values()),
        "performance_still_closed": committed["authorization"]["performance_experiment"]
        == "NOT_AUTHORIZED",
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise RuntimeError("S1-v2 audit failed: " + ", ".join(failures))
    result = {
        "schema": "v5-final.s1-scientific-semantic-audit.v2",
        "stage": "S1",
        "passed": True,
        "checks": checks,
        "failed_checks": [],
        "claim_boundary": committed["claim_boundary"],
    }
    result["audit_digest"] = _digest_without(result, "audit_digest")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("build", "verify"))
    arguments = parser.parse_args()
    output = ROOT / "artifacts" / "v5-final" / "s1" / "scientific-semantic-contract-v2.json"
    if arguments.action == "build":
        write_json_exclusive(output, build_contract())
        print(json.dumps({"path": str(output), "status": "CORRECTED_COMPLETE"}, sort_keys=True))
        return
    result = audit_contract()
    print(json.dumps({"checks": len(result["checks"]), "passed": True}, sort_keys=True))


if __name__ == "__main__":
    main()

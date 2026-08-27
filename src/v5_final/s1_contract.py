"""Build and audit the S1 scientific semantic contract."""

from __future__ import annotations

import argparse
import hashlib
import json
from typing import Any

from jsonschema import Draft202012Validator

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from . import PROTOCOL_ID
from .s0_successor import ROOT
from .scientific_values import ScientificValueState, TaggedScientificValue
from .semantic_contract import REQUIRED_TERMINAL_EVIDENCE, TerminalStatus


def _digest_without(value: dict[str, Any], field: str) -> str:
    payload = dict(value)
    payload.pop(field, None)
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def build_contract() -> dict[str, Any]:
    legacy = TaggedScientificValue.from_legacy_energy(0)
    result: dict[str, Any] = {
        "schema": "v5-final.s1-scientific-semantic-contract.v1",
        "protocol_id": PROTOCOL_ID,
        "stage": "S1",
        "status": "COMPLETE",
        "scientific_value_states": [state.value for state in ScientificValueState],
        "legacy_zero_mapping": legacy.to_dict(),
        "delta_partitions": {
            "state_delta": "source identity and committed architecture mutation only",
            "resource_delta": "raw physical operation counters only",
            "scientific_value_delta": "tagged scientific value transition only",
            "work_delta": "matched-work envelope charge only",
        },
        "terminal_evidence": {
            status.value: sorted(REQUIRED_TERMINAL_EVIDENCE[status])
            for status in TerminalStatus
        },
        "terminal_semantics": {
            "EXECUTED": "kernel segment and finite AVAILABLE value; commit is represented separately",
            "DEDUPLICATED": "zero state/resource/work delta; alias points to canonical evaluation",
            "STRUCTURALLY_REJECTED": "zero state delta and no scientific evaluation",
            "BUDGET_REJECTED": "pre-operation rejection and no scientific evaluation",
            "FAILED": "INVALID value and exact source rollback",
            "CANCELLED": "no committed mutation and no scientific evaluation",
        },
        "academic_integrity": {
            "missingness_is_never_numeric": True,
            "scientific_zero_requires_available_tag": True,
            "legacy_zero_is_not_a_measurement": True,
            "every_terminal_outcome_requires_evidence": True,
        },
        "systems_safety": {
            "delta_namespaces_disjoint": True,
            "failed_transition_restores_exact_digest": True,
            "deduplication_is_zero_charge": True,
            "budget_rejection_precedes_operation": True,
        },
        "authorization": {
            "next_stage": "S2",
            "performance_experiment": "NOT_AUTHORIZED",
            "candidate_molecular_energy_evaluation": "NOT_AUTHORIZED",
            "s5_freeze": "NOT_AUTHORIZED",
        },
        "claim_boundary": "Semantic-contract evidence only; no molecular execution or performance evidence.",
        "decision": "GO_S2_ONLY",
    }
    result["contract_digest"] = _digest_without(result, "contract_digest")
    return result


def audit_contract() -> dict[str, Any]:
    artifact_path = ROOT / "artifacts" / "v5-final" / "s1" / "scientific-semantic-contract-v1.json"
    schema_path = ROOT / "schemas" / "v5-final-s1-scientific-semantic-contract-v1.schema.json"
    committed = json.loads(artifact_path.read_text(encoding="utf-8"))
    rebuilt = build_contract()
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    errors = sorted(
        Draft202012Validator(schema).iter_errors(committed),
        key=lambda error: list(error.path),
    )
    checks = {
        "schema_valid": not errors,
        "deterministic_rebuild": committed == rebuilt,
        "contract_digest": committed.get("contract_digest")
        == _digest_without(committed, "contract_digest"),
        "legacy_zero_non_numeric": committed["legacy_zero_mapping"]["value"] is None,
        "legacy_zero_not_available": committed["legacy_zero_mapping"]["state"]
        == "LEGACY_SENTINEL_NOT_EVALUATED",
        "four_delta_partitions": set(committed["delta_partitions"])
        == {"state_delta", "resource_delta", "scientific_value_delta", "work_delta"},
        "all_terminal_states_covered": set(committed["terminal_evidence"])
        == {status.value for status in TerminalStatus},
        "terminal_evidence_nonempty": all(committed["terminal_evidence"].values()),
        "academic_integrity_gate": all(committed["academic_integrity"].values()),
        "systems_safety_gate": all(committed["systems_safety"].values()),
        "performance_still_closed": committed["authorization"]["performance_experiment"]
        == "NOT_AUTHORIZED",
    }
    failures = [name for name, passed in checks.items() if not passed]
    result = {
        "schema": "v5-final.s1-scientific-semantic-audit.v1",
        "protocol_id": PROTOCOL_ID,
        "stage": "S1",
        "passed": not failures,
        "checks": checks,
        "failed_checks": failures,
        "schema_errors": [error.message for error in errors],
        "claim_boundary": committed["claim_boundary"],
    }
    result["audit_digest"] = _digest_without(result, "audit_digest")
    if failures:
        raise RuntimeError("S1 contract audit failed: " + ", ".join(failures))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("build", "verify"))
    arguments = parser.parse_args()
    output = ROOT / "artifacts" / "v5-final" / "s1" / "scientific-semantic-contract-v1.json"
    if arguments.action == "build":
        write_json_exclusive(output, build_contract())
        print(json.dumps({"path": str(output), "status": "COMPLETE"}, sort_keys=True))
        return
    audit = audit_contract()
    print(json.dumps({"checks": len(audit["checks"]), "passed": True}, sort_keys=True))


if __name__ == "__main__":
    main()

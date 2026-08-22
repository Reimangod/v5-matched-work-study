"""Build and audit the S2 three-layer identity contract."""

from __future__ import annotations

import argparse
import hashlib
import json
from typing import Any

from jsonschema import Draft202012Validator

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from . import PROTOCOL_ID
from .s0_successor import ROOT


def _digest_without(value: dict[str, Any], field: str) -> str:
    payload = dict(value)
    payload.pop(field, None)
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def build_contract() -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema": "v5-final.s2-identity-contract.v1",
        "protocol_id": PROTOCOL_ID,
        "stage": "S2",
        "status": "COMPLETE",
        "identity_layers": {
            "CandidateIntentID": [
                "source block",
                "transformation family",
                "target family",
                "candidate provenance",
                "generation path",
            ],
            "ProposedPhysicalStateID": [
                "ProblemID",
                "reference state",
                "generator semantics",
                "block order",
                "mapping",
                "qubit order",
                "canonical coefficient bytes",
                "target structure",
                "native circuit semantics",
            ],
            "ExecutionRequestID": [
                "ProposedPhysicalStateID",
                "source checkpoint",
                "optimizer",
                "initialization",
                "work profile",
                "energy budget",
                "stationarity threshold",
                "protocol digest",
                "environment digest",
            ],
        },
        "deduplication": {
            "quantum_evaluation_key": "ProposedPhysicalStateID",
            "maximum_quantum_evaluations_per_state": 1,
            "preserved_per_intent": [
                "candidate generation work",
                "candidate provenance",
                "generation path",
                "rejection history",
            ],
            "alias_is_not_scientific_evaluation": True,
        },
        "canonicalization": {
            "mapping_keys": "lexicographic through canonical JSON",
            "Hamiltonian_terms": "order independent, exact coefficient bytes retained",
            "generator_terms": "order independent, sign and exact coefficient bytes retained",
            "block_order": "order sensitive",
            "native_circuit_gate_order": "order sensitive",
            "binary_float_input": "rejected",
        },
        "academic_integrity": {
            "Hamiltonian_bound_to_state_identity": True,
            "intent_provenance_not_collapsed_by_dedup": True,
            "circuit_semantics_bound_to_state_identity": True,
            "evaluation_conditions_bound_to_request_identity": True,
        },
        "systems_safety": {
            "content_addressed_ids": True,
            "ambiguous_float_payloads_rejected": True,
            "second_different_evaluation_segment_rejected": True,
            "duplicate_intent_alias_rejected": True,
        },
        "authorization": {
            "next_stage": "S3",
            "performance_experiment": "NOT_AUTHORIZED",
            "candidate_molecular_energy_evaluation": "NOT_AUTHORIZED",
            "s5_freeze": "NOT_AUTHORIZED",
        },
        "claim_boundary": "Identity and deduplication semantics only; no molecular execution or performance evidence.",
        "decision": "GO_S3_ONLY",
    }
    result["contract_digest"] = _digest_without(result, "contract_digest")
    return result


def audit_contract() -> dict[str, Any]:
    path = ROOT / "artifacts" / "v5-final" / "s2" / "identity-contract-v1.json"
    schema_path = ROOT / "schemas" / "v5-final-s2-identity-contract-v1.schema.json"
    committed = json.loads(path.read_text(encoding="utf-8"))
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    errors = sorted(
        Draft202012Validator(schema).iter_errors(committed),
        key=lambda error: list(error.path),
    )
    checks = {
        "schema_valid": not errors,
        "deterministic_rebuild": committed == build_contract(),
        "contract_digest": committed.get("contract_digest")
        == _digest_without(committed, "contract_digest"),
        "three_identity_layers": set(committed["identity_layers"])
        == {"CandidateIntentID", "ProposedPhysicalStateID", "ExecutionRequestID"},
        "physical_state_is_evaluation_key": committed["deduplication"]["quantum_evaluation_key"]
        == "ProposedPhysicalStateID",
        "one_quantum_evaluation": committed["deduplication"][
            "maximum_quantum_evaluations_per_state"
        ]
        == 1,
        "intent_evidence_retained": len(committed["deduplication"]["preserved_per_intent"])
        == 4,
        "academic_integrity_gate": all(committed["academic_integrity"].values()),
        "systems_safety_gate": all(committed["systems_safety"].values()),
        "performance_still_closed": committed["authorization"]["performance_experiment"]
        == "NOT_AUTHORIZED",
    }
    failures = [name for name, passed in checks.items() if not passed]
    result = {
        "schema": "v5-final.s2-identity-audit.v1",
        "protocol_id": PROTOCOL_ID,
        "stage": "S2",
        "passed": not failures,
        "checks": checks,
        "failed_checks": failures,
        "schema_errors": [error.message for error in errors],
        "claim_boundary": committed["claim_boundary"],
    }
    result["audit_digest"] = _digest_without(result, "audit_digest")
    if failures:
        raise RuntimeError("S2 identity audit failed: " + ", ".join(failures))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("build", "verify"))
    arguments = parser.parse_args()
    output = ROOT / "artifacts" / "v5-final" / "s2" / "identity-contract-v1.json"
    if arguments.action == "build":
        write_json_exclusive(output, build_contract())
        print(json.dumps({"path": str(output), "status": "COMPLETE"}, sort_keys=True))
        return
    audit = audit_contract()
    print(json.dumps({"checks": len(audit["checks"]), "passed": True}, sort_keys=True))


if __name__ == "__main__":
    main()

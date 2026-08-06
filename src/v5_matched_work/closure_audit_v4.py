"""Closure audit for the semantic-ledger pre-S5-v4 No-Go."""

from __future__ import annotations

import argparse
import hashlib
import json

from .atomic_artifacts import canonical_json_bytes, write_json_exclusive
from .authoritative_pre_s5_v4 import DEPENDENT_STAGES, build, not_authorized
from .evidence_v2 import verify_historical_evidence
from .s0_common import ROOT, sha256


def audit() -> dict:
    gate_path = ROOT / "artifacts/pre-s5/authoritative-readiness-v4.json"
    gate = json.loads(gate_path.read_text()); rebuilt = build()
    historical = verify_historical_evidence()
    checks = {
        "authoritative_gate_rebuild": gate == rebuilt,
        "historical_evidence_reconstructed": historical["passed"],
        "semantic_duplicate_design_fixed": gate["checks"]["different_candidate_ids_same_proposed_state_deduplicated"],
        "semantic_event_and_nonempty_queue_contracts_present": (
            gate["checks"]["semantic_operation_delta_validation_contract"]
            and gate["checks"]["nonempty_frozen_queue_binding_contract"]
        ),
        "s5_v4_never_authorized": gate["s5_authorization_issued"] is False and not (ROOT / "artifacts/s5/development-freeze-v4.json").exists(),
        "all_s5_through_s14_not_authorized": all(
            json.loads((ROOT / f"artifacts/s{stage}/not-authorized-v4.json").read_text())
            == not_authorized(stage, gate) for stage in DEPENDENT_STAGES
        ),
        "pre_s5_candidate_zero_and_production_unknown": (
            gate["pre_s5_candidate_energy_evaluations"] == 0
            and gate["production_candidate_energy_evaluations"] is None
        ),
        "not_molecular_negative": gate["claim_boundary"].endswith("no molecular result."),
    }
    failures = [name for name, passed in checks.items() if not passed]
    result = {
        "schema": "v5-matched-work.pre-s5-closure-audit.v4",
        "stage": "CLOSURE", "passed": not failures,
        "checks": checks, "failed_checks": failures,
        "gate_sha256": sha256(gate_path),
        "historical_evidence_reconstruction": historical,
        "claim_boundary": "Audit of a pre-S5 semantic-ledger infrastructure No-Go; no molecular result.",
    }
    result["audit_digest"] = hashlib.sha256(canonical_json_bytes(result)).hexdigest()
    if failures:
        raise RuntimeError("closure audit v4 failed: " + ", ".join(failures))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args(); result = audit(); output = ROOT / "artifacts/pre-s5/closure-audit-v4.json"
    if args.verify_only:
        if output.read_bytes() != canonical_json_bytes(result):
            raise RuntimeError("closure audit v4 drift")
    else:
        write_json_exclusive(output, result)
    print(json.dumps({"passed": result["passed"], "checks": len(result["checks"])}, sort_keys=True))


if __name__ == "__main__":
    main()

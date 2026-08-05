"""Audit the unified pre-S5-v3 fail-closed package."""

from __future__ import annotations

import argparse
import hashlib
import json

from .atomic_artifacts import canonical_json_bytes, write_json_exclusive
from .authoritative_pre_s5_v3 import DEPENDENT_STAGES, build, not_authorized
from .evidence_v2 import verify_historical_evidence
from .s0_common import ROOT, sha256


def audit() -> dict:
    gate_path = ROOT / "artifacts/pre-s5/authoritative-readiness-v3.json"
    gate = json.loads(gate_path.read_text())
    rebuilt = build()
    historical = verify_historical_evidence()
    checks = {
        "authoritative_gate_rebuild": gate == rebuilt,
        "historical_486_hashes_parent_tree_and_submodule": historical["passed"],
        "duplicate_state_counter_fixed": gate["checks"]["duplicates_do_not_increment_n_states"],
        "normalized_history_not_claimed_raw": gate["checks"]["normalized_history_distinguished_from_actual_kernel_events"],
        "s5_v3_never_authorized": gate["s5_authorization_issued"] is False and not (ROOT / "artifacts/s5/development-freeze-v3.json").exists(),
        "all_s5_through_s14_not_authorized": all(
            json.loads((ROOT / f"artifacts/s{stage}/not-authorized-v3.json").read_text())
            == not_authorized(stage, gate) for stage in DEPENDENT_STAGES
        ),
        "candidate_performance_zero": gate["candidate_energy_evaluations"] == 0 and gate["performance_execution_started"] is False,
        "not_molecular_negative": gate["claim_boundary"].endswith("no molecular result."),
    }
    failures = [name for name, passed in checks.items() if not passed]
    result = {
        "schema": "v5-matched-work.pre-s5-closure-audit.v3",
        "stage": "CLOSURE", "passed": not failures,
        "checks": checks, "failed_checks": failures,
        "gate_sha256": sha256(gate_path),
        "historical_evidence_reconstruction": historical,
        "claim_boundary": "Audit of a pre-S5 infrastructure No-Go; no molecular result.",
    }
    result["audit_digest"] = hashlib.sha256(canonical_json_bytes(result)).hexdigest()
    if failures:
        raise RuntimeError("closure audit v3 failed: " + ", ".join(failures))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args(); result = audit(); output = ROOT / "artifacts/pre-s5/closure-audit-v3.json"
    if args.verify_only:
        if output.read_bytes() != canonical_json_bytes(result):
            raise RuntimeError("closure audit v3 drift")
    else:
        write_json_exclusive(output, result)
    print(json.dumps({"passed": result["passed"], "checks": len(result["checks"])}, sort_keys=True))


if __name__ == "__main__":
    main()

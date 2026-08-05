"""Closure audit with actual S0 hash/tree/submodule reconstruction."""

from __future__ import annotations

import argparse
import hashlib
import json

from .atomic_artifacts import canonical_json_bytes, write_json_exclusive
from .evidence_v2 import verify_historical_evidence
from .pre_s6_readiness import DEPENDENT_STAGES
from .s0_common import ROOT, git, sha256
from .strict_pre_s6_v2 import build as build_incident, not_authorized
from .work_ledger import event_from_dict, reconstruct_candidate_energy_evaluations


def audit() -> dict:
    incident_path = ROOT / "artifacts/pre-s6/readiness-incident-v2.json"
    incident = json.loads(incident_path.read_text())
    rebuilt = build_incident()
    historical = verify_historical_evidence()
    zero_path = ROOT / "artifacts/work-ledgers/pre-s5-zero-events-v2.json"
    zero = json.loads(zero_path.read_text())
    events = [event_from_dict(value) for value in zero["events"]]
    tag_tree = git(ROOT, "ls-tree", "-r", "--name-only", "v5-matched-work-s5-development-freeze-v2")
    checks = {
        "incident_rebuild": incident == rebuilt,
        "historical_486_hashes": historical["checks"]["all_486_historical_hashes"],
        "historical_parent_tree": historical["checks"]["parent_tree"],
        "historical_ceo_submodule_commit": historical["checks"]["ceo_submodule_commit"],
        "pre_outcome_event_reconstruction": reconstruct_candidate_energy_evaluations(events) == 0,
        "s5_tag_contains_no_v2_candidate_performance_artifact": not any(
            path.startswith("artifacts/s6/") and "not-authorized" not in path
            for path in tag_tree.splitlines()
        ),
        "all_dependents_not_authorized": all(
            json.loads((ROOT / f"artifacts/s{stage}/not-authorized-v2.json").read_text())
            == not_authorized(stage, incident) for stage in DEPENDENT_STAGES
        ),
        "not_molecular_negative": incident["claim_boundary"].startswith("Production molecular executability failure"),
    }
    failures = [name for name, passed in checks.items() if not passed]
    result = {
        "schema": "v5-matched-work.preperformance-closure-audit.v2",
        "stage": "CLOSURE", "passed": not failures, "checks": checks,
        "failed_checks": failures, "historical_evidence_reconstruction": historical,
        "incident_sha256": sha256(incident_path),
        "claim_boundary": "Audit of a pre-performance infrastructure No-Go; no molecular result.",
    }
    result["audit_digest"] = hashlib.sha256(canonical_json_bytes(result)).hexdigest()
    if failures:
        raise RuntimeError("closure audit v2 failed: " + ", ".join(failures))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args(); result = audit()
    output = ROOT / "artifacts/pre-s6/closure-audit-v2.json"
    if args.verify_only:
        if output.read_bytes() != canonical_json_bytes(result):
            raise RuntimeError("closure audit v2 drift")
    else:
        write_json_exclusive(output, result)
    print(json.dumps({"passed": result["passed"], "checks": len(result["checks"])}, sort_keys=True))


if __name__ == "__main__":
    main()

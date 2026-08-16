"""Append-only S4 authorization bound to code and duplicate-state semantics."""

from __future__ import annotations

import argparse
import hashlib
import json
from typing import Any

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .production_bundle import build_production_bundle
from .s0_successor import ROOT
from .s3_smoke_authorization_v3 import build as build_v3


OUTPUT = ROOT / "artifacts/v5-final/s3/s4-smoke-authorization-v4.json"


def _digest(value: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def build() -> dict[str, Any]:
    predecessor = json.loads(
        (ROOT / "artifacts/v5-final/s3/s4-smoke-authorization-v3.json").read_text()
    )
    bundle = build_production_bundle()
    result = build_v3()
    result.pop("authorization_digest")
    result["schema"] = "v5-final.s3-s4-smoke-authorization.v4"
    result["status"] = "LIMITED_CODE_BOUND_DUPLICATE_SMOKE_AUTHORIZED"
    result["supersedes_authorization_digest"] = predecessor["authorization_digest"]
    result["production_bundle_digest"] = bundle["bundle_digest"]
    result["scope"].update(
        {
            "candidate_intent_count": 2,
            "unique_physical_state_count": 1,
            "quantum_evaluation_count": 1,
            "alias_provenance_required": True,
            "control_plane_failure_pairs": 80,
        }
    )
    result["work_cap"]["candidate_generations"] = 3
    result["work_cap"]["search_states"] = 2
    result["work_cap"]["rewrite_verifications"] = 3
    result["protocol_binding"] = (
        "ExecutionRequest.protocol_digest and frozen queue protocol_digest must equal "
        "the complete production code bundle digest"
    )
    result["claim_boundary"] = (
        "One unique H2 physical state may be evaluated once through two retained "
        "candidate intents. This is infrastructure evidence only, not performance evidence."
    )
    result["authorization_digest"] = _digest(result)
    return result


def audit() -> dict[str, bool]:
    committed = json.loads(OUTPUT.read_text())
    payload = dict(committed)
    observed = payload.pop("authorization_digest")
    checks = {
        "deterministic_rebuild": committed == build(),
        "digest_valid": observed == _digest(payload),
        "code_bundle_current": committed["production_bundle_digest"]
        == build_production_bundle()["bundle_digest"],
        "duplicate_scope_bounded": committed["scope"]["candidate_intent_count"] == 2
        and committed["scope"]["unique_physical_state_count"] == 1
        and committed["scope"]["quantum_evaluation_count"] == 1,
        "work_cap_complete": committed["work_cap"]["candidate_generations"] == 3
        and committed["work_cap"]["search_states"] == 2
        and committed["work_cap"]["rewrite_verifications"] == 3,
        "performance_closed": committed["performance_experiment"] == "NOT_AUTHORIZED",
        "s5_closed": committed["s5_freeze"] == "NOT_AUTHORIZED",
    }
    if not all(checks.values()):
        raise RuntimeError("S3-v4 smoke authorization audit failed")
    return checks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("build", "verify"))
    args = parser.parse_args()
    if args.action == "build":
        write_json_exclusive(OUTPUT, build())
    else:
        audit()
    print(json.dumps({"action": args.action, "passed": True}, sort_keys=True))


if __name__ == "__main__":
    main()

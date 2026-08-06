"""S4 smoke authorization corrected to charge post-commit catalog rebuilding."""

from __future__ import annotations

import argparse
import hashlib
import json
from typing import Any

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .s0_successor import ROOT
from .s3_smoke_authorization import build as build_v2


def _digest(value: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def build() -> dict[str, Any]:
    predecessor = json.loads(
        (ROOT / "artifacts/v5-final/s3/s4-smoke-authorization-v2.json").read_text()
    )
    result = build_v2()
    result.pop("authorization_digest")
    result["schema"] = "v5-final.s3-s4-smoke-authorization.v3"
    result["status"] = "LIMITED_SMOKE_AUTHORIZED_REBUILD_CHARGED"
    result["supersedes_authorization_digest"] = predecessor["authorization_digest"]
    result["scope"]["catalog_build_count"] = 1
    result["scope"]["catalog_rebuild_count"] = 1
    for field in ("candidate_generations", "search_states", "rewrite_verifications"):
        result["work_cap"][field] = 2
    result["correction"] = (
        "post-commit catalog rebuilding is real work and receives the same generation, "
        "search-state, and rewrite-verification charges as the initial catalog"
    )
    result["authorization_digest"] = _digest(result)
    return result


def audit() -> dict[str, bool]:
    committed = json.loads(
        (ROOT / "artifacts/v5-final/s3/s4-smoke-authorization-v3.json").read_text()
    )
    payload = dict(committed)
    observed = payload.pop("authorization_digest")
    checks = {
        "deterministic_rebuild": committed == build(),
        "digest_valid": observed == _digest(payload),
        "one_initial_and_one_rebuild": committed["scope"]["catalog_build_count"] == 1
        and committed["scope"]["catalog_rebuild_count"] == 1,
        "generation_work_charged_twice": all(
            committed["work_cap"][field] == 2
            for field in ("candidate_generations", "search_states", "rewrite_verifications")
        ),
        "performance_closed": committed["performance_experiment"] == "NOT_AUTHORIZED",
        "s5_closed": committed["s5_freeze"] == "NOT_AUTHORIZED",
    }
    if not all(checks.values()):
        raise RuntimeError("S3-v3 smoke authorization audit failed")
    return checks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("build", "verify"))
    args = parser.parse_args()
    output = ROOT / "artifacts/v5-final/s3/s4-smoke-authorization-v3.json"
    if args.action == "build":
        write_json_exclusive(output, build())
    else:
        audit()
    print(json.dumps({"action": args.action, "passed": True}, sort_keys=True))


if __name__ == "__main__":
    main()

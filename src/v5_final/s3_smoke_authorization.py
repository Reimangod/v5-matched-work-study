"""Narrow authorization for one S4 molecular infrastructure smoke."""

from __future__ import annotations

import argparse
import hashlib
import json
from typing import Any

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from . import PROTOCOL_ID
from .s0_successor import ROOT
from .semantic_contract_v2 import WORK_COMPONENTS


def _digest(value: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def build() -> dict[str, Any]:
    s3 = json.loads(
        (ROOT / "artifacts/v5-final/s3/integrated-execution-ledger-v1.json").read_text()
    )
    result: dict[str, Any] = {
        "schema": "v5-final.s3-s4-smoke-authorization.v2",
        "protocol_id": PROTOCOL_ID,
        "stage": "S3-S4-BOUNDARY",
        "status": "LIMITED_SMOKE_AUTHORIZED",
        "predecessor_contract_digest": s3["contract_digest"],
        "scope": {
            "case": "H2 at 1.5 angstrom, STO-3G, pinned paper-era CEO* kernel",
            "queue_item_count": 1,
            "execution_request_count": 1,
            "purpose": "production-path semantic and transaction closure only",
            "candidate_kind": "same-structure coefficient-optimization smoke",
            "allowed_outputs": [
                "energy/gradient/resource correctness diagnostics",
                "counter reconciliation",
                "transaction and replay evidence",
            ],
        },
        "work_cap": {
            **{field: 0 for field in WORK_COMPONENTS},
            "energy_evaluations": 20,
            "gradient_vector_evaluations": 20,
            "gradient_component_equivalents": 20,
            "optimizer_starts": 1,
            "optimizer_iterations": 4,
            "resource_recounts": 4,
            "candidate_generations": 1,
            "search_states": 1,
            "rewrite_verifications": 1,
            "statevector_recomputations": 2,
        },
        "prohibited": [
            "method comparison",
            "performance ranking",
            "rebuilding-effect claim",
            "cross-molecule robustness claim",
            "S5 production freeze",
            "reuse as a matched-work outcome",
        ],
        "performance_experiment": "NOT_AUTHORIZED",
        "s5_freeze": "NOT_AUTHORIZED",
        "decision": "GO_S4_REGISTERED_SMOKE_ONLY",
        "claim_boundary": "One bounded H2 infrastructure smoke; not performance evidence.",
    }
    result["authorization_digest"] = _digest(result)
    return result


def audit() -> dict[str, bool]:
    path = ROOT / "artifacts/v5-final/s3/s4-smoke-authorization-v2.json"
    committed = json.loads(path.read_text())
    rebuilt = build()
    payload = dict(committed)
    observed = payload.pop("authorization_digest")
    checks = {
        "deterministic_rebuild": committed == rebuilt,
        "digest_valid": observed == _digest(payload),
        "one_case": committed["scope"]["queue_item_count"] == 1
        and committed["scope"]["execution_request_count"] == 1,
        "bounded_energy": 0 < committed["work_cap"]["energy_evaluations"] <= 20,
        "performance_closed": committed["performance_experiment"] == "NOT_AUTHORIZED",
        "s5_closed": committed["s5_freeze"] == "NOT_AUTHORIZED",
        "comparison_prohibited": "method comparison" in committed["prohibited"],
    }
    if not all(checks.values()):
        raise RuntimeError("S3-v2 smoke authorization audit failed")
    return checks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("build", "verify"))
    arguments = parser.parse_args()
    output = ROOT / "artifacts/v5-final/s3/s4-smoke-authorization-v2.json"
    if arguments.action == "build":
        write_json_exclusive(output, build())
    else:
        audit()
    print(json.dumps({"action": arguments.action, "passed": True}, sort_keys=True))


if __name__ == "__main__":
    main()

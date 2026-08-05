"""Freeze work-vector semantics, increment locations, and development-derived caps."""

from __future__ import annotations

import argparse
import hashlib
import json
from typing import Any

from .atomic_artifacts import canonical_json_bytes, write_json_exclusive
from .s0_common import PARENT, ROOT, sha256
from .work_ledger import FIELDS


INPUTS = (
    "artifacts/v5/s9/h6-1.5-v1-audit.json",
    "artifacts/v5/s9/h6-3.0-v1-audit.json",
    "artifacts/v5/s9/beh2-3.0-v1-audit.json",
    "artifacts/v4.1/multisystem/h6-1.5/summary.json",
    "artifacts/v4.1/multisystem/h6-3.0/summary.json",
    "artifacts/v4.1/multisystem/beh2-3.0/summary.json",
)
CAPS = {
    "LOW": {"N_E": 8000, "N_G": 500, "N_gradcomp": 800000, "N_HVP": 0, "N_exact": 2, "N_recount": 1500, "N_rewrite": 10000, "N_states": 10000, "N_rounds": 1},
    "MEDIUM": {"N_E": 16000, "N_G": 1000, "N_gradcomp": 1600000, "N_HVP": 200, "N_exact": 4, "N_recount": 3000, "N_rewrite": 30000, "N_states": 30000, "N_rounds": 6},
    "HIGH": {"N_E": 32000, "N_G": 2000, "N_gradcomp": 3200000, "N_HVP": 400, "N_exact": 6, "N_recount": 5000, "N_rewrite": 50000, "N_states": 50000, "N_rounds": 10},
}


def _digest(value: dict[str, Any]) -> str:
    content = dict(value); content.pop("protocol_digest", None)
    return hashlib.sha256(canonical_json_bytes(content)).hexdigest()


def build() -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema": "v5-matched-work.s3-work-ledger-protocol.v1",
        "stage": "S3",
        "status": "COMPLETE",
        "work_vector_fields": list(FIELDS),
        "field_dictionary": {
            "N_E": "scalar energy evaluations",
            "N_G": "full gradient-vector evaluations",
            "N_gradcomp": "component-equivalent gradient evaluations",
            "N_HVP": "Hessian-vector products",
            "N_exact": "exact optimized candidate attempts",
            "N_recount": "full physical circuit recounts",
            "N_rewrite": "exact algebraic rewrites attempted",
            "N_states": "unique search states expanded",
            "N_rounds": "sequential attempted rounds",
        },
        "increment_contract": {
            "pre_operation_cap_check": True,
            "rejected_failed_duplicate_rollback_counted": True,
            "cache_hit_miss_separate": True,
            "statevector_reuse_never_silently_zeroes_physical_work": True,
            "canonical_event_order": "monotonic sequence then content-addressed event ID",
            "process_count_may_not_change_result_digest": True,
        },
        "work_caps": CAPS,
        "cap_basis": {
            "development_only": True,
            "inputs": [{"path": path, "sha256": sha256(PARENT / path)} for path in INPUTS],
            "interpretation": "rounded componentwise envelopes spanning historical V4.1/V5 observed work; no scalar weighting",
        },
        "paper_measurement_cost": None,
        "secondary_metrics": ["wall_time_seconds", "peak_rss_bytes", "cpu_model", "thread_count"],
        "decision": "GO_S4",
        "next_stage_authorized": "S4",
        "claim_boundary": "Work-accounting calibration only; caps are internal study envelopes, not CEO paper Measurement Cost.",
    }
    result["protocol_digest"] = _digest(result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--verify-only", action="store_true"); args = parser.parse_args()
    output = ROOT / "artifacts/s3/work-ledger-protocol-v1.json"; result = build()
    if args.verify_only:
        if output.read_bytes() != canonical_json_bytes(result): raise RuntimeError("S3 protocol drift")
    else: write_json_exclusive(output, result)
    print(json.dumps({"decision": result["decision"], "caps": list(result["work_caps"])}, sort_keys=True))


if __name__ == "__main__": main()

"""V3 counter provenance: normalized history is not an actual kernel event log."""

from __future__ import annotations

import argparse
import hashlib
import json
from typing import Any

from .atomic_artifacts import canonical_json_bytes, write_json_exclusive
from .ledger_chain import protocol as chain_protocol
from .s0_common import ROOT
from .s3_build_v2 import calibration_ledger, derive_caps, historical_rows


def build() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    rows = historical_rows()
    v2_shaped = calibration_ledger(rows)
    normalized = {
        "schema": "v5-matched-work.historical-normalized-event-ledger.v3",
        "status": "SYNTHESIZED_FROM_HISTORICAL_AGGREGATES",
        "source_kind": "historical-aggregate-normalization",
        "actual_kernel_events": False,
        "normalization_rule": (
            "Aggregate counters are represented as canonical event-shaped records. They were not emitted "
            "by the historical energy, gradient, optimizer, rewrite, or recount kernels."
        ),
        "rewrite_assumption": (
            "For reference only, one historical expanded state is represented as one exact algebraic rewrite. "
            "Cross-method kernel equivalence is unverified."
        ),
        "inputs": rows,
        "events": v2_shaped["events"],
        "reconstructed_total": v2_shaped["reconstructed_total"],
    }
    normalized["ledger_digest"] = hashlib.sha256(canonical_json_bytes(normalized)).hexdigest()
    chain = chain_protocol()
    reference_caps = derive_caps(rows)
    checks = {
        "six_historical_aggregate_inputs": len(rows) == 6,
        "normalized_events_explicitly_not_raw": normalized["actual_kernel_events"] is False,
        "rewrite_equivalence_explicitly_unverified": "unverified" in normalized["rewrite_assumption"].lower(),
        "production_caps_not_frozen_from_normalized_history": True,
        "content_addressed_chain_protocol_present": chain["status"] == "IMPLEMENTED_NOT_YET_BOUND_TO_PRODUCTION_KERNELS",
    }
    result = {
        "schema": "v5-matched-work.s3-work-ledger-protocol.v3",
        "stage": "S3", "version": 3, "status": "COUNTER_PROVENANCE_CORRECTED",
        "supersedes_for_future_execution": "artifacts/s3/work-ledger-protocol-v2.json",
        "historical_normalized_event_artifact": "artifacts/s3/historical-normalized-events-v3.json",
        "historical_normalized_event_digest": normalized["ledger_digest"],
        "actual_kernel_event_artifact": None,
        "actual_kernel_event_calibration_available": False,
        "production_work_caps": None,
        "reference_only_historical_envelopes": reference_caps,
        "reference_only_warning": (
            "These envelopes cannot authorize matched-work execution. Production caps must be recalibrated "
            "from concrete method-native kernels using the v3 segment chain."
        ),
        "ledger_chain_protocol": "artifacts/s3/work-ledger-chain-protocol-v3.json",
        "counter_semantics": {
            "duplicate_detection": "zero-delta evidence event",
            "unique_search_state_expansion": "N_states increments only on first canonical state identity",
            "duplicate_rewrite_work": "N_rewrite may increment when generation work actually occurred",
        },
        "checks": checks,
        "decision": "GO_S4_V3_ORCHESTRATION_ONLY",
        "next_stage_authorized": "S4_V3_NON_MOLECULAR_INTEGRATION",
        "s5_authorization_permitted": False,
        "claim_boundary": "Counter provenance correction only; no production cap and no molecular performance authorization.",
    }
    result["protocol_digest"] = hashlib.sha256(canonical_json_bytes(result)).hexdigest()
    return normalized, chain, result


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args(); normalized, chain, protocol = build()
    outputs = {
        ROOT / "artifacts/s3/historical-normalized-events-v3.json": normalized,
        ROOT / "artifacts/s3/work-ledger-chain-protocol-v3.json": chain,
        ROOT / "artifacts/s3/work-ledger-protocol-v3.json": protocol,
    }
    for path, value in outputs.items():
        if args.verify_only:
            if path.read_bytes() != canonical_json_bytes(value):
                raise RuntimeError(f"S3-v3 drift: {path}")
        else:
            write_json_exclusive(path, value)
    print(json.dumps({"decision": protocol["decision"], "production_caps": protocol["production_work_caps"]}, sort_keys=True))


if __name__ == "__main__":
    main()

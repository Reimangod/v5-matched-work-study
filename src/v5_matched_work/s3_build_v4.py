"""Freeze the semantic kernel-event and frozen-queue ledger contract."""

from __future__ import annotations

import argparse
import hashlib
import json
from typing import Any

from .atomic_artifacts import canonical_json_bytes, write_json_exclusive
from .kernel_ledger_v4 import protocol as kernel_ledger_protocol
from .s0_common import ROOT


def build() -> tuple[dict[str, Any], dict[str, Any]]:
    kernel_protocol = kernel_ledger_protocol()
    s3_v3 = json.loads((ROOT / "artifacts/s3/work-ledger-protocol-v3.json").read_text())
    checks = {
        "operation_delta_semantic_validation_specified": "operation-to-component" in kernel_protocol["event_validation"],
        "evidence_zero_delta_specified": "evidence-event-zero-delta" in kernel_protocol["event_validation"],
        "event_queue_and_source_binding_specified": all(
            name in kernel_protocol["event_validation"]
            for name in ("event-to-segment-queue", "event-to-segment-source")
        ),
        "nonempty_frozen_queue_required": "nonempty frozen queue" in kernel_protocol["queue_binding"],
        "queue_count_digest_and_artifact_hash_required": all(
            name in kernel_protocol["queue_binding"]
            for name in ("frozen queue count", "canonical queue digest", "frozen artifact SHA-256")
        ),
        "historical_normalization_remains_nonproduction": s3_v3["actual_kernel_event_calibration_available"] is False,
    }
    result = {
        "schema": "v5-matched-work.s3-work-ledger-protocol.v4",
        "stage": "S3", "version": 4, "status": "SEMANTIC_LEDGER_CONTRACT_COMPLETE",
        "supersedes_for_future_execution": "artifacts/s3/work-ledger-protocol-v3.json",
        "semantic_kernel_ledger_protocol": "artifacts/s3/semantic-kernel-ledger-protocol-v4.json",
        "semantic_kernel_ledger_protocol_digest": kernel_protocol["protocol_digest"],
        "historical_normalized_event_artifact": s3_v3["historical_normalized_event_artifact"],
        "actual_kernel_event_segments": None,
        "frozen_queue_binding": None,
        "production_completeness_manifest": None,
        "production_work_caps": None,
        "production_candidate_energy_reconstruction": None,
        "pre_s5_zero_record": {
            "path": "artifacts/work-ledgers/pre-s5-zero-events-v2.json",
            "scope": "pre-S5 repository root only; cannot be used after production starts",
        },
        "checks": checks,
        "decision": "GO_S4_V4_ORCHESTRATION_ONLY",
        "next_stage_authorized": "S4_V4_NON_MOLECULAR_INTEGRATION",
        "s5_authorization_permitted": False,
        "claim_boundary": "Semantic production-ledger contract only; no frozen queue, kernel events, caps, or performance.",
    }
    result["protocol_digest"] = hashlib.sha256(canonical_json_bytes(result)).hexdigest()
    return kernel_protocol, result


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args(); kernel_protocol, protocol = build()
    outputs = {
        ROOT / "artifacts/s3/semantic-kernel-ledger-protocol-v4.json": kernel_protocol,
        ROOT / "artifacts/s3/work-ledger-protocol-v4.json": protocol,
    }
    for path, value in outputs.items():
        if args.verify_only:
            if path.read_bytes() != canonical_json_bytes(value):
                raise RuntimeError(f"S3-v4 drift: {path}")
        else:
            write_json_exclusive(path, value)
    print(json.dumps({"decision": protocol["decision"], "production_manifest": protocol["production_completeness_manifest"]}, sort_keys=True))


if __name__ == "__main__":
    main()

"""Authoritative v4 gate: semantic ledger design is not production evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from typing import Any

from .atomic_artifacts import canonical_json_bytes, write_json_exclusive
from .evidence_v2 import verify_historical_evidence
from .s0_common import ROOT
from .work_ledger import event_from_dict, reconstruct_candidate_energy_evaluations


DEPENDENT_STAGES = tuple(range(5, 15))


def build() -> dict[str, Any]:
    s2 = json.loads((ROOT / "artifacts/s2/stationary-source-protocol-v2.json").read_text())
    s3 = json.loads((ROOT / "artifacts/s3/work-ledger-protocol-v4.json").read_text())
    s4 = json.loads((ROOT / "artifacts/s4/comparator-protocol-v4.json").read_text())
    integration = json.loads((ROOT / s4["integration_artifact"]).read_text())
    pre_s5_zero = json.loads((ROOT / s3["pre_s5_zero_record"]["path"]).read_text())
    zero_events = [event_from_dict(value) for value in pre_s5_zero["events"]]
    production = s4["production_readiness"]
    checks = {
        "historical_evidence_reconstructed": verify_historical_evidence()["passed"],
        "five_stationary_sources_including_h4": len(s2["quantum_probe"]["cases"]) == 5,
        "different_candidate_ids_same_proposed_state_deduplicated": integration["checks"]["different_candidate_ids_same_proposed_state_deduplicated"],
        "semantic_operation_delta_validation_contract": s3["checks"]["operation_delta_semantic_validation_specified"],
        "nonempty_frozen_queue_binding_contract": s3["checks"]["nonempty_frozen_queue_required"],
        "pre_s5_repository_candidate_energy_events_zero": reconstruct_candidate_energy_evaluations(zero_events) == 0,
        "actual_frozen_queue_binding_available": s3["frozen_queue_binding"] is not None,
        "actual_semantic_kernel_event_segments_available": s3["actual_kernel_event_segments"] is not None,
        "actual_queue_bound_completeness_manifest_available": s3["production_completeness_manifest"] is not None,
        "production_candidate_energy_reconstructed_from_v4_chain": s3["production_candidate_energy_reconstruction"] is not None,
        "production_caps_frozen_from_validated_v4_kernel_events": s3["production_work_caps"] is not None,
        "six_concrete_molecular_backend_entrypoints": production["concrete_molecular_backends"],
        "post_rewrite_canonical_state_identity_bound": production["post_rewrite_canonical_state_identity"],
        "counter_binding_inside_pinned_quantum_kernels": production["kernel_counter_binding"],
        "toy_h2_h4_quantum_integration": production["quantum_h2_h4_integration"],
        "method_native_executor_semantics_verified": production["method_native_semantics"],
        "no_s5_v4_freeze_published": not (ROOT / "artifacts/s5/development-freeze-v4.json").exists(),
    }
    failures = [name for name, passed in checks.items() if not passed]
    result = {
        "schema": "v5-matched-work.authoritative-pre-s5-readiness.v4",
        "stage": "AUTHORITATIVE_PRE_S5", "status": "FAIL_CLOSED" if failures else "PASS",
        "authoritative": True,
        "checks": checks, "failed_checks": failures,
        "decision": "NO_GO_BEFORE_S5_V4" if failures else "AUTHORIZED_S5_V4_FREEZE_ONLY",
        "s5_authorization_issued": False if failures else True,
        "pre_s5_candidate_energy_evaluations": 0,
        "production_candidate_energy_evaluations": None,
        "performance_execution_started": False,
        "preserved_valid_evidence": [
            "S2-v2 five-source reconstruction",
            "S3-v4 semantic kernel-event and frozen-queue contract",
            "S4-v4 canonical proposed-state orchestration deduplication",
        ],
        "required_repairs": [
            "Freeze a nonempty S5 queue and bind its count, canonical digest, and artifact SHA-256",
            "Implement concrete method-native molecular executors with post-rewrite canonical state identity",
            "Bind semantic v4 events inside pinned quantum kernels",
            "Run toy/H2/H4 quantum integration and publish queue-bound segments/completeness manifest",
            "Reconstruct candidate-energy totals and production caps only from the complete validated v4 chain",
        ],
        "claim_boundary": "Authoritative infrastructure failure before S5-v4 authorization; no molecular result.",
    }
    result["readiness_digest"] = hashlib.sha256(canonical_json_bytes(result)).hexdigest()
    if not failures:
        raise RuntimeError("authoritative v4 gate unexpectedly passed")
    return result


def not_authorized(stage: int, gate: dict[str, Any]) -> dict[str, Any]:
    result = {
        "schema": "v5-matched-work.not-authorized.v4", "stage": f"S{stage}",
        "status": "NOT_AUTHORIZED", "blocking_decision": gate["decision"],
        "blocking_readiness_digest": gate["readiness_digest"],
        "pre_s5_candidate_energy_evaluations": 0,
        "production_candidate_energy_evaluations": None,
        "scientific_execution_performed": False,
        "claim_boundary": "Stage not executed; no performance evidence.",
    }
    result["record_digest"] = hashlib.sha256(canonical_json_bytes(result)).hexdigest()
    return result


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args(); gate = build()
    outputs = {
        ROOT / "artifacts/pre-s5/authoritative-readiness-v4.json": gate,
        **{ROOT / f"artifacts/s{stage}/not-authorized-v4.json": not_authorized(stage, gate)
           for stage in DEPENDENT_STAGES},
    }
    for path, value in outputs.items():
        if args.verify_only:
            if path.read_bytes() != canonical_json_bytes(value):
                raise RuntimeError(f"authoritative pre-S5-v4 drift: {path}")
        else:
            write_json_exclusive(path, value)
    print(json.dumps({"decision": gate["decision"], "failed_checks": gate["failed_checks"]}, sort_keys=True))


if __name__ == "__main__":
    main()

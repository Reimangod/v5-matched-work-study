"""Single authoritative molecular-readiness gate before any S5-v3 freeze."""

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
    s3 = json.loads((ROOT / "artifacts/s3/work-ledger-protocol-v3.json").read_text())
    s4 = json.loads((ROOT / "artifacts/s4/comparator-protocol-v3.json").read_text())
    integration = json.loads((ROOT / s4["integration_artifact"]).read_text())
    zero = json.loads((ROOT / "artifacts/work-ledgers/pre-s5-zero-events-v2.json").read_text())
    zero_events = [event_from_dict(value) for value in zero["events"]]
    production = s4["production_readiness"]
    checks = {
        "historical_evidence_reconstructed": verify_historical_evidence()["passed"],
        "five_stationary_sources_including_h4": len(s2["quantum_probe"]["cases"]) == 5,
        "duplicates_do_not_increment_n_states": integration["checks"]["duplicates_do_not_increment_n_states"],
        "normalized_history_distinguished_from_actual_kernel_events": s3["actual_kernel_event_calibration_available"] is False,
        "content_addressed_segment_chain_protocol_present": bool(s3["ledger_chain_protocol"]),
        "repository_candidate_energy_events_zero": reconstruct_candidate_energy_evaluations(zero_events) == 0,
        "actual_kernel_events_available_for_cap_calibration": s3["actual_kernel_event_calibration_available"],
        "production_work_caps_frozen_from_actual_kernel_events": s3["production_work_caps"] is not None,
        "six_concrete_molecular_backend_entrypoints": production["concrete_molecular_backends"],
        "counter_binding_inside_pinned_quantum_kernels": production["kernel_counter_binding"],
        "toy_h2_h4_quantum_integration": production["quantum_h2_h4_integration"],
        "method_native_executor_semantics_verified": production["method_native_semantics"],
        "no_s5_v3_freeze_published_before_authoritative_gate": not (ROOT / "artifacts/s5/development-freeze-v3.json").exists(),
    }
    failures = [name for name, passed in checks.items() if not passed]
    result = {
        "schema": "v5-matched-work.authoritative-pre-s5-readiness.v3",
        "stage": "AUTHORITATIVE_PRE_S5", "status": "FAIL_CLOSED" if failures else "PASS",
        "authoritative": True,
        "replaces_gate_sequence": ["pre-S5 orchestration readiness v2", "strict pre-S6 molecular readiness v2"],
        "checks": checks, "failed_checks": failures,
        "decision": "NO_GO_BEFORE_S5_V3" if failures else "AUTHORIZED_S5_V3_FREEZE_ONLY",
        "s5_authorization_issued": False if failures else True,
        "candidate_energy_evaluations": 0, "performance_execution_started": False,
        "preserved_valid_evidence": [
            "S2-v2 five-source reconstruction including H4",
            "S3-v3 counter provenance classification and ledger-chain protocol",
            "S4-v3 duplicate-safe orchestration counters",
        ],
        "required_repairs": [
            "Implement six concrete method-native molecular executors",
            "Bind counters inside pinned quantum kernels",
            "Run outcome-free toy/H2/H4 quantum integration",
            "Capture actual kernel event chains and freeze caps from those events",
        ],
        "claim_boundary": "Authoritative infrastructure failure before S5-v3 authorization; no molecular result.",
    }
    result["readiness_digest"] = hashlib.sha256(canonical_json_bytes(result)).hexdigest()
    if not failures:
        raise RuntimeError("authoritative gate unexpectedly passed")
    return result


def not_authorized(stage: int, gate: dict[str, Any]) -> dict[str, Any]:
    result = {
        "schema": "v5-matched-work.not-authorized.v3", "stage": f"S{stage}",
        "status": "NOT_AUTHORIZED", "blocking_decision": gate["decision"],
        "blocking_readiness_digest": gate["readiness_digest"],
        "candidate_energy_evaluations": 0, "scientific_execution_performed": False,
        "claim_boundary": "Stage not executed; no performance evidence.",
    }
    result["record_digest"] = hashlib.sha256(canonical_json_bytes(result)).hexdigest()
    return result


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args(); gate = build()
    outputs = {
        ROOT / "artifacts/pre-s5/authoritative-readiness-v3.json": gate,
        **{ROOT / f"artifacts/s{stage}/not-authorized-v3.json": not_authorized(stage, gate)
           for stage in DEPENDENT_STAGES},
    }
    for path, value in outputs.items():
        if args.verify_only:
            if path.read_bytes() != canonical_json_bytes(value):
                raise RuntimeError(f"authoritative pre-S5-v3 drift: {path}")
        else:
            write_json_exclusive(path, value)
    print(json.dumps({"decision": gate["decision"], "failed_checks": gate["failed_checks"]}, sort_keys=True))


if __name__ == "__main__":
    main()

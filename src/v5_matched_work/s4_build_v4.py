"""Canonical proposed-state deduplication integration for orchestration only."""

from __future__ import annotations

import argparse
import hashlib
import json
from typing import Any

from .adapters import ENTRYPOINTS
from .atomic_artifacts import canonical_json_bytes, write_json_exclusive
from .comparators import comparator_registry
from .integration_gate import build as build_integration
from .s0_common import ROOT


def build() -> tuple[dict[str, Any], dict[str, Any]]:
    integration = build_integration(counter_semantics="v4-canonical-proposed-states")
    comparators = []
    for base in comparator_registry():
        item = dict(base)
        item.update({
            "entrypoint": ENTRYPOINTS[item["method_id"]],
            "counter_semantics": "v4-canonical-proposed-states",
            "deduplication_key": "canonical proposed_state_id; production must bind post-rewrite structure/state identity",
            "adapter_scope": "orchestration-only",
            "molecular_backend_entrypoint": None,
            "kernel_counter_evidence": None,
            "method_native_executor_evidence": None,
        })
        comparators.append(item)
    checks = {
        "six_orchestration_entrypoints": len(comparators) == 6,
        "same_candidate_id_duplicate_excluded_from_n_states": integration["checks"]["duplicates_do_not_increment_n_states"],
        "different_candidate_ids_same_proposed_state_excluded": integration["checks"]["different_candidate_ids_same_proposed_state_deduplicated"],
        "duplicate_evidence_zero_delta": integration["checks"]["duplicate_detection_is_zero_delta_evidence"],
        "source_immutable_and_deterministic": integration["checks"]["all_sources_immutable"] and integration["checks"]["all_deterministic"],
        "no_molecular_candidate_energy_executed": integration["checks"]["no_molecular_candidate_energy_executed"],
    }
    result = {
        "schema": "v5-matched-work.s4-comparator-protocol.v4",
        "stage": "S4", "version": 4, "status": "CANONICAL_STATE_DEDUP_ORCHESTRATION_COMPLETE",
        "supersedes_for_future_execution": "artifacts/s4/comparator-protocol-v3.json",
        "comparators": comparators,
        "integration_artifact": "artifacts/s4/semantic-dedup-orchestration-integration-v4.json",
        "integration_artifact_digest": integration["artifact_digest"],
        "checks": checks,
        "production_readiness": {
            "concrete_molecular_backends": False,
            "post_rewrite_canonical_state_identity": False,
            "kernel_counter_binding": False,
            "quantum_h2_h4_integration": False,
            "method_native_semantics": False,
        },
        "decision": "GO_AUTHORITATIVE_PRE_S5_READINESS_V4",
        "next_stage_authorized": "AUTHORITATIVE_PRE_S5_READINESS_V4_ONLY",
        "s5_authorization_permitted": False,
        "claim_boundary": "Canonical proposed-state orchestration test only; no molecular quantum execution or performance.",
    }
    result["protocol_digest"] = hashlib.sha256(canonical_json_bytes(result)).hexdigest()
    return integration, result


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args(); integration, protocol = build()
    outputs = {
        ROOT / "artifacts/s4/semantic-dedup-orchestration-integration-v4.json": integration,
        ROOT / "artifacts/s4/comparator-protocol-v4.json": protocol,
    }
    for path, value in outputs.items():
        if args.verify_only:
            if path.read_bytes() != canonical_json_bytes(value):
                raise RuntimeError(f"S4-v4 drift: {path}")
        else:
            write_json_exclusive(path, value)
    print(json.dumps({"decision": protocol["decision"], "semantic_duplicate_fix": protocol["checks"]["different_candidate_ids_same_proposed_state_excluded"]}, sort_keys=True))


if __name__ == "__main__":
    main()

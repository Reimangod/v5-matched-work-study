"""Freeze corrected orchestration counters without claiming molecular readiness."""

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
    integration = build_integration(counter_semantics="v3-unique-states")
    comparators = []
    for base in comparator_registry():
        item = dict(base)
        item.update({
            "entrypoint": ENTRYPOINTS[item["method_id"]],
            "counter_binding": "v5_matched_work.work_ledger.WorkLedger.charge",
            "counter_semantics": "v3-unique-states",
            "adapter_scope": "orchestration-only",
            "molecular_backend_entrypoint": None,
            "kernel_counter_evidence": None,
            "method_native_executor_evidence": None,
        })
        comparators.append(item)
    checks = {
        "six_orchestration_entrypoints": len(comparators) == 6 and all(item["entrypoint"] for item in comparators),
        "duplicates_do_not_increment_n_states": integration["checks"]["duplicates_do_not_increment_n_states"],
        "duplicate_detection_retained_as_zero_delta_evidence": integration["checks"]["duplicate_detection_is_zero_delta_evidence"],
        "cap_rollback_dedup_recount_determinism_control_flow": all(
            integration["checks"][name] for name in (
                "pre_operation_cap_fail_closed", "deduplication_observed", "rollback_observed",
                "resource_recount_observed", "all_deterministic",
            )
        ),
        "scope_explicitly_orchestration_only": all(item["adapter_scope"] == "orchestration-only" for item in comparators),
        "no_molecular_candidate_energy_executed": integration["checks"]["no_molecular_candidate_energy_executed"],
    }
    result = {
        "schema": "v5-matched-work.s4-comparator-protocol.v3",
        "stage": "S4", "version": 3, "status": "ORCHESTRATION_COUNTER_FIX_COMPLETE",
        "supersedes_for_future_execution": "artifacts/s4/comparator-protocol-v2.json",
        "comparators": comparators,
        "integration_artifact": "artifacts/s4/toy-h2-h4-orchestration-integration-v3.json",
        "integration_artifact_digest": integration["artifact_digest"],
        "checks": checks,
        "production_readiness": {
            "concrete_molecular_backends": False,
            "kernel_counter_binding": False,
            "quantum_h2_h4_integration": False,
            "method_native_semantics": False,
        },
        "decision": "GO_AUTHORITATIVE_PRE_S5_READINESS_V3",
        "next_stage_authorized": "AUTHORITATIVE_PRE_S5_READINESS_V3_ONLY",
        "s5_authorization_permitted": False,
        "claim_boundary": (
            "Corrected deterministic orchestration counters only. Pinned H2/H4 structures are not "
            "molecular quantum integration and provide no performance evidence."
        ),
    }
    result["protocol_digest"] = hashlib.sha256(canonical_json_bytes(result)).hexdigest()
    return integration, result


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args(); integration, protocol = build()
    outputs = {
        ROOT / "artifacts/s4/toy-h2-h4-orchestration-integration-v3.json": integration,
        ROOT / "artifacts/s4/comparator-protocol-v3.json": protocol,
    }
    for path, value in outputs.items():
        if args.verify_only:
            if path.read_bytes() != canonical_json_bytes(value):
                raise RuntimeError(f"S4-v3 drift: {path}")
        else:
            write_json_exclusive(path, value)
    print(json.dumps({"decision": protocol["decision"], "duplicate_counter_fix": protocol["checks"]["duplicates_do_not_increment_n_states"]}, sort_keys=True))


if __name__ == "__main__":
    main()

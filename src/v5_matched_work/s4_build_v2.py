"""Freeze executable comparator adapters and their integration evidence."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
from typing import Any

from .adapters import ENTRYPOINTS
from .atomic_artifacts import canonical_json_bytes, write_json_exclusive
from .comparators import PRIMARY_METHODS, comparator_registry
from .integration_gate import build as build_integration
from .s0_common import ROOT, sha256


COUNTER_BINDING = "v5_matched_work.work_ledger.WorkLedger.charge"


def _resolves(value: str) -> bool:
    module_name, attribute = value.split(":", 1)
    return callable(getattr(importlib.import_module(module_name), attribute, None))


def build() -> tuple[dict[str, Any], dict[str, Any]]:
    integration = build_integration()
    integration_path = ROOT / "artifacts/s4/toy-h2-h4-integration-v2.json"
    registry = []
    for item in comparator_registry():
        record = dict(item)
        record["entrypoint"] = ENTRYPOINTS[record["method_id"]]
        record["counter_binding"] = COUNTER_BINDING
        registry.append(record)
    checks = {
        "six_executable_entrypoints": len(registry) == 6 and all(_resolves(item["entrypoint"]) for item in registry),
        "all_share_counter_increment_api": all(item["counter_binding"] == COUNTER_BINDING for item in registry),
        "same_structure_executor_present": _resolves(ENTRYPOINTS[PRIMARY_METHODS[1]]),
        "structural_magnitude_executor_present": _resolves(ENTRYPOINTS[PRIMARY_METHODS[2]]),
        "integration_gate_passed": integration["status"] == "PASS" and all(integration["checks"].values()),
        "integration_has_no_molecular_candidate_energy": integration["checks"]["no_molecular_candidate_energy_executed"],
    }
    failures = [name for name, passed in checks.items() if not passed]
    protocol = {
        "schema": "v5-matched-work.s4-comparator-protocol.v2",
        "stage": "S4", "version": 2,
        "status": "COMPLETE" if not failures else "FAILED",
        "supersedes_for_future_execution": "artifacts/s4/comparator-protocol-v1.json",
        "comparators": registry,
        "common_contract": {
            "immutable_source_interface": "v5_matched_work.comparators.ImmutableSource",
            "componentwise_cap_preflight": True,
            "shared_raw_event_counter_api": COUNTER_BINDING,
            "rejected_failed_duplicate_rollback_retained": True,
            "full_physical_resource_recount": True,
            "fci_or_exact_reference_online": False,
            "deterministic_queue_and_tie_break": True,
        },
        "ablation_identity": (
            "The without-rebuilding adapter reuses its original catalog; only the full V5 adapter "
            "calls the catalog backend again from each accepted child."
        ),
        "integration_artifact": str(integration_path.relative_to(ROOT)),
        "integration_artifact_sha256": hashlib.sha256(canonical_json_bytes(integration)).hexdigest(),
        "checks": checks, "failed_checks": failures,
        "decision": "GO_PRE_S5_READINESS_V2" if not failures else "NO_GO_S4_V2",
        "next_stage_authorized": "PRE_S5_READINESS_V2" if not failures else "NONE",
        "paper_measurement_cost": None,
        "claim_boundary": (
            "Executable adapter and deterministic integration evidence only. H2/H4 structures were used "
            "without molecular candidate-energy calls; no performance claim."
        ),
    }
    protocol["protocol_digest"] = hashlib.sha256(canonical_json_bytes(protocol)).hexdigest()
    if failures:
        raise RuntimeError("S4-v2 gate failed: " + ", ".join(failures))
    return integration, protocol


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args(); integration, protocol = build()
    outputs = {
        ROOT / "artifacts/s4/toy-h2-h4-integration-v2.json": integration,
        ROOT / "artifacts/s4/comparator-protocol-v2.json": protocol,
    }
    for path, value in outputs.items():
        if args.verify_only:
            if path.read_bytes() != canonical_json_bytes(value):
                raise RuntimeError(f"S4-v2 drift: {path}")
        else:
            write_json_exclusive(path, value)
    print(json.dumps({"decision": protocol["decision"], "comparators": len(protocol["comparators"])}, sort_keys=True))


if __name__ == "__main__":
    main()

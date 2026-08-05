"""Strict molecular-executability audit after the v2 infrastructure freeze."""

from __future__ import annotations

import argparse
import hashlib
import json
from typing import Any

from .atomic_artifacts import canonical_json_bytes, write_json_exclusive
from .evidence_v2 import verify_historical_evidence
from .pre_s6_readiness import DEPENDENT_STAGES
from .s0_common import ROOT
from .work_ledger import event_from_dict, reconstruct_candidate_energy_evaluations


def build() -> dict[str, Any]:
    s2 = json.loads((ROOT / "artifacts/s2/stationary-source-protocol-v2.json").read_text())
    s3 = json.loads((ROOT / "artifacts/s3/work-ledger-protocol-v2.json").read_text())
    s4 = json.loads((ROOT / "artifacts/s4/comparator-protocol-v2.json").read_text())
    s5 = json.loads((ROOT / "artifacts/s5/development-freeze-v2.json").read_text())
    integration = json.loads((ROOT / s4["integration_artifact"]).read_text())
    zero = json.loads((ROOT / s5["candidate_energy_evaluations_at_s5"]["ledger_path"]).read_text())
    events = [event_from_dict(value) for value in zero["events"]]
    comparators = s4["comparators"]
    checks = {
        "historical_evidence_reconstructed": verify_historical_evidence()["passed"],
        "five_stationary_sources_including_h4": len(s2["quantum_probe"]["cases"]) == 5,
        "raw_work_calibration_present": bool(s3["raw_event_artifact"]),
        "repository_candidate_energy_events_zero": reconstruct_candidate_energy_evaluations(events) == 0,
        "six_orchestration_entrypoints_callable": all(item.get("entrypoint") for item in comparators),
        # A production adapter must name a concrete serialized-source loader and
        # pinned quantum backend. The v2 orchestration protocol intentionally has neither.
        "six_concrete_molecular_backend_entrypoints": all(item.get("molecular_backend_entrypoint") for item in comparators),
        "counter_binding_reaches_pinned_energy_gradient_optimizer_and_recount_kernels": all(
            item.get("kernel_counter_evidence") for item in comparators
        ),
        "toy_h2_h4_quantum_integration_not_structure_only": all(
            record["source_provenance"].get("candidate_energy_execution") is True
            for record in integration["records"] if record["case_id"] != "toy-structural-integration"
        ),
        "method_native_executor_evidence": all(item.get("method_native_executor_evidence") for item in comparators),
    }
    failures = [name for name, passed in checks.items() if not passed]
    result = {
        "schema": "v5-matched-work.pre-s6-readiness-incident.v2",
        "stage": "PRE_S6", "status": "FAIL_CLOSED" if failures else "PASS",
        "checks": checks, "failed_checks": failures,
        "decision": "NO_GO_PRODUCTION_MOLECULAR_ADAPTERS_INCOMPLETE" if failures else "AUTHORIZED_S6",
        "candidate_energy_evaluations": 0, "performance_execution_started": False,
        "supersedes_authorizations": ["S5-v2 AUTHORIZED_S6_FROM_TAG_ONLY"],
        "preserved_valid_evidence": [
            "S2-v2 five-source pinned-implementation reconstruction including H4",
            "S3-v2 raw-event normalization and componentwise cap calibration",
            "S4-v2 deterministic orchestration/control-flow integration",
            "S5-v2 corrected literature and event-derived zero record",
        ],
        "required_repairs_before_any_new_freeze": [
            "Implement six concrete molecular backends with serialized immutable-source loading",
            "Bind the shared counter inside every pinned energy, gradient, optimizer, rewrite, state-expansion, and recount kernel",
            "Run outcome-free quantum integration on toy/H2/H4 and retain rollback, deduplication, recount, and determinism evidence",
            "Audit native method semantics: same-structure reoptimization, physical magnitude pruning, V4.1 joint one-shot, and the two V5 catalog policies",
            "Issue a new readiness artifact before any replacement S5 authorization",
        ],
        "claim_boundary": (
            "Production molecular executability failure before candidate outcomes. The S4-v2 fixture is "
            "control-flow evidence only and supports no matched-work performance conclusion."
        ),
    }
    result["incident_digest"] = hashlib.sha256(canonical_json_bytes(result)).hexdigest()
    if not failures:
        raise RuntimeError("strict audit unexpectedly passed; use a positive readiness artifact instead")
    return result


def not_authorized(stage: int, incident: dict[str, Any]) -> dict[str, Any]:
    result = {
        "schema": "v5-matched-work.not-authorized.v2", "stage": f"S{stage}",
        "status": "NOT_AUTHORIZED", "blocking_decision": incident["decision"],
        "blocking_incident_digest": incident["incident_digest"],
        "candidate_energy_evaluations": 0, "scientific_execution_performed": False,
        "claim_boundary": "Dependent stage not executed; no performance evidence.",
    }
    result["record_digest"] = hashlib.sha256(canonical_json_bytes(result)).hexdigest()
    return result


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args(); incident = build()
    outputs = {
        ROOT / "artifacts/pre-s6/readiness-incident-v2.json": incident,
        **{ROOT / f"artifacts/s{stage}/not-authorized-v2.json": not_authorized(stage, incident)
           for stage in DEPENDENT_STAGES},
    }
    for path, value in outputs.items():
        if args.verify_only:
            if path.read_bytes() != canonical_json_bytes(value):
                raise RuntimeError(f"strict pre-S6-v2 drift: {path}")
        else:
            write_json_exclusive(path, value)
    print(json.dumps({"decision": incident["decision"], "failed_checks": incident["failed_checks"]}, sort_keys=True))


if __name__ == "__main__":
    main()

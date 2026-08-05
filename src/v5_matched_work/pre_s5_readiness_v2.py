"""Readiness audit that runs before S5-v2 can authorize performance execution."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from typing import Any

from .atomic_artifacts import canonical_json_bytes, write_json_exclusive
from .comparators import PRIMARY_METHODS
from .evidence_v2 import verify_historical_evidence
from .s0_common import ROOT, git
from .work_ledger import WorkVector, event_from_dict, raw_ledger_document, reconstruct_candidate_energy_evaluations


ZERO_LEDGER_PATH = ROOT / "artifacts/work-ledgers/pre-s5-zero-events-v2.json"
READINESS_PATH = ROOT / "artifacts/pre-s5/readiness-v2.json"


def _zero_ledger(high_cap: dict[str, int]) -> dict[str, Any]:
    result = raw_ledger_document(
        ledger_id="study-candidate-work-chain-root-v2",
        phase="initialized-before-s5-authorization",
        cap=WorkVector(**high_cap),
        events=[],
    )
    result.pop("ledger_digest")
    result.update({
        "append_policy": "immutable content-addressed event segments chained from this root",
        "zero_event_semantics": (
            "Proves only that the repository work chain contains no candidate-energy event at initialization; "
            "it does not prove that no computation occurred elsewhere."
        ),
    })
    result["ledger_digest"] = hashlib.sha256(canonical_json_bytes(result)).hexdigest()
    return result


def build() -> tuple[dict[str, Any], dict[str, Any]]:
    s2 = json.loads((ROOT / "artifacts/s2/stationary-source-protocol-v2.json").read_text())
    s3 = json.loads((ROOT / "artifacts/s3/work-ledger-protocol-v2.json").read_text())
    s4 = json.loads((ROOT / "artifacts/s4/comparator-protocol-v2.json").read_text())
    integration = json.loads((ROOT / s4["integration_artifact"]).read_text())
    zero = _zero_ledger(s3["work_caps"]["HIGH"])
    zero_events = [event_from_dict(value) for value in zero["events"]]
    historical = verify_historical_evidence()
    stationary = {item["case_id"] for item in s2["quantum_probe"]["cases"]}
    scheduled = {"lih-3.0", "h6-1.5", "h6-3.0", "beh2-3.0", "h4-1.5-known-development"}
    comparators = {item["method_id"]: item for item in s4["comparators"]}
    checks = {
        "historical_486_hashes_parent_tree_and_submodule_reverified": historical["passed"],
        "all_scheduled_sources_stationarity_audited": scheduled.issubset(stationary),
        "six_executable_comparator_entrypoints": set(comparators) == set(PRIMARY_METHODS) and all(item["entrypoint"] for item in comparators.values()),
        "shared_counter_increment_api_bound_to_each_comparator": len({item["counter_binding"] for item in comparators.values()}) == 1,
        "toy_h2_h4_new_integration_evidence_present": integration["status"] == "PASS",
        "n_rewrite_calibrated_from_comparable_raw_events": s3["checks"]["rewrite_bound_to_each_search_state"],
        "same_structure_and_structural_magnitude_executors_present": all(method in comparators for method in PRIMARY_METHODS[1:3]),
        "zero_candidate_energy_reconstructed_from_raw_events": reconstruct_candidate_energy_evaluations(zero_events) == 0,
        "no_molecular_candidate_energy_in_integration_gate": integration["checks"]["no_molecular_candidate_energy_executed"],
        "s2_s3_s4_v2_gates_passed": all(value["status"] == "COMPLETE" for value in (s2, s3, s4)),
    }
    failures = [name for name, passed in checks.items() if not passed]
    result = {
        "schema": "v5-matched-work.pre-s5-readiness.v2",
        "stage": "PRE_S5_V2",
        "status": "PASS" if not failures else "FAIL_CLOSED",
        "s4_v2_tag_commit": git(ROOT, "rev-parse", "v5-matched-work-s4-comparators-v2^{}"),
        "temporal_order": "This readiness artifact must be committed and tagged before S5-v2 authorization is built.",
        "checks": checks, "failed_checks": failures,
        "historical_evidence_reconstruction": historical,
        "zero_event_ledger": str(ZERO_LEDGER_PATH.relative_to(ROOT)),
        "zero_event_ledger_digest": zero["ledger_digest"],
        "candidate_energy_evaluations_reconstructed": 0,
        "decision": "READY_TO_FREEZE_S5_V2" if not failures else "NO_GO_PRE_S5_V2",
        "next_stage_authorized": "S5_V2_FREEZE_ONLY" if not failures else "NONE",
        "claim_boundary": "Infrastructure readiness before S5 freeze; no candidate-performance evidence.",
    }
    result["readiness_digest"] = hashlib.sha256(canonical_json_bytes(result)).hexdigest()
    if failures:
        raise RuntimeError("pre-S5-v2 readiness failed: " + ", ".join(failures))
    return zero, result


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args(); zero, readiness = build()
    outputs = {ZERO_LEDGER_PATH: zero, READINESS_PATH: readiness}
    for path, value in outputs.items():
        if args.verify_only:
            if path.read_bytes() != canonical_json_bytes(value):
                raise RuntimeError(f"pre-S5-v2 drift: {path}")
        else:
            write_json_exclusive(path, value)
    print(json.dumps({"decision": readiness["decision"], "checks": len(readiness["checks"])}, sort_keys=True))


if __name__ == "__main__":
    main()

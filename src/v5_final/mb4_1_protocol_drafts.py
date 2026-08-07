"""Outcome-blind MB4.1 protocol proposals and continuing No-Go audit."""

from __future__ import annotations

import argparse
import hashlib
import json
from typing import Any

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .method_native_hardening import protocol as hardening_protocol
from .s0_successor import ROOT


OUTPUT = ROOT / "artifacts/v5-final/method-native/mb4-1-protocol-drafts-v1.json"


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _protocol(name: str, body: dict[str, Any]) -> dict[str, Any]:
    result = {
        "schema": f"v5-final.mb4-1.{name}.v1",
        "approval_status": "PROPOSED_AWAITING_INDEPENDENT_HUMAN_APPROVAL",
        "outcome_status": "OUTCOME_BLIND_NO_CANDIDATE_ENERGY_USED",
        **body,
    }
    result["protocol_digest"] = _digest(result)
    return result


def build() -> dict[str, Any]:
    no_rebuild = _protocol(
        "no-rebuild-protocol",
        {
            "classification": "PROSPECTIVELY_REGISTERED_CAUSAL_ABLATION",
            "causal_contrast": (
                "full V5 may regenerate its structural candidate set after each accepted child; "
                "no-rebuild freezes the source structural whitelist and source order"
            ),
            "source_freeze": [
                "structural candidate IDs",
                "source ordering",
                "source checkpoint and runtime identity",
            ],
            "child_rebinding": [
                "rebuild a current-runtime catalog",
                "retain only source-whitelisted structural IDs",
                "recompute numerical constraints, predictions, curvature coordinates, and resources",
                "bar every candidate absent from the source whitelist",
            ],
            "stale_rule": (
                "a whitelisted structural ID absent or semantically incompatible in the current "
                "catalog is STALE_UNAVAILABLE, is recorded, and is never executed"
            ),
            "ordering_rule": "preserve frozen source order; current numerical values never rerank",
            "round_rule": (
                "use the parent V5 acceptance, commit, reoptimization, rollback, and stopping "
                "policies, but never replenish or expand the structural whitelist"
            ),
            "approval_consequence": "not executable until exact wording and digest are approved",
        },
    )
    magnitude = _protocol(
        "magnitude-control-protocol",
        {
            "classification": "PROSPECTIVELY_REGISTERED_MAGNITUDE_CONTROL_NOT_PARENT_NATIVE",
            "score": "squared constraint residual from the pinned parent calibration semantics",
            "selection": "remove the lowest score; ties break by lowercase structural candidate ID",
            "batch_size": 1,
            "sequential_rule": (
                "after each committed deletion, reoptimize the remaining ansatz and recompute all "
                "surviving scores from the committed child before considering another deletion"
            ),
            "physical_rule": "delete the physical generator, then perform a full resource recount",
            "stale_rule": "pre-deletion scores become invalid after every commit or rollback",
            "acceptance_and_rollback": (
                "use the request-bound optimizer and acceptance policy; failed acceptance rolls "
                "back state, ansatz, resources, and optimizer state before termination"
            ),
            "stopping": [
                "no surviving eligible generator",
                "the next deletion is rejected by the frozen acceptance policy",
                "the next operation would exceed the componentwise work cap",
            ],
            "cap_rule": "record work already performed; do not execute an operation that would exceed cap",
            "approval_consequence": "not executable until exact wording and digest are approved",
        },
    )
    v4_sentinel = _protocol(
        "v4-1-h2-h4-sentinel-protocol",
        {
            "classification": "NEW_CASE_SPECIFIC_V4_1_CALIBRATION_FREEZE",
            "scope": "H2/H4 calibration only; separate from the 90-item development queue",
            "screening_inputs_allowed": [
                "source checkpoint identity",
                "Hamiltonian/problem identity without candidate outcomes",
                "structural candidate identity and equivalence class",
                "predeclared work, optimizer, acceptance, RNG, and environment policies",
            ],
            "screening_inputs_forbidden": [
                "FCI or exact reference energy",
                "candidate energy",
                "historical sentinel outcome or rank",
                "development-queue result",
            ],
            "pre_outcome_freeze": [
                "source checkpoint",
                "candidate IDs and order",
                "equivalence classes",
                "queue count and digest",
                "work cap",
                "optimizer and acceptance policies",
                "executor identity and environment",
            ],
            "historical_rule": "historical V4.1 sentinels may be provenance evidence only and may not be copied",
            "authorization_boundary": (
                "an approved protocol still does not authorize energy; a separate audited H2/H4 "
                "queue freeze and pre-calibration gate are required"
            ),
        },
    )
    queue = json.loads(
        (ROOT / "artifacts/v5-final/s5/development-queue-v3.json").read_text()
    )
    ledger = json.loads(
        (ROOT / "artifacts/v5-final/s5/development-ledger-root-v3.json").read_text()
    )
    development_state = {
        "expected_count": queue["expected_queue_count"],
        "not_started_count": sum(
            item["terminal_status"] == "NOT_STARTED" for item in queue["items"]
        ),
        "completed_count": len(ledger["completed_queue_item_ids"]),
        "segment_count": len(ledger["segments"]),
        "candidate_energy_evaluations": ledger["development_candidate_energy_evaluations"],
    }
    result = {
        "schema": "v5-final.method-native.mb4-1-protocol-drafts.v1",
        "stage": "MB4.1_DRAFT",
        "status": "NO_GO_AWAITING_INDEPENDENT_HUMAN_PROTOCOL_APPROVAL",
        "decision": "NO_GO_MB4_1_PROTOCOLS_PROPOSED_NOT_APPROVED",
        "protocols": {
            "no_rebuild": no_rebuild,
            "magnitude_control": magnitude,
            "v4_1_h2_h4_sentinel": v4_sentinel,
        },
        "ledger_hardening_protocol": hardening_protocol(),
        "development_queue": development_state,
        "molecular_candidate_energy_executed": False,
        "H2_H4_calibration_queue_created": False,
        "approval_record": {
            "reviewer": None,
            "approved_protocol_digests": [],
            "approval_artifact": None,
        },
        "authorization": {
            "six_concrete_executors": "NOT_AUTHORIZED",
            "H2_H4_queue_freeze": "NOT_AUTHORIZED",
            "H2_H4_candidate_energy": "NOT_AUTHORIZED",
            "development_queue_execution": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "academic_boundary": (
            "These are prospective proposals, not retroactive method definitions or evidence of performance."
        ),
        "systems_boundary": (
            "No executable authorization can be derived while approval_record is empty."
        ),
    }
    result["artifact_digest"] = _digest(result)
    return result


def audit() -> dict[str, bool]:
    committed = json.loads(OUTPUT.read_text())
    rebuilt = build()
    payload = dict(committed)
    observed = payload.pop("artifact_digest")
    queue = committed["development_queue"]
    checks = {
        "deterministic_rebuild": committed == rebuilt,
        "artifact_digest": observed == _digest(payload),
        "all_proposals_unapproved": all(
            protocol["approval_status"]
            == "PROPOSED_AWAITING_INDEPENDENT_HUMAN_APPROVAL"
            for protocol in committed["protocols"].values()
        ),
        "no_outcomes": committed["molecular_candidate_energy_executed"] is False,
        "no_h2_h4_queue": committed["H2_H4_calibration_queue_created"] is False,
        "development_queue_untouched": queue
        == {
            "expected_count": 90,
            "not_started_count": 90,
            "completed_count": 0,
            "segment_count": 0,
            "candidate_energy_evaluations": 0,
        },
        "approval_empty": committed["approval_record"]
        == {"reviewer": None, "approved_protocol_digests": [], "approval_artifact": None},
        "everything_closed": all(
            value == "NOT_AUTHORIZED" for value in committed["authorization"].values()
        ),
    }
    if not all(checks.values()):
        raise RuntimeError("MB4.1 protocol-draft audit failed")
    return checks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("build", "verify"))
    args = parser.parse_args()
    if args.action == "build":
        write_json_exclusive(OUTPUT, build())
    else:
        audit()
    print(json.dumps({"action": args.action, "passed": True}, sort_keys=True))


if __name__ == "__main__":
    main()

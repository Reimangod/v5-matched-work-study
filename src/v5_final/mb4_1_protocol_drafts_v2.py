"""Additive outcome-blind MB4.1 v2 protocols and empty human-review template."""

from __future__ import annotations

import argparse
import hashlib
import json
from typing import Any

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .mb3_1_hardening_v2_audit import audit as audit_hardening_v2
from .s0_successor import ROOT


OUTPUT = ROOT / "artifacts/v5-final/method-native/mb4-1-protocol-drafts-v2.json"
REVIEW_OUTPUT = ROOT / "artifacts/v5-final/method-native/mb4-1-human-review-template-v2.json"
V1_OUTPUT = ROOT / "artifacts/v5-final/method-native/mb4-1-protocol-drafts-v1.json"


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _protocol(name: str, body: dict[str, Any]) -> dict[str, Any]:
    result = {
        "schema": f"v5-final.mb4-1.{name}.v2",
        "approval_status": "PROPOSED_AWAITING_INDEPENDENT_HUMAN_APPROVAL",
        "outcome_status": "OUTCOME_BLIND_NO_CANDIDATE_ENERGY_USED",
        **body,
    }
    result["protocol_digest"] = _digest(result)
    return result


def _queue_state() -> dict[str, Any]:
    queue = json.loads((ROOT / "artifacts/v5-final/s5/development-queue-v3.json").read_text())
    ledger = json.loads(
        (ROOT / "artifacts/v5-final/s5/development-ledger-root-v3.json").read_text()
    )
    return {
        "expected_count": queue["expected_queue_count"],
        "not_started_count": sum(
            item["terminal_status"] == "NOT_STARTED" for item in queue["items"]
        ),
        "completed_count": len(ledger["completed_queue_item_ids"]),
        "segment_count": len(ledger["segments"]),
        "candidate_energy_evaluations": ledger["development_candidate_energy_evaluations"],
    }


def build_protocols() -> dict[str, Any]:
    no_rebuild = _protocol(
        "no-rebuild-protocol",
        {
            "classification": "PROSPECTIVELY_REGISTERED_SINGLE_CAUSAL_ABLATION",
            "causal_variable": "structural candidate replenishment after accepted children",
            "source_freeze": [
                "source checkpoint and runtime identity",
                "source structural candidate-ID whitelist only",
            ],
            "child_round": [
                "construct the normal full-V5 catalog for the current child runtime",
                "retain every surviving candidate whose structural ID is in the source whitelist",
                "bar every structural candidate absent from the source whitelist",
                "recompute numerical constraints, predictions, curvature coordinates, and resources",
                "apply the same current-state selection and ranking rule as full V5",
            ],
            "ordering_rule": (
                "rerank surviving whitelisted candidates from current-child numerical values; "
                "source ordering is not frozen"
            ),
            "stale_rule": (
                "a whitelisted candidate absent or semantically incompatible in the current catalog "
                "is recorded as STALE_UNAVAILABLE and is never executed"
            ),
            "shared_with_full_v5": [
                "selection and ranking",
                "acceptance",
                "commit",
                "reoptimization",
                "rollback",
                "stopping",
                "componentwise work accounting",
            ],
            "forbidden_compound_ablation": (
                "freezing source order would be a separately named frozen-catalog-order compound "
                "ablation and is excluded from this primary comparison"
            ),
            "approval_consequence": "digest approval still does not authorize an executor or energy",
        },
    )
    magnitude = _protocol(
        "magnitude-control-protocol",
        {
            "classification": "PROSPECTIVELY_REGISTERED_SINGLE_COORDINATE_CONTROL_NOT_PARENT_NATIVE",
            "target_family": (
                "only a valid single coordinate belonging to the pinned CEO/operator family of the "
                "source ansatz; blocks, subsets, and rewrites are excluded"
            ),
            "deletion_unit": "exactly one ansatz generator and its single variational coordinate",
            "constraint_transformation": (
                "construct the registered single-coordinate deletion constraint for theta_i -> 0; "
                "reject the candidate if this transformation is not valid in the target family"
            ),
            "score": (
                "squared residual of that registered deletion constraint; for an ordinary direct "
                "single-coordinate constraint, verify numerically and symbolically that it equals theta_i^2"
            ),
            "selection": "lowest score first; ties break by lowercase canonical structural candidate ID",
            "batch_size": 1,
            "sequentiality": (
                "after each committed deletion, rebuild and reoptimize the remaining ansatz, then "
                "recompute all surviving scores before selecting again"
            ),
            "physical_deletion": (
                "remove the generator from the ansatz structure; setting its coefficient to zero is insufficient"
            ),
            "resource_recount": [
                "rebuild the full circuit after deletion",
                "measure full CNOT count",
                "measure CNOT depth",
                "measure total depth",
                "measure parameter count",
            ],
            "resource_zero_rule": (
                "if a containing CEO block remains and measured resources do not decrease, record zero "
                "resource reduction and never label it a successful circuit reduction"
            ),
            "reoptimization": "use the request-bound optimizer from the committed pre-deletion state",
            "rollback": (
                "failed optimization or acceptance restores ansatz structure, parameters, optimizer state, "
                "resources, and ledger transaction before terminating the attempt"
            ),
            "stopping": [
                "no structurally valid single-coordinate deletion remains",
                "the next deletion is rejected by the frozen acceptance policy",
                "the next required operation would exceed the componentwise work cap",
            ],
            "work_cap": (
                "charge generation, constraint/score work, optimization, and full recount; reject the next "
                "operation before execution when any component would exceed cap"
            ),
            "excluded_protocols": [
                "block deletion",
                "multi-coordinate subset deletion",
                "registered rewrite or fusion",
            ],
            "approval_consequence": "digest approval still does not authorize an executor or energy",
        },
    )
    sentinel = _protocol(
        "v4-1-h2-h4-sentinel-protocol",
        {
            "classification": "NEW_OUTCOME_BLIND_CASE_SPECIFIC_V4_1_CALIBRATION_FREEZE",
            "scope": "H2/H4 calibration only; separate from the 90-item development queue",
            "source_checkpoint": (
                "one pinned stationary source per H2/H4 case, with StatePreparationID, ProblemID, "
                "Hamiltonian digest, and source checkpoint digest frozen"
            ),
            "eligible_candidate_generation": (
                "run the pinned parent V4.1 structural catalog/screening rules using source structure, "
                "registered rewrite validity, and structural compatibility only"
            ),
            "equivalence_classes": (
                "use the pinned catalog's canonical structural equivalence_class_id; no outcome-derived "
                "regrouping or historical rank is permitted"
            ),
            "representative_selection": (
                "within each nonempty equivalence class choose the candidate with the lowest lowercase "
                "canonical structural candidate ID"
            ),
            "sentinel_count": (
                "one representative per selected equivalence class, with at most four sentinels per case"
            ),
            "canonical_order": "ascending equivalence_class_id, then ascending structural candidate ID",
            "overflow_rule": (
                "if more than four equivalence classes are eligible, select the first four under canonical order"
            ),
            "predictor_policy": (
                "no predictor is used for selection in v2; any future OBS-predictor variant must be a "
                "separate protocol and charge all measurement/computation work"
            ),
            "pre_outcome_freeze": [
                "ordered candidate and equivalence-class identities",
                "exact sentinel count",
                "queue artifact and schema-audit digests",
                "componentwise work cap",
                "optimizer and acceptance policy digests",
                "RNG and environment identities",
                "executor identity and pinned provenance commits",
            ],
            "forbidden_inputs": [
                "FCI or exact reference energy",
                "candidate energy",
                "historical success or sentinel rank",
                "development result",
            ],
            "historical_rule": "historical sentinels are provenance only and are never copied",
            "authorization_boundary": (
                "human approval permits only later queue construction and audit; a separate gate is "
                "required for GO_H2_H4_CALIBRATION_ONLY"
            ),
        },
    )
    return {
        "no_rebuild": no_rebuild,
        "magnitude_control": magnitude,
        "v4_1_h2_h4_sentinel": sentinel,
    }


def build() -> dict[str, Any]:
    v1 = json.loads(V1_OUTPUT.read_text())
    result = {
        "schema": "v5-final.method-native.mb4-1-protocol-drafts.v2",
        "stage": "MB4.1_DRAFT_V2",
        "status": "NO_GO_AWAITING_INDEPENDENT_HUMAN_PROTOCOL_APPROVAL",
        "decision": "NO_GO_MB4_1_V2_AWAITING_INDEPENDENT_HUMAN_APPROVAL",
        "v1_disposition": {
            "status": "SUPERSEDED_BY_MB4_1_PROTOCOL_DRAFTS_V2",
            "path": str(V1_OUTPUT.relative_to(ROOT)),
            "sha256": hashlib.sha256(V1_OUTPUT.read_bytes()).hexdigest(),
            "artifact_digest": v1["artifact_digest"],
            "v1_artifact_modified": False,
        },
        "protocols": build_protocols(),
        "development_queue": _queue_state(),
        "molecular_candidate_energy_executed": False,
        "H2_H4_calibration_queue_created": False,
        "six_production_molecular_executors_implemented": False,
        "approval_record": {
            "reviewer": None,
            "review_date": None,
            "decision": None,
            "approval_artifact": None,
            "approved_protocol_digests": [],
        },
        "authorization": {
            "independent_human_review": "REQUEST_READY",
            "protocol_implementation": "NOT_AUTHORIZED",
            "six_concrete_executors": "NOT_AUTHORIZED",
            "H2_H4_queue_freeze": "NOT_AUTHORIZED",
            "H2_H4_candidate_energy": "NOT_AUTHORIZED",
            "development_queue_execution": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "academic_boundary": "Prospective protocol text only; no outcomes or retroactive method definition.",
        "systems_boundary": "Empty approval record and explicit authorizations force continued No-Go.",
    }
    result["artifact_digest"] = _digest(result)
    return result


def build_review_template(protocol_artifact: dict[str, Any] | None = None) -> dict[str, Any]:
    artifact = protocol_artifact or build()
    digests = {
        name: protocol["protocol_digest"] for name, protocol in artifact["protocols"].items()
    }
    checklist = {
        "no_rebuild_is_single_structural_replenishment_ablation": None,
        "no_rebuild_uses_current_state_ranking": None,
        "magnitude_is_single_coordinate_only": None,
        "magnitude_physical_deletion_and_full_recount_are_exact": None,
        "magnitude_zero_resource_rule_is_acceptable": None,
        "v4_1_eligibility_and_equivalence_classes_are_outcome_blind": None,
        "v4_1_one_per_class_max_four_rule_is_acceptable": None,
        "fci_candidate_energy_historical_rank_and_development_results_are_excluded": None,
        "work_optimizer_acceptance_rng_environment_are_frozen_before_outcomes": None,
        "approval_does_not_authorize_energy_or_development_execution": None,
    }
    result = {
        "schema": "v5-final.mb4-1-independent-human-review-template.v2",
        "status": "AWAITING_INDEPENDENT_HUMAN_REVIEW",
        "protocol_artifact_path": str(OUTPUT.relative_to(ROOT)),
        "protocol_artifact_digest": artifact["artifact_digest"],
        "protocol_digests": digests,
        "reviewer": None,
        "reviewer_affiliation_or_role": None,
        "review_date": None,
        "decision": None,
        "checklist": checklist,
        "requested_changes": [],
        "signature_or_attestation": None,
        "instructions": (
            "Create a new immutable review artifact referencing this template and the exact protocol "
            "digests. Do not edit this template or the protocol artifact. APPROVED may be recorded "
            "only by an independent human after every checklist item is explicitly resolved."
        ),
        "authorization_if_completed": (
            "protocol implementation review only; no energy, queue execution, or performance claim"
        ),
    }
    result["template_digest"] = _digest(result)
    return result


def audit() -> dict[str, bool]:
    committed = json.loads(OUTPUT.read_text())
    review = json.loads(REVIEW_OUTPUT.read_text())
    rebuilt = build()
    checks = {
        "prior_hardening": all(audit_hardening_v2().values()),
        "deterministic_rebuild": committed == rebuilt,
        "artifact_digest": committed["artifact_digest"]
        == _digest({key: value for key, value in committed.items() if key != "artifact_digest"}),
        "review_template_deterministic": review == build_review_template(committed),
        "template_digest": review["template_digest"]
        == _digest({key: value for key, value in review.items() if key != "template_digest"}),
        "v1_unchanged": hashlib.sha256(V1_OUTPUT.read_bytes()).hexdigest()
        == committed["v1_disposition"]["sha256"],
        "all_protocols_unapproved": all(
            protocol["approval_status"]
            == "PROPOSED_AWAITING_INDEPENDENT_HUMAN_APPROVAL"
            for protocol in committed["protocols"].values()
        ),
        "human_fields_empty": review["reviewer"] is None
        and review["review_date"] is None
        and review["decision"] is None
        and all(value is None for value in review["checklist"].values()),
        "no_outcomes": committed["molecular_candidate_energy_executed"] is False,
        "queue_untouched": committed["development_queue"]
        == {
            "expected_count": 90,
            "not_started_count": 90,
            "completed_count": 0,
            "segment_count": 0,
            "candidate_energy_evaluations": 0,
        },
        "execution_closed": all(
            value == "NOT_AUTHORIZED"
            for key, value in committed["authorization"].items()
            if key != "independent_human_review"
        ),
    }
    if not all(checks.values()):
        raise RuntimeError("MB4.1 protocol drafts v2 audit failed")
    return checks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("build", "verify"))
    args = parser.parse_args()
    if args.action == "build":
        artifact = build()
        write_json_exclusive(OUTPUT, artifact)
        write_json_exclusive(REVIEW_OUTPUT, build_review_template(artifact))
    else:
        audit()
    print(json.dumps({"action": args.action, "passed": True}, sort_keys=True))


if __name__ == "__main__":
    main()

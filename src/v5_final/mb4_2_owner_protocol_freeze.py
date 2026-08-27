"""Additive repository-owner freeze of the outcome-blind MB4 protocols.

This module does not execute a molecular kernel.  It converts the immutable
MB4.1 v2 proposals into a new, content-addressed freeze after the repository
owner explicitly removed independent-human approval as a governance gate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from typing import Any

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .mb4_1_protocol_drafts_v2 import audit as audit_v2
from .s0_successor import ROOT


OUTPUT = ROOT / "artifacts/v5-final/method-native/mb4-2-owner-protocol-freeze-v1.json"
V2_OUTPUT = ROOT / "artifacts/v5-final/method-native/mb4-1-protocol-drafts-v2.json"
V2_REVIEW_TEMPLATE = (
    ROOT / "artifacts/v5-final/method-native/mb4-1-human-review-template-v2.json"
)
REPOSITORY = "Reimangod/v5-matched-work-study"
REPOSITORY_OWNER = "Reimangod"
OWNER_DIRECTIVE = (
    "独立Human Approvalを必須条件から外し、既存artifactを変更せず、repository ownerの"
    "明示的判断に基づくoutcome-blind protocol freezeを新規artifactとして作成する。"
    "V5 no-rebuildは実態に合わせてV5 fixed-source-whitelist / no-replenishmentへ改称する。"
    "その後、CIでfreezeを検証し、6つのmethod-native executorをoutcome-freeで実装・監査する。"
    "molecular candidate energy、H2/H4実行、90-item development queue、performance claimは"
    "一切許可しない。MB5終了後はMB6 queue freezeだけを許可して停止する。"
)

CANONICAL_METHOD_IDS = (
    "immutable-ceo-star-source",
    "same-structure-reoptimization",
    "structural-magnitude-pruning",
    "v4.1-one-shot-joint-compression",
    "v5-fixed-source-whitelist-no-replenishment",
    "v5-sequential-with-rebuilding",
)
LEGACY_QUEUE_METHOD_IDS = {
    "immutable-ceo-star-source": "immutable-ceo-star-source",
    "same-structure-reoptimization": "same-structure-reoptimization",
    "structural-magnitude-pruning": "structural-magnitude-pruning",
    "v4.1-one-shot-joint-compression": "v4.1-one-shot-joint-compression",
    "v5-fixed-source-whitelist-no-replenishment": "v5-sequential-without-rebuilding",
    "v5-sequential-with-rebuilding": "v5-sequential-with-rebuilding",
}


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


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


def _freeze_protocol(
    *,
    source: dict[str, Any],
    protocol_id: str,
    display_name: str,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    excluded = {
        "schema",
        "approval_status",
        "approval_consequence",
        "authorization_boundary",
        "protocol_digest",
    }
    result = {
        "schema": f"v5-final.mb4-2.{protocol_id}.v1",
        "protocol_id": protocol_id,
        "display_name": display_name,
        "freeze_status": "FROZEN_OUTCOME_BLIND_BY_REPOSITORY_OWNER_DIRECTIVE",
        "outcome_status": "OUTCOME_BLIND_NO_CANDIDATE_ENERGY_USED",
        "source_draft_protocol_digest": source["protocol_digest"],
        **{key: value for key, value in source.items() if key not in excluded},
        **(overrides or {}),
        "authorization_boundary": (
            "the freeze authorizes MB5 outcome-free structural executor implementation and audit "
            "only; it does not authorize a molecule, Hamiltonian kernel, candidate energy, H2/H4 "
            "execution, development-queue execution, or performance claim"
        ),
    }
    result["protocol_digest"] = _digest(result)
    return result


def _established_method_contract(
    protocol_id: str, display_name: str, semantics: list[str]
) -> dict[str, Any]:
    result = {
        "schema": "v5-final.mb4-2.established-method-contract.v1",
        "protocol_id": protocol_id,
        "display_name": display_name,
        "freeze_status": "FROZEN_OUTCOME_BLIND_BY_REPOSITORY_OWNER_DIRECTIVE",
        "semantics": semantics,
        "outcome_status": "OUTCOME_BLIND_NO_CANDIDATE_ENERGY_USED",
        "authorization_boundary": "MB5 outcome-free structural validation only",
    }
    result["protocol_digest"] = _digest(result)
    return result


def build_protocols() -> dict[str, dict[str, Any]]:
    v2 = json.loads(V2_OUTPUT.read_text())
    source = v2["protocols"]
    fixed_source = _freeze_protocol(
        source=source["no_rebuild"],
        protocol_id="v5-fixed-source-whitelist-no-replenishment",
        display_name="V5 fixed-source-whitelist / no-replenishment",
        overrides={
            "classification": "PROSPECTIVELY_FROZEN_SINGLE_CAUSAL_ABLATION",
            "renaming": {
                "old_name": "V5 no-rebuild",
                "new_name": "V5 fixed-source-whitelist / no-replenishment",
                "reason": (
                    "the executor rebuilds a current-runtime catalog and current-state ranking but "
                    "forbids structural candidates outside the source whitelist; only replenishment "
                    "is disabled"
                ),
                "legacy_queue_method_id": "v5-sequential-without-rebuilding",
                "legacy_id_status": "IMMUTABLE_COMPATIBILITY_ALIAS_ONLY",
            },
        },
    )
    magnitude = _freeze_protocol(
        source=source["magnitude_control"],
        protocol_id="single-coordinate-magnitude-control",
        display_name="Single-coordinate magnitude control",
        overrides={"classification": "FROZEN_SINGLE_COORDINATE_CONTROL_NOT_PARENT_NATIVE"},
    )
    sentinel = _freeze_protocol(
        source=source["v4_1_h2_h4_sentinel"],
        protocol_id="v4-1-outcome-blind-sentinel-selection",
        display_name="V4.1 outcome-blind sentinel selection",
        overrides={
            "scope": (
                "selection semantics only; no H2/H4 queue is created and no H2/H4 execution is authorized"
            )
        },
    )
    return {
        "immutable-ceo-star-source": _established_method_contract(
            "immutable-ceo-star-source",
            "Immutable CEO* source",
            [
                "record the exact source structure without candidate construction",
                "do not create a child state",
            ],
        ),
        "same-structure-reoptimization": _established_method_contract(
            "same-structure-reoptimization",
            "Same-structure reoptimization",
            [
                "preserve the exact source generator structure",
                "prepare a bound optimizer transaction but do not run it in outcome-free validation",
            ],
        ),
        "structural-magnitude-pruning": magnitude,
        "v4.1-one-shot-joint-compression": sentinel,
        "v5-fixed-source-whitelist-no-replenishment": fixed_source,
        "v5-sequential-with-rebuilding": _established_method_contract(
            "v5-sequential-with-rebuilding",
            "V5 sequential with rebuilding",
            [
                "construct the current-runtime structural catalog after every accepted child",
                "allow structurally eligible replenished candidates",
                "apply current-state ranking with deterministic candidate-ID tie-breaks",
            ],
        ),
    }


def build() -> dict[str, Any]:
    v2 = json.loads(V2_OUTPUT.read_text())
    review = json.loads(V2_REVIEW_TEMPLATE.read_text())
    protocols = build_protocols()
    result = {
        "schema": "v5-final.method-native.mb4-2-owner-protocol-freeze.v1",
        "stage": "MB4.2_OWNER_PROTOCOL_FREEZE",
        "status": "FROZEN_OUTCOME_BLIND_BY_REPOSITORY_OWNER_DIRECTIVE",
        "decision": "GO_MB5_OUTCOME_FREE_EXECUTOR_IMPLEMENTATION_ONLY",
        "governance": {
            "repository": REPOSITORY,
            "repository_owner": REPOSITORY_OWNER,
            "directive": OWNER_DIRECTIVE,
            "directive_digest": _digest({"directive": OWNER_DIRECTIVE}),
            "independent_human_approval_required": False,
            "basis": (
                "explicit repository-owner instruction; this is a governance authorization, not "
                "scientific outcome evidence"
            ),
        },
        "supersedes_without_modification": {
            "protocol_drafts_v2": {
                "path": str(V2_OUTPUT.relative_to(ROOT)),
                "sha256": hashlib.sha256(V2_OUTPUT.read_bytes()).hexdigest(),
                "artifact_digest": v2["artifact_digest"],
                "status": "SUPERSEDED_BY_MB4_2_OWNER_PROTOCOL_FREEZE_V1",
            },
            "human_review_template_v2": {
                "path": str(V2_REVIEW_TEMPLATE.relative_to(ROOT)),
                "sha256": hashlib.sha256(V2_REVIEW_TEMPLATE.read_bytes()).hexdigest(),
                "template_digest": review["template_digest"],
                "status": "RETAINED_HISTORICAL_NOT_REQUIRED_BY_CURRENT_GATE",
            },
        },
        "canonical_method_ids": list(CANONICAL_METHOD_IDS),
        "legacy_queue_method_id_mapping": dict(LEGACY_QUEUE_METHOD_IDS),
        "protocols": protocols,
        "protocol_digests": {
            method_id: protocol["protocol_digest"]
            for method_id, protocol in protocols.items()
        },
        "development_queue": _queue_state(),
        "molecular_candidate_energy_executed": False,
        "H2_H4_queue_created": False,
        "outcomes_inspected_for_freeze": False,
        "authorization": {
            "MB5_outcome_free_executor_implementation": "AUTHORIZED",
            "MB6_queue_freeze": "NOT_AUTHORIZED_UNTIL_MB5_AUDIT",
            "molecular_candidate_energy": "NOT_AUTHORIZED",
            "H2_H4_execution": "NOT_AUTHORIZED",
            "development_queue_execution": "NOT_AUTHORIZED",
            "six_production_molecular_executors": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "academic_boundary": (
            "The protocol wording and names are frozen before any new outcome. No molecular result "
            "or performance evidence is created by this artifact."
        ),
        "systems_boundary": (
            "Only MB5 outcome-free executor implementation is opened. All queue and molecular "
            "execution paths remain fail-closed."
        ),
    }
    result["freeze_digest"] = _digest(result)
    return result


def _observed_repository_owner() -> str:
    completed = subprocess.run(
        ["gh", "repo", "view", REPOSITORY, "--json", "owner", "--jq", ".owner.login"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return completed.stdout.strip()


def audit() -> dict[str, bool]:
    committed = json.loads(OUTPUT.read_text())
    rebuilt = build()
    v2_record = committed["supersedes_without_modification"]["protocol_drafts_v2"]
    review_record = committed["supersedes_without_modification"]["human_review_template_v2"]
    checks = {
        "prior_v2_still_valid": all(audit_v2().values()),
        "deterministic_rebuild": committed == rebuilt,
        "freeze_digest": committed["freeze_digest"]
        == _digest({key: value for key, value in committed.items() if key != "freeze_digest"}),
        "repository_owner_matches": _observed_repository_owner() == REPOSITORY_OWNER,
        "owner_directive_bound": committed["governance"]["directive_digest"]
        == _digest({"directive": OWNER_DIRECTIVE}),
        "independent_human_not_required": committed["governance"]
        ["independent_human_approval_required"]
        is False,
        "v2_artifact_unchanged": hashlib.sha256(V2_OUTPUT.read_bytes()).hexdigest()
        == v2_record["sha256"],
        "review_template_unchanged": hashlib.sha256(V2_REVIEW_TEMPLATE.read_bytes()).hexdigest()
        == review_record["sha256"],
        "six_canonical_methods": tuple(committed["canonical_method_ids"])
        == CANONICAL_METHOD_IDS,
        "rename_is_exact": committed["protocols"]
        ["v5-fixed-source-whitelist-no-replenishment"]["renaming"]["new_name"]
        == "V5 fixed-source-whitelist / no-replenishment",
        "legacy_id_is_alias_only": committed["legacy_queue_method_id_mapping"]
        ["v5-fixed-source-whitelist-no-replenishment"]
        == "v5-sequential-without-rebuilding",
        "all_protocols_frozen": all(
            protocol["freeze_status"]
            == "FROZEN_OUTCOME_BLIND_BY_REPOSITORY_OWNER_DIRECTIVE"
            for protocol in committed["protocols"].values()
        ),
        "no_outcomes": committed["outcomes_inspected_for_freeze"] is False
        and committed["molecular_candidate_energy_executed"] is False,
        "queue_untouched": committed["development_queue"]
        == {
            "expected_count": 90,
            "not_started_count": 90,
            "completed_count": 0,
            "segment_count": 0,
            "candidate_energy_evaluations": 0,
        },
        "only_mb5_open": committed["authorization"]
        == {
            "MB5_outcome_free_executor_implementation": "AUTHORIZED",
            "MB6_queue_freeze": "NOT_AUTHORIZED_UNTIL_MB5_AUDIT",
            "molecular_candidate_energy": "NOT_AUTHORIZED",
            "H2_H4_execution": "NOT_AUTHORIZED",
            "development_queue_execution": "NOT_AUTHORIZED",
            "six_production_molecular_executors": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
    }
    if not all(checks.values()):
        raise RuntimeError("MB4.2 repository-owner protocol freeze audit failed")
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

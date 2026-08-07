from __future__ import annotations

import hashlib
import json

from v5_final.mb4_2_owner_protocol_freeze import (
    OUTPUT,
    V2_OUTPUT,
    V2_REVIEW_TEMPLATE,
    audit,
    build,
)


def test_owner_directive_replaces_human_gate_without_rewriting_history() -> None:
    artifact = build()
    assert artifact["governance"]["independent_human_approval_required"] is False
    assert artifact["decision"] == "GO_MB5_OUTCOME_FREE_EXECUTOR_IMPLEMENTATION_ONLY"
    assert artifact["supersedes_without_modification"]["protocol_drafts_v2"][
        "sha256"
    ] == hashlib.sha256(V2_OUTPUT.read_bytes()).hexdigest()
    assert artifact["supersedes_without_modification"]["human_review_template_v2"][
        "sha256"
    ] == hashlib.sha256(V2_REVIEW_TEMPLATE.read_bytes()).hexdigest()
    assert json.loads(V2_OUTPUT.read_text())["status"] == (
        "NO_GO_AWAITING_INDEPENDENT_HUMAN_PROTOCOL_APPROVAL"
    )


def test_fixed_source_whitelist_name_and_legacy_alias_are_exact() -> None:
    artifact = build()
    protocol = artifact["protocols"]["v5-fixed-source-whitelist-no-replenishment"]
    assert protocol["display_name"] == "V5 fixed-source-whitelist / no-replenishment"
    assert protocol["renaming"]["legacy_queue_method_id"] == (
        "v5-sequential-without-rebuilding"
    )
    assert protocol["renaming"]["legacy_id_status"] == (
        "IMMUTABLE_COMPATIBILITY_ALIAS_ONLY"
    )
    assert "source structural candidate-ID whitelist only" in protocol["source_freeze"]
    assert "source ordering is not frozen" in protocol["ordering_rule"]


def test_owner_freeze_is_outcome_blind_and_opens_only_mb5() -> None:
    artifact = build()
    assert artifact["outcomes_inspected_for_freeze"] is False
    assert artifact["molecular_candidate_energy_executed"] is False
    assert artifact["H2_H4_queue_created"] is False
    assert artifact["development_queue"] == {
        "expected_count": 90,
        "not_started_count": 90,
        "completed_count": 0,
        "segment_count": 0,
        "candidate_energy_evaluations": 0,
    }
    assert artifact["authorization"]["MB5_outcome_free_executor_implementation"] == (
        "AUTHORIZED"
    )
    assert all(
        value == "NOT_AUTHORIZED"
        for key, value in artifact["authorization"].items()
        if key
        not in {
            "MB5_outcome_free_executor_implementation",
            "MB6_queue_freeze",
        }
    )
    assert OUTPUT.name == "mb4-2-owner-protocol-freeze-v1.json"
    assert all(audit().values())

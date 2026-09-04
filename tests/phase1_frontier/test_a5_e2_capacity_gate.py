from __future__ import annotations

import json

from phase1_frontier.a5_e2_capacity_gate import (
    AUDIT_PATH,
    CAPACITY_PATH,
    E2_PATH,
    audit,
)


def test_final_E2_numerical_certification_is_valid_and_repeatable() -> None:
    value = json.loads(E2_PATH.read_text(encoding="utf-8"))
    assert value["status"] == "VALID"
    assert all(value["checks"].values())
    assert [row["target_class"] for row in value["first_run"]] == [
        "singleton",
        "joint-K2",
    ]
    assert all(len(row["starts"]) == 2 for row in value["first_run"])
    assert all(
        start["valid"]
        for row in value["first_run"]
        for start in row["starts"]
    )
    assert value["E3_candidate_energy_evaluations"] == 0
    assert value["FCI_evaluations"] == 0


def test_capacity_gate_preserves_complete_language_and_fails_closed() -> None:
    value = json.loads(CAPACITY_PATH.read_text(encoding="utf-8"))
    assert value["decision"] == "NO_GO_A5_E2_OR_QUEUE_INVALID"
    assert value["reason_code"] == "E3_EXHAUSTIVE_CAPACITY_UNPROVEN"
    assert value["total_E3_targets"] == 88_148
    assert value["requested_optimizer_starts"] == 176_296
    assert value["queue_created"] is False
    assert value["queue_freeze_authorized"] is False
    assert value["E3_candidate_energy_evaluations"] == 0
    assert value["E3_optimizer_starts"] == 0
    assert value["FCI_evaluations"] == 0
    assert "post-hoc Top-K or energy ranking" in value["forbidden_remediations"]


def test_A5_terminal_audit_is_persisted_and_reconstructible() -> None:
    persisted = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
    reconstructed = audit()
    assert persisted == reconstructed
    assert persisted["passed"] is True
    assert all(persisted["checks"].values())

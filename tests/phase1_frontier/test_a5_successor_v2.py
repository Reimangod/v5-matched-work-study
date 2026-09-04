from __future__ import annotations

import json

from phase1_frontier.a5_successor_v2 import (
    AUDIT_PATH,
    DESIGN_PATH,
    QUEUE_PATH,
    STARTS,
    audit,
    build_design,
)


def test_v2_design_reconstructs_and_preserves_claim_boundary() -> None:
    frozen = json.loads(DESIGN_PATH.read_text(encoding="utf-8"))
    assert build_design() == frozen
    assert frozen["counts"] == {
        "full_registered_joints": 87_399,
        "strict_dominance_eligible_joints": 34_245,
        "complete_primary_CNOT_singletons": 485,
        "screen_joints": 148,
        "screen_targets": 633,
        "two_start_requests": 1_266,
    }
    assert frozen["interpretation"]["population_frontier_claim"] is False
    assert frozen["candidate_energy_evaluations"] == 0
    assert frozen["optimizer_starts"] == 0
    assert frozen["FCI_evaluations"] == 0


def test_v2_queue_is_unique_complete_and_not_started() -> None:
    queue = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
    assert queue["status"] == "FROZEN_NOT_STARTED"
    assert queue["counts"]["requests"] == 1_266
    assert queue["counts"]["targets"] == 633
    assert queue["counts"]["NOT_STARTED"] == 1_266
    assert queue["counts"]["candidate_energy_evaluations"] == 0
    assert queue["counts"]["optimizer_starts"] == 0
    assert queue["counts"]["FCI_evaluations"] == 0
    assert len({row["RequestID"] for row in queue["items"]}) == 1_266
    by_target: dict[str, set[str]] = {}
    for row in queue["items"]:
        by_target.setdefault(row["CandidatePlanID"], set()).add(row["start"])
        assert row["status"] == "NOT_STARTED"
        assert row["initial_inverse_hessian_policy"] == (
            "identity-target-dimension-v1"
        )
        assert len(row["initial_coordinates_float64"]) == row[
            "target_parameter_count"
        ]
    assert len(by_target) == 633
    assert all(starts == set(STARTS) for starts in by_target.values())


def test_v2_freeze_audit_is_persisted_and_reconstructible() -> None:
    persisted = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
    assert persisted == audit()
    assert persisted["passed"] is True
    assert persisted["decision"] == "GO_PHASE1_V2_SCREEN_RUNNER_IMPLEMENTATION"


from __future__ import annotations

import json

from phase1_frontier.a2_source_lock import CASES
from phase1_frontier.a4_structural_census import (
    CAP_PATH,
    FACTORIZED_CERT_PATH,
    A4_ROOT,
    STRUCTURAL_CAP,
    audit,
    census_path,
)


def test_A4_complete_double_census_is_valid_and_outcome_free() -> None:
    result = audit()
    assert result["passed"] is True
    assert result["complete"] is True
    assert result["decision"] == "GO_A5_E2_CERTIFICATION_AND_QUEUE_FREEZE"
    assert result["joint_only_resource_signal_exists"] is True
    for case_id in CASES:
        assert result["cases"][case_id]["status"] == "VALID"
        assert result["cases"][case_id]["byte_identical_identity_payload"] is True


def test_A4_cap_admits_complete_universe_without_outcomes() -> None:
    value = json.loads(CAP_PATH.read_text(encoding="utf-8"))
    assert value["cap_unique_StructuralTargetID"] == STRUCTURAL_CAP
    assert value["total_unique_StructuralTargetID"] == 88_148
    assert value["within_cap"] is True
    assert value["candidate_energy_evaluations"] == 0
    assert value["optimizer_starts"] == 0
    assert value["FCI_evaluations"] == 0


def test_factorized_counter_failed_closed_then_passed_full_parity() -> None:
    failed = json.loads(
        (A4_ROOT / "a4-factorized-counter-certification-v1.json").read_text(
            encoding="utf-8"
        )
    )
    passed = json.loads(FACTORIZED_CERT_PATH.read_text(encoding="utf-8"))
    assert failed["passed"] is False
    assert passed["passed"] is True
    assert passed["candidate_energy_evaluations"] == 0
    assert passed["optimizer_starts"] == 0
    assert passed["FCI_evaluations"] == 0
    assert sum(
        case["canonical_target_parity_count"] for case in passed["checks"].values()
    ) == 1_779
    assert all(case["status"] == "VALID" for case in passed["checks"].values())


def test_primary_signal_is_exactly_canonical_CNOT_reduction() -> None:
    expected = {
        "lih-3.0": (75, 60),
        "beh2-3.0": (1_026, 918),
        "h6-1.5": (40_946, 34_783),
        "h6-3.0": (46_101, 39_454),
    }
    for case_id, (target_count, joint_positive) in expected.items():
        value = json.loads(census_path(case_id, 1).read_text(encoding="utf-8"))
        assert value["unique_structural_target_count"] == target_count
        assert value["joint_only_resource_positive_count"] == joint_positive
        assert value["candidate_energy_evaluations"] == 0
        assert value["optimizer_starts"] == 0
        assert value["FCI_evaluations"] == 0
        assert all(
            row["primary_CNOT_resource_positive"]
            == (row["resource_delta_from_B2"]["cnot_count"] < 0)
            for row in value["rows"]
        )
        assert all("resource_positive" not in row for row in value["rows"])


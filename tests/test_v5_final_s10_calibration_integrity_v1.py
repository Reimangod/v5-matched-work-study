from __future__ import annotations

import pytest


pytest.importorskip("numpy")

from v5_final.s10_calibration_integrity_v1 import OUTPUT, audit, build


def test_s10_reconstructs_complete_negative_calibration() -> None:
    artifact = build()
    assert all(artifact["checks"].values())
    assert artifact["S9_v6"]["completed_terminal_count"] == 36
    assert artifact["S9_v6"]["candidate_molecular_energy_evaluations"] == 84
    assert artifact["scientific_result"] == {
        "classification": "CALIBRATION_NEGATIVE_RESULT_NO_COMPRESSION_ACCEPTED",
        "accepted_structural_candidate_count": 0,
        "accepted_noncompression_control_identifier_count": 6,
        "resource_reduction_result_count": 0,
        "algorithmic_negative_terminal_count": 24,
        "infrastructure_failure_count": 0,
        "interpretation": (
            "The frozen H2/H4 calibration produced no accepted compression and no "
            "resource reduction. This negative calibration is retained in full. It "
            "does not establish superiority, equivalence, or generalization."
        ),
    }


def test_s10_authorizes_only_outcome_blind_successor_freeze() -> None:
    artifact = build()
    assert artifact["decision"] == "GO_90_ITEM_EXECUTION_BINDING_FREEZE_ONLY"
    assert artifact["authorization"][
        "S11_outcome_blind_90_item_successor_freeze"
    ] == "AUTHORIZED"
    assert artifact["authorization"]["existing_90_item_queue_execution"] == (
        "NOT_AUTHORIZED"
    )
    assert artifact["authorization"]["performance_claim"] == "NOT_AUTHORIZED"
    assert artifact["development_successor_contract"][
        "calibration_selects_or_drops_methods"
    ] is False


def test_s10_uses_fci_for_reporting_only_and_non_scalar_pareto() -> None:
    artifact = build()
    assert artifact["FCI_reporting_reference"][
        "used_during_candidate_selection_or_execution"
    ] is False
    assert artifact["FCI_reporting_reference"][
        "used_for_post_execution_absolute_error_reporting_only"
    ] is True
    assert artifact["matched_work_interpretation"][
        "weighted_scalar_winner_selected"
    ] is False
    assert len(artifact["non_scalar_pareto_by_context"]) == 6


def test_s10_frozen_artifact_is_valid_if_present() -> None:
    if OUTPUT.exists():
        assert all(audit().values())

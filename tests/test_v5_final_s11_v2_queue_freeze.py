from __future__ import annotations

from v5_final.s11_v2_queue_freeze import audit, build_queue, build_recalibration


def test_p6_frozen_artifacts_rebuild_exactly() -> None:
    result = audit()
    assert result["status"] == "PASS_P6_S11_V2_QUEUE_FROZEN_NOT_AUTHORIZED"
    assert all(result["checks"].values())


def test_queue_is_fresh_factorial_and_outcome_blocked() -> None:
    queue = build_queue(build_recalibration())
    assert queue["frozen_item_count"] == 90
    assert len({item["queue_item_id"] for item in queue["items"]}) == 90
    assert all(item["terminal_status"] == "NOT_STARTED" for item in queue["items"])
    assert all(item["authorization"].startswith("NOT_AUTHORIZED") for item in queue["items"])
    assert all(item["verifier_componentwise_cap"]["N_dense_expm"] == 0 for item in queue["items"])
    assert all(item["outcome_work_cap"]["energy_evaluations"] is None for item in queue["items"])
    assert queue["old_s11_v1_queue"]["completed_results_copied"] == 0


def test_recalibration_does_not_infer_outcome_caps_from_zero_observations() -> None:
    calibration = build_recalibration()
    assert calibration["candidate_energy_evaluations"] == 0
    assert calibration["FCI_evaluations"] == 0
    assert calibration["performance_outcomes_used"] is False
    assert calibration["outcome_work_cap"]["optimizer_iterations"] is None
    assert calibration["outcome_work_cap"]["energy_evaluations"] is None
    assert calibration["outcome_work_cap"]["zero_calibration_not_misrepresented_as_zero_cap"] is True

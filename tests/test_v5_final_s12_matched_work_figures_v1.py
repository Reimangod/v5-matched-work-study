from v5_final.s12_matched_work_figures_v1 import (
    FIGURE_STEMS,
    build_progression_data,
)


def test_progression_preserves_all_recorded_attempts_and_energy_events() -> None:
    value = build_progression_data()
    assert value["schema"] == "v5-final.s12-trial-work-progression.v1"
    assert len(value["attempts"]) > 50
    assert len(value["energy_events"]) > 1000
    assert all(record["record_type"] == "attempt" for record in value["attempts"])
    assert all(record["record_type"] == "energy_event" for record in value["energy_events"])


def test_progression_retains_rejected_trials_and_does_not_claim_dense_resources() -> None:
    value = build_progression_data()
    assert any(record["terminal_status"] == "ALGORITHM_REJECTED" for record in value["attempts"])
    assert "attempt boundaries" in value["semantics"]["resource_trajectory_limit"]
    assert "do not contain an ADAPT growth trajectory" in value["semantics"]["missing_source_trajectories"]


def test_figure_plan_has_required_status_resource_work_pareto_and_correspondence() -> None:
    assert len(FIGURE_STEMS) == 12
    assert "status-matrix" in FIGURE_STEMS
    assert "paired-resource-reductions" in FIGURE_STEMS
    assert "registered-work-vs-energy-error" in FIGURE_STEMS
    assert "registered-work-vs-cnot" in FIGURE_STEMS
    assert "pareto-fronts" in FIGURE_STEMS
    assert all(f"fig{number}-matched-work-correspondence" in FIGURE_STEMS for number in (11, 14, 15))

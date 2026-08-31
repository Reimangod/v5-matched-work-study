from __future__ import annotations

from aic_a100_pilot.common import embedded_digest_valid, load_json
from aic_a100_pilot.decision_gate import DECISION_V3
from aic_a100_pilot.p3_objective_report import REPORT


def test_objective_report_stops_at_first_registered_scientific_failure():
    value = load_json(REPORT)
    assert embedded_digest_valid(value, "report_digest")
    assert value["status"] == "NO_GO_A100_NUMERICAL_NONPARITY"
    assert value["executed_prefix"] == ["h2", "h4", "lih"]
    assert value["unexecuted_after_first_scientific_failure"] == ["h6", "beh2"]
    assert value["terminal_failure"]["failed_registered_checks"] == [
        "gradient",
        "state",
    ]
    assert value["terminal_failure"]["phase_aligned_state_error"] > value[
        "terminal_failure"
    ]["state_error_threshold"]
    assert value["terminal_failure"]["max_gradient_component_error"] > value[
        "terminal_failure"
    ]["gradient_error_threshold"]
    assert value["terminal_failure"]["energy_error_hartree"] <= value[
        "terminal_failure"
    ]["energy_error_threshold_hartree"]
    assert value["work_disclosure"]["FCI_evaluations"] == 0


def test_p6_v3_is_terminal_and_protects_matched_work():
    value = load_json(DECISION_V3)
    assert embedded_digest_valid(value, "decision_digest")
    assert value["status"] == "NO_GO_A100_NUMERICAL_NONPARITY"
    assert value["phase_status"]["P4_COMPLETE_ITEM_END_TO_END"] == (
        "NOT_EXECUTED_NOT_AUTHORIZED"
    )
    assert value["phase_status"]["P5_LIMITED_SCIENTIFIC_PILOT"] == (
        "NOT_EXECUTED_NOT_AUTHORIZED"
    )
    assert value["protected_scientific_artifacts"]["unchanged"] is True
    assert value["scientific_boundaries"]["FCI_evaluations"] == 0
    assert value["scientific_boundaries"]["full_90_item_rerun"] == "NOT_EXECUTED"

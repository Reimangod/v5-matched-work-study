from __future__ import annotations

from aic_a100_pilot.common import embedded_digest_valid, load_json
from aic_a100_pilot.unified_route_terminal_decision import DECISION, decision_body


def test_unified_route_terminal_decision_stops_after_h4_failure():
    value = load_json(DECISION)
    assert embedded_digest_valid(value, "decision_digest")
    assert value["status"] == "NO_GO_A100_UNIFIED_ROUTE_H4_TRAJECTORY_NONPARITY"
    assert value["executed_prefix"] == ["h2", "h4"]
    assert value["case_evidence"]["h2"]["status"] == "PASS"
    assert value["case_evidence"]["h4"]["status"] == "FAIL"
    assert set(value["terminal_failure"]["failed_registered_checks"]) == {
        "operation_kind_and_stencil_order",
        "optimizer_terminal_counts_and_status",
        "terminal_gradient",
        "terminal_state",
        "trajectory_iteration_parity",
        "trajectory_length",
    }
    observed = value["terminal_failure"]["observed"]
    assert observed["trajectory_length_cpu"] == 6
    assert observed["trajectory_length_gpu"] == 5
    assert observed["gradient_max_abs"] > 1e-8
    assert observed["phase_aligned_state_max_abs"] > 1e-10
    assert value["terminal_failure"]["energy_decision_and_resources_still_matched"]
    assert value["stopped_by_frozen_gate"]["unexecuted_cases"] == [
        "lih",
        "h6",
        "beh2",
    ]
    assert value["scientific_boundaries"]["FCI_evaluations"] == 0
    assert value["scientific_boundaries"]["post_outcome_tolerance_change"] is False
    assert value["immutable_historical_hybrid_no_go"]["modified"] is False
    assert decision_body()["status"] == value["status"]

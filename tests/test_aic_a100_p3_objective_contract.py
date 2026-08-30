from __future__ import annotations

from aic_a100_pilot.common import embedded_digest_valid, load_json
from aic_a100_pilot.p3_objective_contract import CONTRACT


def test_objective_contract_is_bounded_and_uses_frozen_candidates():
    value = load_json(CONTRACT)
    assert embedded_digest_valid(value, "contract_digest")
    assert value["status"] == "GO_BOUNDED_P3_OBJECTIVE_AND_DECISION_PARITY"
    assert value["frozen_before_new_GPU_candidate_outcomes"] is True
    selection = value["selection_policy"]
    assert selection["candidate_count"] == 5
    assert len({case["candidate_id"] for case in selection["cases"]}) == 5
    assert {case["frozen_CPU_terminal_decision"] for case in selection["cases"]} == {
        "ACCEPTED",
        "REJECTED",
    }
    assert value["optimizer_binding"]["CPU_fallback_allowed"] is False
    assert value["scientific_boundary"]["FCI_evaluations"] == 0
    assert value["scientific_boundary"]["P5_limited_scientific_pilot"] == (
        "NOT_AUTHORIZED"
    )

from __future__ import annotations

from aic_a100_pilot.common import embedded_digest_valid, load_json
from aic_a100_pilot.p4_contract import CONTRACT


def test_p4_contract_is_outcome_blind_and_fail_closed():
    value = load_json(CONTRACT)
    assert embedded_digest_valid(value, "contract_digest")
    assert value["status"] == "GO_P4_EXECUTION"
    assert value["frozen_before_timing_outcomes"] is True
    assert value["decision_rule"]["current_case_rule"] == (
        "EVERY_CURRENT_CASE_MUST_MEET_MINIMUM"
    )
    assert value["decision_rule"]["minimum_speedup_cpu_over_gpu"] == 1.2
    assert value["synthetic_diagnostics"]["can_override_current_case_failure"] is False
    assert value["scientific_boundary"]["candidate_molecular_energy_evaluations"] == 0
    assert value["scientific_boundary"]["optimizer_runs"] == 0
    assert value["scientific_boundary"]["FCI_evaluations"] == 0

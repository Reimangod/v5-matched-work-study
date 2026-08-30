from __future__ import annotations

from aic_a100_pilot.common import embedded_digest_valid, load_json
from aic_a100_pilot.p4_report import REPORT


def test_p4_report_applies_frozen_every_case_rule():
    value = load_json(REPORT)
    assert embedded_digest_valid(value, "report_digest")
    assert len(value["current_system_results"]) == 5
    assert len(value["synthetic_diagnostic_results"]) == 3
    assert value["status"] == "GO_P3_PRODUCTION_OBJECTIVE_BINDING_AND_DECISION_PARITY"
    assert value["decision"]["measurement_scope"] == "SOURCE_ROUTE_DIAGNOSTIC_ONLY"
    assert value["decision"]["production_target_aliases"] == [
        "h4",
        "lih",
        "h6",
        "beh2",
    ]
    assert value["decision"]["H2_role"] == (
        "POSITIVE_CONTROL_AND_LAUNCH_OVERHEAD_DIAGNOSTIC"
    )
    assert value["decision"]["production_adoption_decision_authorized"] is False
    assert value["decision"]["synthetic_can_override_current_failure"] is False
    assert value["scientific_boundary"]["candidate_molecular_energy_evaluations"] == 0
    assert value["scientific_boundary"]["optimizer_runs"] == 0
    assert value["scientific_boundary"]["FCI_evaluations"] == 0

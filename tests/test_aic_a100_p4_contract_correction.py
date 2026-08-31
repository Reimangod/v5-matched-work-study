from __future__ import annotations

from aic_a100_pilot.common import embedded_digest_valid, load_json
from aic_a100_pilot.p4_contract_correction import CORRECTION


def test_p4_contract_correction_restores_primary_plan_boundaries():
    value = load_json(CORRECTION)
    assert embedded_digest_valid(value, "correction_digest")
    assert value["corrected_interpretation"]["production_target_aliases"] == [
        "h4",
        "lih",
        "h6",
        "beh2",
    ]
    assert value["corrected_interpretation"][
        "positive_control_not_in_production_speed_gate"
    ] == ["h2"]
    assert value["corrected_interpretation"]["threshold_changed"] is False
    assert value["successor_authorization"][
        "P4_complete_item_end_to_end_gate"
    ] == "NOT_AUTHORIZED_PENDING_PARITY"
    assert value["scientific_boundary"]["candidate_molecular_energy_evaluations"] == 0

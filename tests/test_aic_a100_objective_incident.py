from __future__ import annotations

from aic_a100_pilot.common import embedded_digest_valid, load_json
from aic_a100_pilot.objective_incident import INCIDENT


def test_h2_retry_is_narrow_and_does_not_hide_computed_work():
    value = load_json(INCIDENT)
    assert embedded_digest_valid(value, "incident_digest")
    assert value["status"] == "RETRY_AUTHORIZED_SAME_FROZEN_H2_ONLY"
    assert value["work_disclosure"]["paired_CPU_candidate_computation_reached"] is True
    assert value["work_disclosure"]["GPU_candidate_computation_reached"] is True
    assert value["work_disclosure"]["candidate_outcome_records_persisted"] == 0
    assert value["remediation"]["same_item_retry_only"] == "h2"
    assert value["successor_authorization"]["h4_and_later"].startswith(
        "NOT_AUTHORIZED"
    )

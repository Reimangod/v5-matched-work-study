from __future__ import annotations

import json

from v5_final.p0_capacity_success_v3 import OUTPUT, audit, verify


def test_capacity_v3_preserves_exact_zero_outcome_resume() -> None:
    record = json.loads(OUTPUT.read_text())
    assert record["decision"] == "GO_PARENT_NATIVE_INFRASTRUCTURE_IMPLEMENTATION_ONLY"
    assert record["release_baseline"]["tag"] == "v5-matched-work-infrastructure-no-go-v2"
    assert record["queue_state"]["H2_H4"]["candidate_energy"] == 0
    assert record["queue_state"]["development"]["candidate_energy"] == 0
    assert all(verify(record).values())
    assert all(audit().values())


def test_capacity_v3_does_not_authorize_molecular_execution() -> None:
    record = json.loads(OUTPUT.read_text())
    assert record["authorization"] == {
        "outcome_free_infrastructure_implementation": "AUTHORIZED",
        "molecular_candidate_energy": "NOT_AUTHORIZED",
        "H2_H4_execution": "NOT_AUTHORIZED",
        "development_queue_execution": "NOT_AUTHORIZED",
        "performance_claim": "NOT_AUTHORIZED",
    }

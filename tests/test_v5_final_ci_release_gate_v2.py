from __future__ import annotations

from v5_final.ci_release_gate_v2 import audit


def test_latest_gate_emits_v2_successor_and_keeps_outcomes_closed() -> None:
    result = audit()
    assert result["status"] == "PASS_V2_SUCCESSOR_INFRASTRUCTURE_ONLY"
    assert result["decision"] == "NO_GO_V5_MATCHED_WORK_INFRASTRUCTURE_V2"
    assert all(result["checks"].values())
    assert result["queue_state"] == {
        "H2_H4": {"expected": 36, "terminal": 0, "candidate_energy": 0},
        "development": {"expected": 90, "terminal": 0, "candidate_energy": 0},
    }
    assert result["authorization"]["molecular_candidate_energy"] == "NOT_AUTHORIZED"
    assert result["authorization"]["H2_H4_execution"] == "NOT_AUTHORIZED"

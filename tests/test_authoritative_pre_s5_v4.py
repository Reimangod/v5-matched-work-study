from v5_matched_work.authoritative_pre_s5_v4 import build, not_authorized


def test_v4_gate_keeps_pre_s5_zero_separate_from_production_chain() -> None:
    gate = build()
    assert gate["decision"] == "NO_GO_BEFORE_S5_V4"
    assert gate["pre_s5_candidate_energy_evaluations"] == 0
    assert gate["production_candidate_energy_evaluations"] is None
    assert "actual_frozen_queue_binding_available" in gate["failed_checks"]
    assert "production_candidate_energy_reconstructed_from_v4_chain" in gate["failed_checks"]
    assert not_authorized(5, gate)["status"] == "NOT_AUTHORIZED"

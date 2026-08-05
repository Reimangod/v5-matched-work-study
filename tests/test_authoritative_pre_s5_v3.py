from v5_matched_work.authoritative_pre_s5_v3 import build, not_authorized


def test_single_authoritative_gate_fails_before_s5_authorization() -> None:
    gate = build()
    assert gate["decision"] == "NO_GO_BEFORE_S5_V3"
    assert gate["s5_authorization_issued"] is False
    assert gate["checks"]["duplicates_do_not_increment_n_states"]
    assert "actual_kernel_events_available_for_cap_calibration" in gate["failed_checks"]
    assert not_authorized(5, gate)["status"] == "NOT_AUTHORIZED"

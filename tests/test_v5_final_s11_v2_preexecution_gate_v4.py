from v5_final.s11_v2_preexecution_gate_v4 import audit_frozen


def test_p7_v4_is_a_fail_closed_zero_outcome_no_go() -> None:
    result = audit_frozen()
    assert result["status"] == "PASS_FROZEN_P7_V4_NO_GO_AUDIT"
    assert all(result["checks"].values())

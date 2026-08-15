from __future__ import annotations

from v5_final.s11_v2_preexecution_gate import audit_frozen


def test_frozen_p7_gate_is_integral_fail_closed_and_outcome_free() -> None:
    result = audit_frozen()
    assert result["status"] == "PASS_FROZEN_P7_NO_GO_AUDIT"
    assert all(result["checks"].values())

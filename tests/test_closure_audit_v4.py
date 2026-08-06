from v5_matched_work.closure_audit_v4 import audit


def test_v4_closure_preserves_pre_s5_no_go() -> None:
    result = audit()
    assert result["passed"]
    assert result["checks"]["s5_v4_never_authorized"]
    assert result["checks"]["pre_s5_candidate_zero_and_production_unknown"]

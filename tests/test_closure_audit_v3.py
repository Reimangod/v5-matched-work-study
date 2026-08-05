from v5_matched_work.closure_audit_v3 import audit


def test_v3_closure_is_pre_s5_and_pre_performance() -> None:
    result = audit()
    assert result["passed"]
    assert result["checks"]["s5_v3_never_authorized"]
    assert result["checks"]["candidate_performance_zero"]

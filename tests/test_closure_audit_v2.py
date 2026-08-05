from v5_matched_work.closure_audit_v2 import audit


def test_closure_v2_reconstructs_historical_evidence() -> None:
    result = audit()
    assert result["passed"]
    assert result["checks"]["historical_486_hashes"]
    assert result["checks"]["historical_parent_tree"]
    assert result["checks"]["historical_ceo_submodule_commit"]

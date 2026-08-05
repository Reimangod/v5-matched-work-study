from v5_matched_work.evidence_v2 import verify_historical_evidence


def test_closure_recomputes_historical_hashes_and_git_identities() -> None:
    result = verify_historical_evidence()
    assert result["passed"]
    assert all(result["checks"].values())

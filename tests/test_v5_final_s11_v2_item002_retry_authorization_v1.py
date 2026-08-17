from v5_final.s11_v2_item002_retry_authorization_v1 import inspect_retry_readiness


def test_item002_retry_predicts_zero_outcome_cumulative_cap_rejection() -> None:
    evidence = inspect_retry_readiness()
    assert all(evidence["checks"].values())
    assert evidence["observed"]["candidate_energy_evaluations"] == 0
    assert evidence["observed"]["optimizer_starts"] == 0
    assert evidence["observed"]["FCI_evaluations"] == 0
    assert evidence["observed"]["N_dense_expm"] == 0
    assert evidence["observed"]["candidate_count"] == 15
    assert evidence["observed"]["predicted_cap_rejection_reason"].startswith(
        "verifier cap rejected before session:"
    )

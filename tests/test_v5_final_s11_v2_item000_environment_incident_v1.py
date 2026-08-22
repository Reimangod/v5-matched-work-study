from v5_final.s11_v2_item000_environment_incident_v1 import inspect_incident


def test_item000_incident_is_zero_outcome_and_blocks_continuation() -> None:
    evidence = inspect_incident()
    assert all(evidence["checks"].values())
    assert evidence["checks"]["item000_failed_before_candidate_outcome"] is True
    assert evidence["checks"]["FCI_and_dense_expm_zero"] is True

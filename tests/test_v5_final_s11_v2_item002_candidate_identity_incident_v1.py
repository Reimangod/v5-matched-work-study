from v5_final.s11_v2_item002_candidate_identity_incident_v1 import inspect_incident


def test_item002_identity_incident_is_pre_outcome_and_exactly_rolled_back() -> None:
    evidence = inspect_incident()
    assert all(evidence["checks"].values())
    assert evidence["observed"]["candidate_energy_evaluations"] == 0
    assert evidence["observed"]["optimizer_starts"] == 0
    assert evidence["observed"]["FCI_evaluations"] == 0
    assert evidence["observed"]["N_dense_expm"] == 0
    assert evidence["observed"]["selected_admitted_intersection_count"] == 0

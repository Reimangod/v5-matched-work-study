from v5_final.s11_v2_item002_candidate_identity_incident_v1 import (
    DECISION,
    OUTPUT,
    audit_frozen,
    _embedded_digest,
    _load,
)
from v5_final.historical_artifact_audit import artifact_is_immutable_git_blob


def test_item002_identity_incident_is_pre_outcome_and_exactly_rolled_back() -> None:
    artifact = _load(OUTPUT)
    assert artifact_is_immutable_git_blob(OUTPUT)
    assert _embedded_digest(artifact, "incident_digest")
    assert artifact["decision"] == DECISION
    assert all(artifact["checks"].values())
    assert artifact["observed"]["candidate_energy_evaluations"] == 0
    assert artifact["observed"]["optimizer_starts"] == 0
    assert artifact["observed"]["FCI_evaluations"] == 0
    assert artifact["observed"]["N_dense_expm"] == 0
    assert artifact["observed"]["selected_admitted_intersection_count"] == 0
    assert all(audit_frozen()["checks"].values())

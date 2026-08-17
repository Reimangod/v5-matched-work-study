from v5_final.historical_artifact_audit import artifact_is_immutable_git_blob
from v5_final.s11_v2_item022_symbolic_precheck_incident_v1 import (
    DECISION,
    OUTPUT,
    _embedded_digest,
    _load,
    audit_frozen,
    inspect_incident,
)


def test_item022_incident_reconstructs_nonconservative_symbolic_precheck() -> None:
    evidence = inspect_incident()
    assert all(evidence["checks"].values())
    assert evidence["observed"]["frozen_symbolic_precheck"] == 447
    assert evidence["observed"]["reconstructed_symbolic_work"] == 452
    assert evidence["observed"]["selected_symbolic_check_counts"] == [5, 5, 5, 10]
    assert evidence["observed"]["candidate_energy_evaluations"] == 0
    assert evidence["observed"]["optimizer_starts"] == 0
    assert evidence["observed"]["FCI_evaluations"] == 0
    assert evidence["observed"]["N_dense_expm"] == 0


def test_item022_incident_is_immutable_formal_no_go() -> None:
    artifact = _load(OUTPUT)
    assert artifact_is_immutable_git_blob(OUTPUT)
    assert _embedded_digest(artifact, "incident_digest")
    assert artifact["decision"] == DECISION
    assert all(artifact["checks"].values())
    assert artifact["disposition"]["item022_retry"].startswith("NOT_AUTHORIZED")
    assert artifact["disposition"]["item023_and_later"].startswith("NOT_AUTHORIZED")
    assert all(audit_frozen()["checks"].values())

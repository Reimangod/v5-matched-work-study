from dataclasses import fields

from dvg_obs_ceo.block_ir import CompressionCandidate

from v5_final.s11_v2_item023_relation_metadata_incident_v1 import (
    DECISION,
    OUTPUT,
    _embedded_digest,
    _load,
    audit_frozen,
    inspect_incident,
)
from v5_final.s11_v2_item022_terminal_reconciliation_v1 import (
    historical_artifact_valid,
)
from v5_final.s11_v2_item023_terminal_reconciliation_v1 import (
    OUTPUT as TERMINAL_RECONCILIATION,
    RECEIPT as ITEM023_RECEIPT,
    audit_frozen as audit_terminal_reconciliation,
)


def test_item023_incident_reconstructs_complete_rollback() -> None:
    if ITEM023_RECEIPT.exists():
        artifact = _load(OUTPUT)
        assert historical_artifact_valid(
            OUTPUT,
            artifact,
            digest_field="incident_digest",
            decision=DECISION,
        )
        observed = artifact["observed"]
    else:
        evidence = inspect_incident()
        assert all(evidence["checks"].values())
        observed = evidence["observed"]
    assert observed["terminal_prefix"] == 23
    assert observed["rollback_reason"] == "RelationAwareSymbolicPrecheckError"
    assert observed["raw_work_total"]["resource_recounts"] == 1
    assert observed["raw_work_total"]["statevector_recomputations"] == 1
    assert observed["candidate_energy_evaluations"] == 0
    assert observed["optimizer_starts"] == 0
    assert observed["FCI_evaluations"] == 0
    assert observed["N_dense_expm"] == 0


def test_actual_parent_relation_has_nested_jacobian_shape() -> None:
    names = {field.name for field in fields(CompressionCandidate)}
    assert "transformation" in names
    assert "jacobian" not in names


def test_item023_incident_artifact_or_precapture_state_is_valid() -> None:
    if TERMINAL_RECONCILIATION.exists():
        artifact = _load(OUTPUT)
        assert historical_artifact_valid(
            OUTPUT,
            artifact,
            digest_field="incident_digest",
            decision=DECISION,
        )
        assert all(audit_terminal_reconciliation()["checks"].values())
    elif ITEM023_RECEIPT.exists():
        artifact = _load(OUTPUT)
        assert historical_artifact_valid(
            OUTPUT,
            artifact,
            digest_field="incident_digest",
            decision=DECISION,
        )
    elif OUTPUT.exists():
        artifact = _load(OUTPUT)
        assert artifact["decision"] == DECISION
        assert _embedded_digest(artifact, "incident_digest")
        assert all(audit_frozen()["checks"].values())
    else:
        assert all(inspect_incident()["checks"].values())

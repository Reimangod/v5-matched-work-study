from v5_final.s11_v2_item028_relation_work_precheck_incident_v1 import (
    DECISION,
    OUTPUT,
    _embedded_digest,
    _load,
    inspect_incident,
)
from v5_final.s11_v2_item022_terminal_reconciliation_v1 import (
    historical_artifact_valid,
)


def test_item028_incident_reconstructs_relation_work_underestimate() -> None:
    if OUTPUT.exists():
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
    assert observed["terminal_prefix"] == 28
    assert observed["selected_total_generator_arities"] == [3, 3, 3, 5]
    assert observed["probe_count"] == 3
    assert observed["fixed_arity_sparse_upper_bound"] == 36
    assert observed["reconstructed_sparse_expm_work"] == 42
    assert observed["candidate_energy_evaluations"] == 0
    assert observed["optimizer_starts"] == 0
    assert observed["FCI_evaluations"] == 0
    assert observed["N_dense_expm"] == 0


def test_item028_incident_artifact_or_precapture_state_is_valid() -> None:
    if OUTPUT.exists():
        artifact = _load(OUTPUT)
        assert historical_artifact_valid(
            OUTPUT,
            artifact,
            digest_field="incident_digest",
            decision=DECISION,
        )
    else:
        assert all(inspect_incident()["checks"].values())

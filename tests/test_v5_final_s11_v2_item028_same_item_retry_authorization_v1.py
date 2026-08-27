from v5_final.s11_v2_item028_same_item_retry_authorization_v1 import (
    DECISION,
    OUTPUT,
    _embedded_digest,
    _load,
    inspect_retry_readiness,
)
from v5_final.s11_v2_item022_terminal_reconciliation_v1 import (
    historical_artifact_valid,
)


def test_item028_retry_is_general_outcome_free_and_within_unchanged_cap() -> None:
    if OUTPUT.exists():
        artifact = _load(OUTPUT)
        assert historical_artifact_valid(
            OUTPUT,
            artifact,
            digest_field="authorization_digest",
            decision=DECISION,
        )
        observed = artifact["observed"]
    else:
        evidence = inspect_retry_readiness()
        assert all(evidence["checks"].values())
        observed = evidence["observed"]
    assert observed["previous_sparse_expm_upper_bound"] == 36
    assert observed["corrected_sparse_expm_upper_bound"] == 42
    assert observed["reconstructed_sparse_expm_work"] == 42
    assert observed["frozen_sparse_expm_cap"] == 72
    assert observed["registered_catalog_record_count"] == 949
    assert observed["candidate_energy_evaluations_before_retry"] == 0
    assert observed["optimizer_starts_before_retry"] == 0
    assert observed["FCI_evaluations_before_retry"] == 0
    assert observed["N_dense_expm_before_retry"] == 0


def test_item028_retry_artifact_or_precapture_state_is_valid() -> None:
    if OUTPUT.exists():
        artifact = _load(OUTPUT)
        assert historical_artifact_valid(
            OUTPUT,
            artifact,
            digest_field="authorization_digest",
            decision=DECISION,
        )
    else:
        assert all(inspect_retry_readiness()["checks"].values())

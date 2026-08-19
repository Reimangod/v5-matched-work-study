import inspect

from v5_final.parent_native_verifier_v2 import build_parent_verifier_v2
from v5_final.s11_v2_item023_same_item_retry_authorization_v1 import (
    DECISION,
    OUTPUT,
    _digest,
    _embedded_digest,
    _load,
    audit_frozen,
    inspect_retry_readiness,
)
from v5_final.verifier_v2 import VerifierV2
from v5_final.s11_v2_item022_terminal_reconciliation_v1 import (
    historical_artifact_valid,
)
from v5_final.s11_v2_item023_terminal_reconciliation_v1 import (
    OUTPUT as TERMINAL_RECONCILIATION,
    RECEIPT as ITEM023_RECEIPT,
    audit_frozen as audit_terminal_reconciliation,
)


def test_item023_retry_reconstructs_same_outcome_free_selection_inputs() -> None:
    if ITEM023_RECEIPT.exists():
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
    assert observed["candidate_count"] == 427
    assert observed["selected_relation_symbolic_costs"] == [5, 5, 5, 10]
    assert observed["corrected_relation_aware_upper_bound"] == 452
    assert observed["frozen_symbolic_cap"] == 447
    assert observed["expected_terminal"] == (
        "CAP_REJECTED_BEFORE_VERIFIER_OR_RUNTIME"
    )


def test_item023_retry_binds_candidate_identity_not_descriptor_storage_order() -> None:
    evidence = _load(OUTPUT) if ITEM023_RECEIPT.exists() else inspect_retry_readiness()
    assert evidence["checks"][
        "item022_item023_initial_selection_inputs_are_identical"
    ]


def test_initial_selection_preview_has_no_method_or_outcome_argument() -> None:
    assert "method" not in inspect.signature(build_parent_verifier_v2).parameters
    parameters = inspect.signature(VerifierV2.preview_selected_candidate_ids).parameters
    assert "method" not in parameters
    assert "outcome" not in parameters


def test_item023_retry_digest_rejects_tamper() -> None:
    value = {"decision": DECISION}
    value["authorization_digest"] = _digest(value)
    assert _embedded_digest(value, "authorization_digest")
    value["decision"] = "TAMPERED"
    assert not _embedded_digest(value, "authorization_digest")


def test_item023_retry_artifact_or_precapture_state_is_valid() -> None:
    if TERMINAL_RECONCILIATION.exists():
        artifact = _load(OUTPUT)
        assert historical_artifact_valid(
            OUTPUT,
            artifact,
            digest_field="authorization_digest",
            decision=DECISION,
        )
        assert all(audit_terminal_reconciliation()["checks"].values())
    elif ITEM023_RECEIPT.exists():
        artifact = _load(OUTPUT)
        assert historical_artifact_valid(
            OUTPUT,
            artifact,
            digest_field="authorization_digest",
            decision=DECISION,
        )
    elif OUTPUT.exists():
        artifact = _load(OUTPUT)
        assert artifact["decision"] == DECISION
        assert _embedded_digest(artifact, "authorization_digest")
        assert all(audit_frozen()["checks"].values())
    else:
        assert all(inspect_retry_readiness()["checks"].values())

from pathlib import Path

import pytest

from v5_final.s11_v2_item022_same_item_retry_authorization_v1 import (
    DECISION,
    OUTPUT,
    S11V2Item022RetryAuthorizationError,
    _digest,
    _embedded_digest,
    _load,
    _selected_descriptor_costs,
    audit_frozen,
    inspect_retry_readiness,
)
from v5_final.s11_v2_item022_terminal_reconciliation_v1 import (
    RESULT,
    inspect_terminal_reconciliation,
)


def test_retry_readiness_or_frozen_authorization_is_valid() -> None:
    if RESULT.exists():
        successor = inspect_terminal_reconciliation()
        assert all(successor["checks"].values())
        assert successor["observed"]["terminal_status"] == "CAP_REJECTED"
    elif OUTPUT.exists():
        artifact = _load(OUTPUT)
        assert artifact["decision"] == DECISION
        assert _embedded_digest(artifact, "authorization_digest")
        assert all(audit_frozen()["checks"].values())
    else:
        evidence = inspect_retry_readiness()
        assert all(evidence["checks"].values())


def test_item022_retry_bound_is_reconstructed_without_outcome_services() -> None:
    if RESULT.exists():
        successor = inspect_terminal_reconciliation()
        assert all(successor["checks"].values())
        observed = successor["observed"]
        assert observed["corrected_symbolic_upper_bound"] == 452
        assert observed["frozen_symbolic_cap"] == 447
        assert not any(observed["attempt2_delta"].values())
        return
    evidence = inspect_retry_readiness()
    assert all(evidence["checks"].values())
    observed = evidence["observed"]
    assert observed["historical_fixed_cost_assumption"] == 447
    assert observed["selected_relation_symbolic_costs"] == [5, 5, 5, 10]
    assert observed["corrected_relation_aware_upper_bound"] == 452
    assert observed["frozen_symbolic_cap"] == 447
    assert observed["expected_terminal"] == "CAP_REJECTED_BEFORE_VERIFIER_OR_RUNTIME"
    assert observed["new_attempt_candidate_energy_evaluations"] == 0
    assert observed["new_attempt_optimizer_starts"] == 0
    assert observed["new_attempt_statevector_recomputations"] == 0
    assert observed["new_attempt_FCI_evaluations"] == 0
    assert observed["new_attempt_N_dense_expm"] == 0


def test_selected_descriptor_costs_reject_duplicate_selection() -> None:
    descriptor = {
        "candidate_id": "candidate-v1:test",
        "source_generator_digests": ["a", "b"],
        "target_generator_digests": ["c"],
        "deletion_shortcut": False,
    }
    with pytest.raises(S11V2Item022RetryAuthorizationError, match="selected"):
        _selected_descriptor_costs(
            {"candidate_descriptors": [descriptor]},
            {"selected_candidate_ids": ["candidate-v1:test", "candidate-v1:test"]},
        )


def test_retry_authorization_digest_rejects_tamper() -> None:
    value = {"decision": DECISION}
    value["authorization_digest"] = _digest(value)
    assert _embedded_digest(value, "authorization_digest")
    value["decision"] = "TAMPERED"
    assert not _embedded_digest(value, "authorization_digest")


def test_capture_refuses_dirty_tree(monkeypatch, tmp_path: Path) -> None:
    from v5_final import s11_v2_item022_same_item_retry_authorization_v1 as subject

    monkeypatch.setattr(subject, "OUTPUT", tmp_path / "absent.json")
    monkeypatch.setattr(
        subject,
        "_git",
        lambda *args: {
            ("branch", "--show-current"): "branch",
            ("rev-parse", "HEAD"): "a" * 40,
            ("status", "--porcelain"): " M source.py",
        }[args],
    )
    with pytest.raises(S11V2Item022RetryAuthorizationError, match="clean worktree"):
        subject.capture()

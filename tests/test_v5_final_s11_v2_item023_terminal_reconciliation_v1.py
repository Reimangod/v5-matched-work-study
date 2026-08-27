from pathlib import Path

import pytest

from v5_final.s11_v2_item023_terminal_reconciliation_v1 import (
    DECISION,
    OUTPUT,
    S11V2Item023TerminalReconciliationError,
    _digest,
    _embedded_digest,
    _load,
    audit_frozen,
    inspect_terminal_reconciliation,
)


def test_item023_terminal_reconciles_incident_without_new_outcome_work() -> None:
    if OUTPUT.exists():
        artifact = _load(OUTPUT)
        assert artifact["decision"] == DECISION
        assert _embedded_digest(artifact, "reconciliation_digest")
        assert all(audit_frozen()["checks"].values())
        observed = artifact["observed"]
    else:
        evidence = inspect_terminal_reconciliation()
        assert all(evidence["checks"].values())
        observed = evidence["observed"]
    assert observed["terminal_status"] == "CAP_REJECTED"
    assert observed["terminal_prefix"] == 24
    assert observed["corrected_symbolic_upper_bound"] == 452
    assert observed["frozen_symbolic_cap"] == 447
    assert not any(observed["attempt2_delta"].values())
    assert observed["candidate_energy_evaluations"] == 0
    assert observed["optimizer_starts"] == 0
    assert observed["FCI_evaluations"] == 0
    assert observed["N_dense_expm"] == 0


def test_reconciliation_digest_rejects_tamper() -> None:
    value = {"decision": DECISION}
    value["reconciliation_digest"] = _digest(value)
    assert _embedded_digest(value, "reconciliation_digest")
    value["decision"] = "TAMPERED"
    assert not _embedded_digest(value, "reconciliation_digest")


def test_capture_refuses_dirty_tree(monkeypatch, tmp_path: Path) -> None:
    from v5_final import s11_v2_item023_terminal_reconciliation_v1 as subject

    monkeypatch.setattr(subject, "OUTPUT", tmp_path / "absent.json")
    monkeypatch.setattr(
        subject,
        "_git",
        lambda *args: {
            ("branch", "--show-current"): "branch",
            ("rev-parse", "HEAD"): "a" * 40,
            ("status", "--porcelain"): " M evidence.json",
        }[args],
    )
    with pytest.raises(S11V2Item023TerminalReconciliationError, match="clean worktree"):
        subject.capture()

from pathlib import Path

import pytest

from v5_final.historical_artifact_audit import artifact_is_immutable_git_blob, is_ancestor
from v5_final.s11_v2_execution_readiness_v5 import (
    DECISION,
    OUTPUT,
    S11V2ExecutionReadinessV5Error,
    _digest,
    _embedded_digest,
    _load,
    audit_frozen,
    inspect_checkpoint,
)


def test_five_item_checkpoint_or_frozen_successor_is_valid() -> None:
    if not OUTPUT.exists():
        evidence = inspect_checkpoint()
        assert all(evidence["checks"].values())
        assert evidence["observed_outcomes"]["terminal_count"] == 5
        assert evidence["observed_outcomes"]["candidate_energy_evaluations"] == 75
        return
    artifact = _load(OUTPUT)
    assert artifact_is_immutable_git_blob(OUTPUT)
    assert is_ancestor(artifact["captured_repository_state"]["local_head"])
    assert artifact["decision"] == DECISION
    assert all(audit_frozen()["checks"].values())


def test_readiness_digest_rejects_tamper() -> None:
    value = {"decision": DECISION}
    value["readiness_digest"] = _digest(value)
    assert _embedded_digest(value, "readiness_digest")
    value["decision"] = "TAMPERED"
    assert not _embedded_digest(value, "readiness_digest")


def test_capture_refuses_dirty_tree(monkeypatch, tmp_path: Path) -> None:
    from v5_final import s11_v2_execution_readiness_v5 as subject

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
    with pytest.raises(S11V2ExecutionReadinessV5Error, match="clean worktree"):
        subject.capture()

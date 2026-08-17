from pathlib import Path

import pytest

from v5_final.historical_artifact_audit import (
    artifact_is_immutable_git_blob,
    is_ancestor,
    manifest_matches_commit,
)
from v5_final.s11_v2_execution_readiness_v4 import (
    DECISION,
    OUTPUT,
    S11V2ExecutionReadinessV4Error,
    _digest,
    _embedded_digest,
    _load,
    inspect_pre_retry,
)
from v5_final.s11_v2_item002_retry_authorization_v1 import (
    OUTPUT as RETRY_AUTHORIZATION,
)


def test_pre_retry_state_or_frozen_successor_is_valid() -> None:
    if not OUTPUT.exists():
        evidence = inspect_pre_retry()
        assert all(evidence["checks"].values())
        assert evidence["observed_outcomes"]["terminal_count"] == 2
        assert evidence["observed_outcomes"]["candidate_energy_evaluations"] == 1
        assert evidence["observed_outcomes"]["item002_status"] == "ROLLED_BACK_UNTERMINATED"
        return

    artifact = _load(OUTPUT)
    source_manifest = [
        {"path": path, "sha256": expected}
        for path, expected in artifact["binding"]["source_sha256"].items()
    ]
    assert artifact_is_immutable_git_blob(OUTPUT)
    assert is_ancestor(artifact["captured_repository_state"]["local_head"])
    assert manifest_matches_commit(
        source_manifest, artifact["captured_repository_state"]["local_head"]
    )
    assert _embedded_digest(artifact, "readiness_digest")
    assert artifact["decision"] == DECISION
    assert all(artifact["checks"].values())


def test_retry_authorization_predicts_same_cap_pre_session_rejection() -> None:
    authorization = _load(RETRY_AUTHORIZATION)
    assert authorization["semantic_diff"]["cap_changed"] is False
    assert authorization["semantic_diff"]["counter_reset"] is False
    assert authorization["semantic_diff"]["expected_terminal"] == (
        "CAP_REJECTED_BEFORE_NEW_VERIFIER_SESSION"
    )
    assert authorization["observed"]["predicted_cap_rejection_reason"].startswith(
        "verifier cap rejected before session:"
    )


def test_readiness_digest_rejects_tamper() -> None:
    value = {"decision": DECISION}
    value["readiness_digest"] = _digest(value)
    assert _embedded_digest(value, "readiness_digest")
    value["decision"] = "TAMPERED"
    assert not _embedded_digest(value, "readiness_digest")


def test_capture_refuses_dirty_or_unpushed_tree(monkeypatch, tmp_path: Path) -> None:
    from v5_final import s11_v2_execution_readiness_v4 as subject

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
    with pytest.raises(S11V2ExecutionReadinessV4Error, match="clean worktree"):
        subject.capture()

from __future__ import annotations

from pathlib import Path

import pytest

from v5_final.s11_v2_execution_readiness_v2 import (
    DECISION,
    OUTPUT,
    S11V2ExecutionReadinessV2Error,
    _digest,
    _embedded_digest,
    _load,
)
from v5_final.historical_artifact_audit import (
    artifact_is_immutable_git_blob,
    is_ancestor,
    manifest_matches_commit,
)
from v5_final.s11_v2_item000_environment_incident_v1 import inspect_incident


def test_historical_outcome_free_readiness_is_valid_at_captured_commit() -> None:
    artifact = _load(OUTPUT)
    captured_commit = artifact["captured_repository_state"]["local_head"]
    source_sha256 = artifact["binding"]["source_sha256"]
    source_manifest = [
        {"path": path, "sha256": expected}
        for path, expected in source_sha256.items()
    ]

    assert artifact_is_immutable_git_blob(OUTPUT)
    assert _embedded_digest(artifact, "readiness_digest")
    assert artifact["decision"] == DECISION
    assert artifact["binding"]["source_bundle_digest"] == _digest(source_sha256)
    assert manifest_matches_commit(source_manifest, captured_commit)
    assert is_ancestor(captured_commit)
    assert artifact["observed_outcomes"] == {
        "candidate_energy_evaluations": 0,
        "optimizer_iterations": 0,
        "FCI_evaluations": 0,
        "production_item_artifacts": 0,
    }
    assert len(artifact["binding"]["method_ids"]) == 6
    assert any(
        path.endswith("s11_v2_execution_runner_v1.py")
        for path in source_sha256
    )


def test_current_tree_preserves_v2_supersession_and_blocks_continuation() -> None:
    incident = inspect_incident()
    assert all(incident["checks"].values())
    assert incident["checks"]["item000_failed_before_candidate_outcome"] is True
    assert incident["checks"]["FCI_and_dense_expm_zero"] is True


def test_readiness_digest_rejects_tamper() -> None:
    value = {"decision": DECISION}
    value["readiness_digest"] = _digest(value)
    assert _embedded_digest(value, "readiness_digest")
    value["decision"] = "TAMPERED"
    assert not _embedded_digest(value, "readiness_digest")


def test_capture_refuses_dirty_or_unpushed_tree(monkeypatch, tmp_path: Path) -> None:
    from v5_final import s11_v2_execution_readiness_v2 as subject

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
    with pytest.raises(S11V2ExecutionReadinessV2Error, match="clean worktree"):
        subject.capture()

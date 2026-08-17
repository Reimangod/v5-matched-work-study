from __future__ import annotations

from pathlib import Path

import pytest

from v5_final.s11_v2_execution_readiness_v2 import (
    DECISION,
    S11V2ExecutionReadinessV2Error,
    _embedded_digest,
    inspect_outcome_free,
)


def test_outcome_free_inspection_binds_exact_empty_queue_namespace() -> None:
    evidence = inspect_outcome_free()
    assert all(evidence["checks"].values())
    assert evidence["observed_outcomes"] == {
        "candidate_energy_evaluations": 0,
        "optimizer_iterations": 0,
        "FCI_evaluations": 0,
        "production_item_artifacts": 0,
    }
    assert len(evidence["binding"]["method_ids"]) == 6
    assert any(
        path.endswith("s11_v2_execution_runner_v1.py")
        for path in evidence["binding"]["source_sha256"]
    )


def test_readiness_digest_rejects_tamper() -> None:
    value = {"decision": DECISION}
    from v5_final.s11_v2_execution_readiness_v2 import _digest

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

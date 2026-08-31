from pathlib import Path
from types import SimpleNamespace

import pytest

from v5_final.s11_v2_execution_readiness_v10 import (
    DECISION,
    OUTPUT,
    S11V2ExecutionReadinessV10Error,
    _digest,
    _embedded_digest,
    _load,
    _require_minimum_free_storage,
    inspect_checkpoint,
)
from v5_final.s11_v2_item022_terminal_reconciliation_v1 import (
    historical_artifact_valid,
)


def test_item028_retry_checkpoint_or_frozen_readiness_is_valid() -> None:
    if OUTPUT.exists():
        artifact = _load(OUTPUT)
        assert historical_artifact_valid(
            OUTPUT,
            artifact,
            digest_field="readiness_digest",
            decision=DECISION,
        )
    else:
        evidence = inspect_checkpoint()
        assert all(evidence["checks"].values())
        assert evidence["observed"]["terminal_count"] == 28
        assert evidence["observed"]["retry_queue_index"] == 28
        assert evidence["observed"]["item028_candidate_energy_evaluations"] == 0


def test_readiness_v10_digest_rejects_tamper() -> None:
    value = {"decision": DECISION}
    value["readiness_digest"] = _digest(value)
    assert _embedded_digest(value, "readiness_digest")
    value["decision"] = "TAMPERED"
    assert not _embedded_digest(value, "readiness_digest")


def test_readiness_v10_storage_is_fail_closed(monkeypatch) -> None:
    from v5_final import s11_v2_execution_readiness_v10 as subject

    monkeypatch.setattr(
        subject.shutil,
        "disk_usage",
        lambda path: SimpleNamespace(free=subject.MINIMUM_FREE_BYTES - 1),
    )
    with pytest.raises(S11V2ExecutionReadinessV10Error, match="fell below 40 GiB"):
        _require_minimum_free_storage()


def test_readiness_v10_capture_refuses_dirty_tree(monkeypatch, tmp_path: Path) -> None:
    from v5_final import s11_v2_execution_readiness_v10 as subject

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
    with pytest.raises(S11V2ExecutionReadinessV10Error, match="clean worktree"):
        subject.capture()

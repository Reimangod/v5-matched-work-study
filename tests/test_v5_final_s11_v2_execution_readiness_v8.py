from pathlib import Path
from types import SimpleNamespace

import pytest

from v5_final.s11_v2_execution_readiness_v8 import (
    DECISION,
    OUTPUT,
    S11V2ExecutionReadinessV8Error,
    _digest,
    _embedded_digest,
    _load,
    _require_minimum_free_storage,
    audit_frozen,
    inspect_checkpoint,
)
from v5_final.s11_v2_item023_same_item_retry_authorization_v1 import (
    OUTPUT as RETRY_AUTHORIZATION,
    inspect_retry_readiness,
)


def test_item023_retry_checkpoint_or_frozen_readiness_is_valid() -> None:
    if OUTPUT.exists():
        artifact = _load(OUTPUT)
        assert artifact["decision"] == DECISION
        assert _embedded_digest(artifact, "readiness_digest")
        assert all(audit_frozen()["checks"].values())
    elif RETRY_AUTHORIZATION.exists():
        evidence = inspect_checkpoint()
        assert all(evidence["checks"].values())
        assert evidence["observed"]["terminal_count"] == 23
        assert evidence["observed"]["item023_status"] == "ROLLED_BACK_NONTERMINAL"
        assert evidence["observed"]["item023_corrected_upper_bound"] == 452
        assert evidence["observed"]["item023_frozen_symbolic_cap"] == 447
    else:
        assert all(inspect_retry_readiness()["checks"].values())


def test_readiness_digest_rejects_tamper() -> None:
    value = {"decision": DECISION}
    value["readiness_digest"] = _digest(value)
    assert _embedded_digest(value, "readiness_digest")
    value["decision"] = "TAMPERED"
    assert not _embedded_digest(value, "readiness_digest")


def test_post_verification_storage_is_fail_closed(monkeypatch) -> None:
    from v5_final import s11_v2_execution_readiness_v8 as subject

    monkeypatch.setattr(
        subject.shutil,
        "disk_usage",
        lambda path: SimpleNamespace(free=subject.MINIMUM_FREE_BYTES - 1),
    )
    with pytest.raises(S11V2ExecutionReadinessV8Error, match="fell below 40 GiB"):
        _require_minimum_free_storage()


def test_capture_refuses_dirty_tree(monkeypatch, tmp_path: Path) -> None:
    from v5_final import s11_v2_execution_readiness_v8 as subject

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
    with pytest.raises(S11V2ExecutionReadinessV8Error, match="clean worktree"):
        subject.capture()

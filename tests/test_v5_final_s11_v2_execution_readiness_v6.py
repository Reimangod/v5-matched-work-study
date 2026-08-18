from pathlib import Path
from types import SimpleNamespace

import json
import pytest

from v5_final.s11_v2_execution_readiness_v6 import (
    DECISION,
    ITEM022_RETRY_AUTHORIZATION,
    OUTPUT,
    S11V2ExecutionReadinessV6Error,
    _digest,
    _embedded_digest,
    _live_pr_snapshot,
    _load,
    audit_frozen,
    inspect_checkpoint,
)


def test_pre_retry_checkpoint_or_frozen_readiness_is_valid() -> None:
    if OUTPUT.exists():
        artifact = _load(OUTPUT)
        assert artifact["decision"] == DECISION
        assert _embedded_digest(artifact, "readiness_digest")
        assert all(audit_frozen()["checks"].values())
    elif ITEM022_RETRY_AUTHORIZATION.exists():
        evidence = inspect_checkpoint()
        assert all(evidence["checks"].values())
        assert evidence["observed"]["terminal_count"] == 22
    else:
        # Source-review phase: the retry authorization must be frozen before
        # readiness can even be inspected, never mocked or bypassed.
        assert not OUTPUT.exists()


def test_readiness_digest_rejects_tamper() -> None:
    value = {"decision": DECISION}
    value["readiness_digest"] = _digest(value)
    assert _embedded_digest(value, "readiness_digest")
    value["decision"] = "TAMPERED"
    assert not _embedded_digest(value, "readiness_digest")


def test_live_repository_check_retries_503_then_requires_exact_head(
    monkeypatch,
) -> None:
    from v5_final import s11_v2_execution_readiness_v6 as subject

    head = "a" * 40
    calls = iter(
        (
            SimpleNamespace(returncode=1, stdout="", stderr="HTTP 503 GraphQL"),
            SimpleNamespace(
                returncode=0,
                stderr="",
                stdout=json.dumps(
                    {
                        "number": 8,
                        "state": "OPEN",
                        "isDraft": True,
                        "headRefName": "agent/s11-v2-frozen-90-execution",
                        "baseRefName": "main",
                        "headRefOid": head,
                        "url": "https://github.com/Reimangod/v5-matched-work-study/pull/8",
                        "statusCheckRollup": [
                            {
                                "name": "release-gate",
                                "workflowName": "V5 release gate",
                                "status": "COMPLETED",
                                "conclusion": "SUCCESS",
                                "detailsUrl": "https://github.com/example/check",
                            }
                        ],
                    }
                ),
            ),
        )
    )
    monkeypatch.setattr(subject.subprocess, "run", lambda *args, **kwargs: next(calls))
    monkeypatch.setattr(subject.time, "sleep", lambda seconds: None)
    result = _live_pr_snapshot(expected_head=head, attempts=2, initial_delay_seconds=0)
    assert [record["classification"] for record in result["attempts"]] == [
        "TRANSIENT_HTTP_503",
        "SUCCESS",
    ]
    assert result["checks"][0]["conclusion"] == "SUCCESS"


def test_live_repository_check_rejects_non_green(monkeypatch) -> None:
    from v5_final import s11_v2_execution_readiness_v6 as subject

    head = "b" * 40
    payload = {
        "number": 8,
        "state": "OPEN",
        "isDraft": True,
        "headRefName": "branch",
        "baseRefName": "main",
        "headRefOid": head,
        "url": "https://github.com/example/pr/8",
        "statusCheckRollup": [
            {
                "name": "release-gate",
                "workflowName": "V5 release gate",
                "status": "COMPLETED",
                "conclusion": "FAILURE",
                "detailsUrl": "https://github.com/example/check",
            }
        ],
    }
    monkeypatch.setattr(
        subject.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0, stdout=json.dumps(payload), stderr=""
        ),
    )
    with pytest.raises(S11V2ExecutionReadinessV6Error, match="not green"):
        _live_pr_snapshot(expected_head=head, attempts=1, initial_delay_seconds=0)


def test_capture_refuses_dirty_tree(monkeypatch, tmp_path: Path) -> None:
    from v5_final import s11_v2_execution_readiness_v6 as subject

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
    with pytest.raises(S11V2ExecutionReadinessV6Error, match="clean worktree"):
        subject.capture()

from __future__ import annotations

from types import SimpleNamespace

import pytest

from v5_final.s0_public_amendment import audit, build


def test_public_transition_preserves_history_and_closes_performance() -> None:
    value = build()
    assert value["transition"]["from"] == "PRIVATE"
    assert value["transition"]["to"] == "PUBLIC"
    assert value["transition"]["history_and_tags_rewritten"] is False
    assert value["authorization"]["performance_experiment"] == "NOT_AUTHORIZED"
    result = audit(require_clean=False)
    assert result["passed"] is True
    assert result["sensitive_path_matches"] == []


def test_visibility_uses_bounded_retry(monkeypatch) -> None:
    from v5_final import s0_public_amendment as subject

    calls = []
    responses = [
        SimpleNamespace(returncode=1, stdout="", stderr="HTTP 503"),
        SimpleNamespace(
            returncode=0,
            stdout=(
                '{"visibility":"PUBLIC","isPrivate":false,'
                '"url":"https://github.com/Reimangod/v5-matched-work-study",'
                '"defaultBranchRef":{"name":"main"}}'
            ),
            stderr="",
        ),
    ]
    monkeypatch.setattr(
        subject.subprocess,
        "run",
        lambda *args, **kwargs: calls.append((args, kwargs)) or responses.pop(0),
    )
    sleeps = []
    monkeypatch.setattr(subject.time, "sleep", sleeps.append)
    assert subject._visibility()["visibility"] == "PUBLIC"
    assert len(calls) == 2
    assert sleeps == [1]
    assert all(call[1]["timeout"] == 30 for call in calls)


def test_visibility_fails_closed_after_exact_attempt_bound(monkeypatch) -> None:
    from v5_final import s0_public_amendment as subject

    calls = []
    monkeypatch.setattr(
        subject.subprocess,
        "run",
        lambda *args, **kwargs: calls.append((args, kwargs))
        or SimpleNamespace(returncode=1, stdout="", stderr="HTTP 503"),
    )
    monkeypatch.setattr(subject.time, "sleep", lambda _: None)
    with pytest.raises(RuntimeError, match="GH_REPO_VIEW_VISIBILITY") as error:
        subject._visibility()
    assert len(calls) == 4
    assert '"attempt": 4' in str(error.value)
    assert '"http_status": null' in str(error.value)


def test_history_scan_skips_tree_rescan_when_unique_blobs_are_clean(monkeypatch) -> None:
    from v5_final import s0_public_amendment as subject

    monkeypatch.setattr(subject, "_history_contains_sensitive_blob", lambda: False)
    monkeypatch.setattr(
        subject.subprocess,
        "run",
        lambda *args, **kwargs: pytest.fail("clean blob scan must not rescan trees"),
    )
    assert subject._history_sensitive_path_matches() == []


@pytest.mark.parametrize(
    ("content", "expected"),
    [(b"ordinary text", False), (b"sk-" + b"a" * 20, True)],
)
def test_unique_blob_scan_detects_registered_pattern(
    monkeypatch, content, expected
) -> None:
    from v5_final import s0_public_amendment as subject

    monkeypatch.setattr(subject, "_git", lambda *arguments: "a" * 40 + " path.txt")
    responses = [
        SimpleNamespace(returncode=0, stdout="a" * 40 + " blob\n", stderr=""),
        SimpleNamespace(
            returncode=0,
            stdout=(
                b"a" * 40
                + b" blob "
                + str(len(content)).encode()
                + b"\n"
                + content
                + b"\n"
            ),
            stderr=b"",
        ),
    ]
    monkeypatch.setattr(
        subject.subprocess, "run", lambda *args, **kwargs: responses.pop(0)
    )
    assert subject._history_contains_sensitive_blob() is expected

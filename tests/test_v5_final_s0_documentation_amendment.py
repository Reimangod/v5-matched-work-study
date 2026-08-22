from __future__ import annotations

import copy
import hashlib
import json
import subprocess

import pytest

from v5_final.s0_documentation_amendment import (
    OUTPUT,
    README_PATH,
    audit,
    build,
    validate_transition,
)
from v5_final.s0_successor import BASELINE_TAG, ROOT, audit_manifest
import v5_final.s0_successor as s0_successor


def _old() -> bytes:
    return subprocess.check_output(
        ["git", "-C", str(ROOT), "show", f"{BASELINE_TAG}:{README_PATH}"]
    )


def test_old_baseline_hash_needs_no_documentation_amendment() -> None:
    old = _old()
    inventory = json.loads(
        (ROOT / "artifacts/v5-final/s0/successor-isolation-v1.json").read_text()
    )["baseline"]["inventory"]
    readme = next(item for item in inventory if item["path"] == README_PATH)
    assert hashlib.sha256(old).hexdigest() == readme["sha256"]


def test_exact_approved_readme_transition_passes() -> None:
    artifact = build()
    assert artifact == json.loads(OUTPUT.read_text())
    assert validate_transition(artifact, old=_old(), new=(ROOT / README_PATH).read_bytes())
    result = audit_manifest(require_clean=False)
    assert result["documentation_amendments_applied"] == [README_PATH]
    assert result["passed"] is True
    assert all(audit().values())


def test_third_readme_content_fails_even_with_valid_old_artifact() -> None:
    artifact = build()
    third = (ROOT / README_PATH).read_bytes() + b"\nunauthorized third content\n"
    assert not validate_transition(artifact, old=_old(), new=third)

    tampered = copy.deepcopy(artifact)
    tampered["documentation_change"]["new_sha256"] = hashlib.sha256(third).hexdigest()
    assert not validate_transition(tampered, old=_old(), new=third)

    observed = s0_successor._current_file_sha256

    def third_hash(path: str) -> str | None:
        if path == README_PATH:
            return hashlib.sha256(third).hexdigest()
        return observed(path)

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(s0_successor, "_current_file_sha256", third_hash)
        with pytest.raises(RuntimeError, match="historical_baseline_files_unchanged"):
            audit_manifest(require_clean=False)

from __future__ import annotations

import json
from pathlib import Path

import pytest

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive


def test_exclusive_writer_refuses_overwrite(tmp_path: Path) -> None:
    target = tmp_path / "artifact.json"
    write_json_exclusive(target, {"value": 1})
    original = target.read_bytes()
    with pytest.raises(FileExistsError):
        write_json_exclusive(target, {"value": 2})
    assert target.read_bytes() == original
    assert not list(tmp_path.glob(".staging-*"))


def test_canonical_json_is_order_invariant_and_finite() -> None:
    assert canonical_json_bytes({"b": 2, "a": 1}) == canonical_json_bytes({"a": 1, "b": 2})
    with pytest.raises(ValueError):
        canonical_json_bytes({"bad": float("nan")})
    assert json.loads(canonical_json_bytes({"ok": True})) == {"ok": True}

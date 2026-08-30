"""Shared canonical-artifact and provenance helpers for the A100 pilot."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
from typing import Any, Iterable

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive


ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_ROOT = ROOT / "artifacts/aic-a100-pilot-v1"


class A100PilotError(RuntimeError):
    """Fail-closed pilot error."""


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise A100PilotError(f"expected JSON object: {path}")
    return value


def embedded_digest_valid(record: dict[str, Any], field: str) -> bool:
    observed = record.get(field)
    if not isinstance(observed, str):
        return False
    body = {key: value for key, value in record.items() if key != field}
    return observed == digest(body)


def publish(path: Path, record: dict[str, Any], field: str) -> dict[str, Any]:
    if field in record:
        raise A100PilotError(f"digest field already present: {field}")
    result = dict(record)
    result[field] = digest(result)
    write_json_exclusive(path, result)
    return result


def git(*arguments: str, root: Path = ROOT) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return completed.stdout.strip()


def tree_inventory_digest(paths: Iterable[Path], *, root: Path = ROOT) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for base in sorted((path.resolve() for path in paths), key=str):
        if not base.is_dir() or root.resolve() not in (base, *base.parents):
            raise A100PilotError(f"invalid protected directory: {base}")
        for path in sorted((value for value in base.rglob("*") if value.is_file()), key=str):
            entries.append(
                {
                    "path": path.relative_to(root).as_posix(),
                    "sha256": sha256_file(path),
                    "size_bytes": path.stat().st_size,
                }
            )
    body = {
        "file_count": len(entries),
        "total_size_bytes": sum(int(item["size_bytes"]) for item in entries),
        "inventory_digest": digest(entries),
    }
    return body


def safe_environment(keys: Iterable[str]) -> dict[str, str | None]:
    return {key: os.environ.get(key) for key in sorted(set(keys))}

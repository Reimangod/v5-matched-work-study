"""Audit immutable artifacts against the exact Git blobs they originally bound.

Historical freezes must not be rebuilt from today's source tree.  This module
locates the commit containing the exact committed artifact bytes and validates
its source manifest against blobs from that commit (or an explicitly frozen
validated commit).  Current-tree drift is therefore neither hidden nor
misclassified as corruption of the historical artifact.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
from typing import Any, Mapping, Sequence

from .s0_successor import ROOT


class HistoricalArtifactAuditError(RuntimeError):
    pass


def _git_bytes(*args: str, check: bool = True) -> bytes:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, check=False,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if check and result.returncode != 0:
        raise HistoricalArtifactAuditError(
            result.stderr.decode(errors="replace").strip()
        )
    return result.stdout


def _relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve()))
    except ValueError as error:
        raise HistoricalArtifactAuditError("path is outside repository") from error


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def blob_at(commit: str, path: str | Path) -> bytes:
    relative = _relative(path) if isinstance(path, Path) else str(path)
    if relative.startswith("/") or relative.startswith("../"):
        raise HistoricalArtifactAuditError("unsafe repository-relative path")
    return _git_bytes("show", f"{commit}:{relative}")


def artifact_binding_commit(path: Path) -> str:
    """Return the newest commit containing bytes identical to ``path``."""

    relative = _relative(path)
    current_sha = sha256_bytes(path.read_bytes())
    commits = _git_bytes("log", "--format=%H", "--", relative).decode().splitlines()
    for commit in commits:
        result = subprocess.run(
            ["git", "show", f"{commit}:{relative}"], cwd=ROOT, check=False,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        if result.returncode == 0 and sha256_bytes(result.stdout) == current_sha:
            return commit
    raise HistoricalArtifactAuditError(
        f"no Git commit contains the exact immutable artifact: {relative}"
    )


def manifest_matches_commit(
    manifest: Sequence[Mapping[str, Any]], commit: str
) -> bool:
    if not manifest:
        return False
    observed_paths: set[str] = set()
    for entry in manifest:
        path = entry.get("path")
        expected = entry.get("sha256")
        if (
            not isinstance(path, str)
            or not path
            or path in observed_paths
            or not isinstance(expected, str)
            or len(expected) != 64
        ):
            return False
        observed_paths.add(path)
        try:
            raw = blob_at(commit, path)
        except HistoricalArtifactAuditError:
            return False
        if sha256_bytes(raw) != expected:
            return False
    return True


def manifest_matches_artifact_commit(
    artifact_path: Path, manifest: Sequence[Mapping[str, Any]]
) -> bool:
    return manifest_matches_commit(manifest, artifact_binding_commit(artifact_path))


def artifact_is_immutable_git_blob(path: Path) -> bool:
    commit = artifact_binding_commit(path)
    return blob_at(commit, path) == path.read_bytes()


def is_ancestor(commit: str, descendant: str = "HEAD") -> bool:
    return subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, descendant],
        cwd=ROOT, check=False,
    ).returncode == 0

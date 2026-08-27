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


def parse_sha256_manifest(raw: bytes) -> tuple[dict[str, str], ...]:
    """Parse a strict two-space SHA-256 manifest without trusting the tree."""

    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError as error:
        raise HistoricalArtifactAuditError("manifest is not UTF-8") from error
    records: list[dict[str, str]] = []
    observed: set[str] = set()
    for line in lines:
        parts = line.split("  ")
        if len(parts) != 2:
            raise HistoricalArtifactAuditError("manifest line is malformed")
        sha256, path = parts
        if (
            len(sha256) != 64
            or any(value not in "0123456789abcdef" for value in sha256)
            or not path
            or path.startswith("/")
            or ".." in Path(path).parts
            or path in observed
        ):
            raise HistoricalArtifactAuditError("manifest entry is invalid")
        observed.add(path)
        records.append({"path": path, "sha256": sha256})
    if not records:
        raise HistoricalArtifactAuditError("manifest is empty")
    return tuple(records)


def manifest_file_matches_artifact_commit(
    artifact_path: Path, manifest_path: Path
) -> bool:
    """Validate a sibling manifest at the exact artifact-binding commit.

    Historical manifests use either repository-relative paths or basenames
    relative to the manifest directory.  Resolution is deterministic and
    validated against Git blobs, never against current source bytes.
    """

    try:
        commit = artifact_binding_commit(artifact_path)
        if blob_at(commit, manifest_path) != manifest_path.read_bytes():
            return False
        parsed = parse_sha256_manifest(manifest_path.read_bytes())
        manifest_parent = manifest_path.parent.relative_to(ROOT)
        normalized: list[dict[str, str]] = []
        for record in parsed:
            path = record["path"]
            candidates = (path, str(manifest_parent / path))
            selected = None
            for candidate in candidates:
                try:
                    blob_at(commit, candidate)
                except HistoricalArtifactAuditError:
                    continue
                selected = candidate
                break
            if selected is None:
                return False
            normalized.append(
                {"path": selected, "sha256": record["sha256"]}
            )
        return manifest_matches_commit(normalized, commit)
    except (HistoricalArtifactAuditError, ValueError):
        return False


def is_ancestor(commit: str, descendant: str = "HEAD") -> bool:
    return subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, descendant],
        cwd=ROOT, check=False,
    ).returncode == 0

"""Shared immutable S0 provenance definitions."""

from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
from typing import Iterable


ROOT = Path(__file__).resolve().parents[2]
PARENT = ROOT / "provenance" / "dvg-obs-ceo"
PARENT_TAG = "pra-critical-path-negative-result-v1"
PARENT_COMMIT = "4783b9ff9f9b6f2061a1ef8c02613f4c6cef38db"
CEO_COMMIT = "a3f89d03e6a03c89767d3cf8ee7657a57653dda0"
EXPECTED_LOCK_SHA256 = "8a9021a72dd3bd6af8d8fc656d8f544adf620c1900c5ce081b26f484bbf6909d"

REQUIRED_IMPORTS = (
    "docs/VERSION_BEHAVIOR_AND_MOLECULE_DEPENDENCE_AUDIT.md",
    "docs/V5_RISK_AWARE_SEQUENTIAL_PLAN.md",
    "docs/V5_V5_1_RELEASE_RESULT.md",
    "docs/PRA_CRITICAL_PATH_PLAN.md",
    "docs/PRA_CRITICAL_PATH_S6_RESULT.md",
    "docs/PRA_CRITICAL_PATH_S11_RELEASE.md",
    "src/dvg_obs_ceo/v4_1_multisystem.py",
    "src/dvg_obs_ceo/v4_1_exact_multisystem.py",
    "src/dvg_obs_ceo/v4_1_exact_audit.py",
    "src/dvg_obs_ceo/v5_multitrajectory.py",
    "src/dvg_obs_ceo/v5_multitrajectory_audit.py",
    "src/dvg_obs_ceo/v5_protocol.py",
    "src/dvg_obs_ceo/v5_s9_frozen_multisystem.py",
    "src/dvg_obs_ceo/v5_s9_audit.py",
    "src/dvg_obs_ceo/v5_1_exact_fusion.py",
    "src/dvg_obs_ceo/v5_release_audit.py",
    "artifacts/pra_path/release/negative-result-release-manifest-v1.json",
)


def git(repository: Path, *arguments: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repository), *arguments], text=True
    ).strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tracked_paths(prefix: str | None = None) -> tuple[str, ...]:
    arguments = ["ls-tree", "-r", "--name-only", "HEAD"]
    if prefix is not None:
        arguments.extend(["--", prefix])
    output = git(PARENT, *arguments)
    return tuple(line for line in output.splitlines() if line)


def hash_records(paths: Iterable[str]) -> list[dict[str, str]]:
    return [
        {"path": relative, "sha256": sha256(PARENT / relative)}
        for relative in sorted(paths)
    ]

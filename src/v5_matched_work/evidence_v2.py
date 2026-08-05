"""Closure-time reconstruction of immutable historical evidence."""

from __future__ import annotations

import json
from typing import Any

from .s0_common import CEO_COMMIT, PARENT, PARENT_COMMIT, ROOT, git, sha256


def verify_historical_evidence() -> dict[str, Any]:
    ledger = json.loads((ROOT / "artifacts/s0/isolation-ledger-v1.json").read_text(encoding="utf-8"))
    historical = ledger["historical_artifacts"]
    observed_parent_tree = git(PARENT, "rev-parse", "HEAD^{tree}")
    observed_ceo_commit = git(PARENT / "vendor/ceo-adapt-vqe", "rev-parse", "HEAD")
    checks = {
        "historical_file_count_486": historical["file_count"] == 486 == len(historical["files"]),
        "all_486_historical_hashes": all(
            (PARENT / item["path"]).is_file() and sha256(PARENT / item["path"]) == item["sha256"]
            for item in historical["files"]
        ),
        "parent_commit": git(PARENT, "rev-parse", "HEAD") == PARENT_COMMIT == ledger["historical_parent"]["peeled_commit"],
        "parent_tree": observed_parent_tree == ledger["historical_parent"]["tree_sha1"],
        "ceo_submodule_commit": observed_ceo_commit == CEO_COMMIT == ledger["upstream_ceo_star"]["commit"],
        "parent_dependency_lock": sha256(PARENT / "uv.lock") == ledger["dependency_lock"]["sha256"],
    }
    return {
        "checks": checks,
        "passed": all(checks.values()),
        "observed": {
            "historical_file_count": len(historical["files"]),
            "parent_commit": git(PARENT, "rev-parse", "HEAD"),
            "parent_tree": observed_parent_tree,
            "ceo_submodule_commit": observed_ceo_commit,
        },
    }

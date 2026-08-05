"""Build the S0 immutable import/evidence ledger without touching old artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess
from typing import Any

from .atomic_artifacts import canonical_json_bytes, write_json_exclusive
from .s0_common import (
    CEO_COMMIT,
    EXPECTED_LOCK_SHA256,
    PARENT,
    PARENT_COMMIT,
    PARENT_TAG,
    REQUIRED_IMPORTS,
    ROOT,
    git,
    hash_records,
    sha256,
    tracked_paths,
)


def _digest_without(record: dict[str, Any], field: str) -> str:
    payload = dict(record)
    payload.pop(field, None)
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def build_ledger() -> dict[str, Any]:
    parent_head = git(PARENT, "rev-parse", "HEAD")
    parent_tag_commit = git(PARENT, "rev-parse", f"{PARENT_TAG}^{{}}")
    parent_tree = git(PARENT, "rev-parse", "HEAD^{tree}")
    parent_status = git(PARENT, "status", "--porcelain", "--untracked-files=no")
    nested = git(PARENT, "submodule", "status", "vendor/ceo-adapt-vqe").split()
    if parent_head != PARENT_COMMIT or parent_tag_commit != PARENT_COMMIT:
        raise RuntimeError("historical parent commit/tag mismatch")
    if not nested or nested[0].lstrip("-+") != CEO_COMMIT:
        raise RuntimeError("CEO* submodule commit mismatch")
    if parent_status:
        raise RuntimeError("historical parent tracked worktree is dirty")
    if sha256(PARENT / "uv.lock") != EXPECTED_LOCK_SHA256:
        raise RuntimeError("historical dependency lock drift")

    missing = [relative for relative in REQUIRED_IMPORTS if not (PARENT / relative).is_file()]
    if missing:
        raise RuntimeError(f"required immutable imports are missing: {missing}")
    historical_paths = tracked_paths("artifacts")
    result: dict[str, Any] = {
        "schema": "v5-matched-work.s0-isolation-ledger.v1",
        "stage": "S0",
        "status": "COMPLETE",
        "isolation_method": "git-submodule",
        "repository": {
            "name": "Reimangod/v5-matched-work-study",
            "initial_visibility": "private",
            "observed_visibility": "private",
            "default_branch": "main",
            "remote": "https://github.com/Reimangod/v5-matched-work-study.git",
            "governance": {
                "branch_protection_enforced": False,
                "tag_ruleset_enforced": False,
                "enforcement_attempted": True,
                "enforcement_result": "HTTP_403_GITHUB_PRO_OR_PUBLIC_REQUIRED",
                "fallback_policy": (
                    "private repository; no force-push; no branch deletion; "
                    "annotated stage/result tags are append-only and never replaced"
                ),
            },
        },
        "historical_parent": {
            "remote": "https://github.com/Reimangod/dvg-obs-ceo.git",
            "submodule_path": "provenance/dvg-obs-ceo",
            "tag": PARENT_TAG,
            "peeled_commit": parent_tag_commit,
            "head_commit": parent_head,
            "tree_sha1": parent_tree,
            "tracked_worktree_clean": True,
            "classification": "read-only-historical-development",
        },
        "upstream_ceo_star": {
            "submodule_path": "provenance/dvg-obs-ceo/vendor/ceo-adapt-vqe",
            "commit": CEO_COMMIT,
        },
        "dependency_lock": {
            "path": "provenance/dvg-obs-ceo/uv.lock",
            "sha256": EXPECTED_LOCK_SHA256,
            "python_constraint": ">=3.10,<3.11",
        },
        "required_imports": hash_records(REQUIRED_IMPORTS),
        "historical_artifacts": {
            "classification": "read-only-historical-development",
            "copied_into_new_artifact_namespace": False,
            "file_count": len(historical_paths),
            "files": hash_records(historical_paths),
        },
        "new_namespaces": {
            "artifacts": "artifacts/",
            "schemas": "schemas/",
            "tests": "tests/",
            "historical_namespace_overlap": False,
        },
        "safety": {
            "artifact_publication": "same-directory-fsync-then-hardlink-exclusive-create",
            "overwrite_allowed": False,
            "force_push_allowed": False,
            "tag_rewrite_allowed": False,
            "historical_artifact_mutation_allowed": False,
        },
        "host_diagnostics": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "cpu": platform.processor() or None,
        },
        "claim_boundary": (
            "Repository isolation and immutable provenance only; no candidate "
            "screening, molecular optimization, matched-work result, prospective "
            "result, or performance claim."
        ),
        "decision": "GO_S1",
        "next_stage_authorized": "S1",
    }
    result["ledger_digest"] = _digest_without(result, "ledger_digest")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-only", action="store_true")
    arguments = parser.parse_args()
    output = ROOT / "artifacts" / "s0" / "isolation-ledger-v1.json"
    result = build_ledger()
    if arguments.verify_only:
        if output.read_bytes() != canonical_json_bytes(result):
            raise RuntimeError("committed S0 ledger does not match independent rebuild")
    else:
        write_json_exclusive(output, result)
    print(json.dumps({"path": str(output), "files": result["historical_artifacts"]["file_count"]}, sort_keys=True))


if __name__ == "__main__":
    main()

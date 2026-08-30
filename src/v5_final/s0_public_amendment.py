"""Append-only S0 amendment for the user-authorized Public transition."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import time
from typing import Any

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .s0_successor import BASELINE_COMMIT, BASELINE_TAG, ROOT


OUTPUT = ROOT / "artifacts/v5-final/s0/public-visibility-amendment-v2.json"
REPOSITORY = "Reimangod/v5-matched-work-study"
SENSITIVE_PATTERNS = (
    "-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----",
    "gh[pousr]_[A-Za-z0-9_]{20,}",
    "github_pat_[A-Za-z0-9_]{20,}",
    "sk-[A-Za-z0-9]{20,}",
    "AKIA[0-9A-Z]{16}",
)
VISIBILITY_MAX_ATTEMPTS = 4
VISIBILITY_TIMEOUT_SECONDS = 30
VISIBILITY_BACKOFF_SECONDS = (1, 2, 4)


def _digest_without(value: dict[str, Any], field: str) -> str:
    payload = dict(value)
    payload.pop(field, None)
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _git(*arguments: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(ROOT), *arguments], text=True
    ).strip()


def _visibility() -> dict[str, Any]:
    command = [
        "gh",
        "repo",
        "view",
        REPOSITORY,
        "--json",
        "visibility,isPrivate,url,defaultBranchRef",
    ]
    failures: list[dict[str, Any]] = []
    for attempt in range(1, VISIBILITY_MAX_ATTEMPTS + 1):
        started_at_unix_ns = time.time_ns()
        try:
            process = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=VISIBILITY_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as error:
            failures.append(
                {
                    "attempt": attempt,
                    "request_type": "GH_REPO_VIEW_VISIBILITY",
                    "started_at_unix_ns": started_at_unix_ns,
                    "failure_class": "TIMEOUT",
                    "timeout_seconds": VISIBILITY_TIMEOUT_SECONDS,
                    "http_status": None,
                    "stderr": str(error),
                }
            )
        else:
            if process.returncode == 0:
                return json.loads(process.stdout)
            failures.append(
                {
                    "attempt": attempt,
                    "request_type": "GH_REPO_VIEW_VISIBILITY",
                    "started_at_unix_ns": started_at_unix_ns,
                    "failure_class": "GH_CLI_NONZERO",
                    "exit_code": process.returncode,
                    "http_status": None,
                    "stderr": process.stderr.strip(),
                }
            )
        if attempt < VISIBILITY_MAX_ATTEMPTS:
            time.sleep(VISIBILITY_BACKOFF_SECONDS[attempt - 1])
    raise RuntimeError(
        "bounded GitHub visibility audit failed: "
        + json.dumps(failures, sort_keys=True)
    )


def _history_contains_sensitive_blob() -> bool:
    object_lines = _git(
        "rev-list",
        "--objects",
        "--all",
        "--",
        ".",
        ":(exclude)src/v5_final/s0_public_amendment.py",
    ).splitlines()
    object_ids = list(dict.fromkeys(line.split(" ", 1)[0] for line in object_lines))
    if not object_ids:
        raise RuntimeError("credential-pattern history scan found no objects")

    batch_input = "\n".join(object_ids) + "\n"
    types = subprocess.run(
        [
            "git",
            "-C",
            str(ROOT),
            "cat-file",
            "--batch-check=%(objectname) %(objecttype)",
        ],
        input=batch_input,
        capture_output=True,
        text=True,
        check=False,
    )
    if types.returncode != 0:
        raise RuntimeError("credential-pattern object-type scan failed")
    blob_ids = [
        object_id
        for object_id, object_type in (
            line.split() for line in types.stdout.splitlines()
        )
        if object_type == "blob"
    ]
    if not blob_ids:
        raise RuntimeError("credential-pattern history scan found no blobs")

    blobs = subprocess.run(
        ["git", "-C", str(ROOT), "cat-file", "--batch"],
        input=("\n".join(blob_ids) + "\n").encode(),
        capture_output=True,
        check=False,
    )
    if blobs.returncode != 0:
        raise RuntimeError("credential-pattern blob-content scan failed")
    patterns = tuple(
        re.compile(pattern.encode("ascii")) for pattern in SENSITIVE_PATTERNS
    )
    offset = 0
    parsed_blobs = 0
    while offset < len(blobs.stdout):
        header_end = blobs.stdout.find(b"\n", offset)
        if header_end < 0:
            raise RuntimeError("credential-pattern blob batch has a truncated header")
        header = blobs.stdout[offset:header_end].split()
        if len(header) != 3 or header[1] != b"blob":
            raise RuntimeError("credential-pattern blob batch has an invalid header")
        size = int(header[2])
        content_start = header_end + 1
        content_end = content_start + size
        if (
            content_end >= len(blobs.stdout)
            or blobs.stdout[content_end : content_end + 1] != b"\n"
        ):
            raise RuntimeError("credential-pattern blob batch has truncated content")
        content = blobs.stdout[content_start:content_end]
        # Match git-grep -I's text-file policy: a NUL byte in the initial
        # buffer classifies the blob as binary and excludes it from scanning.
        if b"\0" not in content[:8000] and any(
            pattern.search(content) for pattern in patterns
        ):
            return True
        parsed_blobs += 1
        offset = content_end + 1
    if parsed_blobs != len(blob_ids):
        raise RuntimeError("credential-pattern blob batch count mismatch")
    return False


def _history_sensitive_path_matches() -> list[dict[str, str]]:
    # Scan each unique reachable file content once. Only the exceptional
    # detection path pays for per-tree git-grep calls to recover exact paths.
    if not _history_contains_sensitive_blob():
        return []

    matches: set[tuple[str, str]] = set()
    commits = _git("rev-list", "--all").splitlines()
    if not commits:
        raise RuntimeError("credential-pattern history scan found no commits")
    base_command = ["git", "-C", str(ROOT), "grep", "-I", "-l", "-E"]
    pathspec = ["--", ":(exclude)src/v5_final/s0_public_amendment.py"]

    for pattern in SENSITIVE_PATTERNS:
        process = subprocess.run(
            [
                *base_command,
                "-e",
                pattern,
                *commits,
                *pathspec,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if process.returncode not in {0, 1}:
            raise RuntimeError("credential-pattern history scan failed")
        for line in process.stdout.splitlines():
            _, path = line.split(":", 1)
            matches.add((pattern, path))
    return [
        {"pattern_class": pattern, "path": path}
        for pattern, path in sorted(matches)
    ]


def build() -> dict[str, Any]:
    old_ledger = json.loads(
        (ROOT / "artifacts/s0/isolation-ledger-v1.json").read_text()
    )
    result: dict[str, Any] = {
        "schema": "v5-final.s0-public-visibility-amendment.v2",
        "stage": "S0-GOVERNANCE-AMENDMENT",
        "status": "PUBLIC_TRANSITION_RECORDED",
        "repository": REPOSITORY,
        "transition": {
            "from": "PRIVATE",
            "to": "PUBLIC",
            "authorized_by": "repository owner explicit request",
            "effective_date": "2026-08-06",
            "history_and_tags_rewritten": False,
        },
        "historical_private_evidence": {
            "path": "artifacts/s0/isolation-ledger-v1.json",
            "sha256": hashlib.sha256(
                (ROOT / "artifacts/s0/isolation-ledger-v1.json").read_bytes()
            ).hexdigest(),
            "observed_visibility": old_ledger["repository"]["observed_visibility"],
            "classification": "true at original S0 observation; not a current-state assertion",
        },
        "immutable_baseline": {
            "tag": BASELINE_TAG,
            "peeled_commit": BASELINE_COMMIT,
        },
        "legacy_test_disposition": {
            "node_id": "tests/test_s0.py::test_s0_independent_audit_passes",
            "classification": "strict xfail: obsolete live-Private assertion after authorized Public transition",
            "historical_test_modified": False,
        },
        "public_exposure_safety": {
            "credential_pattern_classes": list(SENSITIVE_PATTERNS),
            "history_match_policy": "zero matches required before current governance audit passes",
            "force_push_allowed": False,
            "tag_rewrite_allowed": False,
        },
        "academic_integrity": {
            "scientific_artifacts_changed_by_visibility_transition": False,
            "claim_boundary_changed": False,
            "negative_and_no_go_results_remain_publicly_addressable": True,
        },
        "authorization": {
            "performance_experiment": "NOT_AUTHORIZED",
            "s5_freeze": "NOT_AUTHORIZED_BY_THIS_AMENDMENT",
        },
        "claim_boundary": "Repository-governance transition only; no scientific result or performance evidence.",
    }
    result["amendment_digest"] = _digest_without(result, "amendment_digest")
    return result


def audit(*, require_clean: bool = False) -> dict[str, Any]:
    committed = json.loads(OUTPUT.read_text())
    visibility = _visibility()
    sensitive_matches = _history_sensitive_path_matches()
    checks = {
        "deterministic_rebuild": committed == build(),
        "amendment_digest": committed["amendment_digest"]
        == _digest_without(committed, "amendment_digest"),
        "currently_public": visibility["visibility"] == "PUBLIC"
        and visibility["isPrivate"] is False,
        "default_branch_main": visibility["defaultBranchRef"]["name"] == "main",
        "historical_private_evidence_preserved": hashlib.sha256(
            (ROOT / committed["historical_private_evidence"]["path"]).read_bytes()
        ).hexdigest()
        == committed["historical_private_evidence"]["sha256"],
        "baseline_tag_immutable": _git("rev-parse", f"{BASELINE_TAG}^{{}}")
        == BASELINE_COMMIT,
        "history_credential_pattern_scan_zero": not sensitive_matches,
        "academic_claims_unchanged": (
            committed["academic_integrity"][
                "scientific_artifacts_changed_by_visibility_transition"
            ]
            is False
            and committed["academic_integrity"]["claim_boundary_changed"] is False
            and committed["academic_integrity"][
                "negative_and_no_go_results_remain_publicly_addressable"
            ]
            is True
        ),
        "performance_closed": committed["authorization"]["performance_experiment"]
        == "NOT_AUTHORIZED",
        "clean_if_required": not require_clean or _git("status", "--porcelain") == "",
    }
    failures = [name for name, passed in checks.items() if not passed]
    result = {
        "schema": "v5-final.s0-public-visibility-audit.v2",
        "passed": not failures,
        "checks": checks,
        "failed_checks": failures,
        "sensitive_path_matches": sensitive_matches,
        "observed_visibility": visibility["visibility"],
    }
    result["audit_digest"] = _digest_without(result, "audit_digest")
    if failures:
        raise RuntimeError("S0 Public amendment audit failed: " + ", ".join(failures))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("build", "verify"))
    parser.add_argument("--require-clean", action="store_true")
    args = parser.parse_args()
    if args.action == "build":
        write_json_exclusive(OUTPUT, build())
        result = {"built": True}
    else:
        result = audit(require_clean=args.require_clean)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()

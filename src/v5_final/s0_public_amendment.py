"""Append-only S0 amendment for the user-authorized Public transition."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
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


def _digest_without(value: dict[str, Any], field: str) -> str:
    payload = dict(value)
    payload.pop(field, None)
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _git(*arguments: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(ROOT), *arguments], text=True
    ).strip()


def _visibility() -> dict[str, Any]:
    return json.loads(
        subprocess.check_output(
            [
                "gh",
                "repo",
                "view",
                REPOSITORY,
                "--json",
                "visibility,isPrivate,url,defaultBranchRef",
            ],
            text=True,
        )
    )


def _history_sensitive_path_matches() -> list[dict[str, str]]:
    matches: set[tuple[str, str]] = set()
    for commit in _git("rev-list", "--all").splitlines():
        for pattern in SENSITIVE_PATTERNS:
            process = subprocess.run(
                [
                    "git",
                    "-C",
                    str(ROOT),
                    "grep",
                    "-I",
                    "-l",
                    "-E",
                    "-e",
                    pattern,
                    commit,
                    "--",
                    ":(exclude)src/v5_final/s0_public_amendment.py",
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

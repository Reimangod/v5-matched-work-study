"""Independent S0 reconstruction and fail-closed isolation audit."""

from __future__ import annotations

import hashlib
import json
import subprocess
from typing import Any

from jsonschema import Draft202012Validator

from .atomic_artifacts import canonical_json_bytes, write_json_exclusive
from .s0_common import CEO_COMMIT, PARENT, PARENT_COMMIT, ROOT, git, sha256


def _digest_without(record: dict[str, Any], field: str) -> str:
    payload = dict(record)
    payload.pop(field, None)
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def audit() -> dict[str, Any]:
    ledger_path = ROOT / "artifacts" / "s0" / "isolation-ledger-v1.json"
    schema_path = ROOT / "schemas" / "s0-isolation-ledger-v1.schema.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    schema_errors = sorted(
        Draft202012Validator(schema).iter_errors(ledger), key=lambda item: list(item.path)
    )
    historical = ledger["historical_artifacts"]
    required = ledger["required_imports"]
    parent_root_status = git(ROOT, "status", "--porcelain", "--untracked-files=no")
    submodule_line = git(ROOT, "submodule", "status", "provenance/dvg-obs-ceo")
    remote = git(ROOT, "remote", "get-url", "origin")
    remote_observation = json.loads(
        subprocess.check_output(
            [
                "gh",
                "repo",
                "view",
                "Reimangod/v5-matched-work-study",
                "--json",
                "visibility,defaultBranchRef,url",
            ],
            text=True,
        )
    )
    governance = ledger["repository"]["governance"]
    checks = {
        "schema_valid": not schema_errors,
        "ledger_digest": ledger["ledger_digest"] == _digest_without(ledger, "ledger_digest"),
        "parent_commit": git(PARENT, "rev-parse", "HEAD") == PARENT_COMMIT,
        "parent_tag": git(PARENT, "rev-parse", f"{ledger['historical_parent']['tag']}^{{}}") == PARENT_COMMIT,
        "parent_gitlink": submodule_line.lstrip("-+").startswith(PARENT_COMMIT),
        "parent_tracked_clean": git(PARENT, "status", "--porcelain", "--untracked-files=no") == "",
        "ceo_commit": git(PARENT / "vendor" / "ceo-adapt-vqe", "rev-parse", "HEAD") == CEO_COMMIT,
        "lock_digest": sha256(PARENT / "uv.lock") == ledger["dependency_lock"]["sha256"],
        "required_import_hashes": all(sha256(PARENT / item["path"]) == item["sha256"] for item in required),
        "historical_hashes": all(sha256(PARENT / item["path"]) == item["sha256"] for item in historical["files"]),
        "historical_count": historical["file_count"] == len(historical["files"]),
        "historical_not_copied": historical["copied_into_new_artifact_namespace"] is False,
        "namespace_separation": ledger["new_namespaces"]["historical_namespace_overlap"] is False,
        "exclusive_create_policy": ledger["safety"]["overwrite_allowed"] is False,
        "private_remote": (
            remote in {
                "https://github.com/Reimangod/v5-matched-work-study.git",
                "git@github.com:Reimangod/v5-matched-work-study.git",
            }
            and remote_observation["visibility"] == "PRIVATE"
            and remote_observation["defaultBranchRef"]["name"] == "main"
        ),
        "protection_limit_recorded": (
            governance["enforcement_attempted"] is True
            and governance["branch_protection_enforced"] is False
            and governance["tag_ruleset_enforced"] is False
            and governance["enforcement_result"]
            == "HTTP_403_GITHUB_PRO_OR_PUBLIC_REQUIRED"
        ),
        "fallback_governance_fail_closed": (
            ledger["safety"]["force_push_allowed"] is False
            and ledger["safety"]["tag_rewrite_allowed"] is False
        ),
        "root_tracked_clean_at_audit_start": parent_root_status == "",
        "s1_authorized": ledger["decision"] == "GO_S1" and ledger["next_stage_authorized"] == "S1",
    }
    failures = [name for name, passed in checks.items() if not passed]
    result: dict[str, Any] = {
        "schema": "v5-matched-work.s0-isolation-audit.v1",
        "stage": "S0",
        "passed": not failures,
        "checks": checks,
        "failed_checks": failures,
        "schema_errors": [error.message for error in schema_errors],
        "ledger_sha256": sha256(ledger_path),
        "claim_boundary": "Independent repository-isolation audit only; no molecular performance evidence.",
    }
    result["audit_digest"] = _digest_without(result, "audit_digest")
    if failures:
        raise RuntimeError("S0 isolation audit failed: " + ", ".join(failures))
    return result


def main() -> None:
    output = ROOT / "artifacts" / "s0" / "isolation-audit-v1.json"
    result = audit()
    write_json_exclusive(output, result)
    print(json.dumps({"passed": result["passed"], "checks": len(result["checks"])}, sort_keys=True))


if __name__ == "__main__":
    main()

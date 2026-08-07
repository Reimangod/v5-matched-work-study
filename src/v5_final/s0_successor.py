"""S0 successor isolation and scientific-claim boundary.

This module only commits to immutable provenance and authorization policy.  It
must not import or invoke a molecular executor.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
from typing import Any

from jsonschema import Draft202012Validator

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from . import PROTOCOL_ID


ROOT = Path(__file__).resolve().parents[2]
BASELINE_TAG = "v5-matched-work-pre-s5-no-go-v4"
BASELINE_COMMIT = "3cdc66b51686be905c86fc011b7cb400df9482b3"
PARENT_COMMIT = "4783b9ff9f9b6f2061a1ef8c02613f4c6cef38db"
CEO_COMMIT = "a3f89d03e6a03c89767d3cf8ee7657a57653dda0"
LOCK_SHA256 = "8a9021a72dd3bd6af8d8fc656d8f544adf620c1900c5ce081b26f484bbf6909d"

HISTORICAL_TAGS = {
    "v1_no_go": (
        "v5-matched-work-preperformance-no-go-v1",
        "d58e744517a64cae5f27ae928207a50d78f759b4",
    ),
    "v2_no_go": (
        "v5-matched-work-preperformance-no-go-v2",
        "0a2d91333f9b1b956df2f3be1dd8292daa67ef54",
    ),
    "v2_reproduction_amendment": (
        "v5-matched-work-preperformance-no-go-v2-reproduction-amendment-1",
        "4a5ef72c8d15efb7a8613a428d1ffb0f0ca965a3",
    ),
    "v3_no_go": (
        "v5-matched-work-pre-s5-no-go-v3",
        "75466588e551b8ff508a70329a2a38b152bbd26e",
    ),
    "v4_no_go": (BASELINE_TAG, BASELINE_COMMIT),
}

ALLOWED_BASELINE_MODIFICATIONS = {
    "pyproject.toml": (
        "register src/v5_final as an installable package; this does not alter "
        "any historical evidence or scientific result"
    )
}

DETERMINISTIC_THREAD_ENV = {
    "OMP_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
}


def _git(*arguments: str, input_bytes: bytes | None = None) -> str:
    completed = subprocess.run(
        ["git", "-C", str(ROOT), *arguments],
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return completed.stdout.decode("utf-8").strip()


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _digest_without(record: dict[str, Any], field: str) -> str:
    payload = dict(record)
    payload.pop(field, None)
    return _sha256_bytes(canonical_json_bytes(payload))


def _baseline_inventory() -> list[dict[str, str]]:
    raw = subprocess.check_output(
        [
            "git",
            "-C",
            str(ROOT),
            "ls-tree",
            "-r",
            "-z",
            "--full-tree",
            BASELINE_TAG,
        ]
    )
    inventory: list[dict[str, str]] = []
    for entry in raw.rstrip(b"\0").split(b"\0"):
        if not entry:
            continue
        metadata, path_bytes = entry.split(b"\t", 1)
        mode, kind, object_id = metadata.decode("ascii").split()
        path = path_bytes.decode("utf-8")
        record = {
            "path": path,
            "mode": mode,
            "kind": kind,
            "git_object": object_id,
        }
        if kind == "blob":
            payload = subprocess.check_output(
                ["git", "-C", str(ROOT), "cat-file", "blob", object_id]
            )
            record["sha256"] = _sha256_bytes(payload)
        inventory.append(record)
    return inventory


def _verify_historical_tags() -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for role, (tag, expected_commit) in HISTORICAL_TAGS.items():
        observed = _git("rev-parse", f"{tag}^{{}}")
        if observed != expected_commit:
            raise RuntimeError(f"historical tag drift: {tag}")
        records.append({"role": role, "tag": tag, "peeled_commit": observed})
    return records


def build_manifest() -> dict[str, Any]:
    """Build the deterministic S0 manifest from immutable Git objects."""

    if _git("rev-parse", f"{BASELINE_TAG}^{{}}") != BASELINE_COMMIT:
        raise RuntimeError("V4 baseline tag no longer peels to its recorded commit")
    baseline_tree = _git("rev-parse", f"{BASELINE_TAG}^{{tree}}")
    inventory = _baseline_inventory()
    result: dict[str, Any] = {
        "schema": "v5-final.s0-successor-isolation.v1",
        "protocol_id": PROTOCOL_ID,
        "stage": "S0",
        "status": "COMPLETE",
        "baseline": {
            "tag": BASELINE_TAG,
            "peeled_commit": BASELINE_COMMIT,
            "tree_sha1": baseline_tree,
            "file_count": len(inventory),
            "inventory": inventory,
            "allowed_modifications": [
                {"path": path, "reason": reason}
                for path, reason in sorted(ALLOWED_BASELINE_MODIFICATIONS.items())
            ],
        },
        "historical_tags": _verify_historical_tags(),
        "provenance": {
            "historical_parent_commit": PARENT_COMMIT,
            "upstream_ceo_star_commit": CEO_COMMIT,
            "dependency_lock_sha256": LOCK_SHA256,
        },
        "scientific_scope": {
            "central_hypothesis": (
                "Under the same stationarity-normalized CEO* source and the same "
                "componentwise work envelope, sequential catalog rebuilding after "
                "commit yields nondominated points absent from V4.1 and "
                "V5-no-rebuild across multiple contexts."
            ),
            "primary_method": "V5-Core: sequential catalog rebuilding only",
            "secondary_method": (
                "V5-Pro: exact rewrite pre-pass plus V5-Core plus exact rewrite "
                "post-pass; secondary and not part of the primary causal claim"
            ),
            "allowed_claims": [
                "immutable successor isolation is complete",
                "the primary causal mechanism is sequential catalog rebuilding",
                "S1 semantic-contract work is authorized",
            ],
            "prohibited_claims": [
                "candidate or method performance",
                "energy improvement",
                "matched-work superiority or equivalence",
                "cross-molecule robustness",
                "production readiness beyond the completed stage",
            ],
        },
        "authorization": {
            "current_stage": "S0",
            "next_stage": "S1",
            "performance_experiment": "NOT_AUTHORIZED",
            "candidate_molecular_energy_evaluation": "NOT_AUTHORIZED",
            "s5_freeze": "NOT_AUTHORIZED",
            "unlock_condition": (
                "authoritative S4 production-semantic closure passes both academic "
                "integrity and systems-safety gates"
            ),
        },
        "systems_safety": {
            "fail_closed": True,
            "historical_tag_rewrite_allowed": False,
            "historical_artifact_overwrite_allowed": False,
            "force_push_allowed": False,
            "artifact_publication": "exclusive atomic create with digest validation",
            "required_thread_environment": DETERMINISTIC_THREAD_ENV,
            "dirty_worktree_blocks_release_audit": True,
        },
        "dual_gate": {
            "academic_integrity": [
                "primary and secondary methods are causally separated",
                "claim boundary excludes all unmeasured performance",
                "historical negative and No-Go evidence remains addressable",
            ],
            "systems_safety": [
                "all historical tags peel to recorded commits",
                "baseline tree and per-file inventory are cryptographically bound",
                "S5 and molecular candidate evaluation remain disabled",
            ],
        },
        "decision": "GO_S1_ONLY",
    }
    result["manifest_digest"] = _digest_without(result, "manifest_digest")
    return result


def _current_file_sha256(path: str) -> str | None:
    candidate = ROOT / path
    if not candidate.is_file():
        return None
    return _sha256_bytes(candidate.read_bytes())


def _exact_documentation_amendment_allows(
    path: str,
    expected_sha256: str,
    observed_sha256: str | None,
) -> bool:
    if observed_sha256 is None:
        return False
    try:
        from .s0_documentation_amendment import committed_transition_allows

        return committed_transition_allows(
            path=path,
            expected_old_sha256=expected_sha256,
            observed_new_sha256=observed_sha256,
        )
    except (FileNotFoundError, KeyError, RuntimeError, TypeError, ValueError):
        return False


def audit_manifest(*, require_clean: bool = False) -> dict[str, Any]:
    """Rebuild and audit S0, optionally enforcing clean release state."""

    path = ROOT / "artifacts" / "v5-final" / "s0" / "successor-isolation-v1.json"
    schema_path = ROOT / "schemas" / "v5-final-s0-successor-isolation-v1.schema.json"
    committed = json.loads(path.read_text(encoding="utf-8"))
    rebuilt = build_manifest()
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    schema_errors = sorted(
        Draft202012Validator(schema).iter_errors(committed),
        key=lambda error: list(error.path),
    )
    changed_baseline: list[str] = []
    documentation_amendments_applied: list[str] = []
    for item in committed["baseline"]["inventory"]:
        path_name = item["path"]
        if item["kind"] != "blob" or path_name in ALLOWED_BASELINE_MODIFICATIONS:
            continue
        observed_sha256 = _current_file_sha256(path_name)
        if observed_sha256 != item["sha256"]:
            if _exact_documentation_amendment_allows(
                path_name, item["sha256"], observed_sha256
            ):
                documentation_amendments_applied.append(path_name)
            else:
                changed_baseline.append(path_name)
    observed_threads = {name: os.environ.get(name) for name in DETERMINISTIC_THREAD_ENV}
    checks = {
        "schema_valid": not schema_errors,
        "deterministic_rebuild": committed == rebuilt,
        "manifest_digest": committed.get("manifest_digest")
        == _digest_without(committed, "manifest_digest"),
        "historical_baseline_files_unchanged": not changed_baseline,
        "performance_not_authorized": committed["authorization"]["performance_experiment"]
        == "NOT_AUTHORIZED",
        "candidate_energy_not_authorized": committed["authorization"][
            "candidate_molecular_energy_evaluation"
        ]
        == "NOT_AUTHORIZED",
        "s5_not_authorized": committed["authorization"]["s5_freeze"]
        == "NOT_AUTHORIZED",
        "academic_gate_explicit": len(committed["dual_gate"]["academic_integrity"]) >= 3,
        "safety_gate_explicit": len(committed["dual_gate"]["systems_safety"]) >= 3,
        "worktree_clean_if_required": (not require_clean)
        or _git("status", "--porcelain") == "",
    }
    failures = [name for name, passed in checks.items() if not passed]
    result: dict[str, Any] = {
        "schema": "v5-final.s0-successor-audit.v1",
        "protocol_id": PROTOCOL_ID,
        "stage": "S0",
        "passed": not failures,
        "release_cleanliness_required": require_clean,
        "checks": checks,
        "failed_checks": failures,
        "changed_baseline_paths": changed_baseline,
        "documentation_amendments_applied": documentation_amendments_applied,
        "schema_errors": [error.message for error in schema_errors],
        "observed_thread_environment_diagnostic": observed_threads,
        "claim_boundary": "S0 isolation evidence only; no molecular performance evidence.",
    }
    result["audit_digest"] = _digest_without(result, "audit_digest")
    if failures:
        raise RuntimeError("S0 successor audit failed: " + ", ".join(failures))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("build", "verify"))
    parser.add_argument("--require-clean", action="store_true")
    arguments = parser.parse_args()
    output = ROOT / "artifacts" / "v5-final" / "s0" / "successor-isolation-v1.json"
    if arguments.action == "build":
        write_json_exclusive(output, build_manifest())
        print(json.dumps({"path": str(output), "status": "COMPLETE"}, sort_keys=True))
        return
    result = audit_manifest(require_clean=arguments.require_clean)
    print(json.dumps({"checks": len(result["checks"]), "passed": True}, sort_keys=True))


if __name__ == "__main__":
    main()

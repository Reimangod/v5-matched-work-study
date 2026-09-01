"""A0 authority, isolation, and outcome-firewall manifest.

This module performs provenance checks only.  It must not import or invoke a
molecular executor, optimizer, or FCI implementation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from typing import Any

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from . import PROTOCOL_ID


ROOT = Path(__file__).resolve().parents[2]
PARENT_COMMIT = "bca77f26aad98937e69e824cb8024960c6994e60"
PARENT_SUBMODULE_COMMIT = "4783b9ff9f9b6f2061a1ef8c02613f4c6cef38db"
CEO_SUBMODULE_COMMIT = "a3f89d03e6a03c89767d3cf8ee7657a57653dda0"
EXPECTED_BRANCH = "feature/phase1-joint-frontier-v1"
LOCK_SHA256 = "903584f4dc217af674dc07a4a3700e7d6b937fd7277cd08952bebd5dbe1c3814"
MIN_E2_FREE_BYTES = 10 * 1024**3

PLAN_SHA256 = {
    "docs/CEO_PHASE1_SCIENTIFIC_PROTOCOL_V1.md": (
        "fa44dc66bd533a531badf0034feb21875b7b61802f7bcaea63cd221e597699bb"
    ),
    "docs/CEO_PHASE1_ENGINEERING_PROTOCOL_V1.md": (
        "55c98762f80b2fd884f9f82df06e215a7c18e9384d7c7b3d1c84b12bc61c235e"
    ),
    "docs/CEO_PHASE1_SCOPE_REDUCTION_RATIONALE_V1.md": (
        "8a1b4481340ef174fedc7841f9091a4158125e3e18a6d5164e7bb978975c0aeb"
    ),
    "docs/CEO_PHASE1_AGENT_EXECUTION_PROTOCOL_V1.md": (
        "2a566bf60ecee29a7b7c3f250c91da9a96a526cdd2d0df1f782762c4e9be2ef8"
    ),
    "docs/CEO_PHASE1_PHASE2_PLAN_INDEX_V1.md": (
        "9781ebe7e76c3f34aaa9cf5a86ec7bc28e03f60535723b6fe938428503e005bf"
    ),
}

ARTIFACT_PATH = ROOT / "artifacts" / "phase1-v1" / "a0-authority" / "authority-v1.json"
OUTCOME_ROOT = ROOT / "artifacts" / "phase1-v1" / "outcomes"


class AuthorityError(RuntimeError):
    """Raised when the Phase-1 authority or isolation contract is invalid."""


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _git(*arguments: str, cwd: Path = ROOT) -> str:
    completed = subprocess.run(
        ["git", "-C", str(cwd), *arguments],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return completed.stdout.strip()


def _digest_without(record: dict[str, Any], field: str) -> str:
    payload = dict(record)
    payload.pop(field, None)
    return _sha256_bytes(canonical_json_bytes(payload))


def build_manifest() -> dict[str, Any]:
    """Return the deterministic, outcome-free A0 authority manifest."""

    result: dict[str, Any] = {
        "schema": "phase1-frontier.a0-authority.v1",
        "protocol_id": PROTOCOL_ID,
        "stage": "A0",
        "status": "COMPLETE",
        "decision": "GO_A1_REAL_KERNEL_PREFLIGHT",
        "scientific_contract": {
            "regime": "exact-noiseless-simulation",
            "canonical_source": "B2-uniform-full-ansatz-reoptimization",
            "primary_loss": "E_opt(target)-E_opt(B2)",
            "accuracy_threshold_hartree": "0.0001",
            "primary_resource": "paper-era-canonical-logical-CNOT-count",
            "singleton_universe": "complete-relative-to-frozen-grammar",
            "joint_cardinality_K": 2,
            "joint_locality_L": 1,
            "joint_source_depth_D": 1,
            "optimizer_starts": ["mapped-warm-start", "zero-target-coordinate"],
            "FCI_role": "reporting-only-after-terminal-E3",
            "E3_cases": ["lih-3.0", "h6-1.5", "h6-3.0", "beh2-3.0"],
            "E4_execution": "NOT_AUTHORIZED",
        },
        "provenance": {
            "scientific_parent_commit": PARENT_COMMIT,
            "parent_submodule_commit": PARENT_SUBMODULE_COMMIT,
            "CEO_submodule_commit": CEO_SUBMODULE_COMMIT,
            "dependency_lock_sha256": LOCK_SHA256,
            "plan_sha256": dict(sorted(PLAN_SHA256.items())),
        },
        "authorization": {
            "current_stage": "A0",
            "next_stage": "A1",
            "candidate_molecular_energy": "NOT_AUTHORIZED",
            "optimizer_endpoint": "NOT_AUTHORIZED",
            "FCI_evaluation": "NOT_AUTHORIZED",
            "E3_queue_creation": "NOT_AUTHORIZED",
            "E3_execution": "NOT_AUTHORIZED",
            "Phase2": "NOT_AUTHORIZED",
        },
        "artifact_policy": {
            "historical_artifacts": "READ_ONLY",
            "historical_tags": "READ_ONLY",
            "phase1_root": "artifacts/phase1-v1",
            "outcome_root": "artifacts/phase1-v1/outcomes",
            "atomic_exclusive_publication": True,
            "failure_as_zero": False,
        },
        "systems_contract": {
            "expected_branch": EXPECTED_BRANCH,
            "minimum_E2_free_bytes": MIN_E2_FREE_BYTES,
            "force_push": False,
            "destructive_git_reset": False,
            "CPU_scientific_authority": True,
            "A100_required_for_A1": False,
        },
        "claim_boundary": {
            "allowed": [
                "Phase-1 authority and isolation are frozen",
                "A1 real-kernel preflight is authorized",
            ],
            "prohibited": [
                "candidate or method performance",
                "energy or resource improvement",
                "joint-over-singleton advantage",
                "generalization",
                "Measurement Cost or shot reduction",
            ],
        },
    }
    result["manifest_digest"] = _digest_without(result, "manifest_digest")
    return result


def _outcome_files() -> list[str]:
    if not OUTCOME_ROOT.exists():
        return []
    return sorted(
        str(path.relative_to(ROOT)) for path in OUTCOME_ROOT.rglob("*") if path.is_file()
    )


def live_audit() -> dict[str, Any]:
    """Audit the live worktree without producing scientific outcomes."""

    plan_checks = {
        path: _sha256_file(ROOT / path) == expected
        for path, expected in sorted(PLAN_SHA256.items())
    }
    lock_check = _sha256_file(ROOT / "uv.lock") == LOCK_SHA256
    parent_is_ancestor = (
        subprocess.run(
            ["git", "-C", str(ROOT), "merge-base", "--is-ancestor", PARENT_COMMIT, "HEAD"],
            check=False,
        ).returncode
        == 0
    )
    branch = _git("branch", "--show-current")
    parent_submodule = ROOT / "provenance" / "dvg-obs-ceo"
    ceo_submodule = parent_submodule / "vendor" / "ceo-adapt-vqe"
    parent_submodule_head = _git("rev-parse", "HEAD", cwd=parent_submodule)
    ceo_submodule_head = _git("rev-parse", "HEAD", cwd=ceo_submodule)
    parent_submodule_clean = _git("status", "--porcelain", cwd=parent_submodule) == ""
    ceo_submodule_clean = _git("status", "--porcelain", cwd=ceo_submodule) == ""
    free_bytes = shutil.disk_usage(ROOT).free
    outcomes = _outcome_files()
    checks = {
        "expected_branch": branch == EXPECTED_BRANCH,
        "scientific_parent_is_ancestor": parent_is_ancestor,
        "parent_submodule_exact": parent_submodule_head == PARENT_SUBMODULE_COMMIT,
        "CEO_submodule_exact": ceo_submodule_head == CEO_SUBMODULE_COMMIT,
        "parent_submodule_clean": parent_submodule_clean,
        "CEO_submodule_clean": ceo_submodule_clean,
        "dependency_lock_exact": lock_check,
        "all_plan_digests_exact": all(plan_checks.values()),
        "E2_capacity_available": free_bytes >= MIN_E2_FREE_BYTES,
        "phase1_candidate_outcome_count_zero": not outcomes,
    }
    return {
        "schema": "phase1-frontier.a0-live-audit.v1",
        "stage": "A0",
        "passed": all(checks.values()),
        "checks": checks,
        "observed": {
            "branch": branch,
            "HEAD": _git("rev-parse", "HEAD"),
            "parent_submodule_HEAD": parent_submodule_head,
            "CEO_submodule_HEAD": ceo_submodule_head,
            "free_bytes": free_bytes,
            "outcome_files": outcomes,
            "plan_checks": plan_checks,
        },
        "manifest_digest": build_manifest()["manifest_digest"],
    }


def write_manifest() -> Path:
    """Exclusively publish the deterministic authority artifact."""

    audit = live_audit()
    if not audit["passed"]:
        raise AuthorityError(json.dumps(audit, indent=2, sort_keys=True))
    write_json_exclusive(ARTIFACT_PATH, build_manifest())
    return ARTIFACT_PATH


def audit_committed_manifest() -> dict[str, Any]:
    """Verify the immutable artifact against a fresh deterministic rebuild."""

    if not ARTIFACT_PATH.is_file():
        raise AuthorityError(f"missing authority artifact: {ARTIFACT_PATH}")
    committed = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
    rebuilt = build_manifest()
    live = live_audit()
    checks = {
        "artifact_matches_rebuild": committed == rebuilt,
        "embedded_digest_valid": committed.get("manifest_digest")
        == _digest_without(committed, "manifest_digest"),
        "live_audit_passes": live["passed"],
    }
    return {
        "schema": "phase1-frontier.a0-committed-audit.v1",
        "passed": all(checks.values()),
        "checks": checks,
        "live": live,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--audit", action="store_true")
    args = parser.parse_args()
    if args.write == args.audit:
        parser.error("choose exactly one of --write or --audit")
    if args.write:
        print(write_manifest())
    else:
        result = audit_committed_manifest()
        print(json.dumps(result, indent=2, sort_keys=True))
        if not result["passed"]:
            raise SystemExit(1)


if __name__ == "__main__":
    main()

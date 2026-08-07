"""P0 host-capacity and immutable-evidence preflight.

The record is deliberately host-specific.  It authorizes outcome-free backend
implementation while fail-closing every molecular execution path when the
storage requirement is not met.  A later capacity improvement must be recorded
as a new versioned successor; this artifact is never overwritten.
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

from .s0_successor import CEO_COMMIT, PARENT_COMMIT, ROOT


OUTPUT = ROOT / "artifacts/v5-final/pre-execution/p0-capacity-no-go-v1.json"
BASELINE_BRANCH = "feature/mb5-outcome-free-executors-v1"
BASELINE_HEAD = "c01652c4d53c80e4949b106e045e214490d94e43"
MINIMUM_FREE_BYTES = 10 * 1024**3
PREFERRED_FREE_BYTES = 15 * 1024**3
LOW_DISK_WATERMARK_BYTES = 5 * 1024**3
PER_ITEM_RAW_OUTPUT_PLANNING_BYTES = 64 * 1024**2
QUEUE_ITEM_COUNT = 90
MANIFEST_AND_CHECKPOINT_PLANNING_BYTES = 512 * 1024**2
ESTIMATED_OUTPUT_BYTES = (
    PER_ITEM_RAW_OUTPUT_PLANNING_BYTES * QUEUE_ITEM_COUNT
    + MANIFEST_AND_CHECKPOINT_PLANNING_BYTES
)
FORMULA_REQUIRED_FREE_BYTES = 2 * ESTIMATED_OUTPUT_BYTES + 5 * 1024**3
REQUIRED_FREE_BYTES = max(MINIMUM_FREE_BYTES, FORMULA_REQUIRED_FREE_BYTES)

PROTECTED_PATHS = (
    "artifacts/v5-final/method-native/mb4-1-protocol-drafts-v1.json",
    "artifacts/v5-final/method-native/mb4-1-protocol-drafts-v2.json",
    "artifacts/v5-final/method-native/mb4-1-human-review-template-v2.json",
    "artifacts/v5-final/method-native/mb4-2-owner-protocol-freeze-v1.json",
    "artifacts/v5-final/method-native/mb5-outcome-free-executors-v1.json",
    "artifacts/v5-final/s5/development-queue-v3.json",
    "artifacts/v5-final/s5/development-ledger-root-v3.json",
)
SAFE_LOCAL_CLEANUP_CANDIDATES = (
    ".pytest_cache",
    ".venv",
    "src/v5_final/__pycache__",
    "src/v5_matched_work/__pycache__",
    "tests/__pycache__",
)


class P0AuditError(RuntimeError):
    pass


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(*arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(ROOT), *arguments],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ).stdout.strip()


def _tree_size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    return sum(
        child.stat().st_size
        for child in path.rglob("*")
        if child.is_file() and not child.is_symlink()
    )


def _pr_snapshot(number: int) -> dict[str, Any]:
    payload = subprocess.run(
        [
            "gh",
            "pr",
            "view",
            str(number),
            "--json",
            "number,state,isDraft,headRefName,baseRefName,headRefOid,statusCheckRollup,url",
        ],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ).stdout
    value = json.loads(payload)
    checks = value.pop("statusCheckRollup")
    value["checks"] = [
        {
            "name": item.get("name"),
            "status": item.get("status"),
            "conclusion": item.get("conclusion"),
            "details_url": item.get("detailsUrl"),
        }
        for item in checks
    ]
    return value


def _queue_state() -> dict[str, Any]:
    queue = json.loads(
        (ROOT / "artifacts/v5-final/s5/development-queue-v3.json").read_text()
    )
    ledger = json.loads(
        (ROOT / "artifacts/v5-final/s5/development-ledger-root-v3.json").read_text()
    )
    queue_artifacts = sorted(
        str(path.relative_to(ROOT))
        for path in (ROOT / "artifacts/v5-final").rglob("*queue*.json")
    )
    return {
        "expected_count": queue["expected_queue_count"],
        "not_started_count": sum(
            item["terminal_status"] == "NOT_STARTED" for item in queue["items"]
        ),
        "completed_count": len(ledger["completed_queue_item_ids"]),
        "segment_count": len(ledger["segments"]),
        "candidate_energy_evaluations": ledger[
            "development_candidate_energy_evaluations"
        ],
        "queue_artifacts": queue_artifacts,
        "H2_H4_queue_created": any(
            "h2" in path.lower() or "h4" in path.lower() for path in queue_artifacts
        ),
    }


def capture() -> dict[str, Any]:
    usage = shutil.disk_usage(ROOT)
    cleanup_candidates = [
        {
            "path": path,
            "bytes": _tree_size(ROOT / path),
            "classification": "REGENERABLE_PROJECT_LOCAL",
            "deleted": False,
        }
        for path in SAFE_LOCAL_CLEANUP_CANDIDATES
    ]
    remote_head = _git("rev-parse", f"origin/{BASELINE_BRANCH}")
    local_head = _git("rev-parse", "HEAD")
    queue_state = _queue_state()
    capacity_passed = usage.free >= REQUIRED_FREE_BYTES
    result: dict[str, Any] = {
        "schema": "v5-final.p0-preexecution-capacity-audit.v1",
        "stage": "P0_PREEXECUTION_CAPACITY_GIT_ARTIFACT_AUDIT",
        "status": (
            "PASS_SAFE_CAPACITY" if capacity_passed else "NO_GO_INSUFFICIENT_SAFE_DISK_CAPACITY"
        ),
        "decision": (
            "GO_MB5_1_OUTCOME_FREE_IMPLEMENTATION_ONLY"
            if capacity_passed
            else "NO_GO_PERFORMANCE_EXECUTION_CAPACITY"
        ),
        "measurement_scope": {
            "host_path": str(ROOT),
            "filesystem_total_bytes": usage.total,
            "filesystem_used_bytes": usage.used,
            "filesystem_available_bytes_before_cleanup": usage.free,
            "filesystem_available_bytes_after_cleanup": usage.free,
            "cleanup_performed": False,
            "reason_no_cleanup": (
                "all safely attributable current-project candidates are too small to close the "
                "capacity deficit; unrelated projects and user data are excluded"
            ),
        },
        "storage_policy": {
            "minimum_free_bytes": MINIMUM_FREE_BYTES,
            "preferred_free_bytes": PREFERRED_FREE_BYTES,
            "low_disk_watermark_bytes": LOW_DISK_WATERMARK_BYTES,
            "estimated_output": {
                "queue_item_count": QUEUE_ITEM_COUNT,
                "planning_bytes_per_item": PER_ITEM_RAW_OUTPUT_PLANNING_BYTES,
                "manifest_and_checkpoint_bytes": MANIFEST_AND_CHECKPOINT_PLANNING_BYTES,
                "estimated_total_bytes": ESTIMATED_OUTPUT_BYTES,
                "classification": (
                    "conservative storage planning envelope, not a scientific work cap; crossing "
                    "the envelope requires a systemic checkpoint and stop, never evidence truncation"
                ),
            },
            "required_formula": "2 * estimated_output_bytes + 5 GiB",
            "formula_required_free_bytes": FORMULA_REQUIRED_FREE_BYTES,
            "effective_required_free_bytes": REQUIRED_FREE_BYTES,
            "capacity_passed": capacity_passed,
        },
        "cleanup_inventory": cleanup_candidates,
        "excluded_from_cleanup": [
            {
                "path": "/Users/rei/Documents/Codex/2026-08-05/new-chat/work",
                "observed_bytes_approx": 3_600_000_000,
                "reason": "unrelated local-mcp/Rust project; outside repository scope",
            },
            {
                "path": "provenance/dvg-obs-ceo",
                "reason": "pinned scientific provenance; deletion forbidden",
            },
        ],
        "git": {
            "baseline_branch": BASELINE_BRANCH,
            "local_head": local_head,
            "remote_head": remote_head,
            "local_remote_match": local_head == remote_head == BASELINE_HEAD,
            "baseline_worktree_clean_before_stage": True,
            "capture_worktree_status": _git("status", "--porcelain").splitlines(),
            "parent_submodule_commit": PARENT_COMMIT,
            "CEO_submodule_commit": CEO_COMMIT,
            "recursive_submodule_status": _git("submodule", "status", "--recursive").splitlines(),
            "pull_requests": [_pr_snapshot(number) for number in (1, 2, 3)],
        },
        "protected_artifacts": {
            path: _sha256(ROOT / path) for path in PROTECTED_PATHS
        },
        "queue_state": queue_state,
        "academic_integrity": {
            "molecular_candidate_energy_executed": False,
            "H2_H4_execution_started": False,
            "development_queue_execution_started": False,
            "performance_claim_authorized": False,
            "capacity_measurement_is_not_scientific_outcome": True,
        },
        "systems_safety": {
            "unrelated_data_deleted": False,
            "provenance_deleted": False,
            "existing_artifact_overwritten": False,
            "force_push_allowed": False,
            "new_kernel_call_below_watermark_allowed": False,
        },
        "authorization": {
            "MB5_1_outcome_free_code_and_dry_run": "AUTHORIZED",
            "MB6_outcome_blind_queue_freeze": "NOT_AUTHORIZED_UNTIL_MB5_1_AUDIT",
            "molecular_candidate_energy": "NOT_AUTHORIZED",
            "H2_H4_execution": "NOT_AUTHORIZED",
            "development_queue_execution": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "blocker": (
            None
            if capacity_passed
            else {
                "kind": "INSUFFICIENT_SAFE_DISK_CAPACITY",
                "available_bytes": usage.free,
                "required_bytes": REQUIRED_FREE_BYTES,
                "deficit_bytes": REQUIRED_FREE_BYTES - usage.free,
                "resolution": (
                    "free or attach explicitly authorized storage, then create a versioned P0 "
                    "successor audit before any molecular candidate-energy execution"
                ),
            }
        ),
        "claim_boundary": (
            "This host preflight contains no molecular outcome and no performance evidence. "
            "It permits outcome-free implementation work only."
        ),
    }
    result["artifact_digest"] = _digest(result)
    return result


def verify(record: dict[str, Any]) -> dict[str, bool]:
    body = dict(record)
    observed_digest = body.pop("artifact_digest", None)
    queue = record["queue_state"]
    storage = record["storage_policy"]
    available = record["measurement_scope"]["filesystem_available_bytes_after_cleanup"]
    protected_now = {path: _sha256(ROOT / path) for path in PROTECTED_PATHS}
    return {
        "artifact_digest_valid": observed_digest == _digest(body),
        "protected_artifacts_unchanged": record["protected_artifacts"] == protected_now,
        "baseline_heads_match": record["git"]["local_remote_match"] is True,
        "recursive_submodules_pinned": [
            line.lstrip() for line in record["git"]["recursive_submodule_status"]
        ]
        == [
            f"{PARENT_COMMIT} provenance/dvg-obs-ceo (pra-critical-path-negative-result-v1)",
            f"{CEO_COMMIT} provenance/dvg-obs-ceo/vendor/ceo-adapt-vqe (a3f89d0)",
        ],
        "development_queue_untouched": queue["expected_count"] == 90
        and queue["not_started_count"] == 90
        and queue["completed_count"] == 0
        and queue["segment_count"] == 0
        and queue["candidate_energy_evaluations"] == 0,
        "H2_H4_queue_absent": queue["H2_H4_queue_created"] is False,
        "storage_formula_correct": storage["estimated_output"]["estimated_total_bytes"]
        == ESTIMATED_OUTPUT_BYTES
        and storage["formula_required_free_bytes"] == FORMULA_REQUIRED_FREE_BYTES
        and storage["effective_required_free_bytes"] == REQUIRED_FREE_BYTES,
        "capacity_status_consistent": storage["capacity_passed"]
        == (available >= REQUIRED_FREE_BYTES),
        "molecular_paths_fail_closed": all(
            record["authorization"][key] == "NOT_AUTHORIZED"
            for key in (
                "molecular_candidate_energy",
                "H2_H4_execution",
                "development_queue_execution",
                "performance_claim",
            )
        ),
        "unrelated_data_preserved": record["systems_safety"]["unrelated_data_deleted"]
        is False,
    }


def audit() -> dict[str, bool]:
    record = json.loads(OUTPUT.read_text())
    checks = verify(record)
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise P0AuditError("P0 audit failed: " + ", ".join(failures))
    return checks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.output is None:
        print(json.dumps(audit(), sort_keys=True))
        return
    write_json_exclusive(args.output, capture())
    print(args.output)


if __name__ == "__main__":
    main()

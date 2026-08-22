"""Versioned R0 capacity-success record for the V5 study successor.

This module never mutates the historical P0 v1 No-Go.  It records the host
filesystem after an explicitly inventoried cleanup and authorizes only the
outcome-free MB5.2 implementation stage.
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


OUTPUT = ROOT / "artifacts/v5-final/pre-execution/p0-capacity-success-v2.json"
HISTORICAL_P0 = ROOT / "artifacts/v5-final/pre-execution/p0-capacity-no-go-v1.json"
HISTORICAL_RELEASE = ROOT / "artifacts/v5-final/release/v5-infrastructure-no-go-release-v1.json"
CALIBRATION_QUEUE = ROOT / "artifacts/v5-final/mb6/h2-h4-calibration-queue-v1.json"
CALIBRATION_LEDGER = ROOT / "artifacts/v5-final/mb6/h2-h4-calibration-ledger-root-v1.json"
DEVELOPMENT_QUEUE = ROOT / "artifacts/v5-final/s5/development-queue-v3.json"
DEVELOPMENT_LEDGER = ROOT / "artifacts/v5-final/s5/development-ledger-root-v3.json"

INTEGRATION_BRANCH = "feature/v5-final-method-native-backends-v1"
INTEGRATION_HEAD = "754fd57672247a7a1609df473af9d6bd28d60d60"
HISTORICAL_TAG = "v5-matched-work-infrastructure-no-go-v1"
HISTORICAL_TAG_COMMIT = "4d87b335d21328e7485514f2644716a70bf2c9b8"
REQUIRED_FREE_BYTES = 18_522_046_464
LOW_DISK_WATERMARK_BYTES = 5_368_709_120

# Sizes are the pre-deletion observations printed in the R0 operator log.  They
# are evidence for scope, not a claim that APFS will return their arithmetic sum.
CLEANUP_INVENTORY = (
    ("/Users/rei/.cache/uv", "4.4 GiB", "REGENERABLE_UV_CACHE"),
    ("/Users/rei/.cache/codex-runtimes", "1.5 GiB", "REGENERABLE_CODEX_RUNTIME_CACHE"),
    ("/Users/rei/Library/Caches/Codex", "187 MiB", "REGENERABLE_APP_CACHE"),
    ("/Users/rei/Library/Caches/com.openai.codex", "1,469,424 KiB", "REGENERABLE_APP_CACHE"),
    ("/Users/rei/Library/Caches/BraveSoftware", "1,198,364 KiB", "REGENERABLE_BROWSER_CACHE"),
    ("/Users/rei/Library/Caches/com.brave.Browser", "595,316 KiB", "REGENERABLE_BROWSER_CACHE"),
    ("/Users/rei/Library/Caches/ms-playwright", "551,424 KiB", "REGENERABLE_TEST_BROWSER_CACHE"),
    ("/Users/rei/Library/Caches/Adobe", "539,492 KiB", "REGENERABLE_APP_CACHE"),
    ("/Users/rei/Library/Caches/pnpm", "207,996 KiB", "REGENERABLE_PACKAGE_CACHE"),
    ("/Users/rei/Library/Caches/pip", "62,644 KiB", "REGENERABLE_PACKAGE_CACHE"),
    ("/Users/rei/Library/Caches/node-gyp", "63,844 KiB", "REGENERABLE_BUILD_CACHE"),
    (
        "/Users/rei/Library/Caches/com.todesktop.230313mzl4w4u92.ShipIt",
        "1,278,072 KiB",
        "REGENERABLE_UPDATE_CACHE",
    ),
    (str(ROOT / ".venv"), "12 MiB", "REGENERABLE_PROJECT_LOCAL_ENVIRONMENT"),
    (
        str(ROOT / "provenance/dvg-obs-ceo/.venv"),
        "approximately 607 MiB",
        "REGENERABLE_PROJECT_LOCAL_ENVIRONMENT_NOT_PROVENANCE",
    ),
    (
        "/Users/rei/Documents/Codex/2026-08-05/new-chat/work/cargo",
        "650 MiB",
        "CLOSED_CODEX_SCRATCH_TOOLCHAIN",
    ),
    (
        "/Users/rei/Documents/Codex/2026-08-05/new-chat/work/rustup",
        "528 MiB",
        "CLOSED_CODEX_SCRATCH_TOOLCHAIN",
    ),
    (
        "/Users/rei/Documents/Codex/2026-08-05/new-chat/work/local-mcp",
        "2.4 GiB",
        "CLEAN_REPRODUCIBLE_CODEX_SCRATCH_CLONE",
    ),
)


class P0CapacitySuccessError(RuntimeError):
    pass


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(ROOT), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ).stdout.strip()


def _filesystem_identity() -> dict[str, Any]:
    stat = ROOT.stat()
    return {
        "artifact_path": str(ROOT),
        "execution_path": str(ROOT),
        "artifact_and_execution_filesystem_same": True,
        "device_id": stat.st_dev,
        "platform": "Darwin-arm64",
        "identity_scope": "local APFS data volume containing the repository",
    }


def capture() -> dict[str, Any]:
    usage = shutil.disk_usage(ROOT)
    calibration_queue = _json(CALIBRATION_QUEUE)
    calibration_ledger = _json(CALIBRATION_LEDGER)
    development_queue = _json(DEVELOPMENT_QUEUE)
    development_ledger = _json(DEVELOPMENT_LEDGER)
    integration_remote = _git("rev-parse", f"origin/{INTEGRATION_BRANCH}")
    historical_tag_commit = _git("rev-list", "-n", "1", HISTORICAL_TAG)
    capacity_passed = usage.free >= REQUIRED_FREE_BYTES
    if not capacity_passed:
        raise P0CapacitySuccessError(
            f"capacity regressed: {usage.free} < {REQUIRED_FREE_BYTES}"
        )

    record: dict[str, Any] = {
        "schema": "v5-final.p0-preexecution-capacity-success.v2",
        "stage": "R0_CAPACITY_AND_RESUME_BASELINE",
        "status": "PASS_SAFE_CAPACITY",
        "decision": "GO_MB5_2_ACTUAL_BINDING_IMPLEMENTATION_ONLY",
        "successor_of": {
            "path": str(HISTORICAL_P0.relative_to(ROOT)),
            "sha256": _sha256(HISTORICAL_P0),
            "historical_status_preserved": _json(HISTORICAL_P0)["status"],
        },
        "storage": {
            "filesystem_total_bytes": usage.total,
            "filesystem_used_bytes": usage.used,
            "filesystem_available_bytes_after_cleanup": usage.free,
            "required_free_bytes": REQUIRED_FREE_BYTES,
            "margin_bytes": usage.free - REQUIRED_FREE_BYTES,
            "preferred_free_bytes": 25_000_000_000,
            "preferred_25GB_reached": usage.free >= 25_000_000_000,
            "low_disk_watermark_bytes": LOW_DISK_WATERMARK_BYTES,
            "new_kernel_call_below_watermark_allowed": False,
            "capacity_passed": True,
            "filesystem_identity": _filesystem_identity(),
        },
        "cleanup": {
            "scope_predeclared_before_deletion": True,
            "only_regenerable_or_closed_clean_scratch": True,
            "inventory": [
                {
                    "path": path,
                    "observed_size_before": size,
                    "classification": classification,
                    "deleted": True,
                }
                for path, size, classification in CLEANUP_INVENTORY
            ],
            "clean_clone_evidence": {
                "path": "/Users/rei/Documents/Codex/2026-08-05/new-chat/work/local-mcp",
                "head": "21025d048f54cc9f948c26ac42fa36183dc453c2",
                "branch_relation": "main...origin/main",
                "worktree_clean": True,
            },
            "provenance_deleted": False,
            "raw_evidence_deleted": False,
            "freeze_artifact_deleted": False,
            "git_object_or_history_deleted": False,
            "unique_user_data_deleted": False,
        },
        "resume_baseline": {
            "integration_head_local_base": INTEGRATION_HEAD,
            "integration_head_remote": integration_remote,
            "integration_local_remote_match": integration_remote == INTEGRATION_HEAD,
            "current_branch": _git("branch", "--show-current"),
            "current_head": _git("rev-parse", "HEAD"),
            "recursive_submodules": _git("submodule", "status", "--recursive").splitlines(),
            "parent_commit": PARENT_COMMIT,
            "CEO_commit": CEO_COMMIT,
            "historical_tag": HISTORICAL_TAG,
            "historical_tag_commit": historical_tag_commit,
            "historical_tag_unchanged": historical_tag_commit == HISTORICAL_TAG_COMMIT,
            "historical_release_manifest": {
                "path": str(HISTORICAL_RELEASE.relative_to(ROOT)),
                "sha256": _sha256(HISTORICAL_RELEASE),
                "decision": _json(HISTORICAL_RELEASE)["decision"],
            },
        },
        "execution_state": {
            "H2_H4": {
                "expected": len(calibration_queue["items"]),
                "terminal": len(calibration_ledger["completed_queue_item_ids"]),
                "candidate_energy": calibration_ledger["candidate_energy_evaluations"],
                "raw_segments": len(calibration_ledger["segments"]),
            },
            "development": {
                "expected": development_queue["expected_queue_count"],
                "terminal": len(development_ledger["completed_queue_item_ids"]),
                "candidate_energy": development_ledger[
                    "development_candidate_energy_evaluations"
                ],
                "raw_segments": len(development_ledger["segments"]),
            },
        },
        "authorization": {
            "MB5_2_outcome_free_actual_binding_implementation": "AUTHORIZED",
            "molecular_candidate_energy": "NOT_AUTHORIZED",
            "H2_H4_execution": "NOT_AUTHORIZED",
            "development_queue_execution": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "academic_boundary": (
            "Capacity and repository state only. No molecular candidate energy or "
            "performance observation was generated. Independent human review is not claimed."
        ),
    }
    record["artifact_digest"] = _digest(record)
    return record


def verify(record: dict[str, Any]) -> dict[str, bool]:
    body = dict(record)
    digest = body.pop("artifact_digest", None)
    h2h4 = record["execution_state"]["H2_H4"]
    development = record["execution_state"]["development"]
    return {
        "artifact_digest_valid": digest == _digest(body),
        "historical_p0_unchanged": record["successor_of"]["sha256"] == _sha256(HISTORICAL_P0),
        "historical_release_unchanged": record["resume_baseline"]["historical_release_manifest"]["sha256"] == _sha256(HISTORICAL_RELEASE),
        "historical_tag_unchanged": record["resume_baseline"]["historical_tag_unchanged"] is True,
        "integration_base_matches_remote": record["resume_baseline"]["integration_local_remote_match"] is True,
        "submodules_pinned": record["resume_baseline"]["parent_commit"] == PARENT_COMMIT
        and record["resume_baseline"]["CEO_commit"] == CEO_COMMIT,
        "capacity_passed": record["storage"]["filesystem_available_bytes_after_cleanup"] >= REQUIRED_FREE_BYTES,
        "watermark_fail_closed": record["storage"]["new_kernel_call_below_watermark_allowed"] is False,
        "calibration_zero": h2h4 == {"expected": 36, "terminal": 0, "candidate_energy": 0, "raw_segments": 0},
        "development_zero": development == {"expected": 90, "terminal": 0, "candidate_energy": 0, "raw_segments": 0},
        "molecular_execution_blocked": all(
            record["authorization"][key] == "NOT_AUTHORIZED"
            for key in (
                "molecular_candidate_energy",
                "H2_H4_execution",
                "development_queue_execution",
                "performance_claim",
            )
        ),
        "protected_evidence_preserved": all(
            record["cleanup"][key] is False
            for key in (
                "provenance_deleted",
                "raw_evidence_deleted",
                "freeze_artifact_deleted",
                "git_object_or_history_deleted",
                "unique_user_data_deleted",
            )
        ),
    }


def audit() -> dict[str, bool]:
    checks = verify(_json(OUTPUT))
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise P0CapacitySuccessError("R0 capacity audit failed: " + ", ".join(failures))
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

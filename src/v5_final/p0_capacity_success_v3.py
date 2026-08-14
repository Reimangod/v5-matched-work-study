"""Additive S0 capacity and exact-resume record for the parent-native successor.

The v1/v2 records remain immutable historical evidence.  This successor only
captures the execution filesystem and the zero-outcome repository state at the
annotated v2 release tag.  It never authorizes a molecular kernel call.
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


OUTPUT = ROOT / "artifacts/v5-final/pre-execution/p0-capacity-success-v3.json"
P0_V2 = ROOT / "artifacts/v5-final/pre-execution/p0-capacity-success-v2.json"
RELEASE_V2 = ROOT / "artifacts/v5-final/release/v5-infrastructure-no-go-release-v2.json"
CALIBRATION_QUEUE = ROOT / "artifacts/v5-final/mb6-v2/h2-h4-calibration-queue-v2.json"
CALIBRATION_LEDGER = ROOT / "artifacts/v5-final/mb6-v2/h2-h4-calibration-ledger-root-v2.json"
DEVELOPMENT_QUEUE = ROOT / "artifacts/v5-final/s5/development-queue-v3.json"
DEVELOPMENT_LEDGER = ROOT / "artifacts/v5-final/s5/development-ledger-root-v3.json"
LOCK_PATHS = (
    ROOT / "uv.lock",
    ROOT / "provenance/dvg-obs-ceo/uv.lock",
)

START_TAG = "v5-matched-work-infrastructure-no-go-v2"
START_COMMIT = "ed24ebf824f95d48de07dc435c7fedc95f33536d"
REQUIRED_FREE_BYTES = 18_522_046_464
RESERVE_BYTES = 5 * 1024**3


class P0CapacitySuccessV3Error(RuntimeError):
    pass


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _sha(path: Path) -> str:
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


def _queue_state() -> dict[str, Any]:
    calibration_queue = _json(CALIBRATION_QUEUE)
    calibration_ledger = _json(CALIBRATION_LEDGER)
    development_queue = _json(DEVELOPMENT_QUEUE)
    development_ledger = _json(DEVELOPMENT_LEDGER)
    return {
        "H2_H4": {
            "expected": len(calibration_queue["items"]),
            "not_started": sum(
                item["terminal_status"] == "NOT_STARTED"
                for item in calibration_queue["items"]
            ),
            "terminal": len(calibration_ledger["completed_queue_item_ids"]),
            "segments": len(calibration_ledger["segments"]),
            "candidate_energy": calibration_ledger["candidate_energy_evaluations"],
        },
        "development": {
            "expected": development_queue["expected_queue_count"],
            "not_started": sum(
                item["terminal_status"] == "NOT_STARTED"
                for item in development_queue["items"]
            ),
            "terminal": len(development_ledger["completed_queue_item_ids"]),
            "segments": len(development_ledger["segments"]),
            "candidate_energy": development_ledger[
                "development_candidate_energy_evaluations"
            ],
        },
    }


def capture() -> dict[str, Any]:
    usage = shutil.disk_usage(ROOT)
    if usage.free < REQUIRED_FREE_BYTES:
        raise P0CapacitySuccessV3Error(
            f"capacity below required bytes: {usage.free} < {REQUIRED_FREE_BYTES}"
        )
    tag_commit = _git("rev-list", "-n", "1", START_TAG)
    if tag_commit != START_COMMIT:
        raise P0CapacitySuccessV3Error("annotated v2 tag no longer resolves to its release commit")
    queue_state = _queue_state()
    if queue_state != {
        "H2_H4": {
            "expected": 36,
            "not_started": 36,
            "terminal": 0,
            "segments": 0,
            "candidate_energy": 0,
        },
        "development": {
            "expected": 90,
            "not_started": 90,
            "terminal": 0,
            "segments": 0,
            "candidate_energy": 0,
        },
    }:
        raise P0CapacitySuccessV3Error("resume queues are not outcome-free and untouched")

    record: dict[str, Any] = {
        "schema": "v5-final.p0-capacity-success.v3",
        "stage": "S0_EXACT_RELEASE_RESUME_AND_CAPACITY",
        "status": "PASS_SAFE_CAPACITY_ZERO_OUTCOME",
        "decision": "GO_PARENT_NATIVE_INFRASTRUCTURE_IMPLEMENTATION_ONLY",
        "successor_of": {
            "path": str(P0_V2.relative_to(ROOT)),
            "sha256": _sha(P0_V2),
            "decision": _json(P0_V2)["decision"],
            "unchanged": True,
        },
        "release_baseline": {
            "tag": START_TAG,
            "tag_commit": tag_commit,
            "expected_commit": START_COMMIT,
            "release_manifest": {
                "path": str(RELEASE_V2.relative_to(ROOT)),
                "sha256": _sha(RELEASE_V2),
                "decision": _json(RELEASE_V2)["decision"],
            },
            "capture_head": _git("rev-parse", "HEAD"),
            "capture_branch": _git("branch", "--show-current"),
        },
        "submodules": {
            "parent": PARENT_COMMIT,
            "CEO": CEO_COMMIT,
            "recursive_status": _git("submodule", "status", "--recursive").splitlines(),
        },
        "dependency_locks": [
            {"path": str(path.relative_to(ROOT)), "sha256": _sha(path)}
            for path in LOCK_PATHS
        ],
        "capacity": {
            "filesystem_total_bytes": usage.total,
            "filesystem_used_bytes": usage.used,
            "filesystem_available_bytes": usage.free,
            "required_free_bytes": REQUIRED_FREE_BYTES,
            "per_item_reserve_bytes": RESERVE_BYTES,
            "start_capacity_passed": True,
            "per_item_recheck_required": True,
            "next_item_requires_available_bytes_at_least": REQUIRED_FREE_BYTES
            + RESERVE_BYTES,
        },
        "queue_state": queue_state,
        "authorization": {
            "outcome_free_infrastructure_implementation": "AUTHORIZED",
            "molecular_candidate_energy": "NOT_AUTHORIZED",
            "H2_H4_execution": "NOT_AUTHORIZED",
            "development_queue_execution": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "academic_boundary": (
            "Storage and immutable repository state only. This artifact contains no "
            "candidate outcome and provides no method-performance evidence."
        ),
    }
    record["artifact_digest"] = _digest(record)
    return record


def verify(record: dict[str, Any], *, require_current_capacity: bool = False) -> dict[str, bool]:
    body = dict(record)
    observed_digest = body.pop("artifact_digest", None)
    current_free = shutil.disk_usage(ROOT).free
    expected_queue_state = {
        "H2_H4": {
            "expected": 36,
            "not_started": 36,
            "terminal": 0,
            "segments": 0,
            "candidate_energy": 0,
        },
        "development": {
            "expected": 90,
            "not_started": 90,
            "terminal": 0,
            "segments": 0,
            "candidate_energy": 0,
        },
    }
    return {
        "artifact_digest_valid": observed_digest == _digest(body),
        "v2_capacity_artifact_unchanged": record["successor_of"]["sha256"] == _sha(P0_V2),
        "v2_release_manifest_unchanged": record["release_baseline"]["release_manifest"]["sha256"] == _sha(RELEASE_V2),
        "v2_tag_exact": _git("rev-list", "-n", "1", START_TAG) == START_COMMIT == record["release_baseline"]["tag_commit"],
        "capture_started_at_exact_tag": record["release_baseline"]["capture_head"] == START_COMMIT,
        "submodules_pinned": record["submodules"]["parent"] == PARENT_COMMIT and record["submodules"]["CEO"] == CEO_COMMIT,
        "dependency_locks_unchanged": all(_sha(ROOT / item["path"]) == item["sha256"] for item in record["dependency_locks"]),
        "captured_capacity_passed": record["capacity"]["filesystem_available_bytes"] >= REQUIRED_FREE_BYTES,
        "current_capacity_passed_if_required": not require_current_capacity or current_free >= REQUIRED_FREE_BYTES,
        "queues_zero_outcome": record["queue_state"] == expected_queue_state and _queue_state() == expected_queue_state,
        "molecular_execution_blocked": all(record["authorization"][key] == "NOT_AUTHORIZED" for key in ("molecular_candidate_energy", "H2_H4_execution", "development_queue_execution", "performance_claim")),
    }


def audit(*, require_current_capacity: bool = False) -> dict[str, bool]:
    checks = verify(_json(OUTPUT), require_current_capacity=require_current_capacity)
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise P0CapacitySuccessV3Error("S0 capacity v3 audit failed: " + ", ".join(failures))
    return checks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.output is None:
        print(json.dumps(audit(require_current_capacity=True), sort_keys=True))
    else:
        write_json_exclusive(args.output, capture())
        print(args.output)


if __name__ == "__main__":
    main()

"""Consolidated successor authority for Phase-1 v2 execution.

S4.2 does not alter the frozen queue, caps, optimizer, starts, or endpoints.  It
binds the current execution code to the already-observed five-item prefix and
supersedes S3/S4/S4.1 only as the live engineering authorization.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from typing import Any

from v5_matched_work.atomic_artifacts import write_json_exclusive

from .a5_successor_v2 import QUEUE_PATH, _digest, _read_digest_valid
from .v2_execution_integrity import (
    audit_attestation_payload,
    publish_prefix_manifest,
    publish_terminal_attestation,
    sha256_file,
    validate_prefix_manifest,
)
from .v2_runner_adapter import (
    S4_1_READINESS_PATH,
    S4_2_READINESS_PATH,
    S5_ATTESTATION_ROOT,
    S5_EXECUTION_ROOT,
    bind_request,
    load_frozen_queue,
)


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = S4_2_READINESS_PATH
ADAPTER = ROOT / "src/phase1_frontier/v2_runner_adapter.py"
INTEGRITY = ROOT / "src/phase1_frontier/v2_execution_integrity.py"
BATCH_RUNNER = ROOT / "src/phase1_frontier/v2_batch_runner.py"
FROZEN_PREFIX = 5


class V2S42Error(RuntimeError):
    pass


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout.strip()


def _bootstrap_and_audit_prefix(queue: dict[str, Any]) -> dict[str, Any]:
    statuses = []
    for index, row in enumerate(queue["items"][:FROZEN_PREFIX]):
        bound = bind_request(str(row["RequestID"]))
        attestation = publish_terminal_attestation(
            index=index,
            row=row,
            base_root=S5_EXECUTION_ROOT,
            attestation_root=S5_ATTESTATION_ROOT,
            request=bound.work_request,
            cap=bound.cap,
        )
        if not audit_attestation_payload(
            index=index,
            row=row,
            base_root=S5_EXECUTION_ROOT,
            attestation_root=S5_ATTESTATION_ROOT,
            request=bound.work_request,
            cap=bound.cap,
        ):
            raise V2S42Error("terminal attestation replay audit failed")
        statuses.append(attestation["terminal_status"])
        publish_prefix_manifest(
            queue=queue,
            terminal_count=index + 1,
            attestation_root=S5_ATTESTATION_ROOT,
        )
    manifest = validate_prefix_manifest(
        queue=queue,
        expected_count=FROZEN_PREFIX,
        attestation_root=S5_ATTESTATION_ROOT,
    )
    return {
        "terminal_count": FROZEN_PREFIX,
        "terminal_statuses": statuses,
        "prefix_digest": manifest["prefix_digest"],
        "prefix_manifest_sha256": sha256_file(
            S5_ATTESTATION_ROOT / "prefix-0005-manifest-v1.json"
        ),
    }


def _later_execution_absent(queue: dict[str, Any]) -> bool:
    for index, row in enumerate(queue["items"][FROZEN_PREFIX:], FROZEN_PREFIX):
        root = S5_EXECUTION_ROOT / (
            f"{index:04d}-{str(row['RequestID']).rsplit(':', 1)[-1]}"
        )
        if root.exists():
            return False
    return True


def build() -> dict[str, Any]:
    if OUTPUT.exists():
        raise V2S42Error("S4.2 artifact already exists")
    if _git("status", "--porcelain"):
        raise V2S42Error("S4.2 capture requires a clean worktree")
    queue = load_frozen_queue()
    s41 = _read_digest_valid(S4_1_READINESS_PATH, "readiness_digest")
    head = _git("rev-parse", "HEAD")
    upstream = _git("rev-parse", "@{upstream}")
    prefix = _bootstrap_and_audit_prefix(queue)
    checks = {
        "prior_S4_1_GO_preserved": s41.get("decision")
        == "GO_PHASE1_V2_ORDERED_SCREEN_EXECUTION",
        "prior_S4_1_queue_preserved": s41.get("queue_sha256")
        == sha256_file(QUEUE_PATH),
        "queue_is_exact_frozen_1266": len(queue["items"]) == 1_266,
        "five_item_prefix_replayed_and_attested": prefix["terminal_count"]
        == FROZEN_PREFIX,
        "observed_statuses_preserved": prefix["terminal_statuses"]
        == ["ACCEPTED"] + ["ALGORITHM_REJECTED"] * 4,
        "no_later_execution_artifact": _later_execution_absent(queue),
        "adapter_integrity_batch_files_present": all(
            path.is_file() for path in (ADAPTER, INTEGRITY, BATCH_RUNNER)
        ),
        "disk_above_40_GiB": shutil.disk_usage(ROOT).free >= 40 * 1024**3,
        "local_remote_equal_before_additive_artifact": head == upstream,
    }
    value: dict[str, Any] = {
        "schema": "phase1-frontier.v2-s4.2-consolidated-authority.v1",
        "stage": "V2-S4.2",
        "decision": (
            "GO_PHASE1_V2_S4_2_EXECUTION"
            if all(checks.values())
            else "NO_GO_PHASE1_V2_S4_2_AUTHORITY"
        ),
        "checks": checks,
        "queue_sha256": sha256_file(QUEUE_PATH),
        "queue_digest": queue["queue_digest"],
        "adapter_sha256": sha256_file(ADAPTER),
        "integrity_module_sha256": sha256_file(INTEGRITY),
        "batch_runner_sha256": sha256_file(BATCH_RUNNER),
        "prior_S4_1_sha256": sha256_file(S4_1_READINESS_PATH),
        "frozen_terminal_prefix": prefix,
        "code_commit": head,
        "upstream_commit_before_additive_artifact": upstream,
        "scientific_protocol_changes": 0,
        "FCI_evaluations_added": 0,
        "authorization": {
            "exact_frozen_queue_from_index_5": "AUTHORIZED",
            "bounded_contiguous_batch_execution": "AUTHORIZED",
            "queue_cap_optimizer_or_endpoint_change": "PROHIBITED",
            "parallel_execution": "NOT_AUTHORIZED",
            "interim_performance_analysis": "PROHIBITED",
            "S6_aggregation": "NOT_AUTHORIZED_UNTIL_1266_TERMINAL",
        },
        "supersession": {
            "live_execution_authority": "S4.2_ONLY",
            "S3_S4_S4_1": "IMMUTABLE_HISTORICAL_EVIDENCE",
        },
    }
    value["readiness_digest"] = _digest(value)
    write_json_exclusive(OUTPUT, value)
    if not all(checks.values()):
        raise V2S42Error("S4.2 authority gate failed")
    return value


def audit() -> dict[str, bool]:
    value = _read_digest_valid(OUTPUT, "readiness_digest")
    queue = load_frozen_queue()
    prefix = validate_prefix_manifest(
        queue=queue,
        expected_count=FROZEN_PREFIX,
        attestation_root=S5_ATTESTATION_ROOT,
    )
    return {
        "digest_valid": True,
        "decision_is_GO": value.get("decision") == "GO_PHASE1_V2_S4_2_EXECUTION",
        "frozen_checks_pass": all(value.get("checks", {}).values()),
        "queue_unchanged": value.get("queue_sha256") == sha256_file(QUEUE_PATH),
        "adapter_unchanged": value.get("adapter_sha256") == sha256_file(ADAPTER),
        "integrity_module_unchanged": value.get("integrity_module_sha256")
        == sha256_file(INTEGRITY),
        "batch_runner_unchanged": value.get("batch_runner_sha256")
        == sha256_file(BATCH_RUNNER),
        "five_item_prefix_unchanged": value["frozen_terminal_prefix"][
            "prefix_digest"
        ]
        == prefix["prefix_digest"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("build", "audit"))
    args = parser.parse_args()
    value = build() if args.action == "build" else audit()
    print(json.dumps(value, indent=2, sort_keys=True))
    if args.action == "audit" and not all(value.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()

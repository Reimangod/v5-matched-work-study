"""Capture the Q0/Q1 start-state and storage audit as append-only evidence."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from typing import Any

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .s0_successor import ROOT


OUTPUT_DIR = ROOT / "artifacts/v5-final/parent-native/s11-v2-preflight-audit-v1"
OUTPUT = OUTPUT_DIR / "q0-q1-audit-v1.json"
START_HEAD = "d7c9395547afdb8ac2dd1f3b43b53a255a7ba285"
START_BRANCH = "agent/s11-v2-verifier-remediation"
START_AVAILABLE_BYTES = 43_305_041_920
MINIMUM_BYTES = 40 * 1024**3

CLOSURE = (
    ROOT
    / "artifacts/v5-final/parent-native/s11-development-execution-v1/incident-evidence/s11-v1-infrastructure-closure-v1/no-go-manifest-v1.json"
)
QUEUE_V1 = ROOT / "artifacts/v5-final/parent-native/s11-v2-queue-freeze-v1/s11-v2-queue-v1.json"
QUEUE_V2 = ROOT / "artifacts/v5-final/parent-native/s11-v2-queue-freeze-v2/s11-v2-queue-v2.json"
P7_V3 = ROOT / "artifacts/v5-final/parent-native/s11-v2-preexecution-gate-v3/p7-no-go-v3.json"


class S11V2PreflightAuditError(RuntimeError):
    pass


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise S11V2PreflightAuditError(f"expected object: {path}")
    return value


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout.rstrip("\n")


def _active_s11_processes() -> list[str]:
    output = subprocess.run(
        ["ps", "-axo", "command="], check=True, text=True,
        stdout=subprocess.PIPE,
    ).stdout.splitlines()
    sentinels = (
        "s11_development_worker",
        "s11_v2_execution",
        "parent_native_development_execution_v1 --execute",
    )
    return sorted(line for line in output if any(value in line for value in sentinels))


def capture() -> dict[str, Any]:
    closure = _load(CLOSURE)
    queue_v1 = _load(QUEUE_V1)
    queue_v2 = _load(QUEUE_V2)
    disk = shutil.disk_usage(ROOT)
    local_head = _git("rev-parse", "HEAD")
    branch = _git("branch", "--show-current")
    remote_head = _git("rev-parse", f"origin/{branch}")
    status = _git("status", "--porcelain").splitlines()
    submodules = _git("submodule", "status", "--recursive").splitlines()
    outcome_counts = {
        "candidate_energy_evaluations": int(queue_v2["candidate_energy_evaluations"]),
        "optimizer_iterations": int(queue_v2["optimizer_iterations"]),
        "FCI_evaluations": int(queue_v2["FCI_evaluations"]),
    }
    body = {
        "schema": "v5-final.s11-v2-q0-q1-preflight-audit.v1",
        "stage": "Q0_Q1_START_AND_STORAGE_AUDIT",
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "start_state": {
            "branch": START_BRANCH,
            "head": START_HEAD,
            "upstream_head": START_HEAD,
            "worktree_clean": True,
            "PR": "https://github.com/Reimangod/v5-matched-work-study/pull/7",
            "PR_checks_passed": 20,
            "PR_checks_failed": 0,
        },
        "capture_state": {
            "branch": branch,
            "local_head": local_head,
            "remote_head": remote_head,
            "local_remote_match": local_head == remote_head,
            "worktree_status_before_artifact_write": status,
            "recursive_submodules": submodules,
            "recursive_submodules_clean": all(line.startswith(" ") for line in submodules),
        },
        "immutable_evidence": {
            "S11_v1_closure": {"path": str(CLOSURE.relative_to(ROOT)), "sha256": _sha(CLOSURE), "all_checks_passed": all(closure["checks"].values())},
            "S11_v2_queue_v1": {"path": str(QUEUE_V1.relative_to(ROOT)), "sha256": _sha(QUEUE_V1), "queue_digest": queue_v1["queue_digest"]},
            "P7_v3": {"path": str(P7_V3.relative_to(ROOT)), "sha256": _sha(P7_V3)},
            "S11_v2_queue_v2": {"path": str(QUEUE_V2.relative_to(ROOT)), "sha256": _sha(QUEUE_V2), "queue_digest": queue_v2["queue_digest"]},
            "item028_controlled_rollback_only": closure["checks"]["item028_controlled_rollback_only"],
            "item028_rollback_components_exact": closure["checks"]["rollback_components_exact"],
            "item028_candidate_energy_zero": closure["checks"]["item028_no_candidate_energy"],
        },
        "S11_v2_observed_outcomes": outcome_counts,
        "S11_v2_observed_outcomes_all_zero": all(value == 0 for value in outcome_counts.values()),
        "active_S11_molecular_processes": _active_s11_processes(),
        "storage": {
            "start_available_bytes": START_AVAILABLE_BYTES,
            "start_available_GiB": START_AVAILABLE_BYTES / 1024**3,
            "after_full_suite_available_bytes": disk.free,
            "after_full_suite_available_GiB": disk.free / 1024**3,
            "required_bytes": MINIMUM_BYTES,
            "required_GiB": 40,
            "current_capacity_passed": disk.free >= MINIMUM_BYTES,
            "measurement": "shutil.disk_usage byte count; df -kP was independently reconciled",
        },
        "cleanup": {
            "deleted": [],
            "research_files_deleted": False,
            "attempted": [
                {
                    "path": "/Users/rei/.cache/uv",
                    "classification": "regenerable package cache",
                    "observed_size": "628 MiB",
                    "action": "uv cache prune",
                    "result": "NOT_PERFORMED_CACHE_IN_USE_NO_FORCE_OVERRIDE",
                }
            ],
            "safety_decision": "did not force-delete an in-use shared package cache and did not touch artifacts, ledgers, checkpoints, results, receipts, provenance, submodules, git objects, tags, releases, or unrelated project environments",
        },
        "full_suite": {
            "command": "pinned parent baseline Python 3.10.19 -m pytest -q",
            "passed": 260,
            "failed": 25,
            "xfailed": 3,
            "duration_seconds": 1001.90,
            "all_tests_passed": False,
            "failure_class_summary": [
                "historical frozen source manifests reject later source drift",
                "one thread-environment test expected OMP_NUM_THREADS to exist",
            ],
        },
        "decision": "NO_GO_Q1_STORAGE_BELOW_40_GIB_AND_FULL_SUITE_NOT_ALL_PASSING",
        "authorization": {
            "candidate_energy": "NOT_AUTHORIZED",
            "optimizer": "NOT_AUTHORIZED",
            "FCI": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
    }
    body["audit_digest"] = _digest(body)
    return body


def write_artifact() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_json_exclusive(OUTPUT, capture())


def audit() -> dict[str, Any]:
    artifact = _load(OUTPUT)
    body = dict(artifact)
    observed = body.pop("audit_digest", None)
    checks = {
        "digest_valid": observed == _digest(body),
        "immutable_evidence_current": all(
            record["sha256"] == _sha(ROOT / record["path"])
            for record in artifact["immutable_evidence"].values()
            if isinstance(record, dict) and "path" in record
        ),
        "outcomes_zero": artifact["S11_v2_observed_outcomes_all_zero"],
        "no_active_process_at_capture": not artifact["active_S11_molecular_processes"],
        "no_research_deletion": artifact["cleanup"]["research_files_deleted"] is False,
        "candidate_execution_blocked": all(
            value == "NOT_AUTHORIZED" for value in artifact["authorization"].values()
        ),
        "no_go_honest": artifact["decision"].startswith("NO_GO"),
    }
    if not all(checks.values()):
        raise S11V2PreflightAuditError([name for name, passed in checks.items() if not passed])
    return {"status": "PASS_FROZEN_Q0_Q1_NO_GO_AUDIT", "checks": checks, "audit_digest": observed}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", action="store_true")
    parser.add_argument("--audit", action="store_true")
    args = parser.parse_args()
    if args.capture:
        write_artifact()
    if args.audit or not args.capture:
        print(json.dumps(audit(), sort_keys=True))


if __name__ == "__main__":
    main()

"""Freeze the pre-outcome S11-v2 item-000 environment incident."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Mapping

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .historical_artifact_audit import artifact_is_immutable_git_blob
from .s0_successor import ROOT


OUTPUT_DIR = ROOT / "artifacts/v5-final/parent-native/s11-v2-item000-incident-v1"
OUTPUT = OUTPUT_DIR / "environment-contract-incident-v1.json"
READINESS_V2 = (
    ROOT
    / "artifacts/v5-final/parent-native/s11-v2-execution-readiness-v2"
    / "execution-readiness-go-v2.json"
)
PRODUCTION_ROOT = (
    ROOT / "artifacts/v5-final/parent-native/s11-v2-production-execution-v1"
)
STEM = "0000-a68dfee7446bd6b0"
RESULT = PRODUCTION_ROOT / "results" / f"{STEM}.json"
RECEIPT = PRODUCTION_ROOT / "receipts" / f"{STEM}.json"
DISPATCH = PRODUCTION_ROOT / "dispatch" / f"{STEM}.json"
RAW_ROOT = PRODUCTION_ROOT / "raw-ledgers" / STEM
PROGRESS = PRODUCTION_ROOT / "progress/0001-terminal.json"
QUEUE_ENVIRONMENT = ROOT / "artifacts/v5-final/mb6-v2/execution-environment-v2.json"
INCORRECT_ENVIRONMENT = (
    ROOT
    / "artifacts/v5-final/parent-native/mb6-v3/execution-environment-v3.json"
)
DECISION = "SUSPEND_S11_V2_READINESS_V2_AFTER_ITEM000_ENVIRONMENT_MISMATCH"


class S11V2Item000IncidentError(RuntimeError):
    pass


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise S11V2Item000IncidentError(f"invalid JSON: {path}") from error
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise S11V2Item000IncidentError(f"noncanonical JSON: {path}")
    return value


def _embedded_digest(value: Mapping[str, Any], field: str) -> bool:
    body = dict(value)
    observed = body.pop(field, None)
    return isinstance(observed, str) and observed == _digest(body)


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout.rstrip("\n")


def inspect_incident() -> dict[str, Any]:
    readiness = _load(READINESS_V2)
    result = _load(RESULT)
    receipt = _load(RECEIPT)
    dispatch = _load(DISPATCH)
    progress = _load(PROGRESS)
    queue_environment = _load(QUEUE_ENVIRONMENT)
    incorrect_environment = _load(INCORRECT_ENVIRONMENT)
    raw_paths = sorted(RAW_ROOT.glob("*.json"))
    raw = [_load(path) for path in raw_paths]
    failed = [record for record in raw if record.get("kind") == "kernel-event"]
    rollback = [record for record in raw if record.get("kind") == "attempt-rollback"]
    terminal = [record for record in raw if record.get("kind") == "terminal"]
    checks = {
        "readiness_v2_was_GO": readiness.get("decision")
        == "GO_S11_V2_EXACT_RUNNER_FROZEN_90_ITEM_EXECUTION",
        "dispatch_bound_wrong_two_thread_environment": dispatch["environment"][
            "required_threads"
        ]
        == incorrect_environment["required_threads"]
        == {key: "2" for key in ("MKL_NUM_THREADS", "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS")},
        "queue_factory_binds_one_thread_environment": queue_environment[
            "required_threads"
        ]
        == {key: "1" for key in ("MKL_NUM_THREADS", "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS")},
        "item000_failed_before_candidate_outcome": result["terminal_status"]
        == "FAILED_ENGINEERING_PRESERVED"
        and result["candidate_energy_evaluations"] == 0
        and result["outcome"] is None,
        "FCI_and_dense_expm_zero": result["FCI_evaluations"] == 0
        and result["N_dense_expm"] == 0,
        "exactly_one_failed_misclassified_event": len(failed) == 1
        and failed[0]["payload"]["operation"] == "rewrite-verification"
        and failed[0]["payload"]["outcome"] == "failed"
        and failed[0]["payload"]["evidence"]["exception_type"]
        == "QueueBoundRuntimeError",
        "synthetic_precontext_rollback_preserved": len(rollback) == 1
        and len(set(rollback[0]["payload"]["component_digests_before"].values())) == 1
        and rollback[0]["payload"]["component_digests_before"]
        == rollback[0]["payload"]["component_digests_after"],
        "single_terminal_prefix_preserved": len(terminal) == 1
        and progress["terminal_count"] == 1
        and progress["terminal_status_counts"]["FAILED_ENGINEERING_PRESERVED"] == 1,
        "receipt_and_result_digests_valid": _embedded_digest(
            receipt, "receipt_digest"
        )
        and _embedded_digest(result, "result_digest"),
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S11V2Item000IncidentError(failures)
    return {
        "checks": checks,
        "bindings": {
            "readiness_v2_sha256": _sha(READINESS_V2),
            "result_sha256": _sha(RESULT),
            "receipt_sha256": _sha(RECEIPT),
            "dispatch_sha256": _sha(DISPATCH),
            "progress_sha256": _sha(PROGRESS),
            "raw_record_sha256": {
                str(path.relative_to(ROOT)): _sha(path) for path in raw_paths
            },
            "queue_environment_sha256": _sha(QUEUE_ENVIRONMENT),
            "incorrect_environment_sha256": _sha(INCORRECT_ENVIRONMENT),
        },
    }


def capture() -> dict[str, Any]:
    if OUTPUT.exists():
        raise S11V2Item000IncidentError("incident artifact already exists")
    if _git("status", "--porcelain"):
        raise S11V2Item000IncidentError("capture requires a clean worktree")
    evidence = inspect_incident()
    body = {
        "schema": "v5-final.s11-v2-item000-environment-incident.v1",
        "stage": "PHASE_C_ITEM000_POST_TERMINAL_PRE_ITEM001",
        "status": DECISION,
        "decision": DECISION,
        "repository_head": _git("rev-parse", "HEAD"),
        **evidence,
        "root_cause": (
            "The runner required the parent-native MB6-v3 two-thread environment, "
            "while the exact frozen S11 development factory and queue predecessor "
            "bind MB6-v2 with one thread. The factory rejected before constructing "
            "a runtime context or evaluating a candidate outcome."
        ),
        "evidence_quality_findings": [
            "The legacy catch path labeled a non-rewrite engineering failure as one failed rewrite verification.",
            "The pre-context rollback used a request-derived synthetic digest rather than live component snapshots.",
        ],
        "disposition": {
            "item000_original_terminal": "PRESERVE_AS_FAILED_ENGINEERING_PRESERVED",
            "item000_retry": "NOT_AUTHORIZED",
            "item001_and_later": "NOT_AUTHORIZED_PENDING_READINESS_V3",
            "readiness_v2": "SUSPENDED",
            "FCI_reporting": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "scientific_boundary": (
            "No molecular candidate energy, optimizer, FCI, CCSD, or dense matrix "
            "exponential outcome was produced. No method ranking or policy changed."
        ),
    }
    body["incident_digest"] = _digest(body)
    return body


def write_artifact() -> None:
    artifact = capture()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_json_exclusive(OUTPUT, artifact)


def audit_frozen() -> dict[str, Any]:
    artifact = _load(OUTPUT)
    checks = {
        "incident_digest_valid": _embedded_digest(artifact, "incident_digest"),
        "decision_exact": artifact.get("decision") == DECISION,
        "all_checks_passed": all(artifact.get("checks", {}).values()),
        "artifact_immutable": artifact_is_immutable_git_blob(OUTPUT),
        "bound_evidence_unchanged": all(
            _sha(ROOT / path) == expected
            for path, expected in artifact["bindings"]["raw_record_sha256"].items()
        )
        and artifact["bindings"]["result_sha256"] == _sha(RESULT)
        and artifact["bindings"]["receipt_sha256"] == _sha(RECEIPT),
        "continuation_closed": artifact["disposition"]["item001_and_later"]
        == "NOT_AUTHORIZED_PENDING_READINESS_V3",
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S11V2Item000IncidentError(failures)
    return {"decision": artifact["decision"], "checks": checks}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", action="store_true")
    parser.add_argument("--audit", action="store_true")
    args = parser.parse_args()
    if args.capture:
        write_artifact()
    if args.audit or not args.capture:
        print(json.dumps(audit_frozen(), sort_keys=True))


if __name__ == "__main__":
    main()

"""Reconcile the item-023 incident with its formal cap-rejection successor."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Mapping

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .historical_artifact_audit import artifact_is_immutable_git_blob
from .parent_native_persistent_runner import replay_raw_ledger
from .s0_successor import ROOT
from .s11_v2_execution_readiness_v4 import CAP_FREEZE, P7_V5
from .s11_v2_execution_runner_v1 import _item_paths, _terminal_prefix
from .s11_v2_item022_terminal_reconciliation_v1 import historical_artifact_valid
from .s11_v2_item023_relation_metadata_incident_v1 import OUTPUT as INCIDENT
from .s11_v2_item023_same_item_retry_authorization_v1 import (
    OUTPUT as RETRY_AUTHORIZATION,
)
from .s11_v2_native_preparation_runtime_v1 import CumulativeVerifierLedger
from .s11_v2_queue_native_adapter import QUEUE_V2, QueueV2NativeAdapter


OUTPUT_DIR = (
    ROOT / "artifacts/v5-final/parent-native/s11-v2-item023-terminal-reconciliation-v1"
)
OUTPUT = OUTPUT_DIR / "terminal-reconciliation-v1.json"
READINESS_V8 = (
    ROOT / "artifacts/v5-final/parent-native/s11-v2-execution-readiness-v8"
    / "execution-readiness-go-v8.json"
)
PRODUCTION_ROOT = (
    ROOT / "artifacts/v5-final/parent-native/s11-v2-production-execution-v1"
)
STEM = "0023-dc3c97796d359265"
RAW_ROOT = PRODUCTION_ROOT / "raw-ledgers" / STEM
VERIFIER_ROOT = PRODUCTION_ROOT / "verifier-ledgers" / STEM
RETRY_DISPATCH = PRODUCTION_ROOT / "dispatch" / f"{STEM}-retry-0002.json"
RESULT = PRODUCTION_ROOT / "results" / f"{STEM}.json"
RECEIPT = PRODUCTION_ROOT / "receipts" / f"{STEM}.json"
PROGRESS = PRODUCTION_ROOT / "progress/0024-terminal.json"
QUEUE_INDEX = 23
DECISION = "RECONCILE_S11_V2_ITEM023_INCIDENT_TO_FORMAL_CAP_REJECTION"
SOURCE_PATHS = (
    "src/v5_final/s11_v2_item023_terminal_reconciliation_v1.py",
    "tests/test_v5_final_s11_v2_item023_terminal_reconciliation_v1.py",
    "tests/test_v5_final_s11_v2_item023_relation_metadata_incident_v1.py",
    "tests/test_v5_final_s11_v2_item023_same_item_retry_authorization_v1.py",
    "tests/test_v5_final_s11_v2_execution_readiness_v8.py",
)


class S11V2Item023TerminalReconciliationError(RuntimeError):
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
        raise S11V2Item023TerminalReconciliationError(
            f"invalid JSON: {path}"
        ) from error
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise S11V2Item023TerminalReconciliationError(f"noncanonical JSON: {path}")
    return value


def _embedded_digest(value: Mapping[str, Any], field: str) -> bool:
    body = dict(value)
    observed = body.pop(field, None)
    return isinstance(observed, str) and observed == _digest(body)


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout.rstrip("\n")


def _remote_head(branch: str) -> str:
    line = subprocess.run(
        ["git", "ls-remote", "--heads", "origin", f"refs/heads/{branch}"],
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout.strip()
    if not line:
        raise S11V2Item023TerminalReconciliationError("remote branch is absent")
    return line.split()[0]


def inspect_terminal_reconciliation() -> dict[str, Any]:
    adapter = QueueV2NativeAdapter()
    request = adapter.request(adapter.queue["items"][QUEUE_INDEX]["queue_item_id"])
    incident = _load(INCIDENT)
    retry = _load(RETRY_AUTHORIZATION)
    readiness = _load(READINESS_V8)
    result = _load(RESULT)
    receipt = _load(RECEIPT)
    progress = _load(PROGRESS)
    retry_dispatch = _load(RETRY_DISPATCH)
    replay = replay_raw_ledger(
        RAW_ROOT,
        request=request.work_request,
        cap=request.outcome_cap,
        require_terminal=True,
    )
    records = [_load(path) for path in sorted(RAW_ROOT.glob("*.json"))]
    attempt2 = [record for record in records if int(record["sequence"]) >= 5]
    cap_event = attempt2[1]
    verifier = CumulativeVerifierLedger(
        VERIFIER_ROOT, cap=request.item["verifier_componentwise_cap"]
    )
    prefix = _terminal_prefix(
        adapter=adapter,
        production_root=PRODUCTION_ROOT,
        readiness_digest=readiness["readiness_digest"],
        predecessor_readiness_digests=tuple(
            readiness["accepted_predecessor_receipt_readiness_digests"]
        ),
    )
    incident_evidence_unchanged = all(
        _sha(ROOT / path) == expected
        for path, expected in incident["bindings"]["evidence_sha256"].items()
    )
    checks = {
        "historical_incident_is_immutable": artifact_is_immutable_git_blob(INCIDENT)
        and _embedded_digest(incident, "incident_digest")
        and incident_evidence_unchanged,
        "historical_retry_gate_valid_at_captured_commit": historical_artifact_valid(
            RETRY_AUTHORIZATION,
            retry,
            digest_field="authorization_digest",
            decision="AUTHORIZE_S11_V2_ITEM023_SAME_ITEM_PREVERIFIER_CAP_RETRY",
        ),
        "historical_readiness_v8_valid_at_captured_commit": historical_artifact_valid(
            READINESS_V8,
            readiness,
            digest_field="readiness_digest",
            decision="GO_S11_V2_ITEM023_SAME_ITEM_PREVERIFIER_CAP_RETRY",
        ),
        "raw_chain_is_exact_append_only_successor": len(records) == 8
        and [record["kind"] for record in attempt2]
        == ["attempt-start", "kernel-event", "terminal"]
        and attempt2[0]["payload"]
        == {"attempt_ordinal": 2, "prior_attempt_rolled_back": True}
        and records[4]["record_digest"]
        == incident["bindings"]["pre_retry_last_record_digest"]
        and replay.terminal is not None
        and replay.terminal["terminal_status"] == "CAP_REJECTED",
        "attempt2_is_zero_work_preverifier_rejection": cap_event["payload"][
            "operation"
        ]
        == "cap-rejection"
        and cap_event["payload"]["outcome"] == "cap-rejected"
        and not any(int(value) for value in cap_event["payload"]["delta"].values())
        and cap_event["payload"]["evidence"]["kernel_executed"] is False
        and "projected=452 cap=447"
        in cap_event["payload"]["evidence"]["verifier_cap_reason"],
        "result_is_outcome_free_cap_rejection": result["terminal_status"]
        == "CAP_REJECTED"
        and result["candidate_energy_evaluations"] == 0
        and result["raw_work_total"]["optimizer_starts"] == 0
        and result["source_energy_evaluations"] == 0
        and result["outcome"] is None
        and result["outcome_checkpoint_digest"] is None
        and result["FCI_evaluations"] == 0
        and result["N_dense_expm"] == 0
        and not result["verifier_round_receipt_digests"]
        and not VERIFIER_ROOT.exists()
        and not any(verifier.total.values()),
        "incident_work_not_misattributed_to_retry": result["raw_work_total"]
        == incident["observed"]["raw_work_total"]
        and cap_event["payload"]["delta"]["statevector_recomputations"] == 0
        and cap_event["payload"]["delta"]["resource_recounts"] == 0,
        "receipt_and_dispatch_bind_exact_authorization": receipt["terminal_status"]
        == "CAP_REJECTED"
        and receipt["execution_readiness_digest"] == readiness["readiness_digest"]
        and retry_dispatch["retry_authorization_digest"]
        == retry["authorization_digest"]
        and retry_dispatch["retry_attempt_ordinal"] == 2,
        "terminal_prefix_advanced_to_24": len(prefix) == 24
        and prefix[-1]["receipt_digest"] == receipt["receipt_digest"]
        and progress["terminal_count"] == 24
        and progress["N_dense_expm"] == 0
        and progress["FCI_evaluations"] == 0
        and progress["performance_claim"] == "NOT_AUTHORIZED",
        "queue_cap_P7_unchanged": _sha(QUEUE_V2)
        == readiness["binding"]["queue_v2"]["sha256"]
        and _sha(CAP_FREEZE)
        == readiness["binding"]["outcome_cap_freeze"]["sha256"]
        and _sha(P7_V5) == readiness["binding"]["P7_v5"]["sha256"],
        "source_bundle_present": all((ROOT / path).is_file() for path in SOURCE_PATHS),
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S11V2Item023TerminalReconciliationError(failures)
    terminal_paths = (
        RETRY_DISPATCH,
        *(RAW_ROOT / f"{index:08d}-{kind}.json" for index, kind in (
            (5, "attempt-start"),
            (6, "kernel-event"),
            (7, "terminal"),
        )),
        RESULT,
        RECEIPT,
        PROGRESS,
    )
    return {
        "checks": checks,
        "observed": {
            "queue_index": QUEUE_INDEX,
            "queue_item_id": request.item["queue_item_id"],
            "terminal_status": result["terminal_status"],
            "terminal_prefix": len(prefix),
            "corrected_symbolic_upper_bound": retry["observed"][
                "corrected_relation_aware_upper_bound"
            ],
            "frozen_symbolic_cap": retry["observed"]["frozen_symbolic_cap"],
            "attempt2_delta": cap_event["payload"]["delta"],
            "cumulative_raw_work_total": result["raw_work_total"],
            "candidate_energy_evaluations": 0,
            "optimizer_starts": 0,
            "FCI_evaluations": 0,
            "N_dense_expm": 0,
        },
        "bindings": {
            "incident_sha256": _sha(INCIDENT),
            "incident_digest": incident["incident_digest"],
            "retry_authorization_sha256": _sha(RETRY_AUTHORIZATION),
            "retry_authorization_digest": retry["authorization_digest"],
            "readiness_v8_sha256": _sha(READINESS_V8),
            "readiness_v8_digest": readiness["readiness_digest"],
            "pre_retry_last_record_digest": incident["bindings"][
                "pre_retry_last_record_digest"
            ],
            "terminal_evidence_sha256": {
                str(path.relative_to(ROOT)): _sha(path) for path in terminal_paths
            },
            "source_sha256": {path: _sha(ROOT / path) for path in SOURCE_PATHS},
        },
    }


def capture() -> dict[str, Any]:
    if OUTPUT.exists():
        raise S11V2Item023TerminalReconciliationError(
            "terminal reconciliation artifact already exists"
        )
    branch = _git("branch", "--show-current")
    head = _git("rev-parse", "HEAD")
    if _git("status", "--porcelain"):
        raise S11V2Item023TerminalReconciliationError(
            "capture requires a clean worktree"
        )
    if head != _remote_head(branch):
        raise S11V2Item023TerminalReconciliationError(
            "local and remote heads differ"
        )
    body = {
        "schema": "v5-final.s11-v2-item023-terminal-reconciliation.v1",
        "stage": "PHASE_C_ITEM023_FORMAL_CAP_REJECTION_TERMINAL",
        "status": DECISION,
        "decision": DECISION,
        "repository_head": head,
        **inspect_terminal_reconciliation(),
        "scientific_interpretation": (
            "Infrastructure cap rejection before Verifier V2 or molecular outcome "
            "work; not a method-performance observation."
        ),
        "authorization": {
            "item024_and_later": (
                "NOT_AUTHORIZED_PENDING_ADDITIVE_READINESS_SUCCESSOR"
            ),
            "FCI_reporting": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
    }
    body["reconciliation_digest"] = _digest(body)
    return body


def write_artifact() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_json_exclusive(OUTPUT, capture())


def audit_frozen() -> dict[str, Any]:
    artifact = _load(OUTPUT)
    checks = {
        "digest_valid": _embedded_digest(artifact, "reconciliation_digest"),
        "decision_exact": artifact.get("decision") == DECISION,
        "all_checks_passed": all(artifact.get("checks", {}).values()),
        "artifact_immutable": artifact_is_immutable_git_blob(OUTPUT),
        "terminal_evidence_unchanged": all(
            _sha(ROOT / path) == expected
            for path, expected in artifact["bindings"][
                "terminal_evidence_sha256"
            ].items()
        ),
        "sources_current": all(
            _sha(ROOT / path) == expected
            for path, expected in artifact["bindings"]["source_sha256"].items()
        ),
        "continuation_closed": artifact["authorization"]["item024_and_later"]
        == "NOT_AUTHORIZED_PENDING_ADDITIVE_READINESS_SUCCESSOR",
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S11V2Item023TerminalReconciliationError(failures)
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

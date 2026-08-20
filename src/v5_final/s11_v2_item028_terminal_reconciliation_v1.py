"""Reconcile the item-028 incident, retry, and formal terminal evidence."""

from __future__ import annotations

import argparse
from dataclasses import asdict
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
from .s11_v2_execution_runner_v1 import _terminal_prefix
from .s11_v2_item022_terminal_reconciliation_v1 import historical_artifact_valid
from .s11_v2_item028_relation_work_precheck_incident_v1 import OUTPUT as INCIDENT
from .s11_v2_item028_same_item_retry_authorization_v1 import (
    OUTPUT as RETRY_AUTHORIZATION,
)
from .s11_v2_queue_native_adapter import QUEUE_V2, QueueV2NativeAdapter


OUTPUT_DIR = (
    ROOT / "artifacts/v5-final/parent-native/s11-v2-item028-terminal-reconciliation-v1"
)
OUTPUT = OUTPUT_DIR / "terminal-reconciliation-v1.json"
READINESS_V10 = (
    ROOT / "artifacts/v5-final/parent-native/s11-v2-execution-readiness-v10"
    / "execution-readiness-go-v10.json"
)
PRODUCTION_ROOT = (
    ROOT / "artifacts/v5-final/parent-native/s11-v2-production-execution-v1"
)
STEM = "0028-7809ff950f7654f1"
RAW_ROOT = PRODUCTION_ROOT / "raw-ledgers" / STEM
VERIFIER_ROOT = PRODUCTION_ROOT / "verifier-ledgers" / STEM
RETRY_DISPATCH = PRODUCTION_ROOT / "dispatch" / f"{STEM}-retry-0002.json"
OUTCOME = PRODUCTION_ROOT / "raw-ledgers" / f"{STEM}.outcome.json"
RESULT = PRODUCTION_ROOT / "results" / f"{STEM}.json"
RECEIPT = PRODUCTION_ROOT / "receipts" / f"{STEM}.json"
PROGRESS = PRODUCTION_ROOT / "progress/0029-terminal.json"
VERIFIER_RECEIPT = VERIFIER_ROOT / "round-0001-receipt.json"
VERIFIER_CORE = VERIFIER_ROOT / "round-0001-session/verification-core-v2.json"
VERIFIER_TELEMETRY = (
    VERIFIER_ROOT / "round-0001-session/operational-telemetry-v2.json"
)
QUEUE_INDEX = 28
DECISION = "RECONCILE_S11_V2_ITEM028_INCIDENT_TO_FORMAL_COMPLETION"
SOURCE_PATHS = (
    "src/v5_final/s11_v2_item028_terminal_reconciliation_v1.py",
    "tests/test_v5_final_s11_v2_item028_terminal_reconciliation_v1.py",
    "tests/test_v5_final_s11_v2_item028_same_item_retry_authorization_v1.py",
)


class S11V2Item028TerminalReconciliationError(RuntimeError):
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
        raise S11V2Item028TerminalReconciliationError(
            f"invalid JSON: {path}"
        ) from error
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise S11V2Item028TerminalReconciliationError(f"noncanonical JSON: {path}")
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
        raise S11V2Item028TerminalReconciliationError("remote branch is absent")
    return line.split()[0]


def inspect_terminal_reconciliation() -> dict[str, Any]:
    adapter = QueueV2NativeAdapter()
    request = adapter.request(adapter.queue["items"][QUEUE_INDEX]["queue_item_id"])
    incident = _load(INCIDENT)
    retry = _load(RETRY_AUTHORIZATION)
    readiness = _load(READINESS_V10)
    retry_dispatch = _load(RETRY_DISPATCH)
    outcome = _load(OUTCOME)
    result = _load(RESULT)
    receipt = _load(RECEIPT)
    progress = _load(PROGRESS)
    verifier_receipt = _load(VERIFIER_RECEIPT)
    replay = replay_raw_ledger(
        RAW_ROOT,
        request=request.work_request,
        cap=request.outcome_cap,
        require_terminal=True,
    )
    records = [_load(path) for path in sorted(RAW_ROOT.glob("*.json"))]
    attempt2 = records[5:]
    kernel_events = [record for record in attempt2 if record["kind"] == "kernel-event"]
    operations = [record["payload"]["operation"] for record in kernel_events]
    final_cap_event = kernel_events[-1]
    raw_total = asdict(replay.work_total)
    predecessor_digests = tuple(
        readiness["accepted_predecessor_receipt_readiness_digests"]
    )
    prefix = _terminal_prefix(
        adapter=adapter,
        production_root=PRODUCTION_ROOT,
        readiness_digest=readiness["readiness_digest"],
        predecessor_readiness_digests=predecessor_digests,
    )
    result_digest_valid = _embedded_digest(result, "result_digest")
    receipt_digest_valid = _embedded_digest(receipt, "receipt_digest")
    outcome_digest_valid = _embedded_digest(outcome, "checkpoint_digest")
    progress_digest_valid = _embedded_digest(progress, "progress_digest")
    checks = {
        "historical_incident_valid_at_captured_commit": historical_artifact_valid(
            INCIDENT,
            incident,
            digest_field="incident_digest",
            decision="NO_GO_S11_V2_ITEM028_NONCONSERVATIVE_RELATION_WORK_PRECHECK",
        ),
        "historical_retry_gate_valid_at_captured_commit": historical_artifact_valid(
            RETRY_AUTHORIZATION,
            retry,
            digest_field="authorization_digest",
            decision="AUTHORIZE_S11_V2_ITEM028_SAME_ITEM_RELATION_WORK_RETRY",
        ),
        "historical_readiness_v10_valid_at_captured_commit": historical_artifact_valid(
            READINESS_V10,
            readiness,
            digest_field="readiness_digest",
            decision="GO_S11_V2_ITEM028_SAME_ITEM_RETRY_ONLY",
        ),
        "raw_chain_is_exact_append_only_retry_successor": len(records) == 39
        and records[4]["record_digest"]
        == incident["bindings"]["pre_retry_last_record_digest"]
        and attempt2[0]["kind"] == "attempt-start"
        and attempt2[0]["payload"]
        == {"attempt_ordinal": 2, "prior_attempt_rolled_back": True}
        and all(record["sequence"] == index for index, record in enumerate(records))
        and replay.terminal is not None
        and replay.terminal["terminal_status"] == "ACCEPTED"
        and replay.active_attempt_id is None
        and len(replay.attempt_ids) == 2
        and len(replay.rolled_back_attempt_ids) == 1,
        "retry_dispatch_binds_exact_frozen_authorization": retry_dispatch[
            "queue_item_id"
        ]
        == request.item["queue_item_id"]
        and retry_dispatch["retry_attempt_ordinal"] == 2
        and retry_dispatch["retry_authorization_digest"]
        == retry["authorization_digest"]
        and retry_dispatch["execution_readiness_digest"]
        == readiness["readiness_digest"]
        and retry_dispatch["outcome_cap_digest"]
        == request.item["outcome_work_cap"]["cap_digest"]
        and retry_dispatch["verifier_cap_digest"]
        == request.item["verifier_componentwise_cap_digest"]
        and retry_dispatch["FCI_reporting_authorized"] is False
        and retry_dispatch["performance_claim_authorized"] is False,
        "corrected_relation_work_bound_matches_formal_verifier": result[
            "verifier_work_total"
        ]
        == verifier_receipt["cumulative_work_counters"]
        and result["verifier_work_total"]["N_symbolic_checks"] == 452
        and result["verifier_work_total"]["N_sparse_expm_multiply"] == 42
        and result["verifier_work_total"]["N_state_probe_vectors"] == 12
        and result["verifier_work_total"]["N_generator_materializations"] == 12
        and result["verifier_work_total"]["N_dense_expm"] == 0
        and result["verifier_round_receipt_digests"]
        == [verifier_receipt["receipt_digest"]],
        "later_verifier_round_is_prechecked_fail_closed": operations[-1]
        == "cap-rejection"
        and final_cap_event["payload"]["outcome"] == "cap-rejected"
        and not any(int(value) for value in final_cap_event["payload"]["delta"].values())
        and final_cap_event["payload"]["evidence"]["kernel_executed"] is False
        and final_cap_event["payload"]["evidence"]["rejected_operation"]
        == "verifier-v2-session"
        and final_cap_event["payload"]["evidence"]["verifier_cap_reason"]
        == "verifier cap rejected before session: N_sparse_expm_multiply"
        and not (VERIFIER_ROOT / "round-0002-receipt.json").exists()
        and not (VERIFIER_ROOT / "round-0002-session").exists(),
        "raw_work_and_terminal_counters_reconcile": result["raw_work_total"]
        == raw_total
        == replay.terminal["work_total"]
        and result["candidate_energy_evaluations"]
        == operations.count("candidate-energy-evaluation")
        == 9
        and raw_total["gradient_vector_evaluations"]
        == operations.count("full-gradient-evaluation")
        == 8
        and raw_total["optimizer_iterations"]
        == operations.count("optimizer-iteration")
        == 7
        and raw_total["optimizer_starts"] == operations.count("optimizer-start") == 1,
        "terminal_artifacts_are_digest_bound": result_digest_valid
        and receipt_digest_valid
        and outcome_digest_valid
        and progress_digest_valid
        and result["terminal_status"] == "COMPLETED"
        and receipt["terminal_status"] == "COMPLETED"
        and receipt["result_digest"] == result["result_digest"]
        and result["outcome_checkpoint_digest"] == outcome["checkpoint_digest"]
        and result["raw_ledger_last_record_digest"] == records[-1]["record_digest"],
        "terminal_prefix_advanced_to_29": len(prefix) == 29
        and prefix[-1]["receipt_digest"] == receipt["receipt_digest"]
        and progress["terminal_count"] == 29
        and progress["terminal_queue_item_ids"][-1]
        == request.item["queue_item_id"]
        and progress["terminal_receipt_digests"][-1] == receipt["receipt_digest"],
        "dense_fci_and_performance_remain_closed": result["FCI_evaluations"] == 0
        and result["N_dense_expm"] == 0
        and receipt["FCI_evaluations"] == 0
        and receipt["N_dense_expm"] == 0
        and progress["FCI_evaluations"] == 0
        and progress["N_dense_expm"] == 0
        and result["performance_claim"] == "NOT_AUTHORIZED"
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
        raise S11V2Item028TerminalReconciliationError(failures)
    terminal_paths = (
        RETRY_DISPATCH,
        *tuple(sorted(RAW_ROOT.glob("*.json")))[5:],
        OUTCOME,
        RESULT,
        RECEIPT,
        PROGRESS,
        VERIFIER_RECEIPT,
        VERIFIER_CORE,
        VERIFIER_TELEMETRY,
    )
    return {
        "checks": checks,
        "observed": {
            "queue_index": QUEUE_INDEX,
            "queue_item_id": request.item["queue_item_id"],
            "terminal_status": result["terminal_status"],
            "terminal_prefix": len(prefix),
            "attempt1_disposition": "ENGINEERING_INCIDENT_ROLLED_BACK",
            "attempt2_disposition": "FORMAL_COMPLETION",
            "verifier_rounds_committed": 1,
            "later_verifier_round_precheck_rejections": 1,
            "raw_work_total": raw_total,
            "verifier_work_total": result["verifier_work_total"],
            "candidate_energy_evaluations": result["candidate_energy_evaluations"],
            "optimizer_starts": raw_total["optimizer_starts"],
            "FCI_evaluations": 0,
            "N_dense_expm": 0,
        },
        "bindings": {
            "incident_sha256": _sha(INCIDENT),
            "incident_digest": incident["incident_digest"],
            "retry_authorization_sha256": _sha(RETRY_AUTHORIZATION),
            "retry_authorization_digest": retry["authorization_digest"],
            "readiness_v10_sha256": _sha(READINESS_V10),
            "readiness_v10_digest": readiness["readiness_digest"],
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
        raise S11V2Item028TerminalReconciliationError(
            "terminal reconciliation artifact already exists"
        )
    branch = _git("branch", "--show-current")
    head = _git("rev-parse", "HEAD")
    if _git("status", "--porcelain"):
        raise S11V2Item028TerminalReconciliationError(
            "capture requires a clean worktree"
        )
    if head != _remote_head(branch):
        raise S11V2Item028TerminalReconciliationError(
            "local and remote heads differ"
        )
    body = {
        "schema": "v5-final.s11-v2-item028-terminal-reconciliation.v1",
        "stage": "PHASE_C_ITEM028_FORMAL_TERMINAL_RECONCILIATION",
        "status": DECISION,
        "decision": DECISION,
        "repository_head": head,
        **inspect_terminal_reconciliation(),
        "scientific_interpretation": (
            "A frozen-queue method-native item completed under its unchanged caps. "
            "This is one protocol outcome, not a comparative performance claim."
        ),
        "authorization": {
            "item029_and_later": (
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
        "continuation_closed": artifact["authorization"]["item029_and_later"]
        == "NOT_AUTHORIZED_PENDING_ADDITIVE_READINESS_SUCCESSOR",
        "FCI_and_performance_closed": artifact["authorization"]["FCI_reporting"]
        == "NOT_AUTHORIZED"
        and artifact["authorization"]["performance_claim"] == "NOT_AUTHORIZED",
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S11V2Item028TerminalReconciliationError(failures)
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

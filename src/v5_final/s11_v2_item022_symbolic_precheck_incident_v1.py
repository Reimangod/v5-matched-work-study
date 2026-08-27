"""Freeze the pre-outcome S11-v2 item-022 symbolic-precheck incident."""

from __future__ import annotations

from dataclasses import asdict
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
from .s11_v2_queue_native_adapter import QueueV2NativeAdapter


OUTPUT_DIR = ROOT / "artifacts/v5-final/parent-native/s11-v2-item022-incident-v1"
OUTPUT = OUTPUT_DIR / "symbolic-precheck-incident-v1.json"
READINESS_V5 = (
    ROOT
    / "artifacts/v5-final/parent-native/s11-v2-execution-readiness-v5"
    / "execution-readiness-go-v5.json"
)
PRODUCTION_ROOT = (
    ROOT / "artifacts/v5-final/parent-native/s11-v2-production-execution-v1"
)
STEM = "0022-b9e587bb7f9b2fc9"
DISPATCH = PRODUCTION_ROOT / "dispatch" / f"{STEM}.json"
RAW_ROOT = PRODUCTION_ROOT / "raw-ledgers" / STEM
VERIFIER_ROOT = PRODUCTION_ROOT / "verifier-ledgers" / STEM
SESSION_ROOT = VERIFIER_ROOT / "round-0001-session"
CHECKPOINT_ROOT = SESSION_ROOT / "checkpoints"
SESSION_BINDING = CHECKPOINT_ROOT / "session-binding-v2.json"
TOP_K_FREEZE = CHECKPOINT_ROOT / "top-k-freeze-v2.json"
VERIFIER_CORE = SESSION_ROOT / "verification-core-v2.json"
VERIFIER_RECEIPT = VERIFIER_ROOT / "round-0001-receipt.json"
RESULT = PRODUCTION_ROOT / "results" / f"{STEM}.json"
RECEIPT = PRODUCTION_ROOT / "receipts" / f"{STEM}.json"
PROGRESS = PRODUCTION_ROOT / "progress/0023-terminal.json"
QUEUE_INDEX = 22
DECISION = "NO_GO_S11_V2_ITEM022_NONCONSERVATIVE_SYMBOLIC_PRECHECK"


class S11V2Item022SymbolicPrecheckIncidentError(RuntimeError):
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
        raise S11V2Item022SymbolicPrecheckIncidentError(
            f"invalid JSON: {path}"
        ) from error
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise S11V2Item022SymbolicPrecheckIncidentError(
            f"noncanonical JSON: {path}"
        )
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


def _evidence_paths() -> list[Path]:
    return [
        DISPATCH,
        *sorted(RAW_ROOT.rglob("*.json")),
        *sorted(VERIFIER_ROOT.rglob("*.json")),
    ]


def inspect_incident() -> dict[str, Any]:
    readiness = _load(READINESS_V5)
    dispatch = _load(DISPATCH)
    session = _load(SESSION_BINDING)
    top_k = _load(TOP_K_FREEZE)
    adapter = QueueV2NativeAdapter()
    request = adapter.request(adapter.queue["items"][QUEUE_INDEX]["queue_item_id"])
    replay = replay_raw_ledger(
        RAW_ROOT,
        request=request.work_request,
        cap=request.outcome_cap,
        require_terminal=False,
    )
    raw_records = [_load(path) for path in sorted(RAW_ROOT.glob("*.json"))]
    rollbacks = [
        record["payload"]
        for record in raw_records
        if record.get("kind") == "attempt-rollback"
    ]
    numeric_paths = sorted(CHECKPOINT_ROOT.glob("numeric-*.json"))
    numeric = [_load(path) for path in numeric_paths]
    semantic_paths = sorted(CHECKPOINT_ROOT.glob("semantic-*.json"))
    descriptors = session["candidate_descriptors"]
    frozen_cap = request.item["verifier_componentwise_cap"]
    observed_symbolic = len(descriptors) + sum(
        int(record["primitive_delta"]["N_symbolic_checks"])
        for record in numeric
    )
    raw_operations = [event.operation for event in replay.work_events]
    checks = {
        "readiness_v5_was_GO": readiness.get("decision")
        == "GO_S11_V2_FROZEN_QUEUE_CONTINUATION_FROM_INDEX_5"
        and _embedded_digest(readiness, "readiness_digest"),
        "dispatch_is_exact_item022": dispatch["queue_index"] == QUEUE_INDEX
        and dispatch["queue_item_id"] == request.item["queue_item_id"]
        and dispatch["outcome_cap_digest"]
        == request.item["outcome_work_cap"]["cap_digest"]
        and dispatch["verifier_cap_digest"]
        == request.item["verifier_componentwise_cap_digest"],
        "raw_chain_unterminated_and_rolled_back": replay.terminal is None
        and replay.active_attempt_id is None
        and len(raw_records) == 5
        and len(rollbacks) == 1
        and rollbacks[0]["component_digests_before"]
        == rollbacks[0]["component_digests_after"]
        and rollbacks[0]["reason"] == "S11V2NativePreparationError",
        "source_work_preserved_only": raw_operations
        == ["full-physical-resource-recount", "statevector-recomputation"]
        and asdict(replay.work_total)["energy_evaluations"] == 0
        and asdict(replay.work_total)["optimizer_starts"] == 0,
        "no_terminal_or_outcome_artifacts": not RESULT.exists()
        and not RECEIPT.exists()
        and not PROGRESS.exists(),
        "uncommitted_verifier_session_preserved": SESSION_BINDING.is_file()
        and TOP_K_FREEZE.is_file()
        and not VERIFIER_CORE.exists()
        and not VERIFIER_RECEIPT.exists(),
        "frozen_candidate_and_selection_counts_exact": len(descriptors) == 427
        and len(top_k["selected_candidate_ids"]) == 4
        and len(numeric) == 4
        and len(semantic_paths) == 319,
        "symbolic_work_exceeds_frozen_precheck": frozen_cap[
            "N_symbolic_checks"
        ]
        == 447
        and observed_symbolic == 452
        and max(
            int(record["primitive_delta"]["N_symbolic_checks"])
            for record in numeric
        )
        == 10,
        "verifier_remained_outcome_free": all(
            record["candidate_energy_evaluations"] == 0
            and record["optimizer_iterations"] == 0
            and record["primitive_delta"]["N_dense_expm"] == 0
            for record in numeric
        )
        and top_k["candidate_outcomes_observed_before_freeze"] is False,
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S11V2Item022SymbolicPrecheckIncidentError(failures)
    return {
        "checks": checks,
        "observed": {
            "queue_index": QUEUE_INDEX,
            "queue_item_id": request.item["queue_item_id"],
            "case_id": request.item["case_id"],
            "method_id": request.method_id,
            "work_envelope": request.item["work_envelope"],
            "raw_work_total": asdict(replay.work_total),
            "raw_operations": raw_operations,
            "candidate_descriptor_count": len(descriptors),
            "unique_semantic_checkpoint_count": len(semantic_paths),
            "selected_numeric_checkpoint_count": len(numeric),
            "selected_symbolic_check_counts": [
                int(record["primitive_delta"]["N_symbolic_checks"])
                for record in numeric
            ],
            "frozen_symbolic_precheck": int(frozen_cap["N_symbolic_checks"]),
            "reconstructed_symbolic_work": observed_symbolic,
            "candidate_energy_evaluations": 0,
            "optimizer_starts": 0,
            "FCI_evaluations": 0,
            "N_dense_expm": 0,
        },
        "bindings": {
            "readiness_v5_sha256": _sha(READINESS_V5),
            "readiness_v5_digest": readiness["readiness_digest"],
            "queue_digest": adapter.queue["queue_digest"],
            "pre_retry_last_record_digest": replay.records[-1]["record_digest"],
            "evidence_sha256": {
                str(path.relative_to(ROOT)): _sha(path)
                for path in _evidence_paths()
            },
        },
    }


def capture() -> dict[str, Any]:
    if OUTPUT.exists():
        raise S11V2Item022SymbolicPrecheckIncidentError(
            "item022 incident artifact already exists"
        )
    if _git("status", "--porcelain"):
        raise S11V2Item022SymbolicPrecheckIncidentError(
            "capture requires a clean worktree"
        )
    body = {
        "schema": "v5-final.s11-v2-item022-symbolic-precheck-incident.v1",
        "stage": "PHASE_C_ITEM022_PRE_OUTCOME_UNTERMINATED",
        "status": DECISION,
        "decision": DECISION,
        "repository_head": _git("rev-parse", "HEAD"),
        **inspect_incident(),
        "root_cause": (
            "The frozen typed-verifier precheck budgets five symbolic checks per "
            "selected candidate. One H6 method-native relation required ten checks, "
            "so the completed outcome-free verifier session exceeded both its "
            "prechecked upper bound and the unchanged frozen symbolic cap."
        ),
        "disposition": {
            "item022_partial_evidence": "PRESERVE_APPEND_ONLY",
            "item022_retry": "NOT_AUTHORIZED_PENDING_ADDITIVE_RETRY_GATE",
            "item023_and_later": "NOT_AUTHORIZED_PENDING_READINESS_SUCCESSOR",
            "readiness_v5": "SUSPENDED",
            "queue_v2": "PRESERVE_IMMUTABLE",
            "verifier_cap": "PRESERVE_IMMUTABLE",
            "FCI_reporting": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "required_remediation": [
            "Derive symbolic-check upper bounds from relation arity in outcome-free tests.",
            "Prove the corrected bound rejects item022 before verifier work under the unchanged frozen cap.",
            "Freeze an additive same-item retry authorization bound to this rollback digest.",
            "Freeze a readiness successor before any retry or later queue item.",
        ],
        "scientific_boundary": (
            "No molecular candidate energy, optimizer, FCI, CCSD, dense matrix "
            "exponential, or performance comparison was produced. The incident "
            "exposes an infrastructure-bound error, not a method-performance result."
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
            for path, expected in artifact["bindings"]["evidence_sha256"].items()
        ),
        "continuation_closed": artifact["disposition"]["item023_and_later"]
        == "NOT_AUTHORIZED_PENDING_READINESS_SUCCESSOR",
        "performance_closed": artifact["disposition"]["performance_claim"]
        == "NOT_AUTHORIZED",
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S11V2Item022SymbolicPrecheckIncidentError(failures)
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

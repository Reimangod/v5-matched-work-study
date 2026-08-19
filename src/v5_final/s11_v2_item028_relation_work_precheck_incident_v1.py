"""Freeze the pre-outcome item-028 relation-work precheck incident."""

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
from .s11_v2_queue_native_adapter import QUEUE_V2, QueueV2NativeAdapter


OUTPUT_DIR = ROOT / "artifacts/v5-final/parent-native/s11-v2-item028-incident-v1"
OUTPUT = OUTPUT_DIR / "relation-work-precheck-incident-v1.json"
READINESS_V9 = (
    ROOT
    / "artifacts/v5-final/parent-native/s11-v2-execution-readiness-v9"
    / "execution-readiness-go-v9.json"
)
PRODUCTION_ROOT = ROOT / "artifacts/v5-final/parent-native/s11-v2-production-execution-v1"
CAP_FREEZE = (
    ROOT
    / "artifacts/v5-final/parent-native/s11-v2-outcome-cap-freeze-v1"
    / "outcome-cap-freeze-v1.json"
)
P7_V5 = (
    ROOT
    / "artifacts/v5-final/parent-native/s11-v2-preexecution-gate-v5"
    / "p7-go-v5.json"
)
STEM = "0028-7809ff950f7654f1"
DISPATCH = PRODUCTION_ROOT / "dispatch" / f"{STEM}.json"
RAW_ROOT = PRODUCTION_ROOT / "raw-ledgers" / STEM
VERIFIER_ROOT = PRODUCTION_ROOT / "verifier-ledgers" / STEM
CHECKPOINT_ROOT = VERIFIER_ROOT / "round-0001-session/checkpoints"
SESSION_BINDING = CHECKPOINT_ROOT / "session-binding-v2.json"
TOP_K_FREEZE = CHECKPOINT_ROOT / "top-k-freeze-v2.json"
VERIFIER_CORE = VERIFIER_ROOT / "round-0001-session/verification-core-v2.json"
VERIFIER_RECEIPT = VERIFIER_ROOT / "round-0001-receipt.json"
OUTCOME_CHECKPOINT = RAW_ROOT.with_suffix(".outcome.json")
RESULT = PRODUCTION_ROOT / "results" / f"{STEM}.json"
RECEIPT = PRODUCTION_ROOT / "receipts" / f"{STEM}.json"
PROGRESS = PRODUCTION_ROOT / "progress/0029-terminal.json"
QUEUE_INDEX = 28
DECISION = "NO_GO_S11_V2_ITEM028_NONCONSERVATIVE_RELATION_WORK_PRECHECK"


class S11V2Item028RelationWorkPrecheckIncidentError(RuntimeError):
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
        raise S11V2Item028RelationWorkPrecheckIncidentError(
            f"invalid JSON: {path}"
        ) from error
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise S11V2Item028RelationWorkPrecheckIncidentError(
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


def _evidence_paths() -> tuple[Path, ...]:
    return (
        DISPATCH,
        *sorted(RAW_ROOT.glob("*.json")),
        *sorted(VERIFIER_ROOT.rglob("*.json")),
    )


def inspect_incident() -> dict[str, Any]:
    readiness = _load(READINESS_V9)
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
    numeric = [_load(path) for path in sorted(CHECKPOINT_ROOT.glob("numeric-*.json"))]
    semantic_count = len(tuple(CHECKPOINT_ROOT.glob("semantic-*.json")))
    descriptors = session["candidate_descriptors"]
    by_id = {value["candidate_id"]: value for value in descriptors}
    selected = tuple(top_k["selected_candidate_ids"])
    selected_arities = [
        len(by_id[value]["source_generator_digests"])
        + len(by_id[value]["target_generator_digests"])
        for value in selected
    ]
    probe_count = int(session["policy"]["probe_count"])
    old_sparse_upper = 3 * probe_count * len(selected)
    reconstructed_sparse = sum(
        int(record["primitive_delta"]["N_sparse_expm_multiply"])
        for record in numeric
    )
    work_total = asdict(replay.work_total)
    operations = [event.operation for event in replay.work_events]
    checks = {
        "readiness_v9_was_GO": readiness.get("decision")
        == "GO_S11_V2_FROZEN_QUEUE_CONTINUATION_FROM_INDEX_24"
        and _embedded_digest(readiness, "readiness_digest"),
        "dispatch_is_exact_item028": dispatch["queue_index"] == QUEUE_INDEX
        and dispatch["queue_item_id"] == request.item["queue_item_id"]
        and dispatch["execution_readiness_digest"] == readiness["readiness_digest"]
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
        "source_work_preserved_only": operations
        == ["full-physical-resource-recount", "statevector-recomputation"]
        and work_total["resource_recounts"] == 1
        and work_total["statevector_recomputations"] == 1
        and work_total["energy_evaluations"] == 0
        and work_total["optimizer_starts"] == 0,
        "no_terminal_or_outcome_artifacts": not OUTCOME_CHECKPOINT.exists()
        and not RESULT.exists()
        and not RECEIPT.exists()
        and not PROGRESS.exists(),
        "uncommitted_verifier_session_preserved": SESSION_BINDING.is_file()
        and TOP_K_FREEZE.is_file()
        and not VERIFIER_CORE.exists()
        and not VERIFIER_RECEIPT.exists(),
        "frozen_candidate_and_selection_counts_exact": len(descriptors) == 427
        and len(top_k["ranked_candidates"]) == semantic_count == 319
        and len(selected) == len(numeric) == 4,
        "sparse_work_exceeds_fixed_arity_precheck": selected_arities
        == [3, 3, 3, 5]
        and probe_count == 3
        and old_sparse_upper == 36
        and reconstructed_sparse == 42,
        "symbolic_successor_was_exact": [
            int(value["primitive_delta"]["N_symbolic_checks"])
            for value in numeric
        ]
        == [5, 5, 5, 10]
        and len(descriptors)
        + sum(int(value["primitive_delta"]["N_symbolic_checks"]) for value in numeric)
        == 452,
        "verifier_remained_outcome_free": all(
            value["candidate_energy_evaluations"] == 0
            and value["optimizer_iterations"] == 0
            and value["primitive_delta"]["N_dense_expm"] == 0
            for value in numeric
        )
        and top_k["candidate_outcomes_observed_before_freeze"] is False,
        "queue_cap_P7_are_unchanged": _sha(QUEUE_V2)
        == "be88c730f7ba44efd8867c0bf571ecb01afe0349d68e5fdc11733e67c779b1b4"
        and _sha(CAP_FREEZE)
        == "3f0b7c5a8c09dcfb9e5553231894a923efc1e87bd92a6dde54afd5f028a68fb9"
        and _sha(P7_V5)
        == "7ffd316208758bd4a5f63357b0e74b6b8f4df7fac0fe9a1e0b42240d70eb3a63",
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S11V2Item028RelationWorkPrecheckIncidentError(failures)
    return {
        "checks": checks,
        "observed": {
            "queue_index": QUEUE_INDEX,
            "queue_item_id": request.item["queue_item_id"],
            "case_id": request.item["case_id"],
            "method_id": request.method_id,
            "terminal_prefix": 28,
            "raw_work_total": work_total,
            "raw_operations": operations,
            "rollback_reason": rollbacks[0]["reason"],
            "rollback_component_digests": rollbacks[0]["component_digests_after"],
            "candidate_descriptor_count": len(descriptors),
            "unique_semantic_checkpoint_count": semantic_count,
            "selected_candidate_ids": list(selected),
            "selected_total_generator_arities": selected_arities,
            "probe_count": probe_count,
            "fixed_arity_sparse_upper_bound": old_sparse_upper,
            "reconstructed_sparse_expm_work": reconstructed_sparse,
            "candidate_energy_evaluations": 0,
            "optimizer_starts": 0,
            "FCI_evaluations": 0,
            "N_dense_expm": 0,
        },
        "bindings": {
            "readiness_v9_sha256": _sha(READINESS_V9),
            "readiness_v9_digest": readiness["readiness_digest"],
            "queue_sha256": _sha(QUEUE_V2),
            "queue_digest": adapter.queue["queue_digest"],
            "cap_freeze_sha256": _sha(CAP_FREEZE),
            "P7_v5_sha256": _sha(P7_V5),
            "pre_retry_last_record_digest": replay.records[-1]["record_digest"],
            "evidence_sha256": {
                str(path.relative_to(ROOT)): _sha(path) for path in _evidence_paths()
            },
        },
    }


def capture() -> dict[str, Any]:
    if OUTPUT.exists():
        raise S11V2Item028RelationWorkPrecheckIncidentError(
            "item028 incident artifact already exists"
        )
    if _git("status", "--porcelain"):
        raise S11V2Item028RelationWorkPrecheckIncidentError(
            "capture requires a clean worktree"
        )
    body = {
        "schema": "v5-final.s11-v2-item028-relation-work-precheck-incident.v1",
        "stage": "PHASE_C_ITEM028_PRE_OUTCOME_UNTERMINATED",
        "status": DECISION,
        "decision": DECISION,
        "repository_head": _git("rev-parse", "HEAD"),
        **inspect_incident(),
        "root_cause": (
            "The symbolic-check successor derived selected relation arities, but "
            "the sparse-exponential precheck retained the frozen three-generators-"
            "per-relation assumption. The selected outcome-free arities totalled "
            "fourteen, requiring 42 sparse exponentials at three probes, while the "
            "session upper bound admitted only 36."
        ),
        "disposition": {
            "item028_partial_evidence": "PRESERVE_APPEND_ONLY",
            "item028_retry": "NOT_AUTHORIZED_PENDING_GENERAL_RELATION_WORK_AUDIT",
            "item029_and_later": "NOT_AUTHORIZED_PENDING_READINESS_SUCCESSOR",
            "readiness_v9": "SUSPENDED_AFTER_ENGINEERING_INCIDENT",
            "queue_v2": "PRESERVE_IMMUTABLE",
            "outcome_and_verifier_caps": "PRESERVE_IMMUTABLE",
            "FCI_reporting": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "required_remediation": [
            "Derive every relation-dependent verifier counter from registered arity.",
            "Prove componentwise dominance over the complete frozen relation catalog and preserved numeric checkpoints.",
            "Reject unknown or malformed relation metadata fail-closed.",
            "Freeze an additive same-item retry gate bound to this rollback and verifier evidence.",
            "Freeze a readiness successor before retrying item028.",
        ],
        "scientific_boundary": (
            "No candidate energy, optimizer, FCI, dense matrix exponential, terminal "
            "result, or performance comparison was produced. This is an outcome-free "
            "infrastructure-bound incident."
        ),
    }
    body["incident_digest"] = _digest(body)
    return body


def write_artifact() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_json_exclusive(OUTPUT, capture())


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
        "continuation_closed": artifact["disposition"]["item029_and_later"]
        == "NOT_AUTHORIZED_PENDING_READINESS_SUCCESSOR",
        "performance_closed": artifact["disposition"]["performance_claim"]
        == "NOT_AUTHORIZED",
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S11V2Item028RelationWorkPrecheckIncidentError(failures)
    return {"decision": artifact["decision"], "checks": checks}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", action="store_true")
    parser.add_argument("--audit", action="store_true")
    args = parser.parse_args()
    if args.capture:
        write_artifact()
    elif args.audit:
        print(json.dumps(audit_frozen(), sort_keys=True))
    else:
        print(json.dumps(inspect_incident(), sort_keys=True))


if __name__ == "__main__":
    main()

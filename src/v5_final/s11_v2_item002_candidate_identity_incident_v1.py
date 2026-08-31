"""Freeze the pre-outcome S11-v2 item-002 candidate-identity incident."""

from __future__ import annotations

from dataclasses import asdict
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Mapping

from dvg_obs_ceo.identity import canonical_json_bytes as parent_canonical_json_bytes
from dvg_obs_ceo.molecular_identity import state_preparation_spec
from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .historical_artifact_audit import artifact_is_immutable_git_blob
from .parent_native_development_runtime_factory_v1 import (
    build_queue_bound_development_runtime_v1,
)
from .parent_native_persistent_runner import replay_raw_ledger
from .s0_successor import ROOT
from .s11_v2_native_preparation_runtime_v1 import CumulativeVerifierLedger
from .s11_v2_queue_native_adapter import QueueV2NativeAdapter


OUTPUT_DIR = ROOT / "artifacts/v5-final/parent-native/s11-v2-item002-incident-v1"
OUTPUT = OUTPUT_DIR / "candidate-identity-incident-v1.json"
READINESS_V3 = (
    ROOT
    / "artifacts/v5-final/parent-native/s11-v2-execution-readiness-v3"
    / "execution-readiness-go-v3.json"
)
PRODUCTION_ROOT = (
    ROOT / "artifacts/v5-final/parent-native/s11-v2-production-execution-v1"
)
STEM = "0002-7e30eb71e976122e"
DISPATCH = PRODUCTION_ROOT / "dispatch" / f"{STEM}.json"
RAW_ROOT = PRODUCTION_ROOT / "raw-ledgers" / STEM
VERIFIER_ROOT = PRODUCTION_ROOT / "verifier-ledgers" / STEM
VERIFIER_RECEIPT = VERIFIER_ROOT / "round-0001-receipt.json"
VERIFIER_CORE = VERIFIER_ROOT / "round-0001-session/verification-core-v2.json"
RESULT = PRODUCTION_ROOT / "results" / f"{STEM}.json"
RECEIPT = PRODUCTION_ROOT / "receipts" / f"{STEM}.json"
DECISION = (
    "SUSPEND_S11_V2_READINESS_V3_AFTER_ITEM002_"
    "CANDIDATE_ID_CANONICALIZATION_MISMATCH"
)
QUEUE_INDEX = 2


class S11V2Item002CandidateIdentityIncidentError(RuntimeError):
    pass


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _parent_digest(value: Any) -> str:
    return hashlib.sha256(parent_canonical_json_bytes(value)).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise S11V2Item002CandidateIdentityIncidentError(
            f"invalid JSON: {path}"
        ) from error
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise S11V2Item002CandidateIdentityIncidentError(
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
    return [DISPATCH, *sorted(RAW_ROOT.rglob("*.json")), *sorted(VERIFIER_ROOT.rglob("*.json"))]


def inspect_incident() -> dict[str, Any]:
    readiness = _load(READINESS_V3)
    dispatch = _load(DISPATCH)
    verifier_receipt = _load(VERIFIER_RECEIPT)
    verifier_core = _load(VERIFIER_CORE)
    adapter = QueueV2NativeAdapter()
    request = adapter.request(adapter.queue["items"][QUEUE_INDEX]["queue_item_id"])
    replay = replay_raw_ledger(
        RAW_ROOT,
        request=request.work_request,
        cap=request.outcome_cap,
        require_terminal=False,
    )
    verifier = CumulativeVerifierLedger(
        VERIFIER_ROOT, cap=request.item["verifier_componentwise_cap"]
    )
    verifier_rounds = verifier.replay()
    raw_records = [_load(path) for path in sorted(RAW_ROOT.glob("*.json"))]
    rollbacks = [
        record["payload"]
        for record in raw_records
        if record.get("kind") == "attempt-rollback"
    ]
    context = build_queue_bound_development_runtime_v1(
        request.execution_item_v4["queue_item_id"]
    )
    current_state = state_preparation_spec(
        context.runtime,
        algorithm=context._actual_algorithm,
        pool=context.pool,
    )
    payloads = [
        {
            "source_state_preparation_id": current_state.state_preparation_id,
            "position": position,
            "pool_index": int(pool_index),
            "constraint": "theta_i->0",
            "physical_generator_deletion": True,
        }
        for position, pool_index in enumerate(context.runtime.ansatz.indices)
    ]
    frozen_ids = {
        "magnitude-delete-v1:" + _parent_digest(payload) for payload in payloads
    }
    runtime_ids = {"magnitude-delete-v1:" + _digest(payload) for payload in payloads}
    admitted_ids = set(request.admitted_candidate_ids)
    session_ids = {
        str(value["candidate_id"])
        for value in verifier_core["session_binding"]["candidate_descriptors"]
    }
    selected_ids = set(verifier_receipt["selected_candidate_ids"])
    raw_operations = [event.operation for event in replay.work_events]
    checks = {
        "readiness_v3_was_GO": readiness.get("decision")
        == "GO_S11_V2_EXACT_RUNNER_ONE_THREAD_POST_INCIDENT_EXECUTION"
        and _embedded_digest(readiness, "readiness_digest"),
        "dispatch_is_exact_item002_one_thread": dispatch["queue_index"] == QUEUE_INDEX
        and dispatch["queue_item_id"] == request.item["queue_item_id"]
        and dispatch["environment"]["required_threads"]
        == {
            key: "1"
            for key in ("MKL_NUM_THREADS", "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS")
        }
        and all(dispatch["environment"]["checks"].values()),
        "raw_chain_valid_unterminated": replay.terminal is None
        and len(raw_records) == 5,
        "rollback_exact": len(rollbacks) == 1
        and rollbacks[0]["component_digests_before"]
        == rollbacks[0]["component_digests_after"],
        "candidate_optimizer_FCI_zero": "candidate-energy-evaluation"
        not in raw_operations
        and "optimizer-start" not in raw_operations
        and not RESULT.exists()
        and not RECEIPT.exists(),
        "verifier_round_preserved_and_dense_zero": len(verifier_rounds) == 1
        and verifier.total["N_dense_expm"] == 0
        and verifier.total["energy_evaluations"] == 0
        and verifier.total["optimizer_iterations"] == 0,
        "frozen_parent_canonical_ids_match_admission": frozen_ids == admitted_ids,
        "runtime_newline_canonical_ids_match_session": runtime_ids == session_ids,
        "canonical_id_sets_are_disjoint": runtime_ids.isdisjoint(admitted_ids),
        "selected_ids_are_all_unbound": bool(selected_ids)
        and selected_ids.issubset(runtime_ids)
        and selected_ids.isdisjoint(admitted_ids),
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S11V2Item002CandidateIdentityIncidentError(failures)
    return {
        "checks": checks,
        "observed": {
            "queue_index": QUEUE_INDEX,
            "queue_item_id": request.item["queue_item_id"],
            "case_id": request.item["case_id"],
            "method_id": request.method_id,
            "raw_work_total": asdict(replay.work_total),
            "raw_operations": raw_operations,
            "verifier_total": verifier.total,
            "frozen_candidate_count": len(frozen_ids),
            "runtime_candidate_count": len(runtime_ids),
            "selected_candidate_count": len(selected_ids),
            "selected_admitted_intersection_count": len(selected_ids & admitted_ids),
            "candidate_energy_evaluations": 0,
            "optimizer_starts": 0,
            "FCI_evaluations": 0,
            "N_dense_expm": 0,
        },
        "bindings": {
            "readiness_v3_sha256": _sha(READINESS_V3),
            "readiness_v3_digest": readiness["readiness_digest"],
            "queue_digest": adapter.queue["queue_digest"],
            "evidence_sha256": {
                str(path.relative_to(ROOT)): _sha(path) for path in _evidence_paths()
            },
        },
    }


def capture() -> dict[str, Any]:
    if OUTPUT.exists():
        raise S11V2Item002CandidateIdentityIncidentError(
            "item002 incident artifact already exists"
        )
    if _git("status", "--porcelain"):
        raise S11V2Item002CandidateIdentityIncidentError(
            "capture requires a clean worktree"
        )
    evidence = inspect_incident()
    body = {
        "schema": "v5-final.s11-v2-item002-candidate-identity-incident.v1",
        "stage": "PHASE_C_ITEM002_PRE_OUTCOME_UNTERMINATED",
        "status": DECISION,
        "decision": DECISION,
        "repository_head": _git("rev-parse", "HEAD"),
        **evidence,
        "root_cause": (
            "The frozen magnitude candidate IDs use the parent scientific identity "
            "canonical JSON encoding without a trailing newline. The Verifier V2 "
            "runtime recomputed the same payload with the artifact serializer, whose "
            "trailing newline changes every SHA-256 candidate ID."
        ),
        "disposition": {
            "item002_partial_evidence": "PRESERVE_APPEND_ONLY",
            "item002_retry": "NOT_AUTHORIZED_PENDING_ADDITIVE_RETRY_GATE",
            "item003_and_later": "NOT_AUTHORIZED_PENDING_READINESS_SUCCESSOR",
            "readiness_v3": "SUSPENDED",
            "FCI_reporting": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "scientific_boundary": (
            "The mismatch was detected before candidate energy or optimizer work. "
            "A correction may only restore the frozen candidate identity function; "
            "it may not change candidates, ranking, tie-breaks, caps, or outcomes."
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
        "continuation_closed": artifact["disposition"]["item003_and_later"]
        == "NOT_AUTHORIZED_PENDING_READINESS_SUCCESSOR",
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S11V2Item002CandidateIdentityIncidentError(failures)
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

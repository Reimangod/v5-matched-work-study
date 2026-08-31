"""Outcome-free authorization for one append-only retry of S11-v2 item 002."""

from __future__ import annotations

from dataclasses import asdict
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
from typing import Any, Mapping

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .historical_artifact_audit import artifact_is_immutable_git_blob
from .parent_native_development_runtime_factory_v1 import (
    build_queue_bound_development_runtime_v1,
)
from .parent_native_persistent_runner import replay_raw_ledger
from .s0_successor import ROOT
from .s11_v2_item002_candidate_identity_incident_v1 import (
    OUTPUT as ITEM002_INCIDENT,
    audit_frozen as audit_incident,
)
from .s11_v2_native_preparation_runtime_v1 import (
    CumulativeVerifierLedger,
    VerifierComponentwiseCapRejected,
    build_magnitude_verifier_v2,
    conservative_session_upper_bound,
    policy_from_queue_item,
)
from .s11_v2_queue_native_adapter import QUEUE_V2, QueueV2NativeAdapter


OUTPUT_DIR = (
    ROOT
    / "artifacts/v5-final/parent-native/s11-v2-item002-retry-authorization-v1"
)
OUTPUT = OUTPUT_DIR / "retry-authorization-v1.json"
READINESS_V3 = (
    ROOT
    / "artifacts/v5-final/parent-native/s11-v2-execution-readiness-v3"
    / "execution-readiness-go-v3.json"
)
PRODUCTION_ROOT = (
    ROOT / "artifacts/v5-final/parent-native/s11-v2-production-execution-v1"
)
STEM = "0002-7e30eb71e976122e"
RAW_ROOT = PRODUCTION_ROOT / "raw-ledgers" / STEM
VERIFIER_ROOT = PRODUCTION_ROOT / "verifier-ledgers" / STEM
DISPATCH = PRODUCTION_ROOT / "dispatch" / f"{STEM}.json"
RESULT = PRODUCTION_ROOT / "results" / f"{STEM}.json"
RECEIPT = PRODUCTION_ROOT / "receipts" / f"{STEM}.json"
QUEUE_INDEX = 2
DECISION = "AUTHORIZE_S11_V2_ITEM002_SAME_ITEM_APPEND_ONLY_RETRY"
SOURCE_PATHS = (
    "src/v5_final/s11_v2_native_preparation_runtime_v1.py",
    "src/v5_final/s11_v2_prepared_executor_v1.py",
    "src/v5_final/s11_v2_execution_runner_v1.py",
    "src/v5_final/s11_v2_item002_candidate_identity_incident_v1.py",
    "src/v5_final/s11_v2_item002_retry_authorization_v1.py",
    "tests/test_v5_final_s11_v2_native_preparation_runtime_v1.py",
    "tests/test_v5_final_s11_v2_prepared_executor_v1.py",
    "tests/test_v5_final_s11_v2_execution_runner_v1.py",
    "tests/test_v5_final_s11_v2_item002_candidate_identity_incident_v1.py",
    "tests/test_v5_final_s11_v2_item002_retry_authorization_v1.py",
)


class S11V2Item002RetryAuthorizationError(RuntimeError):
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
        raise S11V2Item002RetryAuthorizationError(
            f"invalid JSON: {path}"
        ) from error
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise S11V2Item002RetryAuthorizationError(
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
        raise S11V2Item002RetryAuthorizationError("remote branch is absent")
    return line.split()[0]


def inspect_retry_readiness() -> dict[str, Any]:
    readiness = _load(READINESS_V3)
    incident = _load(ITEM002_INCIDENT)
    dispatch = _load(DISPATCH)
    adapter = QueueV2NativeAdapter()
    request = adapter.request(adapter.queue["items"][QUEUE_INDEX]["queue_item_id"])
    replay = replay_raw_ledger(
        RAW_ROOT,
        request=request.work_request,
        cap=request.outcome_cap,
        require_terminal=False,
    )
    verifier_ledger = CumulativeVerifierLedger(
        VERIFIER_ROOT, cap=request.item["verifier_componentwise_cap"]
    )
    prior_rounds = verifier_ledger.replay()
    context = build_queue_bound_development_runtime_v1(
        request.execution_item_v4["queue_item_id"]
    )
    policy = policy_from_queue_item(request.item)
    upper = conservative_session_upper_bound(
        candidate_count=len(context.runtime.ansatz.indices),
        selected_count=min(policy.top_k, len(context.runtime.ansatz.indices)),
        source_block_count=len(context.runtime.ansatz.cumulative_parameter_counts),
        maximum_relation_terms=1,
        matrix_dimension=1 << int(context.pool.n),
        qubit_count=int(context.pool.n),
        probe_count=policy.probe_count,
    )
    cap_rejection_reason = None
    try:
        verifier_ledger.precheck(upper)
    except VerifierComponentwiseCapRejected as error:
        cap_rejection_reason = str(error)
    with tempfile.TemporaryDirectory(prefix="s11-v2-item002-retry-") as directory:
        bundle = build_magnitude_verifier_v2(
            context=context,
            policy=policy,
            checkpoint_dir=Path(directory) / "checkpoints",
        )
    actual_ids = {candidate.candidate_id for candidate in bundle.candidates}
    admitted_ids = set(request.admitted_candidate_ids)
    checks = {
        "incident_is_frozen_and_suspends_v3": all(
            audit_incident()["checks"].values()
        )
        and incident["decision"].startswith("SUSPEND_S11_V2_READINESS_V3"),
        "readiness_v3_preserved": readiness["readiness_digest"]
        == "85cce0cc03289753f146f7d2cb4cfd12789dfd9f156f6a8ca292a5daa404e355",
        "same_item_method_cap": dispatch["queue_index"] == QUEUE_INDEX
        and dispatch["queue_item_id"] == request.item["queue_item_id"]
        and dispatch["outcome_cap_digest"]
        == request.item["outcome_work_cap"]["cap_digest"]
        and dispatch["verifier_cap_digest"]
        == request.item["verifier_componentwise_cap_digest"],
        "exact_rollback_ready_for_attempt_2": replay.terminal is None
        and replay.active_attempt_id is None
        and len(replay.attempt_ids) == 1
        and replay.rolled_back_attempt_ids == replay.attempt_ids,
        "no_outcome_or_terminal_artifacts": not RESULT.exists()
        and not RECEIPT.exists()
        and all(event.operation != "candidate-energy-evaluation" for event in replay.work_events)
        and all(event.operation != "optimizer-start" for event in replay.work_events),
        "prior_verifier_work_preserved": len(prior_rounds) == 1
        and verifier_ledger.total["N_dense_expm"] == 0,
        "corrected_ids_equal_frozen_admission": actual_ids == admitted_ids,
        "corrected_verifier_upper_bound_is_outcome_free": upper["N_dense_expm"] == 0
        and upper["energy_evaluations"] == 0
        and upper["optimizer_iterations"] == 0,
        "cumulative_verifier_cap_rejection_predicted": cap_rejection_reason
        is not None
        and cap_rejection_reason.startswith("verifier cap rejected before session:"),
        "source_bundle_present": all((ROOT / path).is_file() for path in SOURCE_PATHS),
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S11V2Item002RetryAuthorizationError(failures)
    source_sha256 = {path: _sha(ROOT / path) for path in SOURCE_PATHS}
    return {
        "checks": checks,
        "observed": {
            "prior_raw_work_total": asdict(replay.work_total),
            "prior_verifier_total": verifier_ledger.total,
            "corrected_verifier_upper_bound": upper,
            "predicted_cap_rejection_reason": cap_rejection_reason,
            "candidate_count": len(actual_ids),
            "selected_candidate_ids": [],
            "candidate_energy_evaluations": 0,
            "optimizer_starts": 0,
            "FCI_evaluations": 0,
            "N_dense_expm": 0,
        },
        "bindings": {
            "queue_v2_sha256": _sha(QUEUE_V2),
            "queue_digest": adapter.queue["queue_digest"],
            "readiness_v3_sha256": _sha(READINESS_V3),
            "readiness_v3_digest": readiness["readiness_digest"],
            "item002_incident_sha256": _sha(ITEM002_INCIDENT),
            "item002_incident_digest": incident["incident_digest"],
            "original_dispatch_sha256": _sha(DISPATCH),
            "original_dispatch_digest": dispatch["dispatch_digest"],
            "pre_retry_last_record_digest": replay.records[-1]["record_digest"],
            "source_sha256": source_sha256,
            "source_bundle_digest": _digest(source_sha256),
        },
    }


def capture() -> dict[str, Any]:
    if OUTPUT.exists():
        raise S11V2Item002RetryAuthorizationError(
            "retry authorization artifact already exists"
        )
    branch = _git("branch", "--show-current")
    local_head = _git("rev-parse", "HEAD")
    if _git("status", "--porcelain"):
        raise S11V2Item002RetryAuthorizationError(
            "capture requires a clean worktree"
        )
    if local_head != _remote_head(branch):
        raise S11V2Item002RetryAuthorizationError(
            "local and remote heads differ"
        )
    evidence = inspect_retry_readiness()
    body = {
        "schema": "v5-final.s11-v2-item002-retry-authorization.v1",
        "stage": "PHASE_C_ITEM002_PRE_OUTCOME_RETRY_AUTHORIZATION",
        "status": DECISION,
        "decision": DECISION,
        "repository_head": local_head,
        "queue_index": QUEUE_INDEX,
        "queue_item_id": QueueV2NativeAdapter().queue["items"][QUEUE_INDEX][
            "queue_item_id"
        ],
        "retry_attempt_ordinal": 2,
        "scientific_change": False,
        "candidate_outcomes_used": False,
        **evidence,
        "authorization": {
            "item002_retry": (
                "AUTHORIZED_ONCE_APPEND_ONLY_SAME_CAP_EXPECTED_CAP_REJECTION"
            ),
            "item003_and_later": "NOT_AUTHORIZED_PENDING_READINESS_V4",
            "FCI_reporting": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "semantic_diff": {
            "queue_changed": False,
            "candidate_payload_changed": False,
            "candidate_set_changed": False,
            "ranking_changed": False,
            "tie_break_changed": False,
            "cap_changed": False,
            "counter_reset": False,
            "expected_terminal": "CAP_REJECTED_BEFORE_NEW_VERIFIER_SESSION",
            "correction": (
                "Use the parent scientific identity canonical JSON encoding already "
                "used to freeze the magnitude candidate IDs."
            ),
        },
    }
    body["authorization_digest"] = _digest(body)
    return body


def write_artifact() -> None:
    artifact = capture()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_json_exclusive(OUTPUT, artifact)


def audit_frozen(*, require_live: bool = False) -> dict[str, Any]:
    artifact = _load(OUTPUT)
    checks = {
        "authorization_digest_valid": _embedded_digest(
            artifact, "authorization_digest"
        ),
        "decision_exact": artifact.get("decision") == DECISION,
        "all_checks_passed": all(artifact.get("checks", {}).values()),
        "artifact_immutable": artifact_is_immutable_git_blob(OUTPUT),
        "incident_unchanged": artifact["bindings"]["item002_incident_sha256"]
        == _sha(ITEM002_INCIDENT),
        "pre_retry_evidence_preserved": artifact["bindings"][
            "original_dispatch_sha256"
        ]
        == _sha(DISPATCH),
        "sources_current": all(
            _sha(ROOT / path) == expected
            for path, expected in artifact["bindings"]["source_sha256"].items()
        ),
        "single_retry_only": artifact["retry_attempt_ordinal"] == 2
        and artifact["authorization"]["item002_retry"]
        == "AUTHORIZED_ONCE_APPEND_ONLY_SAME_CAP_EXPECTED_CAP_REJECTION",
    }
    if require_live:
        branch = _git("branch", "--show-current")
        checks.update(
            worktree_clean=_git("status", "--porcelain") == "",
            local_remote_head_match=_git("rev-parse", "HEAD")
            == _remote_head(branch),
        )
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S11V2Item002RetryAuthorizationError(failures)
    return {
        "decision": artifact["decision"],
        "authorization_digest": artifact["authorization_digest"],
        "checks": checks,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", action="store_true")
    parser.add_argument("--audit", action="store_true")
    parser.add_argument("--audit-live", action="store_true")
    args = parser.parse_args()
    if args.capture:
        write_artifact()
    if args.audit or args.audit_live or not args.capture:
        print(json.dumps(audit_frozen(require_live=args.audit_live), sort_keys=True))


if __name__ == "__main__":
    main()

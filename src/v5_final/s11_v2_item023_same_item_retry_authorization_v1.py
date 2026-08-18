"""Authorize one zero-new-work retry of item 023 after metadata repair."""

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
from .s11_v2_item023_relation_metadata_incident_v1 import (
    OUTPUT as ITEM023_INCIDENT,
    audit_frozen as audit_incident,
)
from .s11_v2_queue_native_adapter import QUEUE_V2, QueueV2NativeAdapter
from .s11_v2_relation_aware_symbolic_precheck_v1 import (
    relation_aware_symbolic_upper_bound,
    symbolic_check_cost_from_arity,
)


OUTPUT_DIR = (
    ROOT
    / "artifacts/v5-final/parent-native/s11-v2-item023-retry-authorization-v1"
)
OUTPUT = OUTPUT_DIR / "same-item-retry-authorization-v1.json"
PRODUCTION_ROOT = (
    ROOT / "artifacts/v5-final/parent-native/s11-v2-production-execution-v1"
)
ITEM022_CHECKPOINT_ROOT = (
    PRODUCTION_ROOT
    / "verifier-ledgers/0022-b9e587bb7f9b2fc9/round-0001-session/checkpoints"
)
ITEM022_SESSION_BINDING = ITEM022_CHECKPOINT_ROOT / "session-binding-v2.json"
ITEM022_TOP_K = ITEM022_CHECKPOINT_ROOT / "top-k-freeze-v2.json"
STEM = "0023-dc3c97796d359265"
RAW_ROOT = PRODUCTION_ROOT / "raw-ledgers" / STEM
DISPATCH = PRODUCTION_ROOT / "dispatch" / f"{STEM}.json"
VERIFIER_ROOT = PRODUCTION_ROOT / "verifier-ledgers" / STEM
RESULT = PRODUCTION_ROOT / "results" / f"{STEM}.json"
RECEIPT = PRODUCTION_ROOT / "receipts" / f"{STEM}.json"
QUEUE_INDEX = 23
DECISION = "AUTHORIZE_S11_V2_ITEM023_SAME_ITEM_PREVERIFIER_CAP_RETRY"
SOURCE_PATHS = (
    "src/v5_final/s11_v2_relation_aware_symbolic_precheck_v1.py",
    "src/v5_final/verifier_v2.py",
    "src/v5_final/parent_native_verifier_v2.py",
    "src/v5_final/s11_v2_native_preparation_runtime_v1.py",
    "src/v5_final/s11_v2_prepared_executor_v1.py",
    "src/v5_final/s11_v2_execution_runner_v1.py",
    "src/v5_final/s11_v2_item023_relation_metadata_incident_v1.py",
    "src/v5_final/s11_v2_item023_same_item_retry_authorization_v1.py",
    "tests/test_v5_final_s11_v2_relation_aware_symbolic_precheck_v1.py",
    "tests/test_v5_final_s11_v2_execution_runner_v1.py",
    "tests/test_v5_final_s11_v2_item023_relation_metadata_incident_v1.py",
    "tests/test_v5_final_s11_v2_item023_same_item_retry_authorization_v1.py",
)


class S11V2Item023RetryAuthorizationError(RuntimeError):
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
        raise S11V2Item023RetryAuthorizationError(
            f"invalid JSON: {path}"
        ) from error
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise S11V2Item023RetryAuthorizationError(f"noncanonical JSON: {path}")
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
        raise S11V2Item023RetryAuthorizationError("remote branch is absent")
    return line.split()[0]


def _selected_descriptor_costs(
    session: Mapping[str, Any], top_k: Mapping[str, Any]
) -> tuple[tuple[str, ...], tuple[int, ...]]:
    descriptors = session.get("candidate_descriptors")
    selected = top_k.get("selected_candidate_ids")
    if not isinstance(descriptors, list) or not isinstance(selected, list):
        raise S11V2Item023RetryAuthorizationError("candidate freeze is malformed")
    selected_ids = tuple(selected)
    by_id = {value.get("candidate_id"): value for value in descriptors}
    if (
        not selected_ids
        or len(set(selected_ids)) != len(selected_ids)
        or len(by_id) != len(descriptors)
        or any(value not in by_id for value in selected_ids)
    ):
        raise S11V2Item023RetryAuthorizationError("candidate descriptors differ")
    costs: list[int] = []
    for candidate_id in selected_ids:
        descriptor = by_id[candidate_id]
        source = descriptor.get("source_generator_digests")
        target = descriptor.get("target_generator_digests")
        deletion = descriptor.get("deletion_shortcut")
        if not isinstance(source, list) or not isinstance(target, list):
            raise S11V2Item023RetryAuthorizationError("relation arity is absent")
        costs.append(
            symbolic_check_cost_from_arity(
                source_arity=len(source),
                target_arity=len(target),
                deletion_shortcut=deletion,
            )
        )
    return selected_ids, tuple(costs)


def inspect_retry_readiness() -> dict[str, Any]:
    incident = _load(ITEM023_INCIDENT)
    dispatch = _load(DISPATCH)
    session = _load(ITEM022_SESSION_BINDING)
    top_k = _load(ITEM022_TOP_K)
    adapter = QueueV2NativeAdapter()
    item022 = adapter.request(adapter.queue["items"][22]["queue_item_id"])
    item023 = adapter.request(adapter.queue["items"][QUEUE_INDEX]["queue_item_id"])
    replay = replay_raw_ledger(
        RAW_ROOT,
        request=item023.work_request,
        cap=item023.outcome_cap,
        require_terminal=False,
    )
    selected_ids, selected_costs = _selected_descriptor_costs(session, top_k)
    candidate_count = len(session["candidate_descriptors"])
    predicted = relation_aware_symbolic_upper_bound(
        candidate_count=candidate_count,
        selected_costs=selected_costs,
    )
    cap = int(item023.item["verifier_componentwise_cap"]["N_symbolic_checks"])
    descriptor_ids = tuple(
        value["candidate_id"] for value in session["candidate_descriptors"]
    )
    checks = {
        "incident_is_immutable_formal_no_go": all(
            audit_incident()["checks"].values()
        )
        and incident["decision"]
        == "NO_GO_S11_V2_ITEM023_RELATION_METADATA_PRECHECK",
        "same_frozen_item_method_and_caps": dispatch["queue_index"] == QUEUE_INDEX
        and dispatch["queue_item_id"] == item023.item["queue_item_id"]
        and dispatch["outcome_cap_digest"]
        == item023.item["outcome_work_cap"]["cap_digest"]
        and dispatch["verifier_cap_digest"]
        == item023.item["verifier_componentwise_cap_digest"],
        "exact_rollback_ready_for_attempt_2": replay.terminal is None
        and replay.active_attempt_id is None
        and len(replay.attempt_ids) == 1
        and replay.rolled_back_attempt_ids == replay.attempt_ids
        and replay.records[-1]["record_digest"]
        == incident["bindings"]["pre_retry_last_record_digest"],
        "no_terminal_verifier_or_outcome_artifacts": not VERIFIER_ROOT.exists()
        and not RESULT.exists()
        and not RECEIPT.exists()
        and all(
            event.operation
            not in {"candidate-energy-evaluation", "optimizer-start"}
            for event in replay.work_events
        ),
        "item022_item023_initial_selection_inputs_are_identical": item022.item[
            "source_identity"
        ]
        == item023.item["source_identity"]
        and item022.admitted_candidate_ids == item023.admitted_candidate_ids
        and len(descriptor_ids) == len(set(descriptor_ids))
        and set(item023.admitted_candidate_ids) == set(descriptor_ids)
        and item022.item["candidate_binding"]["candidate_ids_digest"]
        == item023.item["candidate_binding"]["candidate_ids_digest"]
        and item022.item["K"] == item023.item["K"] == len(selected_ids)
        and item022.item["tie_break"] == item023.item["tie_break"]
        and item022.item["verifier_policy"] == item023.item["verifier_policy"],
        "selection_and_relation_costs_are_outcome_free": selected_ids
        == tuple(top_k["selected_candidate_ids"])
        and top_k["candidate_outcomes_observed_before_freeze"] is False
        and list(selected_costs) == [5, 5, 5, 10]
        and candidate_count == 427,
        "unchanged_cap_rejects_before_runtime": predicted == 452
        and cap == 447
        and predicted > cap,
        "outcome_free_zero_dense_and_fci": asdict(replay.work_total)[
            "energy_evaluations"
        ]
        == 0
        and asdict(replay.work_total)["optimizer_starts"] == 0
        and incident["observed"]["FCI_evaluations"] == 0
        and incident["observed"]["N_dense_expm"] == 0,
        "source_bundle_present": all((ROOT / path).is_file() for path in SOURCE_PATHS),
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S11V2Item023RetryAuthorizationError(failures)
    source_sha256 = {path: _sha(ROOT / path) for path in SOURCE_PATHS}
    evidence_paths = (
        DISPATCH,
        *tuple(sorted(RAW_ROOT.glob("*.json"))),
        ITEM022_SESSION_BINDING,
        ITEM022_TOP_K,
    )
    return {
        "checks": checks,
        "observed": {
            "candidate_count": candidate_count,
            "selected_candidate_ids": list(selected_ids),
            "selected_relation_symbolic_costs": list(selected_costs),
            "corrected_relation_aware_upper_bound": predicted,
            "frozen_symbolic_cap": cap,
            "expected_terminal": "CAP_REJECTED_BEFORE_VERIFIER_OR_RUNTIME",
            "new_attempt_candidate_energy_evaluations": 0,
            "new_attempt_optimizer_starts": 0,
            "new_attempt_statevector_recomputations": 0,
            "new_attempt_FCI_evaluations": 0,
            "new_attempt_N_dense_expm": 0,
        },
        "bindings": {
            "queue_v2_sha256": _sha(QUEUE_V2),
            "queue_digest": adapter.queue["queue_digest"],
            "item023_incident_sha256": _sha(ITEM023_INCIDENT),
            "item023_incident_digest": incident["incident_digest"],
            "original_dispatch_sha256": _sha(DISPATCH),
            "original_dispatch_digest": dispatch["dispatch_digest"],
            "pre_retry_last_record_digest": replay.records[-1]["record_digest"],
            "outcome_cap_digest": item023.item["outcome_work_cap"]["cap_digest"],
            "verifier_cap_digest": item023.item[
                "verifier_componentwise_cap_digest"
            ],
            "item022_session_binding_sha256": _sha(ITEM022_SESSION_BINDING),
            "item022_top_k_sha256": _sha(ITEM022_TOP_K),
            "preserved_preoutcome_evidence_sha256": {
                str(path.relative_to(ROOT)): _sha(path) for path in evidence_paths
            },
            "source_sha256": source_sha256,
            "source_bundle_digest": _digest(source_sha256),
        },
    }


def capture() -> dict[str, Any]:
    if OUTPUT.exists():
        raise S11V2Item023RetryAuthorizationError(
            "item023 retry authorization already exists"
        )
    branch = _git("branch", "--show-current")
    head = _git("rev-parse", "HEAD")
    if _git("status", "--porcelain"):
        raise S11V2Item023RetryAuthorizationError(
            "capture requires a clean worktree"
        )
    if head != _remote_head(branch):
        raise S11V2Item023RetryAuthorizationError("local and remote heads differ")
    adapter = QueueV2NativeAdapter()
    evidence = inspect_retry_readiness()
    body = {
        "schema": "v5-final.s11-v2-item023-same-item-retry-authorization.v1",
        "stage": "PHASE_C_ITEM023_PREVERIFIER_RETRY_AUTHORIZATION",
        "status": DECISION,
        "decision": DECISION,
        "repository_head": head,
        "queue_index": QUEUE_INDEX,
        "queue_item_id": adapter.queue["items"][QUEUE_INDEX]["queue_item_id"],
        "retry_attempt_ordinal": 2,
        "scientific_change": False,
        "candidate_outcomes_used": False,
        **evidence,
        "authorization": {
            "item023_retry": (
                "AUTHORIZED_ONCE_APPEND_ONLY_SAME_CAP_PREVERIFIER_REJECTION"
            ),
            "item024_and_later": "NOT_AUTHORIZED_PENDING_TERMINAL_RECONCILIATION",
            "FCI_reporting": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "semantic_diff": {
            "queue_changed": False,
            "candidate_set_changed": False,
            "ranking_changed": False,
            "selected_candidate_identity_changed": False,
            "method_semantics_changed": False,
            "cap_changed": False,
            "counter_reset": False,
            "correction": (
                "Normalize the registered parent relation metadata shape without "
                "changing relation arity or symbolic-cost semantics."
            ),
        },
    }
    body["authorization_digest"] = _digest(body)
    return body


def write_artifact() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_json_exclusive(OUTPUT, capture())


def audit_frozen(*, require_live: bool = False) -> dict[str, Any]:
    artifact = _load(OUTPUT)
    bindings = artifact["bindings"]
    checks = {
        "authorization_digest_valid": _embedded_digest(
            artifact, "authorization_digest"
        ),
        "decision_exact": artifact.get("decision") == DECISION,
        "all_checks_passed": all(artifact.get("checks", {}).values()),
        "artifact_immutable": artifact_is_immutable_git_blob(OUTPUT),
        "incident_unchanged": bindings["item023_incident_sha256"]
        == _sha(ITEM023_INCIDENT),
        "preserved_evidence_unchanged": all(
            _sha(ROOT / path) == expected
            for path, expected in bindings[
                "preserved_preoutcome_evidence_sha256"
            ].items()
        ),
        "sources_current": all(
            _sha(ROOT / path) == expected
            for path, expected in bindings["source_sha256"].items()
        ),
        "single_same_item_retry_only": artifact["queue_index"] == QUEUE_INDEX
        and artifact["retry_attempt_ordinal"] == 2
        and artifact["authorization"]["item023_retry"]
        == "AUTHORIZED_ONCE_APPEND_ONLY_SAME_CAP_PREVERIFIER_REJECTION",
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
        raise S11V2Item023RetryAuthorizationError(failures)
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

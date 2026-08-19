"""Authorize one append-only item-028 retry after a general relation-work audit."""

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
from .s11_v2_item028_relation_work_precheck_incident_v1 import (
    OUTPUT as ITEM028_INCIDENT,
    audit_frozen as audit_incident,
)
from .s11_v2_queue_native_adapter import QUEUE_V2, QueueV2NativeAdapter
from .s11_v2_relation_aware_symbolic_precheck_v1 import (
    REGISTERED_RELATION_ARITIES,
    relation_verifier_work_from_arity,
)


OUTPUT_DIR = (
    ROOT / "artifacts/v5-final/parent-native/s11-v2-item028-retry-authorization-v1"
)
OUTPUT = OUTPUT_DIR / "same-item-retry-authorization-v1.json"
PRODUCTION_ROOT = ROOT / "artifacts/v5-final/parent-native/s11-v2-production-execution-v1"
SOURCE_CATALOG = (
    ROOT
    / "artifacts/v5-final/parent-native/s11-development-queue-v4"
    / "development-source-catalog-v1.json"
)
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
RAW_ROOT = PRODUCTION_ROOT / "raw-ledgers" / STEM
DISPATCH = PRODUCTION_ROOT / "dispatch" / f"{STEM}.json"
VERIFIER_ROOT = PRODUCTION_ROOT / "verifier-ledgers" / STEM
CHECKPOINT_ROOT = VERIFIER_ROOT / "round-0001-session/checkpoints"
SESSION_BINDING = CHECKPOINT_ROOT / "session-binding-v2.json"
TOP_K_FREEZE = CHECKPOINT_ROOT / "top-k-freeze-v2.json"
RESULT = PRODUCTION_ROOT / "results" / f"{STEM}.json"
RECEIPT = PRODUCTION_ROOT / "receipts" / f"{STEM}.json"
QUEUE_INDEX = 28
DECISION = "AUTHORIZE_S11_V2_ITEM028_SAME_ITEM_RELATION_WORK_RETRY"
SOURCE_PATHS = (
    "src/v5_final/verifier_v2.py",
    "src/v5_final/s11_v2_relation_aware_symbolic_precheck_v1.py",
    "src/v5_final/s11_v2_native_preparation_runtime_v1.py",
    "src/v5_final/s11_v2_prepared_executor_v1.py",
    "src/v5_final/s11_v2_execution_runner_v1.py",
    "src/v5_final/s11_v2_item028_relation_work_precheck_incident_v1.py",
    "src/v5_final/s11_v2_item028_same_item_retry_authorization_v1.py",
    "tests/test_v5_final_s11_v2_relation_aware_symbolic_precheck_v1.py",
    "tests/test_v5_final_s11_v2_execution_runner_v1.py",
    "tests/test_v5_final_s11_v2_item028_relation_work_precheck_incident_v1.py",
    "tests/test_v5_final_s11_v2_item028_same_item_retry_authorization_v1.py",
)
ADDITIVE_INTEGRATION_PATHS = {
    "src/v5_final/s11_v2_execution_runner_v1.py",
    "src/v5_final/s11_v2_item028_same_item_retry_authorization_v1.py",
    "tests/test_v5_final_s11_v2_execution_runner_v1.py",
}


class S11V2Item028RetryAuthorizationError(RuntimeError):
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
        raise S11V2Item028RetryAuthorizationError(f"invalid JSON: {path}") from error
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise S11V2Item028RetryAuthorizationError(f"noncanonical JSON: {path}")
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
        raise S11V2Item028RetryAuthorizationError("remote branch is absent")
    return line.split()[0]


def _descriptor_work(descriptor: Mapping[str, Any]):
    source = descriptor.get("source_generator_digests")
    target = descriptor.get("target_generator_digests")
    deletion = descriptor.get("deletion_shortcut")
    if not isinstance(source, list) or not isinstance(target, list):
        raise S11V2Item028RetryAuthorizationError("relation arity is absent")
    return relation_verifier_work_from_arity(
        source_arity=len(source),
        target_arity=len(target),
        deletion_shortcut=deletion,
    )


def inspect_retry_readiness() -> dict[str, Any]:
    incident = _load(ITEM028_INCIDENT)
    dispatch = _load(DISPATCH)
    session = _load(SESSION_BINDING)
    top_k = _load(TOP_K_FREEZE)
    catalog = _load(SOURCE_CATALOG)
    adapter = QueueV2NativeAdapter()
    request = adapter.request(adapter.queue["items"][QUEUE_INDEX]["queue_item_id"])
    replay = replay_raw_ledger(
        RAW_ROOT,
        request=request.work_request,
        cap=request.outcome_cap,
        require_terminal=False,
    )
    descriptors = session["candidate_descriptors"]
    by_id = {value["candidate_id"]: value for value in descriptors}
    selected = tuple(top_k["selected_candidate_ids"])
    if len(by_id) != len(descriptors) or any(value not in by_id for value in selected):
        raise S11V2Item028RetryAuthorizationError("selected descriptors differ")
    work = tuple(_descriptor_work(by_id[value]) for value in selected)
    probe_count = int(session["policy"]["probe_count"])
    corrected_sparse = probe_count * sum(
        value.sparse_expm_per_probe for value in work
    )
    numeric = [_load(path) for path in sorted(CHECKPOINT_ROOT.glob("numeric-*.json"))]
    reconstructed_sparse = sum(
        int(value["primitive_delta"]["N_sparse_expm_multiply"])
        for value in numeric
    )
    frozen_cap = int(
        request.item["verifier_componentwise_cap"]["N_sparse_expm_multiply"]
    )
    catalog_records = [
        candidate
        for case in catalog["cases"]
        for candidate in case["source_structural_catalog"]
    ]
    catalog_arities = {
        (record["kind"], len(record["source_pool_indices"]), len(record["target_pool_indices"]))
        for record in catalog_records
    }
    catalog_complete = all(
        kind in REGISTERED_RELATION_ARITIES
        and (source, target) in REGISTERED_RELATION_ARITIES[kind]
        and relation_verifier_work_from_arity(
            source_arity=source,
            target_arity=target,
            deletion_shortcut=target == 0,
        ).sparse_expm_per_probe
        == (0 if target == 0 else source + target)
        for kind, source, target in catalog_arities
    )
    work_total = asdict(replay.work_total)
    checks = {
        "incident_is_immutable_formal_no_go": all(audit_incident()["checks"].values())
        and incident["decision"]
        == "NO_GO_S11_V2_ITEM028_NONCONSERVATIVE_RELATION_WORK_PRECHECK",
        "same_frozen_item_method_and_caps": dispatch["queue_index"] == QUEUE_INDEX
        and dispatch["queue_item_id"] == request.item["queue_item_id"]
        and dispatch["outcome_cap_digest"]
        == request.item["outcome_work_cap"]["cap_digest"]
        and dispatch["verifier_cap_digest"]
        == request.item["verifier_componentwise_cap_digest"],
        "exact_rollback_ready_for_attempt_2": replay.terminal is None
        and replay.active_attempt_id is None
        and len(replay.attempt_ids) == 1
        and replay.rolled_back_attempt_ids == replay.attempt_ids
        and replay.records[-1]["record_digest"]
        == incident["bindings"]["pre_retry_last_record_digest"],
        "no_terminal_or_outcome_artifacts": not RESULT.exists()
        and not RECEIPT.exists()
        and work_total["energy_evaluations"] == 0
        and work_total["optimizer_starts"] == 0,
        "selection_is_outcome_free_and_unchanged": selected
        == tuple(incident["observed"]["selected_candidate_ids"])
        and top_k["candidate_outcomes_observed_before_freeze"] is False,
        "general_catalog_is_registered": len(catalog_records) == 949
        and set(kind for kind, _, _ in catalog_arities)
        == set(REGISTERED_RELATION_ARITIES)
        and catalog_complete,
        "componentwise_relation_bound_is_conservative": [
            value.sparse_expm_per_probe for value in work
        ]
        == [3, 3, 3, 5]
        and corrected_sparse == reconstructed_sparse == 42
        and frozen_cap == 72
        and corrected_sparse <= frozen_cap,
        "outcome_free_zero_dense_and_fci": all(
            value["candidate_energy_evaluations"] == 0
            and value["optimizer_iterations"] == 0
            and value["primitive_delta"]["N_dense_expm"] == 0
            for value in numeric
        )
        and incident["observed"]["FCI_evaluations"] == 0,
        "queue_cap_P7_unchanged": _sha(QUEUE_V2)
        == incident["bindings"]["queue_sha256"]
        and _sha(CAP_FREEZE) == incident["bindings"]["cap_freeze_sha256"]
        and _sha(P7_V5) == incident["bindings"]["P7_v5_sha256"],
        "source_bundle_present": all((ROOT / path).is_file() for path in SOURCE_PATHS),
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S11V2Item028RetryAuthorizationError(failures)
    source_sha256 = {path: _sha(ROOT / path) for path in SOURCE_PATHS}
    evidence_paths = (
        DISPATCH,
        *tuple(sorted(RAW_ROOT.glob("*.json"))),
        *tuple(sorted(VERIFIER_ROOT.rglob("*.json"))),
    )
    return {
        "checks": checks,
        "observed": {
            "candidate_count": len(descriptors),
            "selected_candidate_ids": list(selected),
            "selected_total_generator_arities": [
                value.sparse_expm_per_probe for value in work
            ],
            "probe_count": probe_count,
            "previous_sparse_expm_upper_bound": 36,
            "corrected_sparse_expm_upper_bound": corrected_sparse,
            "reconstructed_sparse_expm_work": reconstructed_sparse,
            "frozen_sparse_expm_cap": frozen_cap,
            "registered_catalog_record_count": len(catalog_records),
            "expected_retry_boundary": (
                "OUTCOME_FREE_VERIFIER_SESSION_WITHIN_UNCHANGED_CAP"
            ),
            "candidate_energy_evaluations_before_retry": 0,
            "optimizer_starts_before_retry": 0,
            "FCI_evaluations_before_retry": 0,
            "N_dense_expm_before_retry": 0,
        },
        "bindings": {
            "queue_v2_sha256": _sha(QUEUE_V2),
            "queue_digest": adapter.queue["queue_digest"],
            "cap_freeze_sha256": _sha(CAP_FREEZE),
            "P7_v5_sha256": _sha(P7_V5),
            "source_catalog_sha256": _sha(SOURCE_CATALOG),
            "item028_incident_sha256": _sha(ITEM028_INCIDENT),
            "item028_incident_digest": incident["incident_digest"],
            "original_dispatch_sha256": _sha(DISPATCH),
            "original_dispatch_digest": dispatch["dispatch_digest"],
            "pre_retry_last_record_digest": replay.records[-1]["record_digest"],
            "outcome_cap_digest": request.item["outcome_work_cap"]["cap_digest"],
            "verifier_cap_digest": request.item["verifier_componentwise_cap_digest"],
            "preserved_preoutcome_evidence_sha256": {
                str(path.relative_to(ROOT)): _sha(path) for path in evidence_paths
            },
            "source_sha256": source_sha256,
            "source_bundle_digest": _digest(source_sha256),
        },
    }


def capture() -> dict[str, Any]:
    if OUTPUT.exists():
        raise S11V2Item028RetryAuthorizationError(
            "item028 retry authorization already exists"
        )
    branch = _git("branch", "--show-current")
    head = _git("rev-parse", "HEAD")
    if _git("status", "--porcelain"):
        raise S11V2Item028RetryAuthorizationError("capture requires a clean worktree")
    if head != _remote_head(branch):
        raise S11V2Item028RetryAuthorizationError("local and remote heads differ")
    adapter = QueueV2NativeAdapter()
    body = {
        "schema": "v5-final.s11-v2-item028-same-item-retry-authorization.v1",
        "stage": "PHASE_C_ITEM028_RELATION_WORK_RETRY_AUTHORIZATION",
        "status": DECISION,
        "decision": DECISION,
        "repository_head": head,
        "queue_index": QUEUE_INDEX,
        "queue_item_id": adapter.queue["items"][QUEUE_INDEX]["queue_item_id"],
        "retry_attempt_ordinal": 2,
        "scientific_change": False,
        "candidate_outcomes_used": False,
        **inspect_retry_readiness(),
        "authorization": {
            "item028_retry": "AUTHORIZED_ONCE_APPEND_ONLY_SAME_CAP_RELATION_WORK_RETRY",
            "item029_and_later": "NOT_AUTHORIZED_PENDING_TERMINAL_RECONCILIATION",
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
                "Derive all relation-dependent verifier work from registered arity."
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
        "incident_unchanged": bindings["item028_incident_sha256"]
        == _sha(ITEM028_INCIDENT),
        "preserved_evidence_unchanged": all(
            _sha(ROOT / path) == expected
            for path, expected in bindings["preserved_preoutcome_evidence_sha256"].items()
        ),
        "scientific_sources_current": all(
            _sha(ROOT / path) == expected
            for path, expected in bindings["source_sha256"].items()
            if path not in ADDITIVE_INTEGRATION_PATHS
        ),
        "single_same_item_retry_only": artifact["queue_index"] == QUEUE_INDEX
        and artifact["retry_attempt_ordinal"] == 2
        and artifact["authorization"]["item028_retry"]
        == "AUTHORIZED_ONCE_APPEND_ONLY_SAME_CAP_RELATION_WORK_RETRY",
    }
    if require_live:
        branch = _git("branch", "--show-current")
        checks.update(
            worktree_clean=_git("status", "--porcelain") == "",
            local_remote_head_match=_git("rev-parse", "HEAD") == _remote_head(branch),
        )
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S11V2Item028RetryAuthorizationError(failures)
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

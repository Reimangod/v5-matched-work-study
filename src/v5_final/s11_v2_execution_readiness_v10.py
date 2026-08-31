"""Additive readiness gate for the single authorized item-028 retry."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import shutil
import sys
from typing import Any

from v5_matched_work.atomic_artifacts import write_json_exclusive

from .historical_artifact_audit import artifact_is_immutable_git_blob
from .parent_native_persistent_runner import replay_raw_ledger
from .s0_successor import ROOT
from .s11_v2_execution_readiness_v4 import (
    CAP_FREEZE,
    ENVIRONMENT,
    MINIMUM_FREE_BYTES,
    P7_V5,
    PRODUCTION_ROOT,
    _digest,
    _embedded_digest,
    _git,
    _load,
    _remote_head,
    _run,
    _sha,
)
from .s11_v2_execution_readiness_v6 import _live_pr_snapshot
from .s11_v2_execution_readiness_v9 import OUTPUT as READINESS_V9
from .s11_v2_execution_runner_v1 import _item_paths, _terminal_prefix
from .s11_v2_item028_relation_work_precheck_incident_v1 import (
    OUTPUT as ITEM028_INCIDENT,
)
from .s11_v2_item028_same_item_retry_authorization_v1 import (
    OUTPUT as ITEM028_RETRY_AUTHORIZATION,
    audit_frozen as audit_retry_authorization,
)
from .s11_v2_preexecution_gate_v5 import audit_frozen as audit_p7_v5
from .s11_v2_queue_native_adapter import QUEUE_V2, QueueV2NativeAdapter


OUTPUT_DIR = ROOT / "artifacts/v5-final/parent-native/s11-v2-execution-readiness-v10"
OUTPUT = OUTPUT_DIR / "execution-readiness-go-v10.json"
DECISION = "GO_S11_V2_ITEM028_SAME_ITEM_RETRY_ONLY"
SOURCE_PATHS = (
    "src/v5_final/full_repository_suite_v2.py",
    "src/v5_final/parent_native_development_execution_v1.py",
    "src/v5_final/parent_native_development_runtime_factory_v1.py",
    "src/v5_final/parent_native_execution_services.py",
    "src/v5_final/parent_native_persistent_runner.py",
    "src/v5_final/parent_native_work_accounting.py",
    "src/v5_final/verifier_v2.py",
    "src/v5_final/parent_native_verifier_v2.py",
    "src/v5_final/s11_v2_relation_aware_symbolic_precheck_v1.py",
    "src/v5_final/s11_v2_native_preparation_runtime_v1.py",
    "src/v5_final/s11_v2_prepared_executor_v1.py",
    "src/v5_final/s11_v2_queue_native_adapter.py",
    "src/v5_final/s11_v2_execution_runner_v1.py",
    "src/v5_final/s11_v2_item028_relation_work_precheck_incident_v1.py",
    "src/v5_final/s11_v2_item028_same_item_retry_authorization_v1.py",
    "src/v5_final/s11_v2_execution_readiness_v10.py",
    "tests/test_v5_final_full_repository_suite_v2.py",
    "tests/test_v5_final_s11_v2_relation_aware_symbolic_precheck_v1.py",
    "tests/test_v5_final_s11_v2_execution_runner_v1.py",
    "tests/test_v5_final_s11_v2_item028_relation_work_precheck_incident_v1.py",
    "tests/test_v5_final_s11_v2_item028_same_item_retry_authorization_v1.py",
    "tests/test_v5_final_s11_v2_execution_readiness_v10.py",
)
SCOPED_TESTS = tuple(path for path in SOURCE_PATHS if path.startswith("tests/"))


class S11V2ExecutionReadinessV10Error(RuntimeError):
    pass


def _require_minimum_free_storage() -> int:
    available = int(shutil.disk_usage(ROOT).free)
    if available < MINIMUM_FREE_BYTES:
        raise S11V2ExecutionReadinessV10Error(
            "free storage fell below 40 GiB during readiness verification"
        )
    return available


def _production_evidence() -> dict[str, str]:
    return {
        str(path.relative_to(ROOT)): _sha(path)
        for path in sorted(PRODUCTION_ROOT.rglob("*.json"))
    }


def inspect_checkpoint() -> dict[str, Any]:
    adapter = QueueV2NativeAdapter()
    queue = adapter.queue
    cap = _load(CAP_FREEZE)
    p7 = _load(P7_V5)
    environment = _load(ENVIRONMENT)
    readiness_v9 = _load(READINESS_V9)
    incident = _load(ITEM028_INCIDENT)
    retry = _load(ITEM028_RETRY_AUTHORIZATION)
    predecessor_digests = tuple(
        readiness_v9["accepted_predecessor_receipt_readiness_digests"]
    ) + (readiness_v9["readiness_digest"],)
    prefix = _terminal_prefix(
        adapter=adapter,
        production_root=PRODUCTION_ROOT,
        readiness_digest="0" * 64,
        predecessor_readiness_digests=predecessor_digests,
    )
    results = [
        _load(
            _item_paths(
                PRODUCTION_ROOT, index, adapter.request(item["queue_item_id"])
            )["result"]
        )
        for index, item in enumerate(queue["items"][: len(prefix)])
    ]
    request = adapter.request(queue["items"][28]["queue_item_id"])
    paths = _item_paths(PRODUCTION_ROOT, 28, request)
    replay = replay_raw_ledger(
        paths["raw"],
        request=request.work_request,
        cap=request.outcome_cap,
        require_terminal=False,
    )
    work_total = asdict(replay.work_total)
    source_sha256 = {path: _sha(ROOT / path) for path in SOURCE_PATHS}
    checks = {
        "P7_v5_GO_valid": audit_p7_v5()["decision"]
        == "GO_S11_V2_FROZEN_90_ITEM_EXECUTION",
        "queue_cap_P7_environment_exact": len(queue["items"]) == 90
        and _embedded_digest(queue, "queue_digest")
        and _embedded_digest(cap, "freeze_digest")
        and p7["gate_digest"]
        == "701a327f20a4a195c1710af548211f541a2932b8d545492b9d219de9bd95b8b7"
        and environment["required_threads"]
        == {
            key: "1"
            for key in ("MKL_NUM_THREADS", "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS")
        },
        "readiness_v9_is_immutable_predecessor": artifact_is_immutable_git_blob(
            READINESS_V9
        )
        and _embedded_digest(readiness_v9, "readiness_digest")
        and readiness_v9["decision"]
        == "GO_S11_V2_FROZEN_QUEUE_CONTINUATION_FROM_INDEX_24",
        "item028_incident_and_retry_are_bound": artifact_is_immutable_git_blob(
            ITEM028_INCIDENT
        )
        and _embedded_digest(incident, "incident_digest")
        and all(audit_retry_authorization()["checks"].values())
        and retry["bindings"]["item028_incident_digest"]
        == incident["incident_digest"],
        "terminal_prefix_is_exact_28": len(prefix) == 28
        and prefix[-1]["queue_item_id"] == queue["items"][27]["queue_item_id"],
        "item028_is_rolled_back_nonterminal": replay.terminal is None
        and replay.active_attempt_id is None
        and len(replay.attempt_ids) == 1
        and replay.rolled_back_attempt_ids == replay.attempt_ids
        and replay.records[-1]["record_digest"]
        == retry["bindings"]["pre_retry_last_record_digest"]
        and not paths["result"].exists()
        and not paths["receipt"].exists()
        and not paths["progress"].exists(),
        "item028_outcome_boundary_is_clean": work_total["energy_evaluations"] == 0
        and work_total["optimizer_starts"] == 0
        and incident["observed"]["FCI_evaluations"] == 0
        and incident["observed"]["N_dense_expm"] == 0,
        "corrected_bound_fits_unchanged_cap": retry["observed"][
            "corrected_sparse_expm_upper_bound"
        ]
        == 42
        and retry["observed"]["frozen_sparse_expm_cap"] == 72
        and retry["semantic_diff"]["cap_changed"] is False
        and retry["semantic_diff"]["method_semantics_changed"] is False,
        "completed_prefix_dense_and_FCI_remain_zero": sum(
            int(result["N_dense_expm"]) for result in results
        )
        == 0
        and sum(int(result["FCI_evaluations"]) for result in results) == 0,
        "performance_claim_remains_closed": all(
            result["performance_claim"] == "NOT_AUTHORIZED" for result in results
        ),
        "source_bundle_present": all((ROOT / path).is_file() for path in SOURCE_PATHS),
        "storage_at_least_40_GiB": shutil.disk_usage(ROOT).free
        >= MINIMUM_FREE_BYTES,
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S11V2ExecutionReadinessV10Error(failures)
    evidence = _production_evidence()
    return {
        "checks": checks,
        "observed": {
            "terminal_count": len(prefix),
            "retry_queue_index": 28,
            "retry_queue_item_id": request.item["queue_item_id"],
            "item028_candidate_energy_evaluations": 0,
            "item028_optimizer_starts": 0,
            "FCI_evaluations": 0,
            "N_dense_expm": 0,
        },
        "binding": {
            "queue_v2": {"sha256": _sha(QUEUE_V2), "queue_digest": queue["queue_digest"]},
            "outcome_cap_freeze": {
                "sha256": _sha(CAP_FREEZE),
                "freeze_digest": cap["freeze_digest"],
            },
            "P7_v5": {"sha256": _sha(P7_V5), "gate_digest": p7["gate_digest"]},
            "readiness_v9": {
                "sha256": _sha(READINESS_V9),
                "readiness_digest": readiness_v9["readiness_digest"],
            },
            "item028_incident": {
                "sha256": _sha(ITEM028_INCIDENT),
                "incident_digest": incident["incident_digest"],
            },
            "item028_retry_authorization": {
                "sha256": _sha(ITEM028_RETRY_AUTHORIZATION),
                "authorization_digest": retry["authorization_digest"],
            },
            "environment": {
                "sha256": _sha(ENVIRONMENT),
                "environment_digest": environment["environment_digest"],
            },
            "production_evidence_sha256": evidence,
            "production_evidence_digest": _digest(evidence),
            "source_sha256": source_sha256,
            "source_bundle_digest": _digest(source_sha256),
        },
        "accepted_predecessor_receipt_readiness_digests": list(
            predecessor_digests
        ),
    }


def capture() -> dict[str, Any]:
    if OUTPUT.exists():
        raise S11V2ExecutionReadinessV10Error("readiness v10 artifact already exists")
    branch = _git("branch", "--show-current")
    head = _git("rev-parse", "HEAD")
    if _git("status", "--porcelain"):
        raise S11V2ExecutionReadinessV10Error("capture requires a clean worktree")
    if head != _remote_head(branch):
        raise S11V2ExecutionReadinessV10Error("local and remote heads differ")
    evidence = inspect_checkpoint()
    scoped = _run([sys.executable, "-m", "pytest", "-q", *SCOPED_TESTS])
    full = _run(
        [sys.executable, "-m", "v5_final.full_repository_suite_v2"],
        full_suite=True,
    )
    if not scoped["passed"] or not full["passed"]:
        raise S11V2ExecutionReadinessV10Error("local verification suite failed")
    live = _live_pr_snapshot(expected_head=head)
    available_after_verification = _require_minimum_free_storage()
    body = {
        "schema": "v5-final.s11-v2-execution-readiness.v10",
        "stage": "PHASE_C_ITEM028_SAME_ITEM_RETRY_READINESS",
        "status": DECISION,
        "decision": DECISION,
        "captured_repository_state": {
            "branch": branch,
            "local_head": head,
            "remote_head": head,
            "worktree_clean": True,
            "recursive_submodule_status": _git(
                "submodule", "status", "--recursive"
            ).splitlines(),
        },
        "storage": {
            "available_bytes": available_after_verification,
            "required_bytes": MINIMUM_FREE_BYTES,
            "measured_after_local_and_live_verification": True,
        },
        "tests": {
            "scoped": scoped,
            "full_repository_suite": full,
            "core_offline_and_historical_partitions": "PASS",
            "live_repository_checks": live,
        },
        **evidence,
        "execution_start_index": 28,
        "blockers": [],
        "authorization": {
            "S11_v2_execution": "AUTHORIZED_EXACT_ITEM028_SAME_ITEM_RETRY_ONLY",
            "candidate_energy": "AUTHORIZED_ONLY_AFTER_OUTCOME_FREE_VERIFIER_COMMIT",
            "optimizer": "AUTHORIZED_ONLY_INSIDE_UNCHANGED_ITEM028_CAP",
            "item029_and_later": "NOT_AUTHORIZED_PENDING_ITEM028_TERMINAL_RECONCILIATION",
            "FCI_reporting": "NOT_AUTHORIZED_UNTIL_ALL_90_TERMINAL",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "semantic_diff": {
            "queue_changed": False,
            "cap_changed": False,
            "ranking_changed": False,
            "selected_candidate_identity_changed": False,
            "method_semantics_changed": False,
            "outcome_information_used_to_change_protocol": False,
            "item028_incident_disposition": "ENGINEERING_INCIDENT_PRESERVED",
        },
    }
    body["readiness_digest"] = _digest(body)
    return body


def write_artifact() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_json_exclusive(OUTPUT, capture())


def audit_frozen(*, require_live: bool = False) -> dict[str, Any]:
    artifact = _load(OUTPUT)
    bindings = artifact["binding"]
    checks = {
        "digest_valid": _embedded_digest(artifact, "readiness_digest"),
        "decision_exact": artifact.get("decision") == DECISION,
        "all_checks_passed": all(artifact.get("checks", {}).values()),
        "blockers_empty": artifact.get("blockers") == [],
        "immutable_inputs_unchanged": bindings["queue_v2"]["sha256"]
        == _sha(QUEUE_V2)
        and bindings["outcome_cap_freeze"]["sha256"] == _sha(CAP_FREEZE)
        and bindings["P7_v5"]["sha256"] == _sha(P7_V5)
        and bindings["readiness_v9"]["sha256"] == _sha(READINESS_V9)
        and bindings["item028_incident"]["sha256"] == _sha(ITEM028_INCIDENT)
        and bindings["item028_retry_authorization"]["sha256"]
        == _sha(ITEM028_RETRY_AUTHORIZATION),
        "production_evidence_preserved": all(
            _sha(ROOT / path) == expected
            for path, expected in bindings["production_evidence_sha256"].items()
        ),
        "sources_current": all(
            _sha(ROOT / path) == expected
            for path, expected in bindings["source_sha256"].items()
        ),
        "tests_and_live_checks_recorded_green": artifact["tests"]["scoped"]["passed"]
        and artifact["tests"]["full_repository_suite"]["passed"]
        and bool(artifact["tests"]["live_repository_checks"]["checks"])
        and all(
            item["status"] == "COMPLETED" and item["conclusion"] == "SUCCESS"
            for item in artifact["tests"]["live_repository_checks"]["checks"]
        ),
        "single_retry_and_scientific_boundaries": artifact["authorization"][
            "S11_v2_execution"
        ]
        == "AUTHORIZED_EXACT_ITEM028_SAME_ITEM_RETRY_ONLY"
        and artifact["authorization"]["item029_and_later"].startswith(
            "NOT_AUTHORIZED"
        )
        and artifact["authorization"]["FCI_reporting"]
        == "NOT_AUTHORIZED_UNTIL_ALL_90_TERMINAL"
        and artifact["authorization"]["performance_claim"] == "NOT_AUTHORIZED",
    }
    if require_live:
        branch = _git("branch", "--show-current")
        checks.update(
            artifact_immutable=artifact_is_immutable_git_blob(OUTPUT),
            worktree_clean=_git("status", "--porcelain") == "",
            local_remote_head_match=_git("rev-parse", "HEAD") == _remote_head(branch),
            submodules_clean=all(
                line.startswith(" ")
                for line in _git("submodule", "status", "--recursive").splitlines()
            ),
            storage_at_least_40_GiB=shutil.disk_usage(ROOT).free
            >= MINIMUM_FREE_BYTES,
        )
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S11V2ExecutionReadinessV10Error(failures)
    return {
        "decision": artifact["decision"],
        "readiness_digest": artifact["readiness_digest"],
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

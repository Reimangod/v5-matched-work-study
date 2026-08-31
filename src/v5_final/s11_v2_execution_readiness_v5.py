"""Five-item checkpoint successor for frozen S11-v2 queue continuation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys
from typing import Any

from v5_matched_work.atomic_artifacts import write_json_exclusive

from .historical_artifact_audit import (
    artifact_is_immutable_git_blob,
    is_ancestor,
    manifest_matches_commit,
)
from .s0_successor import ROOT
from .s11_v2_execution_readiness_v4 import (
    CAP_FREEZE,
    ENVIRONMENT,
    ITEM000_INCIDENT,
    ITEM002_INCIDENT,
    ITEM002_RETRY_AUTHORIZATION,
    MINIMUM_FREE_BYTES,
    P7_V5,
    PRODUCTION_ROOT,
    READINESS_V2,
    READINESS_V2_DIGEST,
    READINESS_V3,
    READINESS_V3_DIGEST,
    _digest,
    _embedded_digest,
    _git,
    _load,
    _remote_head,
    _run,
    _sha,
)
from .s11_v2_execution_runner_v1 import _item_paths, _terminal_prefix
from .s11_v2_item002_candidate_identity_incident_v1 import (
    audit_frozen as audit_item002_incident,
)
from .s11_v2_preexecution_gate_v5 import audit_frozen as audit_p7_v5
from .s11_v2_queue_native_adapter import QUEUE_V2, QueueV2NativeAdapter


OUTPUT_DIR = ROOT / "artifacts/v5-final/parent-native/s11-v2-execution-readiness-v5"
OUTPUT = OUTPUT_DIR / "execution-readiness-go-v5.json"
READINESS_V4 = (
    ROOT / "artifacts/v5-final/parent-native/s11-v2-execution-readiness-v4"
    / "execution-readiness-go-v4.json"
)
READINESS_V4_DIGEST = "7a624e305178993c2d4087f5ee5f4bfc459e96d1efdae2b83c7ca0d7bc277878"
DECISION = "GO_S11_V2_FROZEN_QUEUE_CONTINUATION_FROM_INDEX_5"
SOURCE_PATHS = (
    "src/v5_final/full_repository_suite_v2.py",
    "src/v5_final/parent_native_development_execution_v1.py",
    "src/v5_final/parent_native_development_runtime_factory_v1.py",
    "src/v5_final/parent_native_execution_services.py",
    "src/v5_final/parent_native_persistent_runner.py",
    "src/v5_final/parent_native_work_accounting.py",
    "src/v5_final/s11_v2_execution_readiness_v4.py",
    "src/v5_final/s11_v2_execution_readiness_v5.py",
    "src/v5_final/s11_v2_execution_runner_v1.py",
    "src/v5_final/s11_v2_item002_candidate_identity_incident_v1.py",
    "src/v5_final/s11_v2_item002_retry_authorization_v1.py",
    "src/v5_final/s11_v2_native_preparation_runtime_v1.py",
    "src/v5_final/s11_v2_prepared_executor_v1.py",
    "src/v5_final/s11_v2_queue_native_adapter.py",
    "tests/test_v5_final_bfgs_runtime_parity_v1.py",
    "tests/test_v5_final_s11_v2_execution_readiness_v3.py",
    "tests/test_v5_final_s11_v2_execution_readiness_v4.py",
    "tests/test_v5_final_s11_v2_execution_readiness_v5.py",
    "tests/test_v5_final_s11_v2_execution_runner_v1.py",
    "tests/test_v5_final_s11_v2_item002_candidate_identity_incident_v1.py",
    "tests/test_v5_final_s11_v2_item002_retry_authorization_v1.py",
    "tests/test_v5_final_s11_v2_native_preparation_runtime_v1.py",
    "tests/test_v5_final_s11_v2_prepared_executor_v1.py",
    "tests/test_v5_final_s11_v2_queue_native_adapter.py",
)
SCOPED_TESTS = tuple(path for path in SOURCE_PATHS if path.startswith("tests/"))
PREDECESSOR_DIGESTS = (
    READINESS_V2_DIGEST,
    READINESS_V3_DIGEST,
    READINESS_V4_DIGEST,
)


class S11V2ExecutionReadinessV5Error(RuntimeError):
    pass


def _historical_authorization_valid(artifact: dict[str, Any]) -> bool:
    source_sha256 = artifact.get("bindings", {}).get("source_sha256", {})
    manifest = [
        {"path": path, "sha256": expected}
        for path, expected in source_sha256.items()
    ]
    commit = artifact.get("repository_head")
    return (
        artifact_is_immutable_git_blob(ITEM002_RETRY_AUTHORIZATION)
        and _embedded_digest(artifact, "authorization_digest")
        and artifact.get("decision")
        == "AUTHORIZE_S11_V2_ITEM002_SAME_ITEM_APPEND_ONLY_RETRY"
        and all(artifact.get("checks", {}).values())
        and isinstance(commit, str)
        and manifest_matches_commit(manifest, commit)
        and is_ancestor(commit)
    )


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
    readiness_v2 = _load(READINESS_V2)
    readiness_v3 = _load(READINESS_V3)
    readiness_v4 = _load(READINESS_V4)
    incident = _load(ITEM002_INCIDENT)
    retry = _load(ITEM002_RETRY_AUTHORIZATION)
    prefix = _terminal_prefix(
        adapter=adapter,
        production_root=PRODUCTION_ROOT,
        readiness_digest="0" * 64,
        predecessor_readiness_digests=PREDECESSOR_DIGESTS,
    )
    results = []
    for index in range(len(prefix)):
        request = adapter.request(str(queue["items"][index]["queue_item_id"]))
        results.append(_load(_item_paths(PRODUCTION_ROOT, index, request)["result"]))
    statuses = [receipt["terminal_status"] for receipt in prefix]
    expected_statuses = [
        "FAILED_ENGINEERING_PRESERVED",
        "COMPLETED",
        "CAP_REJECTED",
        "ALGORITHM_REJECTED",
        "COMPLETED",
    ]
    item002 = results[2]
    source_sha256 = {path: _sha(ROOT / path) for path in SOURCE_PATHS}
    checks = {
        "P7_v5_GO_valid": audit_p7_v5()["decision"]
        == "GO_S11_V2_FROZEN_90_ITEM_EXECUTION",
        "historical_readiness_chain_exact": readiness_v2["readiness_digest"]
        == READINESS_V2_DIGEST
        and readiness_v3["readiness_digest"] == READINESS_V3_DIGEST
        and readiness_v4["readiness_digest"] == READINESS_V4_DIGEST
        and all(
            artifact_is_immutable_git_blob(path)
            for path in (READINESS_V2, READINESS_V3, READINESS_V4)
        ),
        "historical_item002_incident_valid": all(
            audit_item002_incident()["checks"].values()
        )
        and incident["decision"].startswith("SUSPEND_S11_V2_READINESS_V3"),
        "historical_item002_retry_authorization_valid": _historical_authorization_valid(retry),
        "queue_cap_environment_exact": len(queue["items"]) == 90
        and len({item["queue_item_id"] for item in queue["items"]}) == 90
        and _embedded_digest(queue, "queue_digest")
        and _embedded_digest(cap, "freeze_digest")
        and environment["required_threads"]
        == {key: "1" for key in ("MKL_NUM_THREADS", "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS")},
        "terminal_prefix_is_exact_five": statuses == expected_statuses,
        "item002_retry_terminal_matches_prediction": item002["terminal_status"]
        == "CAP_REJECTED"
        and item002["candidate_energy_evaluations"] == 0
        and item002["raw_work_total"]["optimizer_starts"] == 0
        and item002["verifier_work_total"] == retry["observed"]["prior_verifier_total"],
        "aggregate_work_is_reconstructable": sum(
            int(result["candidate_energy_evaluations"]) for result in results
        ) == 75
        and sum(int(result["raw_work_total"]["optimizer_starts"]) for result in results) == 4
        and sum(int(result["FCI_evaluations"]) for result in results) == 0
        and sum(int(result["N_dense_expm"]) for result in results) == 0,
        "performance_claim_remains_closed": all(
            result["performance_claim"] == "NOT_AUTHORIZED" for result in results
        ),
        "shared_accounting_protocol_unchanged": _sha(
            ROOT / "src/v5_final/parent_native_work_accounting.py"
        ) == queue["execution_source_sha256"][
            "src/v5_final/parent_native_work_accounting.py"
        ],
        "source_bundle_present": all((ROOT / path).is_file() for path in SOURCE_PATHS),
        "storage_at_least_40_GiB": shutil.disk_usage(ROOT).free >= MINIMUM_FREE_BYTES,
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S11V2ExecutionReadinessV5Error(failures)
    evidence = _production_evidence()
    return {
        "checks": checks,
        "observed_outcomes": {
            "terminal_count": 5,
            "terminal_statuses": statuses,
            "candidate_energy_evaluations": 75,
            "optimizer_starts": 4,
            "FCI_evaluations": 0,
            "N_dense_expm": 0,
        },
        "binding": {
            "queue_v2": {"sha256": _sha(QUEUE_V2), "queue_digest": queue["queue_digest"]},
            "outcome_cap_freeze": {"sha256": _sha(CAP_FREEZE), "freeze_digest": cap["freeze_digest"]},
            "P7_v5": {"sha256": _sha(P7_V5), "gate_digest": p7["gate_digest"]},
            "readiness_v2": {"sha256": _sha(READINESS_V2), "readiness_digest": READINESS_V2_DIGEST},
            "readiness_v3": {"sha256": _sha(READINESS_V3), "readiness_digest": READINESS_V3_DIGEST},
            "readiness_v4": {"sha256": _sha(READINESS_V4), "readiness_digest": READINESS_V4_DIGEST},
            "item000_incident": {"sha256": _sha(ITEM000_INCIDENT)},
            "item002_incident": {"sha256": _sha(ITEM002_INCIDENT), "incident_digest": incident["incident_digest"]},
            "item002_retry_authorization": {"sha256": _sha(ITEM002_RETRY_AUTHORIZATION), "authorization_digest": retry["authorization_digest"]},
            "environment": {"sha256": _sha(ENVIRONMENT), "environment_digest": environment["environment_digest"]},
            "five_item_production_evidence_sha256": evidence,
            "five_item_production_evidence_digest": _digest(evidence),
            "source_sha256": source_sha256,
            "source_bundle_digest": _digest(source_sha256),
        },
    }


def capture() -> dict[str, Any]:
    if OUTPUT.exists():
        raise S11V2ExecutionReadinessV5Error("readiness v5 artifact already exists")
    branch = _git("branch", "--show-current")
    head = _git("rev-parse", "HEAD")
    if _git("status", "--porcelain"):
        raise S11V2ExecutionReadinessV5Error("capture requires a clean worktree")
    if head != _remote_head(branch):
        raise S11V2ExecutionReadinessV5Error("local and remote heads differ")
    evidence = inspect_checkpoint()
    scoped = _run([sys.executable, "-m", "pytest", "-q", *SCOPED_TESTS])
    full = _run([sys.executable, "-m", "v5_final.full_repository_suite_v2"], full_suite=True)
    if not scoped["passed"] or not full["passed"]:
        raise S11V2ExecutionReadinessV5Error("verification suite failed")
    body = {
        "schema": "v5-final.s11-v2-execution-readiness.v5",
        "stage": "PHASE_C_POST_FIVE_ITEM_CHECKPOINT",
        "status": DECISION,
        "decision": DECISION,
        "captured_repository_state": {
            "branch": branch,
            "local_head": head,
            "remote_head": head,
            "worktree_clean": True,
            "recursive_submodule_status": _git("submodule", "status", "--recursive").splitlines(),
        },
        "storage": {"available_bytes": shutil.disk_usage(ROOT).free, "required_bytes": MINIMUM_FREE_BYTES},
        "tests": {"scoped": scoped, "full_repository_suite": full},
        **evidence,
        "execution_start_index": 5,
        "item002_retry_attempt_ordinal": 2,
        "accepted_predecessor_receipt_readiness_digests": list(PREDECESSOR_DIGESTS),
        "semantic_diff": {
            "queue_changed": False,
            "method_policy_changed": False,
            "cap_changed": False,
            "outcome_information_used_to_change_protocol": False,
            "historical_test_correction": (
                "Validate incident and retry artifacts at their captured commits; "
                "validate their terminal successor in the current tree."
            ),
        },
        "blockers": [],
        "authorization": {
            "S11_v2_execution": "AUTHORIZED_EXACT_FROZEN_QUEUE_FROM_INDEX_5_ONLY",
            "candidate_energy": "AUTHORIZED_ONLY_INSIDE_EXACT_QUEUE_V2_ITEM_CAPS",
            "optimizer": "AUTHORIZED_ONLY_INSIDE_EXACT_QUEUE_V2_ITEM_CAPS",
            "FCI_reporting": "NOT_AUTHORIZED_UNTIL_ALL_90_TERMINAL",
            "performance_claim": "NOT_AUTHORIZED",
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
        "immutable_inputs_unchanged": bindings["queue_v2"]["sha256"] == _sha(QUEUE_V2)
        and bindings["outcome_cap_freeze"]["sha256"] == _sha(CAP_FREEZE)
        and bindings["P7_v5"]["sha256"] == _sha(P7_V5)
        and bindings["readiness_v4"]["sha256"] == _sha(READINESS_V4),
        "five_item_evidence_preserved": all(
            _sha(ROOT / path) == expected
            for path, expected in bindings["five_item_production_evidence_sha256"].items()
        ),
        "sources_current": all(
            _sha(ROOT / path) == expected
            for path, expected in bindings["source_sha256"].items()
        ),
        "continuation_starts_at_five": artifact["execution_start_index"] == 5,
        "predecessors_exact": artifact["accepted_predecessor_receipt_readiness_digests"]
        == list(PREDECESSOR_DIGESTS),
        "FCI_performance_closed": artifact["authorization"]["FCI_reporting"]
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
            storage_at_least_40_GiB=shutil.disk_usage(ROOT).free >= MINIMUM_FREE_BYTES,
        )
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S11V2ExecutionReadinessV5Error(failures)
    return {"decision": artifact["decision"], "readiness_digest": artifact["readiness_digest"], "checks": checks}


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

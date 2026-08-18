"""Additive readiness successor for the exact item-022 cap-rejection retry."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import shutil
import subprocess
import sys
import time
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
from .s11_v2_execution_runner_v1 import _item_paths, _terminal_prefix
from .s11_v2_item022_same_item_retry_authorization_v1 import (
    OUTPUT as ITEM022_RETRY_AUTHORIZATION,
    audit_frozen as audit_retry,
)
from .s11_v2_item022_symbolic_precheck_incident_v1 import (
    OUTPUT as ITEM022_INCIDENT,
    audit_frozen as audit_incident,
)
from .s11_v2_preexecution_gate_v5 import audit_frozen as audit_p7_v5
from .s11_v2_queue_native_adapter import QUEUE_V2, QueueV2NativeAdapter


OUTPUT_DIR = ROOT / "artifacts/v5-final/parent-native/s11-v2-execution-readiness-v6"
OUTPUT = OUTPUT_DIR / "execution-readiness-go-v6.json"
READINESS_V5 = (
    ROOT / "artifacts/v5-final/parent-native/s11-v2-execution-readiness-v5"
    / "execution-readiness-go-v5.json"
)
DECISION = "GO_S11_V2_ITEM022_SAME_ITEM_PREVERIFIER_CAP_RETRY"
PR_NUMBER = 8
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
    "src/v5_final/s11_v2_item022_symbolic_precheck_incident_v1.py",
    "src/v5_final/s11_v2_item022_same_item_retry_authorization_v1.py",
    "src/v5_final/s11_v2_execution_readiness_v6.py",
    "tests/test_v5_final_full_repository_suite_v2.py",
    "tests/test_v5_final_s11_v2_relation_aware_symbolic_precheck_v1.py",
    "tests/test_v5_final_s11_v2_execution_runner_v1.py",
    "tests/test_v5_final_s11_v2_item022_symbolic_precheck_incident_v1.py",
    "tests/test_v5_final_s11_v2_item022_same_item_retry_authorization_v1.py",
    "tests/test_v5_final_s11_v2_execution_readiness_v6.py",
)
SCOPED_TESTS = tuple(path for path in SOURCE_PATHS if path.startswith("tests/"))


class S11V2ExecutionReadinessV6Error(RuntimeError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _live_pr_snapshot(
    *, expected_head: str, attempts: int = 4, initial_delay_seconds: float = 1.0
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for ordinal in range(1, attempts + 1):
        completed = subprocess.run(
            [
                "gh", "pr", "view", str(PR_NUMBER), "--json",
                "number,state,isDraft,headRefName,baseRefName,headRefOid,statusCheckRollup,url",
            ],
            cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        record: dict[str, Any] = {
            "attempt": ordinal,
            "timestamp_utc": _utc_now(),
            "request_type": "GitHub GraphQL pullRequest statusCheckRollup",
            "exit_code": completed.returncode,
            "stderr": completed.stderr[-1000:],
        }
        if completed.returncode == 0:
            try:
                value = json.loads(completed.stdout)
            except json.JSONDecodeError as error:
                record["classification"] = "INVALID_JSON"
                records.append(record)
                raise S11V2ExecutionReadinessV6Error(
                    "live repository check returned invalid JSON"
                ) from error
            checks = value.pop("statusCheckRollup")
            normalized = [
                {
                    "name": item.get("name"),
                    "workflow_name": item.get("workflowName"),
                    "status": item.get("status"),
                    "conclusion": item.get("conclusion"),
                    "details_url": item.get("detailsUrl"),
                }
                for item in checks
            ]
            record["classification"] = "SUCCESS"
            records.append(record)
            if (
                value.get("headRefOid") != expected_head
                or value.get("state") != "OPEN"
                or not normalized
                or any(
                    item["status"] != "COMPLETED" or item["conclusion"] != "SUCCESS"
                    for item in normalized
                )
            ):
                raise S11V2ExecutionReadinessV6Error(
                    "live repository checks are not green for the captured head"
                )
            return {"pull_request": value, "checks": normalized, "attempts": records}
        text = (completed.stderr + "\n" + completed.stdout).lower()
        record["http_status"] = 503 if "503" in text else None
        record["classification"] = (
            "TRANSIENT_HTTP_503" if record["http_status"] == 503 else "EXTERNAL_FAILURE"
        )
        records.append(record)
        if ordinal < attempts:
            time.sleep(initial_delay_seconds * (2 ** (ordinal - 1)))
    raise S11V2ExecutionReadinessV6Error(
        "live repository checks failed after bounded retries: "
        + json.dumps(records, sort_keys=True)
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
    readiness_v5 = _load(READINESS_V5)
    incident = _load(ITEM022_INCIDENT)
    retry = _load(ITEM022_RETRY_AUTHORIZATION)
    predecessor_digests = tuple(
        readiness_v5["accepted_predecessor_receipt_readiness_digests"]
    ) + (readiness_v5["readiness_digest"],)
    prefix = _terminal_prefix(
        adapter=adapter,
        production_root=PRODUCTION_ROOT,
        readiness_digest="0" * 64,
        predecessor_readiness_digests=predecessor_digests,
    )
    item022 = adapter.request(queue["items"][22]["queue_item_id"])
    paths = _item_paths(PRODUCTION_ROOT, 22, item022)
    replay = replay_raw_ledger(
        paths["raw"], request=item022.work_request, cap=item022.outcome_cap,
        require_terminal=False,
    )
    results = [
        _load(
            _item_paths(
                PRODUCTION_ROOT, index, adapter.request(item["queue_item_id"])
            )["result"]
        )
        for index, item in enumerate(queue["items"][: len(prefix)])
    ]
    source_sha256 = {path: _sha(ROOT / path) for path in SOURCE_PATHS}
    checks = {
        "P7_v5_GO_valid": audit_p7_v5()["decision"]
        == "GO_S11_V2_FROZEN_90_ITEM_EXECUTION",
        "queue_cap_P7_environment_exact": len(queue["items"]) == 90
        and _embedded_digest(queue, "queue_digest")
        and _embedded_digest(cap, "freeze_digest")
        and p7["gate_digest"] == "701a327f20a4a195c1710af548211f541a2932b8d545492b9d219de9bd95b8b7"
        and environment["required_threads"]
        == {key: "1" for key in ("MKL_NUM_THREADS", "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS")},
        "terminal_prefix_is_exact_22": len(prefix) == 22,
        "incident_and_retry_gate_valid": all(audit_incident()["checks"].values())
        and all(audit_retry()["checks"].values()),
        "item022_exactly_rolled_back_nonterminal": replay.terminal is None
        and replay.active_attempt_id is None
        and len(replay.attempt_ids) == 1
        and replay.rolled_back_attempt_ids == replay.attempt_ids
        and replay.records[-1]["record_digest"]
        == incident["bindings"]["pre_retry_last_record_digest"]
        and not paths["result"].exists()
        and not paths["receipt"].exists(),
        "corrected_bound_rejects_unchanged_cap": retry["observed"][
            "corrected_relation_aware_upper_bound"
        ] == 452
        and retry["observed"]["frozen_symbolic_cap"] == 447
        and retry["observed"]["selected_relation_symbolic_costs"] == [5, 5, 5, 10],
        "item022_outcome_services_remain_zero": all(
            event.operation not in {"candidate-energy-evaluation", "optimizer-start"}
            for event in replay.work_events
        )
        and incident["observed"]["FCI_evaluations"] == 0
        and incident["observed"]["N_dense_expm"] == 0,
        "production_dense_and_FCI_remain_zero": sum(
            int(result["N_dense_expm"]) for result in results
        ) == 0
        and sum(int(result["FCI_evaluations"]) for result in results) == 0,
        "performance_claim_remains_closed": all(
            result["performance_claim"] == "NOT_AUTHORIZED" for result in results
        ),
        "source_bundle_present": all((ROOT / path).is_file() for path in SOURCE_PATHS),
        "storage_at_least_40_GiB": shutil.disk_usage(ROOT).free >= MINIMUM_FREE_BYTES,
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S11V2ExecutionReadinessV6Error(failures)
    evidence = _production_evidence()
    return {
        "checks": checks,
        "observed": {
            "terminal_count": len(prefix),
            "item022_status": "ROLLED_BACK_NONTERMINAL",
            "item022_corrected_upper_bound": 452,
            "item022_frozen_symbolic_cap": 447,
            "candidate_energy_evaluations_before_retry": sum(
                int(result["candidate_energy_evaluations"]) for result in results
            ),
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
            "readiness_v5": {
                "sha256": _sha(READINESS_V5),
                "readiness_digest": readiness_v5["readiness_digest"],
            },
            "item022_incident": {
                "sha256": _sha(ITEM022_INCIDENT),
                "incident_digest": incident["incident_digest"],
            },
            "item022_retry_authorization": {
                "sha256": _sha(ITEM022_RETRY_AUTHORIZATION),
                "authorization_digest": retry["authorization_digest"],
            },
            "environment": {
                "sha256": _sha(ENVIRONMENT),
                "environment_digest": environment["environment_digest"],
            },
            "pre_retry_production_evidence_sha256": evidence,
            "pre_retry_production_evidence_digest": _digest(evidence),
            "source_sha256": source_sha256,
            "source_bundle_digest": _digest(source_sha256),
        },
        "accepted_predecessor_receipt_readiness_digests": list(predecessor_digests),
    }


def capture() -> dict[str, Any]:
    if OUTPUT.exists():
        raise S11V2ExecutionReadinessV6Error("readiness v6 artifact already exists")
    branch = _git("branch", "--show-current")
    head = _git("rev-parse", "HEAD")
    if _git("status", "--porcelain"):
        raise S11V2ExecutionReadinessV6Error("capture requires a clean worktree")
    if head != _remote_head(branch):
        raise S11V2ExecutionReadinessV6Error("local and remote heads differ")
    evidence = inspect_checkpoint()
    scoped = _run([sys.executable, "-m", "pytest", "-q", *SCOPED_TESTS])
    full = _run([sys.executable, "-m", "v5_final.full_repository_suite_v2"], full_suite=True)
    if not scoped["passed"] or not full["passed"]:
        raise S11V2ExecutionReadinessV6Error("local verification suite failed")
    live = _live_pr_snapshot(expected_head=head)
    body = {
        "schema": "v5-final.s11-v2-execution-readiness.v6",
        "stage": "PHASE_C_ITEM022_PREVERIFIER_RETRY_READINESS",
        "status": DECISION,
        "decision": DECISION,
        "captured_repository_state": {
            "branch": branch,
            "local_head": head,
            "remote_head": head,
            "worktree_clean": True,
            "recursive_submodule_status": _git("submodule", "status", "--recursive").splitlines(),
        },
        "storage": {
            "available_bytes": shutil.disk_usage(ROOT).free,
            "required_bytes": MINIMUM_FREE_BYTES,
        },
        "tests": {
            "scoped": scoped,
            "full_repository_suite": full,
            "core_offline_and_historical_partitions": "PASS",
            "live_repository_checks": live,
        },
        **evidence,
        "execution_start_index": 22,
        "item022_retry_attempt_ordinal": 2,
        "blockers": [],
        "authorization": {
            "item022_retry": "AUTHORIZED_ONCE_PREVERIFIER_CAP_REJECTION_ONLY",
            "S11_v2_after_item022": (
                "AUTHORIZED_EXACT_FROZEN_ORDER_AFTER_TERMINAL_PREFIX_RECONCILIATION"
            ),
            "candidate_energy": "AUTHORIZED_ONLY_INSIDE_LATER_EXACT_QUEUE_V2_ITEM_CAPS",
            "optimizer": "AUTHORIZED_ONLY_INSIDE_LATER_EXACT_QUEUE_V2_ITEM_CAPS",
            "FCI_reporting": "NOT_AUTHORIZED_UNTIL_ALL_90_TERMINAL",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "semantic_diff": {
            "queue_changed": False,
            "cap_changed": False,
            "ranking_changed": False,
            "selected_candidate_identity_changed": False,
            "method_semantics_changed": False,
            "outcome_information_used": False,
            "precheck_correction": "relation-arity-derived conservative symbolic bound",
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
        and bindings["readiness_v5"]["sha256"] == _sha(READINESS_V5)
        and bindings["item022_incident"]["sha256"] == _sha(ITEM022_INCIDENT)
        and bindings["item022_retry_authorization"]["sha256"]
        == _sha(ITEM022_RETRY_AUTHORIZATION),
        "pre_retry_evidence_preserved": all(
            _sha(ROOT / path) == expected
            for path, expected in bindings["pre_retry_production_evidence_sha256"].items()
        ),
        "sources_current": all(
            _sha(ROOT / path) == expected
            for path, expected in bindings["source_sha256"].items()
        ),
        "tests_and_live_checks_recorded_green": artifact["tests"]["scoped"]["passed"]
        and artifact["tests"]["full_repository_suite"]["passed"]
        and all(
            item["status"] == "COMPLETED" and item["conclusion"] == "SUCCESS"
            for item in artifact["tests"]["live_repository_checks"]["checks"]
        ),
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
        raise S11V2ExecutionReadinessV6Error(failures)
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

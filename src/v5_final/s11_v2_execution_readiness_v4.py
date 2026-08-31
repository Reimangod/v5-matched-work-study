"""Authorize one same-cap item-002 retry and subsequent frozen queue order."""

from __future__ import annotations

from dataclasses import asdict
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Mapping

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .historical_artifact_audit import artifact_is_immutable_git_blob
from .parent_native_persistent_runner import replay_raw_ledger
from .s0_successor import ROOT
from .s11_v2_execution_runner_v1 import _item_paths, _terminal_prefix
from .s11_v2_item002_candidate_identity_incident_v1 import (
    OUTPUT as ITEM002_INCIDENT,
    audit_frozen as audit_item002_incident,
)
from .s11_v2_item002_retry_authorization_v1 import (
    OUTPUT as ITEM002_RETRY_AUTHORIZATION,
    audit_frozen as audit_item002_retry,
)
from .s11_v2_native_preparation_runtime_v1 import CumulativeVerifierLedger
from .s11_v2_preexecution_gate_v5 import OUTPUT as P7_V5, audit_frozen as audit_p7_v5
from .s11_v2_queue_native_adapter import QUEUE_V2, QueueV2NativeAdapter


OUTPUT_DIR = ROOT / "artifacts/v5-final/parent-native/s11-v2-execution-readiness-v4"
OUTPUT = OUTPUT_DIR / "execution-readiness-go-v4.json"
READINESS_V2 = (
    ROOT / "artifacts/v5-final/parent-native/s11-v2-execution-readiness-v2"
    / "execution-readiness-go-v2.json"
)
READINESS_V3 = (
    ROOT / "artifacts/v5-final/parent-native/s11-v2-execution-readiness-v3"
    / "execution-readiness-go-v3.json"
)
CAP_FREEZE = (
    ROOT / "artifacts/v5-final/parent-native/s11-v2-outcome-cap-freeze-v1"
    / "outcome-cap-freeze-v1.json"
)
ENVIRONMENT = ROOT / "artifacts/v5-final/mb6-v2/execution-environment-v2.json"
ITEM000_INCIDENT = (
    ROOT / "artifacts/v5-final/parent-native/s11-v2-item000-incident-v1"
    / "environment-contract-incident-v1.json"
)
PRODUCTION_ROOT = ROOT / "artifacts/v5-final/parent-native/s11-v2-production-execution-v1"
DECISION = "GO_S11_V2_ITEM002_RETRY_AND_FROZEN_QUEUE_CONTINUATION"
READINESS_V2_DIGEST = "5ce843ca5d057594d490243055cd657086ea8a60275c41623ff7a9e4aee6d409"
READINESS_V3_DIGEST = "85cce0cc03289753f146f7d2cb4cfd12789dfd9f156f6a8ca292a5daa404e355"
MINIMUM_FREE_BYTES = 40 * 1024**3
SOURCE_PATHS = (
    "src/v5_final/full_repository_suite_v2.py",
    "src/v5_final/parent_native_development_execution_v1.py",
    "src/v5_final/parent_native_development_runtime_factory_v1.py",
    "src/v5_final/parent_native_execution_services.py",
    "src/v5_final/parent_native_persistent_runner.py",
    "src/v5_final/parent_native_work_accounting.py",
    "src/v5_final/s11_v2_execution_readiness_v4.py",
    "src/v5_final/s11_v2_execution_runner_v1.py",
    "src/v5_final/s11_v2_item002_candidate_identity_incident_v1.py",
    "src/v5_final/s11_v2_item002_retry_authorization_v1.py",
    "src/v5_final/s11_v2_native_preparation_runtime_v1.py",
    "src/v5_final/s11_v2_prepared_executor_v1.py",
    "src/v5_final/s11_v2_queue_native_adapter.py",
    "tests/test_v5_final_bfgs_runtime_parity_v1.py",
    "tests/test_v5_final_s11_v2_execution_readiness_v3.py",
    "tests/test_v5_final_s11_v2_execution_readiness_v4.py",
    "tests/test_v5_final_s11_v2_execution_runner_v1.py",
    "tests/test_v5_final_s11_v2_item002_candidate_identity_incident_v1.py",
    "tests/test_v5_final_s11_v2_item002_retry_authorization_v1.py",
    "tests/test_v5_final_s11_v2_native_preparation_runtime_v1.py",
    "tests/test_v5_final_s11_v2_prepared_executor_v1.py",
    "tests/test_v5_final_s11_v2_queue_native_adapter.py",
)
SCOPED_TESTS = tuple(path for path in SOURCE_PATHS if path.startswith("tests/"))


class S11V2ExecutionReadinessV4Error(RuntimeError):
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
        raise S11V2ExecutionReadinessV4Error(f"invalid JSON: {path}") from error
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise S11V2ExecutionReadinessV4Error(f"noncanonical artifact: {path}")
    return value


def _embedded_digest(value: Mapping[str, Any], field: str) -> bool:
    body = dict(value)
    observed = body.pop(field, None)
    return isinstance(observed, str) and observed == _digest(body)


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout.rstrip("\n")


def _remote_head(branch: str) -> str:
    line = subprocess.run(
        ["git", "ls-remote", "--heads", "origin", f"refs/heads/{branch}"],
        cwd=ROOT, check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout.strip()
    if not line:
        raise S11V2ExecutionReadinessV4Error("remote branch is absent")
    return line.split()[0]


def _run(command: list[str], *, full_suite: bool = False) -> dict[str, Any]:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        (
            str(ROOT / "src"),
            str(ROOT / "provenance/dvg-obs-ceo/src"),
            str(ROOT / "provenance/dvg-obs-ceo/vendor/ceo-adapt-vqe"),
        )
    )
    environment.update(
        OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1"
    )
    completed = subprocess.run(
        command, cwd=ROOT, env=environment, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    return {
        "command": command,
        "exit_code": completed.returncode,
        "passed": completed.returncode == 0,
        "stdout_sha256": hashlib.sha256(completed.stdout.encode()).hexdigest(),
        "last_lines": completed.stdout.splitlines()[-12:],
        "suite_scope": "full_repository" if full_suite else "readiness_scoped",
    }


def _production_evidence() -> dict[str, str]:
    return {
        str(path.relative_to(ROOT)): _sha(path)
        for path in sorted(PRODUCTION_ROOT.rglob("*.json"))
    }


def inspect_pre_retry() -> dict[str, Any]:
    adapter = QueueV2NativeAdapter()
    queue = adapter.queue
    cap = _load(CAP_FREEZE)
    p7 = _load(P7_V5)
    readiness_v2 = _load(READINESS_V2)
    readiness_v3 = _load(READINESS_V3)
    environment = _load(ENVIRONMENT)
    incident = _load(ITEM002_INCIDENT)
    authorization = _load(ITEM002_RETRY_AUTHORIZATION)
    item002 = adapter.request(str(queue["items"][2]["queue_item_id"]))
    paths = _item_paths(PRODUCTION_ROOT, 2, item002)
    replay = replay_raw_ledger(
        paths["raw"], request=item002.work_request,
        cap=item002.outcome_cap, require_terminal=False,
    )
    verifier = CumulativeVerifierLedger(
        paths["verifier"], cap=item002.item["verifier_componentwise_cap"]
    )
    verifier_rounds = verifier.replay()
    prefix = _terminal_prefix(
        adapter=adapter,
        production_root=PRODUCTION_ROOT,
        readiness_digest="0" * 64,
        predecessor_readiness_digests=(READINESS_V2_DIGEST, READINESS_V3_DIGEST),
    )
    results = [
        _load(_item_paths(PRODUCTION_ROOT, index, adapter.request(
            str(queue["items"][index]["queue_item_id"])
        ))["result"])
        for index in range(len(prefix))
    ]
    retry_dispatch = paths["dispatch"].with_name(
        paths["dispatch"].stem + "-retry-0002.json"
    )
    source_sha256 = {path: _sha(ROOT / path) for path in SOURCE_PATHS}
    checks = {
        "P7_v5_GO_valid": audit_p7_v5()["decision"]
        == "GO_S11_V2_FROZEN_90_ITEM_EXECUTION",
        "readiness_v2_v3_immutable_chain": readiness_v2["readiness_digest"]
        == READINESS_V2_DIGEST
        and readiness_v3["readiness_digest"] == READINESS_V3_DIGEST
        and incident["decision"].startswith("SUSPEND_S11_V2_READINESS_V3"),
        "item002_incident_audit_passed": all(
            audit_item002_incident()["checks"].values()
        ),
        "item002_retry_authorization_audit_passed": all(
            audit_item002_retry()["checks"].values()
        ),
        "queue_is_exact_frozen_90": len(queue["items"]) == 90
        and len({item["queue_item_id"] for item in queue["items"]}) == 90
        and _embedded_digest(queue, "queue_digest")
        and _embedded_digest(cap, "freeze_digest"),
        "queue_cap_P7_environment_unchanged": p7["artifact_bindings"][
            "queue_v2_sha256"
        ] == _sha(QUEUE_V2)
        and p7["artifact_bindings"]["outcome_cap_freeze_sha256"] == _sha(CAP_FREEZE)
        and environment["required_threads"]
        == {key: "1" for key in ("MKL_NUM_THREADS", "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS")},
        "terminal_prefix_is_exact_two": [receipt["terminal_status"] for receipt in prefix]
        == ["FAILED_ENGINEERING_PRESERVED", "COMPLETED"],
        "item002_exact_rollback_is_append_only_ready": replay.terminal is None
        and replay.active_attempt_id is None
        and len(replay.attempt_ids) == 1
        and replay.rolled_back_attempt_ids == replay.attempt_ids
        and len(replay.records) == 5,
        "item002_prior_work_and_verifier_preserved": len(verifier_rounds) == 1
        and verifier.total == authorization["observed"]["prior_verifier_total"]
        and asdict(replay.work_total) == authorization["observed"]["prior_raw_work_total"],
        "item002_has_no_outcome_terminal_or_retry_dispatch": not paths["result"].exists()
        and not paths["receipt"].exists()
        and not paths["raw"].with_suffix(".outcome.json").exists()
        and not retry_dispatch.exists(),
        "retry_is_same_cap_no_reset_expected_cap_rejection": authorization[
            "semantic_diff"
        ]["cap_changed"] is False
        and authorization["semantic_diff"]["counter_reset"] is False
        and authorization["semantic_diff"]["expected_terminal"]
        == "CAP_REJECTED_BEFORE_NEW_VERIFIER_SESSION"
        and authorization["observed"]["predicted_cap_rejection_reason"].startswith(
            "verifier cap rejected before session:"
        ),
        "current_outcomes_are_only_item001": sum(
            int(result["candidate_energy_evaluations"]) for result in results
        ) == 1
        and sum(int(result["raw_work_total"]["optimizer_starts"]) for result in results) == 1
        and sum(int(result["FCI_evaluations"]) for result in results) == 0
        and sum(int(result["N_dense_expm"]) for result in results) == 0,
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
        raise S11V2ExecutionReadinessV4Error(failures)
    production_sha256 = _production_evidence()
    return {
        "checks": checks,
        "observed_outcomes": {
            "terminal_count": 2,
            "FAILED_ENGINEERING_PRESERVED": 1,
            "COMPLETED": 1,
            "item002_status": "ROLLED_BACK_UNTERMINATED",
            "candidate_energy_evaluations": 1,
            "optimizer_starts": 1,
            "FCI_evaluations": 0,
            "N_dense_expm": 0,
        },
        "binding": {
            "queue_v2": {"sha256": _sha(QUEUE_V2), "queue_digest": queue["queue_digest"]},
            "outcome_cap_freeze": {"sha256": _sha(CAP_FREEZE), "freeze_digest": cap["freeze_digest"]},
            "P7_v5": {"sha256": _sha(P7_V5), "gate_digest": p7["gate_digest"]},
            "readiness_v2": {"sha256": _sha(READINESS_V2), "readiness_digest": READINESS_V2_DIGEST},
            "readiness_v3": {"sha256": _sha(READINESS_V3), "readiness_digest": READINESS_V3_DIGEST},
            "item000_incident": {"sha256": _sha(ITEM000_INCIDENT)},
            "item002_incident": {"sha256": _sha(ITEM002_INCIDENT), "incident_digest": incident["incident_digest"]},
            "item002_retry_authorization": {
                "sha256": _sha(ITEM002_RETRY_AUTHORIZATION),
                "authorization_digest": authorization["authorization_digest"],
            },
            "environment": {"sha256": _sha(ENVIRONMENT), "environment_digest": environment["environment_digest"]},
            "pre_retry_production_evidence_sha256": production_sha256,
            "pre_retry_production_evidence_digest": _digest(production_sha256),
            "source_sha256": source_sha256,
            "source_bundle_digest": _digest(source_sha256),
        },
    }


def capture() -> dict[str, Any]:
    if OUTPUT.exists():
        raise S11V2ExecutionReadinessV4Error("readiness v4 artifact already exists")
    branch = _git("branch", "--show-current")
    local_head = _git("rev-parse", "HEAD")
    if _git("status", "--porcelain"):
        raise S11V2ExecutionReadinessV4Error("capture requires a clean worktree")
    if local_head != _remote_head(branch):
        raise S11V2ExecutionReadinessV4Error("local and remote heads differ")
    evidence = inspect_pre_retry()
    scoped = _run([sys.executable, "-m", "pytest", "-q", *SCOPED_TESTS])
    full = _run([sys.executable, "-m", "v5_final.full_repository_suite_v2"], full_suite=True)
    if not scoped["passed"] or not full["passed"]:
        raise S11V2ExecutionReadinessV4Error("verification suite failed")
    body = {
        "schema": "v5-final.s11-v2-execution-readiness.v4",
        "stage": "PHASE_C_ITEM002_APPEND_ONLY_RETRY_PRE_DISPATCH",
        "status": DECISION,
        "decision": DECISION,
        "captured_repository_state": {
            "branch": branch,
            "local_head": local_head,
            "remote_head": local_head,
            "worktree_clean": True,
            "recursive_submodule_status": _git("submodule", "status", "--recursive").splitlines(),
        },
        "storage": {"available_bytes": shutil.disk_usage(ROOT).free, "required_bytes": MINIMUM_FREE_BYTES},
        "tests": {"scoped": scoped, "full_repository_suite": full},
        **evidence,
        "execution_start_index": 2,
        "retry_attempt_ordinal": 2,
        "accepted_predecessor_receipt_readiness_digests": [
            READINESS_V2_DIGEST,
            READINESS_V3_DIGEST,
        ],
        "semantic_diff": {
            "queue_changed": False,
            "candidate_payload_changed": False,
            "candidate_set_changed": False,
            "ranking_changed": False,
            "tie_break_changed": False,
            "cap_changed": False,
            "counter_reset": False,
            "outcome_information_used": False,
            "item002_retry_expected_terminal": "CAP_REJECTED_BEFORE_NEW_VERIFIER_SESSION",
        },
        "blockers": [],
        "authorization": {
            "S11_v2_execution": "AUTHORIZED_EXACT_FROZEN_QUEUE_FROM_ITEM002_RETRY",
            "item002_retry": "AUTHORIZED_ONCE_APPEND_ONLY_SAME_CAP_EXPECTED_CAP_REJECTION",
            "candidate_energy": "AUTHORIZED_ONLY_INSIDE_EXACT_QUEUE_V2_ITEM_CAPS",
            "optimizer": "AUTHORIZED_ONLY_INSIDE_EXACT_QUEUE_V2_ITEM_CAPS",
            "FCI_reporting": "NOT_AUTHORIZED_UNTIL_ALL_90_TERMINAL",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "scientific_boundary": (
            "Item 002 may append exactly attempt 2 under the unchanged frozen cap. "
            "Its preserved first-attempt verifier work predicts a pre-session cap rejection; "
            "no counter reset, cap expansion, candidate outcome, or policy change is authorized."
        ),
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
        and bindings["environment"]["sha256"] == _sha(ENVIRONMENT)
        and bindings["item000_incident"]["sha256"] == _sha(ITEM000_INCIDENT)
        and bindings["item002_incident"]["sha256"] == _sha(ITEM002_INCIDENT)
        and bindings["item002_retry_authorization"]["sha256"] == _sha(ITEM002_RETRY_AUTHORIZATION),
        "pre_retry_evidence_preserved": all(
            _sha(ROOT / path) == expected
            for path, expected in bindings["pre_retry_production_evidence_sha256"].items()
        ),
        "sources_current": all(
            _sha(ROOT / path) == expected
            for path, expected in bindings["source_sha256"].items()
        ),
        "single_same_cap_retry_no_reset": artifact["execution_start_index"] == 2
        and artifact["retry_attempt_ordinal"] == 2
        and artifact["semantic_diff"]["cap_changed"] is False
        and artifact["semantic_diff"]["counter_reset"] is False,
        "predecessor_receipts_accepted_exactly": artifact[
            "accepted_predecessor_receipt_readiness_digests"
        ] == [READINESS_V2_DIGEST, READINESS_V3_DIGEST],
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
        raise S11V2ExecutionReadinessV4Error(failures)
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

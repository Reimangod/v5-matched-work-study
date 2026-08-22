"""Post-incident, outcome-free S11-v2 execution readiness successor."""

from __future__ import annotations

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
from .s0_successor import ROOT
from .s11_v2_item000_environment_incident_v1 import (
    OUTPUT as ITEM000_INCIDENT,
    audit_frozen as audit_incident,
)
from .s11_v2_preexecution_gate_v5 import OUTPUT as P7_V5, audit_frozen as audit_p7_v5
from .s11_v2_queue_native_adapter import QUEUE_V2, QueueV2NativeAdapter


OUTPUT_DIR = ROOT / "artifacts/v5-final/parent-native/s11-v2-execution-readiness-v3"
OUTPUT = OUTPUT_DIR / "execution-readiness-go-v3.json"
READINESS_V2 = (
    ROOT
    / "artifacts/v5-final/parent-native/s11-v2-execution-readiness-v2"
    / "execution-readiness-go-v2.json"
)
CAP_FREEZE = (
    ROOT
    / "artifacts/v5-final/parent-native/s11-v2-outcome-cap-freeze-v1"
    / "outcome-cap-freeze-v1.json"
)
ENVIRONMENT = ROOT / "artifacts/v5-final/mb6-v2/execution-environment-v2.json"
PRODUCTION_ROOT = ROOT / "artifacts/v5-final/parent-native/s11-v2-production-execution-v1"
ITEM000_RESULT = PRODUCTION_ROOT / "results/0000-a68dfee7446bd6b0.json"
ITEM000_RECEIPT = PRODUCTION_ROOT / "receipts/0000-a68dfee7446bd6b0.json"
DECISION = "GO_S11_V2_EXACT_RUNNER_ONE_THREAD_POST_INCIDENT_EXECUTION"
READINESS_V2_DIGEST = "5ce843ca5d057594d490243055cd657086ea8a60275c41623ff7a9e4aee6d409"
MINIMUM_FREE_BYTES = 40 * 1024**3
SOURCE_PATHS = (
    "src/v5_final/parent_native_work_accounting.py",
    "src/v5_final/s11_v2_queue_native_adapter.py",
    "src/v5_final/s11_v2_native_preparation_runtime_v1.py",
    "src/v5_final/s11_v2_prepared_executor_v1.py",
    "src/v5_final/s11_v2_execution_runner_v1.py",
    "src/v5_final/s11_v2_item000_environment_incident_v1.py",
    "src/v5_final/s11_v2_execution_readiness_v3.py",
    "src/v5_final/parent_native_development_execution_v1.py",
    "src/v5_final/parent_native_development_runtime_factory_v1.py",
    "src/v5_final/parent_native_execution_services.py",
    "src/v5_final/parent_native_persistent_runner.py",
    "tests/test_v5_final_s11_v2_execution_runner_v1.py",
    "tests/test_v5_final_s11_v2_item000_environment_incident_v1.py",
    "tests/test_v5_final_s11_v2_execution_readiness_v3.py",
    "tests/test_v5_final_s11_v2_native_preparation_runtime_v1.py",
    "tests/test_v5_final_s11_v2_prepared_executor_v1.py",
    "tests/test_v5_final_s11_v2_queue_native_adapter.py",
    "tests/test_v5_final_bfgs_runtime_parity_v1.py",
)
SCOPED_TESTS = tuple(path for path in SOURCE_PATHS if path.startswith("tests/"))


class S11V2ExecutionReadinessV3Error(RuntimeError):
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
        raise S11V2ExecutionReadinessV3Error(f"invalid JSON: {path}") from error
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise S11V2ExecutionReadinessV3Error(f"noncanonical artifact: {path}")
    return value


def _embedded_digest(value: Mapping[str, Any], field: str) -> bool:
    body = dict(value)
    observed = body.pop(field, None)
    return isinstance(observed, str) and observed == _digest(body)


def _production_item_stem(path: Path) -> str:
    parts = path.relative_to(PRODUCTION_ROOT).parts
    if parts[0] in {"raw-ledgers", "verifier-ledgers"} and len(parts) > 2:
        return parts[1]
    return path.name


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
        raise S11V2ExecutionReadinessV3Error("remote branch is absent")
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
    if not full_suite:
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
    }


def inspect_outcome_free() -> dict[str, Any]:
    queue = _load(QUEUE_V2)
    cap = _load(CAP_FREEZE)
    p7 = _load(P7_V5)
    readiness_v2 = _load(READINESS_V2)
    incident = _load(ITEM000_INCIDENT)
    environment = _load(ENVIRONMENT)
    result = _load(ITEM000_RESULT)
    receipt = _load(ITEM000_RECEIPT)
    adapter = QueueV2NativeAdapter()
    production_files = sorted(path for path in PRODUCTION_ROOT.rglob("*") if path.is_file())
    expected_files = 9
    source_sha256 = {path: _sha(ROOT / path) for path in SOURCE_PATHS}
    checks = {
        "P7_v5_GO_valid": audit_p7_v5()["decision"]
        == "GO_S11_V2_FROZEN_90_ITEM_EXECUTION",
        "readiness_v2_preserved_and_suspended": readiness_v2["readiness_digest"]
        == READINESS_V2_DIGEST
        and incident["decision"].startswith("SUSPEND_S11_V2_READINESS_V2"),
        "incident_audit_passed": all(audit_incident()["checks"].values()),
        "queue_and_cap_unchanged": _embedded_digest(queue, "queue_digest")
        and _embedded_digest(cap, "freeze_digest")
        and adapter.queue["queue_digest"] == queue["queue_digest"],
        "queue_environment_is_exact_one_thread": environment["required_threads"]
        == {key: "1" for key in ("MKL_NUM_THREADS", "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS")},
        "item000_terminal_preserved_without_retry": result["terminal_status"]
        == "FAILED_ENGINEERING_PRESERVED"
        and receipt["terminal_status"] == "FAILED_ENGINEERING_PRESERVED"
        and receipt["execution_readiness_digest"] == READINESS_V2_DIGEST,
        "item000_has_zero_candidate_optimizer_FCI_dense": result[
            "candidate_energy_evaluations"
        ]
        == 0
        and result["raw_work_total"]["optimizer_iterations"] == 0
        and result["FCI_evaluations"] == 0
        and result["N_dense_expm"] == 0,
        "production_namespace_is_exact_incident_prefix": len(production_files)
        == expected_files,
        "remaining_89_have_no_production_artifacts": not any(
            any(
                _production_item_stem(path).startswith(f"{index:04d}-")
                for index in range(1, 90)
            )
            for path in production_files
            if path.relative_to(PRODUCTION_ROOT).parts[0]
            in {"dispatch", "raw-ledgers", "results", "receipts", "verifier-ledgers"}
        ),
        "shared_accounting_protocol_remains_unchanged": _sha(
            ROOT / "src/v5_final/parent_native_work_accounting.py"
        )
        == queue["execution_source_sha256"][
            "src/v5_final/parent_native_work_accounting.py"
        ],
        "source_bundle_present": all((ROOT / path).is_file() for path in SOURCE_PATHS),
        "storage_at_least_40_GiB": shutil.disk_usage(ROOT).free >= MINIMUM_FREE_BYTES,
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S11V2ExecutionReadinessV3Error(failures)
    return {
        "checks": checks,
        "observed_outcomes": {
            "terminal_count": 1,
            "FAILED_ENGINEERING_PRESERVED": 1,
            "candidate_energy_evaluations": 0,
            "optimizer_iterations": 0,
            "FCI_evaluations": 0,
            "N_dense_expm": 0,
        },
        "binding": {
            "queue_v2": {"sha256": _sha(QUEUE_V2), "queue_digest": queue["queue_digest"]},
            "outcome_cap_freeze": {"sha256": _sha(CAP_FREEZE), "freeze_digest": cap["freeze_digest"]},
            "P7_v5": {"sha256": _sha(P7_V5), "gate_digest": p7["gate_digest"]},
            "readiness_v2": {"sha256": _sha(READINESS_V2), "readiness_digest": READINESS_V2_DIGEST},
            "item000_incident": {"sha256": _sha(ITEM000_INCIDENT), "incident_digest": incident["incident_digest"]},
            "item000_result_sha256": _sha(ITEM000_RESULT),
            "item000_receipt_sha256": _sha(ITEM000_RECEIPT),
            "environment": {"sha256": _sha(ENVIRONMENT), "environment_digest": environment["environment_digest"]},
            "source_sha256": source_sha256,
            "source_bundle_digest": _digest(source_sha256),
        },
    }


def capture() -> dict[str, Any]:
    if OUTPUT.exists():
        raise S11V2ExecutionReadinessV3Error("readiness v3 artifact already exists")
    branch = _git("branch", "--show-current")
    local_head = _git("rev-parse", "HEAD")
    if _git("status", "--porcelain"):
        raise S11V2ExecutionReadinessV3Error("capture requires a clean worktree")
    if local_head != _remote_head(branch):
        raise S11V2ExecutionReadinessV3Error("local and remote heads differ")
    evidence = inspect_outcome_free()
    scoped = _run([sys.executable, "-m", "pytest", "-q", *SCOPED_TESTS])
    full = _run([sys.executable, "-m", "v5_final.full_repository_suite_v2"], full_suite=True)
    if not scoped["passed"] or not full["passed"]:
        raise S11V2ExecutionReadinessV3Error("verification suite failed")
    body = {
        "schema": "v5-final.s11-v2-execution-readiness.v3",
        "stage": "PHASE_C_POST_ITEM000_PRE_ITEM001",
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
        "execution_start_index": 1,
        "accepted_predecessor_receipt_readiness_digests": [READINESS_V2_DIGEST],
        "semantic_diff": {
            "queue_v2_changed": False,
            "method_policy_changed": False,
            "outcome_information_used": False,
            "environment_correction": "restore exact queue-bound MB6-v2 one-thread contract",
            "failure_event_correction": (
                "non-primitive failures roll back and remain unterminated pending an additive incident; "
                "no false primitive work event is created"
            ),
            "item000_retry": False,
        },
        "blockers": [],
        "authorization": {
            "S11_v2_execution": "AUTHORIZED_EXACT_FROZEN_QUEUE_FROM_INDEX_1_ONLY",
            "candidate_energy": "AUTHORIZED_ONLY_INSIDE_EXACT_QUEUE_V2_ITEM_CAPS",
            "optimizer": "AUTHORIZED_ONLY_INSIDE_EXACT_QUEUE_V2_ITEM_CAPS",
            "FCI_reporting": "NOT_AUTHORIZED_UNTIL_ALL_90_TERMINAL",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "scientific_boundary": (
            "Item 000 remains a disclosed engineering failure. No retry or outcome-based "
            "policy change is authorized. This gate only resumes the exact frozen order at item 001."
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
        "queue_cap_incident_environment_unchanged": bindings["queue_v2"]["sha256"] == _sha(QUEUE_V2)
        and bindings["outcome_cap_freeze"]["sha256"] == _sha(CAP_FREEZE)
        and bindings["item000_incident"]["sha256"] == _sha(ITEM000_INCIDENT)
        and bindings["environment"]["sha256"] == _sha(ENVIRONMENT),
        "sources_current": all(_sha(ROOT / path) == expected for path, expected in bindings["source_sha256"].items()),
        "item000_no_retry": artifact["execution_start_index"] == 1
        and artifact["semantic_diff"]["item000_retry"] is False,
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
            submodules_clean=all(line.startswith(" ") for line in _git("submodule", "status", "--recursive").splitlines()),
            storage_at_least_40_GiB=shutil.disk_usage(ROOT).free >= MINIMUM_FREE_BYTES,
        )
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S11V2ExecutionReadinessV3Error(failures)
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

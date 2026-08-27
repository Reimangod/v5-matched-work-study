"""Outcome-free successor gate for the exact S11-v2 production runner."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any, Mapping

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .historical_artifact_audit import artifact_is_immutable_git_blob
from .s0_successor import ROOT
from .s11_v2_execution_readiness_v1 import OUTPUT as READINESS_V1
from .s11_v2_preexecution_gate_v5 import OUTPUT as P7_V5, audit_frozen as audit_p7_v5
from .s11_v2_queue_native_adapter import QUEUE_V2, QueueV2NativeAdapter


OUTPUT_DIR = ROOT / "artifacts/v5-final/parent-native/s11-v2-execution-readiness-v2"
OUTPUT = OUTPUT_DIR / "execution-readiness-go-v2.json"
CAP_FREEZE = (
    ROOT
    / "artifacts/v5-final/parent-native/s11-v2-outcome-cap-freeze-v1"
    / "outcome-cap-freeze-v1.json"
)
ENVIRONMENT = (
    ROOT
    / "artifacts/v5-final/parent-native/mb6-v3"
    / "execution-environment-v3.json"
)
PRODUCTION_ROOT = (
    ROOT / "artifacts/v5-final/parent-native/s11-v2-production-execution-v1"
)
DECISION = "GO_S11_V2_EXACT_RUNNER_FROZEN_90_ITEM_EXECUTION"
MINIMUM_FREE_BYTES = 40 * 1024**3
SOURCE_PATHS = (
    "src/v5_final/s11_v2_queue_native_adapter.py",
    "src/v5_final/s11_v2_native_preparation_runtime_v1.py",
    "src/v5_final/s11_v2_prepared_executor_v1.py",
    "src/v5_final/s11_v2_execution_runner_v1.py",
    "src/v5_final/parent_native_development_execution_v1.py",
    "src/v5_final/parent_native_development_runtime_factory_v1.py",
    "src/v5_final/parent_native_execution_services.py",
    "src/v5_final/parent_native_persistent_runner.py",
    "src/v5_final/parent_native_work_accounting.py",
    "tests/test_v5_final_s11_v2_queue_native_adapter.py",
    "tests/test_v5_final_s11_v2_native_preparation_runtime_v1.py",
    "tests/test_v5_final_s11_v2_prepared_executor_v1.py",
    "tests/test_v5_final_s11_v2_execution_runner_v1.py",
    "tests/test_v5_final_bfgs_runtime_parity_v1.py",
    "src/v5_final/s11_v2_execution_readiness_v2.py",
    "tests/test_v5_final_s11_v2_execution_readiness_v2.py",
)
SCOPED_TESTS = tuple(path for path in SOURCE_PATHS if path.startswith("tests/"))


class S11V2ExecutionReadinessV2Error(RuntimeError):
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
        raise S11V2ExecutionReadinessV2Error(f"invalid JSON: {path}") from error
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise S11V2ExecutionReadinessV2Error(f"noncanonical artifact: {path}")
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
    output = subprocess.run(
        ["git", "ls-remote", "--heads", "origin", f"refs/heads/{branch}"],
        cwd=ROOT, check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout.strip()
    if not output:
        raise S11V2ExecutionReadinessV2Error("remote branch is absent")
    return output.split()[0]


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
    started = time.monotonic()
    completed = subprocess.run(
        command, cwd=ROOT, env=environment, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    return {
        "command": command,
        "exit_code": completed.returncode,
        "duration_seconds": round(time.monotonic() - started, 3),
        "stdout_sha256": hashlib.sha256(completed.stdout.encode()).hexdigest(),
        "last_lines": completed.stdout.splitlines()[-12:],
        "passed": completed.returncode == 0,
    }


def inspect_outcome_free() -> dict[str, Any]:
    queue = _load(QUEUE_V2)
    cap = _load(CAP_FREEZE)
    p7 = _load(P7_V5)
    predecessor = _load(READINESS_V1)
    environment = _load(ENVIRONMENT)
    adapter = QueueV2NativeAdapter()
    items = list(queue.get("items", ()))
    production_entries = (
        list(PRODUCTION_ROOT.rglob("*")) if PRODUCTION_ROOT.exists() else []
    )
    source_sha256 = {path: _sha(ROOT / path) for path in SOURCE_PATHS}
    method_ids = sorted({str(item["method_id"]) for item in items})
    checks = {
        "P7_v5_GO_valid": audit_p7_v5()["decision"]
        == "GO_S11_V2_FROZEN_90_ITEM_EXECUTION",
        "predecessor_readiness_is_preserved_No_Go": predecessor.get("decision")
        == "NO_GO_S11_V2_UNBOUND_DYNAMIC_VERIFIER_AND_PRODUCTION_RUNNER"
        and artifact_is_immutable_git_blob(READINESS_V1),
        "queue_v2_digest_valid": _embedded_digest(queue, "queue_digest")
        and adapter.queue["queue_digest"] == queue["queue_digest"],
        "outcome_cap_digest_valid": _embedded_digest(cap, "freeze_digest"),
        "exact_90_item_order_preserved": len(items) == 90
        and [item["queue_item_id"] for item in items]
        == [item["queue_item_id"] for item in adapter.queue["items"]],
        "six_methods_bound": len(method_ids) == 6,
        "all_items_still_NOT_STARTED": all(
            item.get("terminal_status") == "NOT_STARTED" for item in items
        ),
        "candidate_optimizer_FCI_zero": queue.get("candidate_energy_evaluations") == 0
        and queue.get("optimizer_iterations") == 0
        and queue.get("FCI_evaluations") == 0,
        "production_namespace_empty": production_entries == [],
        "production_N_dense_expm_cap_zero": all(
            item["combined_all_counter_cap"]["N_dense_expm"] == 0
            and item["verifier_componentwise_cap"]["N_dense_expm"] == 0
            for item in items
        ),
        "environment_requires_exact_two_threads": environment.get("required_threads")
        == {
            "MKL_NUM_THREADS": "2",
            "OMP_NUM_THREADS": "2",
            "OPENBLAS_NUM_THREADS": "2",
        },
        "runner_and_remediation_sources_present": all(
            (ROOT / path).is_file() for path in SOURCE_PATHS
        ),
        "storage_at_least_40_GiB": shutil.disk_usage(ROOT).free
        >= MINIMUM_FREE_BYTES,
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S11V2ExecutionReadinessV2Error(failures)
    return {
        "checks": checks,
        "observed_outcomes": {
            "candidate_energy_evaluations": 0,
            "optimizer_iterations": 0,
            "FCI_evaluations": 0,
            "production_item_artifacts": len(production_entries),
        },
        "binding": {
            "queue_v2": {
                "sha256": _sha(QUEUE_V2),
                "queue_digest": queue["queue_digest"],
            },
            "outcome_cap_freeze": {
                "sha256": _sha(CAP_FREEZE),
                "freeze_digest": cap["freeze_digest"],
            },
            "P7_v5": {"sha256": _sha(P7_V5), "gate_digest": p7["gate_digest"]},
            "predecessor_readiness_v1_sha256": _sha(READINESS_V1),
            "environment": {
                "sha256": _sha(ENVIRONMENT),
                "environment_digest": environment["environment_digest"],
            },
            "source_sha256": source_sha256,
            "source_bundle_digest": _digest(source_sha256),
            "method_ids": method_ids,
        },
    }


def capture() -> dict[str, Any]:
    if OUTPUT.exists():
        raise S11V2ExecutionReadinessV2Error("readiness v2 artifact already exists")
    branch = _git("branch", "--show-current")
    local_head = _git("rev-parse", "HEAD")
    if _git("status", "--porcelain"):
        raise S11V2ExecutionReadinessV2Error("capture requires a clean worktree")
    remote_head = _remote_head(branch)
    if local_head != remote_head:
        raise S11V2ExecutionReadinessV2Error("local and remote branch heads differ")
    evidence = inspect_outcome_free()
    scoped = _run([sys.executable, "-m", "pytest", "-q", *SCOPED_TESTS])
    full = _run(
        [sys.executable, "-m", "v5_final.full_repository_suite_v2"],
        full_suite=True,
    )
    if not scoped["passed"] or not full["passed"]:
        raise S11V2ExecutionReadinessV2Error("verification suite failed")
    body = {
        "schema": "v5-final.s11-v2-execution-readiness.v2",
        "stage": "PHASE_B_PRE_FIRST_CANDIDATE_OUTCOME",
        "status": DECISION,
        "decision": DECISION,
        "captured_repository_state": {
            "branch": branch,
            "local_head": local_head,
            "remote_head": remote_head,
            "worktree_clean": True,
            "recursive_submodule_status": _git(
                "submodule", "status", "--recursive"
            ).splitlines(),
        },
        "storage": {
            "available_bytes": shutil.disk_usage(ROOT).free,
            "required_bytes": MINIMUM_FREE_BYTES,
        },
        "tests": {"scoped": scoped, "full_repository_suite": full},
        **evidence,
        "semantic_diff": {
            "queue_v2_changed": False,
            "scientific_method_policy_changed": False,
            "outcome_information_used": False,
            "realized_missing_composition": [
                "cumulative Verifier V2 preparation ledger",
                "actual magnitude Verifier V2 builder",
                "post-commit Verifier V2 rebuilding",
                "exact queue-v2 durable production runner",
            ],
            "queue_v3_required": False,
        },
        "blockers": [],
        "authorization": {
            "S11_v2_execution": "AUTHORIZED_EXACT_FROZEN_90_ITEM_ORDER_ONLY",
            "candidate_energy": "AUTHORIZED_ONLY_INSIDE_EXACT_QUEUE_V2_ITEM_CAPS",
            "optimizer": "AUTHORIZED_ONLY_INSIDE_EXACT_QUEUE_V2_ITEM_CAPS",
            "FCI_reporting": "NOT_AUTHORIZED_UNTIL_ALL_90_TERMINAL",
            "S12_and_later": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "scientific_boundary": (
            "This additive gate realizes the already-frozen queue-v2 composition. "
            "It contains no molecular candidate outcome and makes no performance claim."
        ),
    }
    body["readiness_digest"] = _digest(body)
    return body


def write_artifact() -> None:
    artifact = capture()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_json_exclusive(OUTPUT, artifact)


def audit_frozen(*, require_live: bool = False) -> dict[str, Any]:
    artifact = _load(OUTPUT)
    bindings = artifact["binding"]
    checks = {
        "readiness_digest_valid": _embedded_digest(artifact, "readiness_digest"),
        "decision_exact": artifact.get("decision") == DECISION,
        "all_frozen_checks_passed": all(artifact.get("checks", {}).values()),
        "blockers_empty": artifact.get("blockers") == [],
        "queue_v2_unchanged": bindings["queue_v2"]["sha256"] == _sha(QUEUE_V2),
        "cap_freeze_unchanged": bindings["outcome_cap_freeze"]["sha256"]
        == _sha(CAP_FREEZE),
        "P7_v5_unchanged": bindings["P7_v5"]["sha256"] == _sha(P7_V5),
        "environment_unchanged": bindings["environment"]["sha256"]
        == _sha(ENVIRONMENT),
        "sources_current": all(
            _sha(ROOT / path) == expected
            for path, expected in bindings["source_sha256"].items()
        ),
        "FCI_and_performance_closed": artifact["authorization"]["FCI_reporting"]
        == "NOT_AUTHORIZED_UNTIL_ALL_90_TERMINAL"
        and artifact["authorization"]["performance_claim"] == "NOT_AUTHORIZED",
    }
    if require_live:
        branch = _git("branch", "--show-current")
        checks.update(
            artifact_is_immutable_git_blob=artifact_is_immutable_git_blob(OUTPUT),
            worktree_clean=_git("status", "--porcelain") == "",
            local_remote_HEAD_match=_git("rev-parse", "HEAD")
            == _remote_head(branch),
            recursive_submodules_clean=all(
                line.startswith(" ")
                for line in _git("submodule", "status", "--recursive").splitlines()
            ),
            storage_at_least_40_GiB=shutil.disk_usage(ROOT).free
            >= MINIMUM_FREE_BYTES,
        )
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S11V2ExecutionReadinessV2Error(failures)
    return {
        "status": "PASS_FROZEN_S11_V2_EXECUTION_READINESS_GO_V2",
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

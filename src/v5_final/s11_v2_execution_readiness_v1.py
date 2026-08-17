"""Additive, outcome-free execution-readiness audit for frozen S11-v2.

P7-v5 authorized the exact frozen queue, but deliberately did not bind a
production dispatch runner added after that gate.  This audit checks whether a
transport-only runner can be added without changing the frozen scientific
executor.  It never constructs a molecular runtime or invokes an outcome
kernel.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from typing import Any

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .historical_artifact_audit import (
    artifact_is_immutable_git_blob,
    manifest_matches_artifact_commit,
)
from .s0_successor import ROOT
from .s11_v2_preexecution_gate_v5 import (
    OUTPUT as P7_V5,
    audit_frozen as audit_p7_v5,
)


OUTPUT_DIR = ROOT / "artifacts/v5-final/parent-native/s11-v2-execution-readiness-v1"
OUTPUT = OUTPUT_DIR / "execution-readiness-no-go-v1.json"
QUEUE = (
    ROOT
    / "artifacts/v5-final/parent-native/s11-v2-queue-freeze-v2"
    / "s11-v2-queue-v2.json"
)
CAP_FREEZE = (
    ROOT
    / "artifacts/v5-final/parent-native/s11-v2-outcome-cap-freeze-v1"
    / "outcome-cap-freeze-v1.json"
)
ADAPTER = ROOT / "src/v5_final/s11_v2_queue_native_adapter.py"
EXECUTION_SERVICES = ROOT / "src/v5_final/parent_native_execution_services.py"
EXECUTORS = ROOT / "src/v5_final/parent_native_executors.py"
REWRITE = ROOT / "src/v5_final/parent_native_rewrite.py"
PARENT_VERIFIER = ROOT / "src/v5_final/parent_native_verifier_v2.py"
EXPECTED_RUNNER = ROOT / "src/v5_final/s11_v2_execution_runner_v1.py"
MINIMUM_FREE_BYTES = 40 * 1024**3
DECISION = "NO_GO_S11_V2_UNBOUND_DYNAMIC_VERIFIER_AND_PRODUCTION_RUNNER"
SCOPED_TESTS = (
    "tests/test_v5_final_s11_v2_queue_native_adapter.py",
    "tests/test_v5_final_s11_v2_execution_readiness_v1.py",
)


class S11V2ExecutionReadinessV1Error(RuntimeError):
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
        raise S11V2ExecutionReadinessV1Error(f"invalid JSON: {path}") from error
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise S11V2ExecutionReadinessV1Error(f"noncanonical artifact: {path}")
    return value


def _embedded_digest(value: dict[str, Any], field: str) -> bool:
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
        raise S11V2ExecutionReadinessV1Error("remote branch is absent")
    return line.split()[0]


def _function_calls(path: Path, function_name: str) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    matches = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == function_name
    ]
    if len(matches) != 1:
        raise S11V2ExecutionReadinessV1Error(
            f"expected one function {function_name} in {path}"
        )
    calls: set[str] = set()
    for node in ast.walk(matches[0]):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            calls.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            calls.add(node.func.attr)
    return calls


def _module_function_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _pytest_summary(stdout: str) -> dict[str, int]:
    summaries = re.findall(
        r"(?m)^(\d+) passed(?:, (\d+) xfailed)?(?:, \d+ warnings?)? in ",
        stdout,
    )
    return {
        "partitions": len(summaries),
        "passed": sum(int(passed) for passed, _ in summaries),
        "xfailed": sum(int(xfailed or 0) for _, xfailed in summaries),
    }


def _run(command: list[str], *, full_suite: bool = False) -> dict[str, Any]:
    environment = dict(os.environ)
    source_paths = (
        str(ROOT / "src"),
        str(ROOT / "provenance/dvg-obs-ceo/src"),
        str(ROOT / "provenance/dvg-obs-ceo/vendor/ceo-adapt-vqe"),
    )
    existing_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = os.pathsep.join(
        source_paths
        if not existing_pythonpath
        else (*source_paths, existing_pythonpath)
    )
    if not full_suite:
        environment.update(
            OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1"
        )
    started = time.monotonic()
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    summary = _pytest_summary(completed.stdout)
    return {
        "command": command,
        "exit_code": completed.returncode,
        "duration_seconds": round(time.monotonic() - started, 3),
        "summary": summary,
        "passed": completed.returncode == 0 and summary["passed"] > 0,
        "stdout_sha256": hashlib.sha256(completed.stdout.encode()).hexdigest(),
        "last_lines": completed.stdout.splitlines()[-8:],
    }


def inspect_readiness() -> dict[str, Any]:
    """Return source and artifact evidence without running molecular code."""

    queue = _load(QUEUE)
    p7 = _load(P7_V5)
    cap = _load(CAP_FREEZE)
    p7_audit = audit_p7_v5()
    dynamic_calls = _function_calls(EXECUTION_SERVICES, "_dynamic_v5_preparation")
    ranking_calls = _function_calls(EXECUTORS, "_rank_parent_candidates")
    generator_calls = _function_calls(REWRITE, "_generator_matrix")
    verifier_functions = _module_function_names(PARENT_VERIFIER)
    adapter_methods = {
        node.name
        for node in ast.walk(ast.parse(ADAPTER.read_text(encoding="utf-8")))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    frozen_sources = dict(queue.get("execution_source_sha256", {}))
    frozen_source_manifest = [
        {"path": path, "sha256": expected}
        for path, expected in frozen_sources.items()
    ]
    queue_items = list(queue.get("items", ()))
    outcomes = {
        "candidate_energy_evaluations": queue.get("candidate_energy_evaluations"),
        "optimizer_iterations": queue.get("optimizer_iterations"),
        "FCI_evaluations": queue.get("FCI_evaluations"),
    }
    checks = {
        "queue_v2_digest_valid": _embedded_digest(queue, "queue_digest"),
        "queue_v2_is_immutable_git_blob": artifact_is_immutable_git_blob(QUEUE),
        "cap_freeze_digest_valid": _embedded_digest(cap, "freeze_digest"),
        "p7_v5_go_is_valid": p7_audit["decision"]
        == "GO_S11_V2_FROZEN_90_ITEM_EXECUTION"
        and all(p7_audit["checks"].values()),
        "p7_v5_did_not_bind_a_production_runner": "runner" not in p7[
            "artifact_bindings"
        ]
        and not any("execution_runner" in path for path in p7["artifact_bindings"]["source_manifest"]),
        "exact_queue_runner_is_absent": not EXPECTED_RUNNER.exists(),
        "adapter_has_no_execution_entrypoint": not {
            "execute", "execute_item", "execute_queue_item"
        }.intersection(adapter_methods),
        "historical_frozen_executor_sources_are_valid": (
            manifest_matches_artifact_commit(QUEUE, frozen_source_manifest)
        ),
        "queue_forbids_legacy_dense_verifier": queue["executor_code_binding"][
            "legacy_dense_verifier_allowed"
        ]
        is False,
        "dynamic_v5_calls_legacy_ranker": "_rank_parent_candidates" in dynamic_calls,
        "legacy_ranker_calls_legacy_rewrite_verifier": (
            "prepare_rewrite_for_optimizer" in ranking_calls
        ),
        "legacy_rewrite_materializes_generator_dense": "toarray" in generator_calls,
        "dynamic_v5_does_not_call_verifier_v2": not {
            "build_parent_verifier_v2", "VerifierV2"
        }.intersection(dynamic_calls),
        "actual_magnitude_verifier_v2_builder_is_absent": (
            "build_magnitude_verifier_v2" not in verifier_functions
        ),
        "all_90_items_remain_not_started": len(queue_items) == 90
        and all(item.get("terminal_status") == "NOT_STARTED" for item in queue_items),
        "candidate_optimizer_fci_outcomes_remain_zero": all(
            value == 0 for value in outcomes.values()
        ),
        "production_dense_expm_cap_remains_zero": all(
            item["combined_all_counter_cap"]["N_dense_expm"] == 0
            for item in queue_items
        ),
        "storage_at_least_40_GiB": shutil.disk_usage(ROOT).free
        >= MINIMUM_FREE_BYTES,
    }
    if not all(checks.values()):
        raise S11V2ExecutionReadinessV1Error(
            [name for name, passed in checks.items() if not passed]
        )
    return {
        "checks": checks,
        "observed_outcomes": outcomes,
        "source_observations": {
            "dynamic_v5_calls": sorted(dynamic_calls),
            "legacy_ranker_calls": sorted(ranking_calls),
            "generator_matrix_calls": sorted(generator_calls),
            "parent_verifier_v2_functions": sorted(verifier_functions),
            "adapter_methods": sorted(adapter_methods),
        },
        "artifact_bindings": {
            "queue_v2_sha256": _sha(QUEUE),
            "queue_v2_digest": queue["queue_digest"],
            "outcome_cap_freeze_sha256": _sha(CAP_FREEZE),
            "outcome_cap_freeze_digest": cap["freeze_digest"],
            "p7_v5_sha256": _sha(P7_V5),
            "p7_v5_gate_digest": p7["gate_digest"],
            "frozen_execution_source_sha256": frozen_sources,
            "audited_source_sha256": {
                str(path.relative_to(ROOT)): _sha(path)
                for path in (
                    ADAPTER,
                    EXECUTION_SERVICES,
                    EXECUTORS,
                    REWRITE,
                    PARENT_VERIFIER,
                    ROOT / "src/v5_final/s11_v2_execution_readiness_v1.py",
                    ROOT / "tests/test_v5_final_s11_v2_execution_readiness_v1.py",
                )
            },
        },
    }


def capture() -> dict[str, Any]:
    if OUTPUT.exists():
        raise S11V2ExecutionReadinessV1Error("readiness artifact already exists")
    branch = _git("branch", "--show-current")
    local_head = _git("rev-parse", "HEAD")
    remote_head = _remote_head(branch)
    status = _git("status", "--porcelain")
    if status:
        raise S11V2ExecutionReadinessV1Error(
            "capture requires a clean tree so the audited source is committed"
        )
    evidence = inspect_readiness()
    scoped = _run([sys.executable, "-m", "pytest", "-q", *SCOPED_TESTS])
    full = _run(
        [sys.executable, "-m", "v5_final.full_repository_suite_v2"],
        full_suite=True,
    )
    if not scoped["passed"] or not full["passed"] or full["summary"]["xfailed"] != 3:
        raise S11V2ExecutionReadinessV1Error("readiness verification suite failed")
    blockers = [
        {
            "blocker_id": "R1_EXACT_QUEUE_V2_PRODUCTION_RUNNER_ABSENT",
            "classification": "ENGINEERING_BUT_NOT_INDEPENDENTLY_REPAIRABLE",
            "evidence": "No exact queue-v2 runner is bound by P7-v5 or present in source.",
        },
        {
            "blocker_id": "R2_DYNAMIC_V5_BYPASSES_VERIFIER_V2",
            "classification": "FROZEN_SCIENTIFIC_EXECUTOR_CONFLICT",
            "evidence": (
                "The frozen post-commit path calls _rank_parent_candidates, which calls "
                "prepare_rewrite_for_optimizer and dense generator toarray materialization."
            ),
        },
        {
            "blocker_id": "R3_ACTUAL_MAGNITUDE_VERIFIER_V2_BUILDER_ABSENT",
            "classification": "FROZEN_EXECUTION_COMPOSITION_INCOMPLETE",
            "evidence": (
                "The adapter accepts Verifier V2 records, but the actual parent verifier "
                "builder only accepts typed parent catalogs; no magnitude builder exists."
            ),
        },
        {
            "blocker_id": "R4_CUMULATIVE_DYNAMIC_VERIFIER_LEDGER_UNBOUND",
            "classification": "WORK_ACCOUNTING_COMPLETENESS_FAILURE",
            "evidence": (
                "No production path cumulatively binds post-commit Verifier V2 primitive "
                "counters and checkpoints to the queue combined-all cap and terminal receipt."
            ),
        },
    ]
    body = {
        "schema": "v5-final.s11-v2-execution-readiness.v1",
        "stage": "PHASE_B_PRE_FIRST_CANDIDATE_OUTCOME",
        "status": DECISION,
        "decision": DECISION,
        "captured_repository_state": {
            "branch": branch,
            "local_head": local_head,
            "remote_head": remote_head,
            "worktree_clean": True,
        },
        "storage": {
            "available_bytes": shutil.disk_usage(ROOT).free,
            "required_bytes": MINIMUM_FREE_BYTES,
        },
        "tests": {"scoped": scoped, "full_repository_suite": full},
        **evidence,
        "blockers": blockers,
        "authorization": {
            "S11_v2_candidate_outcome_execution": "NOT_AUTHORIZED_BY_ADDITIVE_RUNNER_READINESS",
            "molecular_candidate_energy": "NOT_AUTHORIZED",
            "optimizer": "NOT_AUTHORIZED",
            "FCI_reporting": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "required_resolution": (
            "A new outcome-blind readiness successor must bind an actual magnitude Verifier V2 builder, "
            "Verifier V2 post-commit rebuilding for both V5 methods, cumulative deterministic "
            "counter/checkpoint accounting, and an exact production runner. Because this "
            "changes the executed composition, an outcome-free semantic diff must first prove "
            "that it only realizes the already-frozen queue-v2 policy. If that proof fails, an "
            "additive queue v3 is required and queue v2 may not execute."
        ),
        "scientific_boundary": (
            "No candidate energy, optimizer, or FCI outcome was evaluated. This is an "
            "infrastructure and frozen-composition No-Go, not a performance result."
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
    body = dict(artifact)
    observed_digest = body.pop("readiness_digest", None)
    bindings = artifact["artifact_bindings"]
    checks = {
        "readiness_digest_valid": observed_digest == _digest(body),
        "decision_is_no_go": artifact["decision"] == DECISION,
        "all_evidence_checks_passed": all(artifact["checks"].values()),
        "four_blockers_preserved": len(artifact["blockers"]) == 4,
        "outcomes_zero": all(
            value == 0 for value in artifact["observed_outcomes"].values()
        ),
        "queue_v2_unchanged": bindings["queue_v2_sha256"] == _sha(QUEUE),
        "cap_freeze_unchanged": bindings["outcome_cap_freeze_sha256"]
        == _sha(CAP_FREEZE),
        "p7_v5_unchanged": bindings["p7_v5_sha256"] == _sha(P7_V5),
        "historical_sources_match_artifact_commit": manifest_matches_artifact_commit(
            OUTPUT,
            [
                {"path": path, "sha256": expected}
                for path, expected in bindings["audited_source_sha256"].items()
            ],
        ),
        "all_outcome_authorizations_closed": all(
            str(value).startswith("NOT_AUTHORIZED")
            for value in artifact["authorization"].values()
        ),
    }
    if require_live:
        branch = _git("branch", "--show-current")
        checks.update(
            artifact_is_immutable_git_blob=artifact_is_immutable_git_blob(OUTPUT),
            worktree_clean=_git("status", "--porcelain") == "",
            local_remote_head_match=_git("rev-parse", "HEAD")
            == _remote_head(branch),
            storage_at_least_40_GiB=shutil.disk_usage(ROOT).free
            >= MINIMUM_FREE_BYTES,
        )
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S11V2ExecutionReadinessV1Error(failures)
    return {
        "status": "PASS_FROZEN_S11_V2_EXECUTION_READINESS_NO_GO_V1",
        "decision": artifact["decision"],
        "checks": checks,
        "readiness_digest": observed_digest,
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

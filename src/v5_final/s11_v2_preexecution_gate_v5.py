"""Additive P7-v5 gate for the frozen S11-v2 90-item execution.

This gate runs only outcome-free audits.  It can authorize the already-frozen
queue, but it never dispatches an item or evaluates a molecular candidate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import time
from typing import Any

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .full_repository_suite_v2 import suite_plan
from .historical_artifact_audit import artifact_is_immutable_git_blob
from .s0_successor import ROOT
from .s11_v2_adapter_readiness_v1 import (
    OUTPUT as ADAPTER_READINESS,
    audit as audit_adapter_readiness,
)
from .s11_v2_outcome_cap_freeze import audit as audit_caps
from .s11_v2_queue_freeze_v2 import audit as audit_queue


OUTPUT_DIR = ROOT / "artifacts/v5-final/parent-native/s11-v2-preexecution-gate-v5"
OUTPUT = OUTPUT_DIR / "p7-go-v5.json"
P7_V4 = ROOT / "artifacts/v5-final/parent-native/s11-v2-preexecution-gate-v4/p7-no-go-v4.json"
QUEUE_DIR = ROOT / "artifacts/v5-final/parent-native/s11-v2-queue-freeze-v2"
QUEUE = QUEUE_DIR / "s11-v2-queue-v2.json"
QUEUE_MANIFEST = QUEUE_DIR / "MANIFEST.sha256"
CAP_DIR = ROOT / "artifacts/v5-final/parent-native/s11-v2-outcome-cap-freeze-v1"
CAP_FREEZE = CAP_DIR / "outcome-cap-freeze-v1.json"
CAP_MANIFEST = CAP_DIR / "MANIFEST.sha256"
S5_PROTOCOL = ROOT / "artifacts/v5-final/s5/development-protocol-freeze-v3.json"
REPOSITORY = "Reimangod/v5-matched-work-study"
MINIMUM_FREE_BYTES = 40 * 1024**3
GO_DECISION = "GO_S11_V2_FROZEN_90_ITEM_EXECUTION"
SCOPED_TESTS = (
    "tests/test_v5_final_s11_v2_queue_native_adapter.py",
    "tests/test_v5_final_s11_v2_adapter_readiness_v1.py",
    "tests/test_v5_final_bfgs_runtime_parity_v1.py",
)


class S11V2PreexecutionGateV5Error(RuntimeError):
    pass


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise S11V2PreexecutionGateV5Error(f"expected object: {path}")
    return value


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout.rstrip("\n")


def _manifest_ok(path: Path) -> bool:
    for line in path.read_text(encoding="utf-8").splitlines():
        expected, relative = line.split("  ", 1)
        target = path.parent / relative
        if not target.is_file() or _sha(target) != expected:
            return False
    return True


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
        command, cwd=ROOT, env=environment, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
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


def _live_visibility() -> dict[str, Any]:
    return json.loads(
        subprocess.run(
            [
                "gh", "repo", "view", REPOSITORY, "--json",
                "visibility,isPrivate,url,defaultBranchRef",
            ],
            cwd=ROOT, check=True, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        ).stdout
    )


def _remote_head(branch: str) -> str:
    line = subprocess.run(
        ["git", "ls-remote", "--heads", "origin", f"refs/heads/{branch}"],
        cwd=ROOT, check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout.strip()
    if not line:
        raise S11V2PreexecutionGateV5Error("remote branch is absent")
    return line.split()[0]


def capture() -> dict[str, Any]:
    if OUTPUT.exists():
        raise S11V2PreexecutionGateV5Error("P7-v5 artifact already exists")

    branch = _git("branch", "--show-current")
    local_head = _git("rev-parse", "HEAD")
    remote_head = _remote_head(branch)
    status = _git("status", "--porcelain")
    submodules = _git("submodule", "status", "--recursive").splitlines()
    visibility = _live_visibility()
    disk = shutil.disk_usage(ROOT)

    queue = _load(QUEUE)
    cap_freeze = _load(CAP_FREEZE)
    readiness = _load(ADAPTER_READINESS)
    adapter_audit = audit_adapter_readiness()
    queue_audit = audit_queue()
    cap_audit = audit_caps()

    scoped = _run([sys.executable, "-m", "pytest", "-q", *SCOPED_TESTS])
    full = _run(
        [sys.executable, "-m", "v5_final.full_repository_suite_v2"],
        full_suite=True,
    )
    plan = suite_plan()
    exact_environment = {
        "python_version": platform.python_version(),
        "root_pyproject_sha256": _sha(ROOT / "pyproject.toml"),
        "root_uv_lock_sha256": _sha(ROOT / "uv.lock"),
        "parent_pyproject_sha256": _sha(
            ROOT / "provenance/dvg-obs-ceo/pyproject.toml"
        ),
        "parent_uv_lock_sha256": _sha(ROOT / "provenance/dvg-obs-ceo/uv.lock"),
    }
    protocol_environment = {
        item["path"]: item["sha256"]
        for item in _load(S5_PROTOCOL)["policy"]["environment"]["files"]
    }
    environment_lock_match = all(
        protocol_environment[path] == exact_environment[key]
        for path, key in (
            ("pyproject.toml", "root_pyproject_sha256"),
            ("uv.lock", "root_uv_lock_sha256"),
            ("provenance/dvg-obs-ceo/pyproject.toml", "parent_pyproject_sha256"),
            ("provenance/dvg-obs-ceo/uv.lock", "parent_uv_lock_sha256"),
        )
    )
    source_manifest = {
        path: _sha(ROOT / path)
        for path in (
            "src/v5_final/s11_v2_preexecution_gate_v5.py",
            "src/v5_final/full_repository_suite_v2.py",
            "src/v5_final/s11_v2_queue_native_adapter.py",
            "src/v5_final/parent_native_execution_services.py",
            "tests/test_v5_final_s11_v2_queue_native_adapter.py",
            "tests/test_v5_final_s11_v2_adapter_readiness_v1.py",
            "tests/test_v5_final_bfgs_runtime_parity_v1.py",
            "tests/test_v5_final_s11_v2_preexecution_gate_v5.py",
        )
    }
    readiness_sources = readiness["binding"]["source_sha256"]
    readiness_source_match = all(
        _sha(ROOT / path) == expected
        for path, expected in readiness_sources.items()
    )
    outcomes = {
        "candidate_energy_evaluations": queue["candidate_energy_evaluations"],
        "optimizer_iterations": queue["optimizer_iterations"],
        "FCI_evaluations": queue["FCI_evaluations"],
    }
    checks = {
        "full_repository_suite_passed": full["passed"]
        and full["summary"]["partitions"] == 2
        and full["summary"]["xfailed"] == 3,
        "suite_plan_covers_every_module_once": plan["coverage_exactly_once"] is True,
        "adapter_digest_binding_passed": adapter_audit["adapter_digest"]
        == readiness["binding"]["adapter_digest"]
        and readiness["binding"]["queue_v2"]["sha256"] == _sha(QUEUE)
        and readiness["binding"]["queue_v2"]["queue_digest"] == queue["queue_digest"]
        and readiness_source_match,
        "all_six_methods_outcome_free_adapter_tests_passed": scoped["passed"]
        and len(readiness["binding"]["method_ids"]) == 6,
        "BFGS_nfev_njev_nit_parity_passed": scoped["passed"]
        and readiness["test_contract"]["BFGS_nfev_njev_nit_parity"] is True,
        "storage_at_least_40_GiB": disk.free >= MINIMUM_FREE_BYTES,
        "90_of_90_NOT_STARTED": len(queue["items"]) == 90
        and all(item["terminal_status"] == "NOT_STARTED" for item in queue["items"]),
        "candidate_energy_optimizer_FCI_all_zero": all(
            value == 0 for value in outcomes.values()
        ),
        "production_N_dense_expm_zero": all(
            item["combined_all_counter_cap"]["N_dense_expm"] == 0
            for item in queue["items"]
        ),
        "local_remote_HEAD_match": local_head == remote_head,
        "worktree_clean": status == "",
        "recursive_submodules_clean": all(line.startswith(" ") for line in submodules),
        "exact_environment_lock_match": environment_lock_match,
        "queue_and_cap_manifests_passed": _manifest_ok(QUEUE_MANIFEST)
        and _manifest_ok(CAP_MANIFEST),
        "queue_and_cap_audits_passed": queue_audit["status"].startswith("PASS")
        and cap_audit["status"].startswith("PASS"),
        "repository_public_live": visibility["visibility"] == "PUBLIC"
        and visibility["isPrivate"] is False,
        "default_branch_main_live": visibility["defaultBranchRef"]["name"] == "main",
        "P7_v4_preserved": artifact_is_immutable_git_blob(P7_V4),
    }
    blockers = ["GATE_FAILED:" + name for name, passed in checks.items() if not passed]
    if blockers:
        raise S11V2PreexecutionGateV5Error(blockers)

    body = {
        "schema": "v5-final.s11-v2-p7-preexecution-gate.v5",
        "stage": "Q7_P7_PREEXECUTION_GATE_V5",
        "status": GO_DECISION,
        "decision": GO_DECISION,
        "captured_repository_state": {
            "branch": branch,
            "local_head": local_head,
            "remote_head": remote_head,
            "worktree_status": status.splitlines(),
            "recursive_submodule_status": submodules,
            "repository_visibility": visibility,
        },
        "storage": {
            "available_bytes": disk.free,
            "available_GiB": disk.free / 1024**3,
            "required_bytes": MINIMUM_FREE_BYTES,
            "required_GiB": 40,
        },
        "exact_environment": exact_environment,
        "tests": {
            "full_repository_suite": full,
            "outcome_free_adapter_and_BFGS": scoped,
            "suite_plan": plan,
        },
        "artifact_bindings": {
            "P7_v4_predecessor_sha256": _sha(P7_V4),
            "queue_v2_sha256": _sha(QUEUE),
            "queue_v2_digest": queue["queue_digest"],
            "outcome_cap_freeze_sha256": _sha(CAP_FREEZE),
            "outcome_cap_freeze_digest": cap_freeze["freeze_digest"],
            "adapter_readiness_sha256": _sha(ADAPTER_READINESS),
            "adapter_readiness_digest": readiness["readiness_digest"],
            "adapter_digest": readiness["binding"]["adapter_digest"],
            "source_manifest": source_manifest,
        },
        "checks": checks,
        "blockers": [],
        "observed_outcomes": outcomes,
        "authorization": {
            "S11_v2_execution": "AUTHORIZED_EXACT_FROZEN_90_ITEM_QUEUE_ONLY",
            "candidate_energy": "AUTHORIZED_ONLY_INSIDE_EXACT_FROZEN_QUEUE_CAPS",
            "optimizer": "AUTHORIZED_ONLY_INSIDE_EXACT_FROZEN_QUEUE_CAPS",
            "FCI_reporting": "NOT_AUTHORIZED_UNTIL_ALL_90_TERMINAL",
            "S12_and_later": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "scientific_boundary": (
            "This GO authorizes only execution of the exact frozen S11-v2 queue "
            "under bound caps and ledgers. It is not a performance result, and it "
            "does not authorize S12, FCI reporting, or any performance claim."
        ),
    }
    body["gate_digest"] = _digest(body)
    return body


def write_artifact() -> None:
    artifact = capture()
    if artifact["decision"] != GO_DECISION or not all(artifact["checks"].values()):
        raise S11V2PreexecutionGateV5Error("P7-v5 is fail-closed")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_json_exclusive(OUTPUT, artifact)


def audit_frozen(*, require_live: bool = False) -> dict[str, Any]:
    artifact = _load(OUTPUT)
    body = dict(artifact)
    observed_digest = body.pop("gate_digest", None)
    bindings = artifact["artifact_bindings"]
    checks = {
        "gate_digest_valid": observed_digest == _digest(body),
        "decision_exact": artifact["decision"] == GO_DECISION,
        "all_frozen_checks_passed": all(artifact["checks"].values()),
        "blockers_empty": artifact["blockers"] == [],
        "outcomes_zero_at_authorization": all(
            value == 0 for value in artifact["observed_outcomes"].values()
        ),
        "P7_v4_preserved": bindings["P7_v4_predecessor_sha256"] == _sha(P7_V4),
        "queue_v2_bound": bindings["queue_v2_sha256"] == _sha(QUEUE),
        "cap_freeze_bound": bindings["outcome_cap_freeze_sha256"] == _sha(CAP_FREEZE),
        "adapter_readiness_bound": bindings["adapter_readiness_sha256"]
        == _sha(ADAPTER_READINESS),
        "source_manifest_current": all(
            _sha(ROOT / path) == expected
            for path, expected in bindings["source_manifest"].items()
        ),
        "performance_claim_still_closed": artifact["authorization"]["performance_claim"]
        == "NOT_AUTHORIZED",
    }
    if require_live:
        branch = _git("branch", "--show-current")
        visibility = _live_visibility()
        checks.update(
            artifact_is_immutable_git_blob=artifact_is_immutable_git_blob(OUTPUT),
            worktree_clean=_git("status", "--porcelain") == "",
            local_remote_HEAD_match=_git("rev-parse", "HEAD") == _remote_head(branch),
            recursive_submodules_clean=all(
                line.startswith(" ")
                for line in _git("submodule", "status", "--recursive").splitlines()
            ),
            repository_public_live=visibility["visibility"] == "PUBLIC"
            and visibility["isPrivate"] is False,
            storage_at_least_40_GiB=shutil.disk_usage(ROOT).free >= MINIMUM_FREE_BYTES,
        )
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S11V2PreexecutionGateV5Error(failures)
    return {
        "status": "PASS_FROZEN_P7_V5_GO_AUDIT",
        "decision": artifact["decision"],
        "checks": checks,
        "gate_digest": observed_digest,
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

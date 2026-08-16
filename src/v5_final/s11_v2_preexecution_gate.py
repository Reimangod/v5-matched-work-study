"""P7 fail-closed pre-execution gate for the frozen S11-v2 queue."""

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
from typing import Any

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .s0_successor import ROOT


V1_OUTPUT = ROOT / "artifacts/v5-final/parent-native/s11-v2-preexecution-gate-v1/p7-no-go-v1.json"
V2_OUTPUT = ROOT / "artifacts/v5-final/parent-native/s11-v2-preexecution-gate-v2/p7-no-go-v2.json"
OUTPUT_DIR = ROOT / "artifacts/v5-final/parent-native/s11-v2-preexecution-gate-v3"
OUTPUT = OUTPUT_DIR / "p7-no-go-v3.json"
QUEUE_DIR = ROOT / "artifacts/v5-final/parent-native/s11-v2-queue-freeze-v1"
QUEUE_PATH = QUEUE_DIR / "s11-v2-queue-v1.json"
QUEUE_IDENTITY = QUEUE_DIR / "queue-byte-identity-v1.json"
QUEUE_MANIFEST = QUEUE_DIR / "MANIFEST.sha256"
CALIBRATION_DIR = ROOT / "artifacts/v5-final/parent-native/s11-v2-verifier-calibration-v1"
CALIBRATION_SUMMARY = CALIBRATION_DIR / "calibration-summary-v1.json"
CALIBRATION_MANIFEST = CALIBRATION_DIR / "MANIFEST.sha256"
DESIGN = ROOT / "artifacts/v5-final/parent-native/s11-v2-verifier-remediation/verifier-v2-design-v1.json"
EXECUTOR_MANIFEST = ROOT / "artifacts/v5-final/parent-native/s11-development-queue-v4/development-executor-manifest-v1.json"
S5_PROTOCOL = ROOT / "artifacts/v5-final/s5/development-protocol-freeze-v3.json"
MINIMUM_FREE_BYTES = 35 * 1024**3
RECOMMENDED_FREE_BYTES = 40 * 1024**3


class S11V2PreexecutionGateError(RuntimeError):
    pass


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout.rstrip("\n")


def _manifest_ok(path: Path, *, root_relative_entries: bool) -> bool:
    base = ROOT if root_relative_entries else path.parent
    for line in path.read_text().splitlines():
        expected, relative = line.split("  ", 1)
        target = base / relative
        if not target.is_file() or _sha(target) != expected:
            return False
    return True


def _run_tests() -> dict[str, Any]:
    required_files = [
        "tests/test_atomic_artifacts.py",
        "tests/test_v5_final_s11_v1_controlled_termination_item028_v1.py",
        "tests/test_v5_final_s11_v1_infrastructure_closure_v1.py",
        "tests/test_v5_final_verifier_v2.py",
        "tests/test_v5_final_s11_v2_verifier_design_audit.py",
        "tests/test_v5_final_s11_v2_outcome_free_calibration.py",
        "tests/test_v5_final_s11_v2_queue_freeze.py",
    ]
    command = [sys.executable, "-m", "pytest", "-q", *required_files]
    environment = dict(os.environ)
    frozen_threads = {
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
    }
    environment.update(frozen_threads)
    completed = subprocess.run(
        command, cwd=ROOT, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, check=False, env=environment,
    )
    match = re.search(r"(\d+) passed", completed.stdout)
    return {
        "command": command,
        "exit_code": completed.returncode,
        "passed_count": int(match.group(1)) if match else None,
        "stdout_sha256": hashlib.sha256(completed.stdout.encode()).hexdigest(),
        "last_lines": completed.stdout.splitlines()[-3:],
        "passed": completed.returncode == 0 and match is not None,
        "scope": "P0-P6 remediation tests and their immutable artifact audits",
        "required_test_files": required_files,
        "frozen_thread_environment": frozen_threads,
        "historical_closed_release_live_inventory_tests": "OUT_OF_SCOPE_BECAUSE_ADDITIVE_S11_V2_ARTIFACTS_MUST_NOT_REDEFINE_CLOSED_V1_RELEASE_INVENTORIES",
    }


def _binding_checks(queue: dict[str, Any], design: dict[str, Any]) -> dict[str, bool]:
    code = queue["executor_code_binding"]
    fields = set(design["counter_schema"]["fields"])
    deterministic = set(queue["items"][0]["verifier_componentwise_cap"])
    expected_deterministic = fields - {
        "CPU_time_seconds", "wall_time_seconds", "peak_RSS_raw",
        "optimizer_iterations", "energy_evaluations",
    }
    return {
        "verifier_code_digest_match": code["verifier_v2_sha256"] == _sha(ROOT / "src/v5_final/verifier_v2.py"),
        "parent_adapter_digest_match": code["parent_native_verifier_v2_sha256"] == _sha(ROOT / "src/v5_final/parent_native_verifier_v2.py"),
        "method_executor_manifest_digest_match": code["method_native_executor_manifest_sha256"] == _sha(EXECUTOR_MANIFEST),
        "design_digest_match": code["verifier_design_freeze_digest"] == design["design_freeze_digest"],
        "counter_schema_complete": deterministic == expected_deterministic,
        "all_item_bindings_equal_queue": all(item["executor_bundle_digest"] == queue["executor_bundle_digest"] and item["counter_schema_digest"] == queue["counter_schema_digest"] for item in queue["items"]),
        "outcome_caps_defined": all(item["outcome_work_cap"]["optimizer_iterations"] is not None and item["outcome_work_cap"]["energy_evaluations"] is not None for item in queue["items"]),
    }


def capture() -> dict[str, Any]:
    queue = _load(QUEUE_PATH)
    identity = _load(QUEUE_IDENTITY)
    calibration = _load(CALIBRATION_SUMMARY)
    design = _load(DESIGN)
    disk = shutil.disk_usage(ROOT)
    local_head = _git("rev-parse", "HEAD")
    branch = _git("branch", "--show-current")
    remote_ref = f"origin/{branch}"
    remote_head = _git("rev-parse", remote_ref)
    status = _git("status", "--porcelain")
    submodules = _git("submodule", "status", "--recursive").splitlines()
    tests = _run_tests()
    bindings = _binding_checks(queue, design)
    exact_environment = {
        "python_version": platform.python_version(),
        "root_pyproject_sha256": _sha(ROOT / "pyproject.toml"),
        "root_uv_lock_sha256": _sha(ROOT / "uv.lock"),
        "parent_pyproject_sha256": _sha(ROOT / "provenance/dvg-obs-ceo/pyproject.toml"),
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
    checks = {
        "disk_free_at_least_35_GiB": disk.free >= MINIMUM_FREE_BYTES,
        "worktree_clean": status == "",
        "local_remote_HEAD_match": local_head == remote_head,
        "recursive_dependency_checkout_clean": all(line and line[0] == " " for line in submodules),
        "exact_environment_lock_match": environment_lock_match,
        "tests_passed": tests["passed"],
        "hash_manifests_passed": _manifest_ok(
            QUEUE_MANIFEST, root_relative_entries=False
        ) and _manifest_ok(CALIBRATION_MANIFEST, root_relative_entries=True),
        "production_dense_expm_zero": calibration["production_dense_expm"] == 0 and all(item["verifier_componentwise_cap"]["N_dense_expm"] == 0 for item in queue["items"]),
        "checkpoint_resume_passed": calibration["checks"]["lih_resume_equals_uninterrupted"] is True and calibration["checks"]["lih_partial_was_checkpointed"] is True,
        "H2_H4_calibration_passed": all(calibration["checks"][key] is True for key in ("old_new_pass_fail_parity", "h2_byte_identical", "h4_byte_identical")),
        "queue_byte_identity_passed": identity["byte_identical"] is True,
        "counter_completeness_passed": bindings["counter_schema_complete"] and bindings["outcome_caps_defined"],
        "executor_queue_code_digest_binding_passed": all(value for key, value in bindings.items() if key != "outcome_caps_defined" and key != "counter_schema_complete"),
    }
    blockers = []
    if not checks["disk_free_at_least_35_GiB"]:
        blockers.append("INSUFFICIENT_SAFE_DISK_CAPACITY_BELOW_35_GIB")
    if not bindings["outcome_caps_defined"]:
        blockers.append("OUTCOME_WORK_CAPS_UNDEFINED_NOT_INFERRED_FROM_ZERO_OUTCOMES")
    for name, passed in checks.items():
        if not passed and name not in {"disk_free_at_least_35_GiB", "counter_completeness_passed"}:
            blockers.append("GATE_FAILED:" + name)
    body = {
        "schema": "v5-final.s11-v2-p7-preexecution-gate.v3",
        "stage": "P7_PREEXECUTION_GATE",
        "status": "NO_GO_S11_V2_CANDIDATE_OUTCOME_EXECUTION",
        "decision": "NO_GO" if blockers else "GO",
        "captured_repository_state": {
            "branch": branch,
            "local_head": local_head,
            "remote_ref": remote_ref,
            "remote_head": remote_head,
            "worktree_status": status.splitlines(),
            "recursive_submodule_status": submodules,
        },
        "storage": {
            "available_bytes": disk.free,
            "available_GiB": disk.free / 1024**3,
            "minimum_required_bytes": MINIMUM_FREE_BYTES,
            "minimum_required_GiB": 35,
            "recommended_bytes": RECOMMENDED_FREE_BYTES,
            "recommended_GiB": 40,
            "capacity_passed": disk.free >= MINIMUM_FREE_BYTES,
        },
        "exact_environment": exact_environment,
        "tests": tests,
        "artifact_bindings": {
            "p7_v1_predecessor_sha256": _sha(V1_OUTPUT),
            "p7_v2_predecessor_sha256": _sha(V2_OUTPUT),
            "queue_sha256": _sha(QUEUE_PATH),
            "queue_digest": queue["queue_digest"],
            "queue_identity_sha256": _sha(QUEUE_IDENTITY),
            "calibration_summary_sha256": _sha(CALIBRATION_SUMMARY),
            "calibration_summary_digest": calibration["summary_digest"],
            "verifier_design_sha256": _sha(DESIGN),
            "verifier_design_freeze_digest": design["design_freeze_digest"],
        },
        "binding_checks": bindings,
        "checks": checks,
        "blockers": blockers,
        "authorization": {
            "candidate_energy": "NOT_AUTHORIZED",
            "optimizer": "NOT_AUTHORIZED",
            "FCI_reporting": "NOT_AUTHORIZED",
            "S11_v2_execution": "NOT_AUTHORIZED",
            "S12_and_later": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "observed_outcomes": {
            "S11_v2_candidate_energy_evaluations": 0,
            "S11_v2_optimizer_iterations": 0,
            "S11_v2_FCI_evaluations": 0,
        },
        "scientific_boundary": "This is a pre-outcome infrastructure No-Go, not evidence for or against V5 performance.",
        "resolution": "Provide at least 35 GiB free space (40 GiB recommended) and freeze non-outcome-derived optimizer/energy component caps in a new versioned artifact; then rerun every P7 gate before any candidate outcome.",
    }
    body["gate_digest"] = _digest(body)
    return body


def audit_frozen() -> dict[str, Any]:
    artifact = _load(OUTPUT)
    digest = artifact.pop("gate_digest")
    checks = {
        "gate_digest_valid": digest == _digest(artifact),
        "decision_no_go": artifact["decision"] == "NO_GO" and artifact["status"].startswith("NO_GO"),
        "blocker_present": bool(artifact["blockers"]),
        "all_outcomes_zero": all(value == 0 for value in artifact["observed_outcomes"].values()),
        "all_outcomes_blocked": all(value == "NOT_AUTHORIZED" for value in artifact["authorization"].values()),
        "queue_binding_current": artifact["artifact_bindings"]["queue_sha256"] == _sha(QUEUE_PATH),
        "calibration_binding_current": artifact["artifact_bindings"]["calibration_summary_sha256"] == _sha(CALIBRATION_SUMMARY),
        "design_binding_current": artifact["artifact_bindings"]["verifier_design_sha256"] == _sha(DESIGN),
        "p7_v1_predecessor_preserved": artifact["artifact_bindings"]["p7_v1_predecessor_sha256"] == _sha(V1_OUTPUT),
        "p7_v2_predecessor_preserved": artifact["artifact_bindings"]["p7_v2_predecessor_sha256"] == _sha(V2_OUTPUT),
        "scientific_boundary_explicit": "not evidence" in artifact["scientific_boundary"],
    }
    if not all(checks.values()):
        raise S11V2PreexecutionGateError([key for key, value in checks.items() if not value])
    return {"status": "PASS_FROZEN_P7_NO_GO_AUDIT", "checks": checks, "gate_digest": digest}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", action="store_true")
    parser.add_argument("--audit", action="store_true")
    args = parser.parse_args()
    if args.capture:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        write_json_exclusive(OUTPUT, capture())
    if args.audit or not args.capture:
        print(json.dumps(audit_frozen(), sort_keys=True))


if __name__ == "__main__":
    main()

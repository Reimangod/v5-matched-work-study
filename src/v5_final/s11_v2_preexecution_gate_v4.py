"""Authoritative P7-v4 gate for the additive S11-v2 queue-v2 freeze."""

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
from .s11_v2_outcome_cap_freeze import audit as audit_caps
from .s11_v2_preflight_audit_v1 import OUTPUT as PREFLIGHT, audit as audit_preflight
from .s11_v2_queue_freeze_v2 import audit as audit_queue


OUTPUT_DIR = ROOT / "artifacts/v5-final/parent-native/s11-v2-preexecution-gate-v4"
OUTPUT = OUTPUT_DIR / "p7-no-go-v4.json"
P7_V3 = ROOT / "artifacts/v5-final/parent-native/s11-v2-preexecution-gate-v3/p7-no-go-v3.json"
QUEUE_DIR = ROOT / "artifacts/v5-final/parent-native/s11-v2-queue-freeze-v2"
QUEUE = QUEUE_DIR / "s11-v2-queue-v2.json"
QUEUE_IDENTITY = QUEUE_DIR / "queue-byte-identity-v2.json"
QUEUE_DIFF = QUEUE_DIR / "queue-v1-v2-semantic-diff-v1.json"
QUEUE_MANIFEST = QUEUE_DIR / "MANIFEST.sha256"
CAP_DIR = ROOT / "artifacts/v5-final/parent-native/s11-v2-outcome-cap-freeze-v1"
CAP_FREEZE = CAP_DIR / "outcome-cap-freeze-v1.json"
CROSSWALK = CAP_DIR / "primitive-accounting-crosswalk-v1.json"
CAP_MANIFEST = CAP_DIR / "MANIFEST.sha256"
CALIBRATION = ROOT / "artifacts/v5-final/parent-native/s11-v2-verifier-calibration-v1/calibration-summary-v1.json"
S5_PROTOCOL = ROOT / "artifacts/v5-final/s5/development-protocol-freeze-v3.json"
MINIMUM_FREE_BYTES = 40 * 1024**3


class S11V2PreexecutionGateV4Error(RuntimeError):
    pass


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise S11V2PreexecutionGateV4Error(f"expected object: {path}")
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


def _run_scoped_tests() -> dict[str, Any]:
    files = (
        "tests/test_v5_final_s11_v2_outcome_cap_and_queue_v2.py",
        "tests/test_v5_final_s5_parent_native_work_accounting_audit.py",
        "tests/test_v5_final_s6_parent_native_persistent_runner_audit.py",
        "tests/test_v5_final_verifier_v2.py",
        "tests/test_v5_final_s11_v2_outcome_free_calibration.py",
    )
    environment = dict(os.environ)
    environment.update(
        OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1"
    )
    command = [sys.executable, "-m", "pytest", "-q", *files]
    result = subprocess.run(
        command, cwd=ROOT, env=environment, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    match = re.search(r"(\d+) passed", result.stdout)
    return {
        "command": command,
        "exit_code": result.returncode,
        "passed_count": int(match.group(1)) if match else None,
        "passed": result.returncode == 0 and match is not None,
        "stdout_sha256": hashlib.sha256(result.stdout.encode()).hexdigest(),
        "last_lines": result.stdout.splitlines()[-4:],
        "frozen_thread_environment": {
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
        },
    }


def capture() -> dict[str, Any]:
    preflight = _load(PREFLIGHT)
    queue = _load(QUEUE)
    identity = _load(QUEUE_IDENTITY)
    diff = _load(QUEUE_DIFF)
    cap_freeze = _load(CAP_FREEZE)
    crosswalk = _load(CROSSWALK)
    calibration = _load(CALIBRATION)
    disk = shutil.disk_usage(ROOT)
    branch = _git("branch", "--show-current")
    local_head = _git("rev-parse", "HEAD")
    remote_head = _git("rev-parse", f"origin/{branch}")
    status = _git("status", "--porcelain")
    submodules = _git("submodule", "status", "--recursive").splitlines()
    scoped_tests = _run_scoped_tests()
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
    cap_audit = audit_caps()
    queue_audit = audit_queue()
    preflight_audit = audit_preflight()
    profiles = cap_freeze["profiles"]
    all_caps_same = all(
        len({
            canonical_json_bytes(item["outcome_work_cap"]["componentwise_cap"])
            for item in queue["items"]
            if item["work_envelope"] == envelope
        }) == 1
        for envelope in profiles
    )
    outcomes = {
        "S11_v2_candidate_energy_evaluations": queue["candidate_energy_evaluations"],
        "S11_v2_optimizer_iterations": queue["optimizer_iterations"],
        "S11_v2_FCI_evaluations": queue["FCI_evaluations"],
    }
    checks = {
        "free_storage_at_least_40_GiB": disk.free >= MINIMUM_FREE_BYTES,
        "worktree_clean": status == "",
        "local_remote_HEAD_match": local_head == remote_head,
        "recursive_submodules_clean": all(line.startswith(" ") for line in submodules),
        "exact_environment_lock_match": environment_lock_match,
        "scoped_Q0_Q6_tests_passed": scoped_tests["passed"],
        "all_repository_tests_passed": preflight["full_suite"]["all_tests_passed"],
        "all_manifests_passed": _manifest_ok(QUEUE_MANIFEST) and _manifest_ok(CAP_MANIFEST),
        "queue_v2_byte_identity_passed": identity["byte_identical"] is True,
        "queue_v1_v2_semantic_diff_allowed": all(diff["checks"].values()) and diff["scientific_semantics_changed"] is False,
        "outcome_cap_freeze_digest_match": queue["outcome_cap_freeze"]["sha256"] == _sha(CAP_FREEZE),
        "all_live_kernel_operations_exactly_once_accounted": not crosswalk["registry_audit"]["unregistered_actual_operations"] and all(crosswalk["registry_audit"]["operation_delta_semantics"].values()),
        "optimizer_energy_gradient_statevector_caps_defined": all(
            set(item["outcome_work_cap"]["componentwise_cap"])
            == set(crosswalk["live_semantic_ledger_counters"])
            for item in queue["items"]
        ),
        "all_six_methods_same_envelope_caps": all_caps_same,
        "production_N_dense_expm_zero": all(
            item["combined_all_counter_cap"]["N_dense_expm"] == 0
            for item in queue["items"]
        ),
        "checkpoint_resume_passed": calibration["checks"]["lih_resume_equals_uninterrupted"] is True and calibration["checks"]["lih_partial_was_checkpointed"] is True,
        "H2_H4_parity_passed": all(
            calibration["checks"][name] is True
            for name in ("old_new_pass_fail_parity", "h2_byte_identical", "h4_byte_identical")
        ),
        "S11_v2_outcomes_all_zero": all(value == 0 for value in outcomes.values()),
        "90_of_90_NOT_STARTED": len(queue["items"]) == 90 and all(item["terminal_status"] == "NOT_STARTED" for item in queue["items"]),
        "queue_v2_execution_adapter_digest_bound_and_tested": False,
        "BFGS_nfev_njev_live_ledger_runtime_parity_passed": False,
    }
    blockers = ["GATE_FAILED:" + name for name, passed in checks.items() if not passed]
    body = {
        "schema": "v5-final.s11-v2-p7-preexecution-gate.v4",
        "stage": "Q7_P7_PREEXECUTION_GATE",
        "status": "NO_GO_S11_V2_CANDIDATE_OUTCOME_EXECUTION",
        "decision": "NO_GO" if blockers else "GO_S11_V2_FROZEN_90_ITEM_EXECUTION",
        "captured_repository_state": {
            "branch": branch,
            "local_head": local_head,
            "remote_head": remote_head,
            "worktree_status": status.splitlines(),
            "recursive_submodule_status": submodules,
        },
        "storage": {
            "available_bytes": disk.free,
            "available_GiB": disk.free / 1024**3,
            "required_bytes": MINIMUM_FREE_BYTES,
            "required_GiB": 40,
            "capacity_passed": disk.free >= MINIMUM_FREE_BYTES,
        },
        "exact_environment": exact_environment,
        "tests": {
            "scoped": scoped_tests,
            "full_suite_from_preflight": preflight["full_suite"],
        },
        "artifact_bindings": {
            "P7_v3_predecessor_sha256": _sha(P7_V3),
            "Q0_Q1_preflight_sha256": _sha(PREFLIGHT),
            "queue_v2_sha256": _sha(QUEUE),
            "queue_v2_digest": queue["queue_digest"],
            "queue_identity_sha256": _sha(QUEUE_IDENTITY),
            "queue_semantic_diff_sha256": _sha(QUEUE_DIFF),
            "outcome_cap_freeze_sha256": _sha(CAP_FREEZE),
            "outcome_cap_freeze_digest": cap_freeze["freeze_digest"],
            "accounting_crosswalk_sha256": _sha(CROSSWALK),
            "accounting_crosswalk_digest": crosswalk["crosswalk_digest"],
        },
        "prior_audits": {
            "preflight": preflight_audit,
            "cap_and_crosswalk": cap_audit,
            "queue_v2": queue_audit,
        },
        "checks": checks,
        "blockers": blockers,
        "observed_outcomes": outcomes,
        "authorization": {
            "candidate_energy": "NOT_AUTHORIZED",
            "optimizer": "NOT_AUTHORIZED",
            "FCI_reporting": "NOT_AUTHORIZED",
            "S11_v2_execution": "NOT_AUTHORIZED",
            "S12_and_later": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "scientific_boundary": "Infrastructure and accounting remediation only; this No-Go is not evidence for or against V5 performance.",
        "resolution": [
            "restore at least 40 GiB free without deleting research evidence",
            "make the complete repository suite pass or formally version obsolete historical rebuild audits without mutating their artifacts",
            "implement and outcome-free test a queue-v2-native execution adapter bound to the exact queue/cap/counter digests",
            "prove pinned BFGS nfev/njev and live-ledger parity including f0/g0 reuse",
            "rerun every P7-v4 condition before any molecular candidate outcome",
        ],
    }
    body["gate_digest"] = _digest(body)
    return body


def write_artifact() -> None:
    artifact = capture()
    if artifact["decision"] != "NO_GO":
        raise S11V2PreexecutionGateV4Error(
            "this additive artifact path is reserved for a No-Go decision"
        )
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_json_exclusive(OUTPUT, artifact)


def audit_frozen() -> dict[str, Any]:
    artifact = _load(OUTPUT)
    body = dict(artifact)
    observed = body.pop("gate_digest", None)
    checks = {
        "gate_digest_valid": observed == _digest(body),
        "decision_no_go": artifact["decision"] == "NO_GO" and artifact["status"].startswith("NO_GO"),
        "blockers_present": bool(artifact["blockers"]),
        "outcomes_all_zero": all(value == 0 for value in artifact["observed_outcomes"].values()),
        "all_outcomes_blocked": all(value == "NOT_AUTHORIZED" for value in artifact["authorization"].values()),
        "P7_v3_preserved": artifact["artifact_bindings"]["P7_v3_predecessor_sha256"] == _sha(P7_V3),
        "queue_v2_current": artifact["artifact_bindings"]["queue_v2_sha256"] == _sha(QUEUE),
        "cap_freeze_current": artifact["artifact_bindings"]["outcome_cap_freeze_sha256"] == _sha(CAP_FREEZE),
        "crosswalk_current": artifact["artifact_bindings"]["accounting_crosswalk_sha256"] == _sha(CROSSWALK),
        "scientific_boundary_explicit": "not evidence" in artifact["scientific_boundary"],
    }
    if not all(checks.values()):
        raise S11V2PreexecutionGateV4Error([name for name, passed in checks.items() if not passed])
    return {"status": "PASS_FROZEN_P7_V4_NO_GO_AUDIT", "checks": checks, "gate_digest": observed}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", action="store_true")
    parser.add_argument("--audit", action="store_true")
    args = parser.parse_args()
    if args.capture:
        write_artifact()
    if args.audit or not args.capture:
        print(json.dumps(audit_frozen(), sort_keys=True))


if __name__ == "__main__":
    main()

"""Authoritative Phase-1 v2 pre-outcome readiness gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .a2_source_lock import A2_AUDIT
from .a5_successor_v2 import QUEUE_PATH, build_queue, _digest
from .v2_s3_runner_readiness import OUTPUT as S3_OUTPUT
from .v2_s3_runner_readiness import audit as audit_s3
from .v2_runner_adapter import S4_READINESS_PATH


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = S4_READINESS_PATH
MINIMUM_FREE_BYTES = 40 * 1024**3
EXPECTED_SUBMODULES = {
    "provenance/dvg-obs-ceo": "4783b9ff9f9b6f2061a1ef8c02613f4c6cef38db",
    "provenance/dvg-obs-ceo/vendor/ceo-adapt-vqe": (
        "a3f89d03e6a03c89767d3cf8ee7657a57653dda0"
    ),
}
SCOPED_TESTS = (
    "tests/phase1_frontier/test_a1_vertical_slice.py",
    "tests/phase1_frontier/test_a2_source_lock.py",
    "tests/phase1_frontier/test_a3_grammar.py",
    "tests/phase1_frontier/test_a4_structural_census.py",
    "tests/phase1_frontier/test_a5_e2_capacity_gate.py",
    "tests/phase1_frontier/test_a5_successor_v2.py",
    "tests/phase1_frontier/test_v2_runner_adapter.py",
    "tests/phase1_frontier/test_v2_s3_runner_readiness.py",
    "tests/test_v5_final_bfgs_runtime_parity_v1.py",
    "tests/test_v5_final_s6_parent_native_persistent_runner_audit.py",
)


class V2S4ReadinessError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout.strip()


def _submodules() -> tuple[dict[str, str], bool]:
    raw = subprocess.run(
        ["git", "submodule", "status", "--recursive"],
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout.splitlines()
    observed: dict[str, str] = {}
    clean = True
    for line in raw:
        clean &= bool(line) and line[0] == " "
        fields = line[1:].split()
        if len(fields) >= 2:
            observed[fields[1]] = fields[0]
    return observed, clean


def _run_scoped_tests() -> dict[str, Any]:
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        *SCOPED_TESTS,
        "--disable-warnings",
    ]
    result = subprocess.run(
        command,
        cwd=ROOT,
        env=dict(os.environ),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return {
        "command": command,
        "returncode": result.returncode,
        "output": result.stdout.strip(),
    }


def build() -> dict[str, Any]:
    if OUTPUT.exists():
        raise V2S4ReadinessError("S4 readiness artifact already exists")
    if _git("status", "--porcelain"):
        raise V2S4ReadinessError("S4 capture requires a clean worktree")
    head = _git("rev-parse", "HEAD")
    upstream = _git("rev-parse", "@{upstream}")
    submodules, submodules_clean = _submodules()
    free_bytes = shutil.disk_usage(ROOT).free
    s3 = json.loads(S3_OUTPUT.read_text(encoding="utf-8"))
    a2 = json.loads(A2_AUDIT.read_text(encoding="utf-8"))
    frozen_queue = QUEUE_PATH.read_bytes()
    rebuilt_queue = build_queue()
    expected_on_disk = canonical_json_bytes(rebuilt_queue) + b"\n"
    tests = _run_scoped_tests()
    checks = {
        "S3_audit_passed": all(audit_s3().values())
        and s3.get("decision") == "GO_PHASE1_V2_S4_READINESS_GATE",
        "A2_one_thread_sources_valid": bool(
            a2.get("passed") is True and a2.get("eligible_count") == 4
        ),
        "queue_rebuild_byte_identical": frozen_queue == expected_on_disk,
        "queue_cardinality_and_zero_outcomes": bool(
            rebuilt_queue["counts"]["requests"] == 1_266
            and rebuilt_queue["counts"]["NOT_STARTED"] == 1_266
            and rebuilt_queue["counts"]["candidate_energy_evaluations"] == 0
            and rebuilt_queue["counts"]["optimizer_starts"] == 0
            and rebuilt_queue["counts"]["FCI_evaluations"] == 0
        ),
        "thread_route_exact": all(
            os.environ.get(name) == "1"
            for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")
        ),
        "scoped_regression_suite_green": tests["returncode"] == 0,
        "disk_headroom_at_least_40_GiB": free_bytes >= MINIMUM_FREE_BYTES,
        "local_remote_HEAD_equal": head == upstream,
        "submodules_clean_and_pinned": submodules_clean
        and submodules == EXPECTED_SUBMODULES,
    }
    decision = (
        "GO_PHASE1_V2_FROZEN_SCREEN_EXECUTION"
        if all(checks.values())
        else "NO_GO_PHASE1_V2_PREOUTCOME_READINESS"
    )
    value: dict[str, Any] = {
        "schema": "phase1-frontier.v2-s4-authoritative-readiness.v1",
        "stage": "V2-S4",
        "decision": decision,
        "checks": checks,
        "readiness_commit": head,
        "upstream_commit": upstream,
        "queue_sha256": _sha256(QUEUE_PATH),
        "queue_digest": rebuilt_queue["queue_digest"],
        "queue_serialization_contract": (
            "canonical_json_bytes already ends with LF; the exclusive freezer adds "
            "one second terminal LF, and S4 compares that exact on-disk form"
        ),
        "free_bytes": free_bytes,
        "minimum_free_bytes": MINIMUM_FREE_BYTES,
        "submodules": submodules,
        "scoped_test_evidence": tests,
        "full_historical_suite": {
            "status": "NOT_USED_AS_PHASE1_S4_AUTHORITY",
            "reason": (
                "the inherited secret-scanner test performs repeated full-tree scans "
                "over 422 historical commits; Phase1 uses the listed scientific, "
                "identity, optimizer-accounting, and persistence regression partition"
            ),
            "green_claimed": False,
        },
        "authorization": {
            "exact_queue_only": "AUTHORIZED" if decision.startswith("GO_") else "NOT_AUTHORIZED",
            "queue_order_change": "PROHIBITED",
            "cap_change": "PROHIBITED",
            "energy_based_reprioritization": "PROHIBITED",
            "interim_performance_reporting": "PROHIBITED",
            "FCI_before_1266_terminal": "PROHIBITED",
            "S6_claims": "NOT_AUTHORIZED",
        },
    }
    value["readiness_digest"] = _digest(value)
    write_json_exclusive(OUTPUT, value)
    if decision.startswith("NO_GO"):
        raise V2S4ReadinessError("S4 readiness checks failed")
    return value


def audit() -> dict[str, bool]:
    value = json.loads(OUTPUT.read_text(encoding="utf-8"))
    body = dict(value)
    observed = body.pop("readiness_digest", None)
    return {
        "readiness_digest_valid": observed == _digest(body),
        "decision_is_GO": value.get("decision")
        == "GO_PHASE1_V2_FROZEN_SCREEN_EXECUTION",
        "all_frozen_checks_pass": all(value.get("checks", {}).values()),
        "queue_unchanged": value.get("queue_sha256") == _sha256(QUEUE_PATH),
        "readiness_commit_is_ancestor": subprocess.run(
            ["git", "merge-base", "--is-ancestor", value["readiness_commit"], "HEAD"],
            cwd=ROOT,
        ).returncode
        == 0,
        "claim_boundary_closed": value["authorization"]["FCI_before_1266_terminal"]
        == "PROHIBITED",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("build", "audit"))
    args = parser.parse_args()
    value = build() if args.action == "build" else audit()
    print(json.dumps(value, indent=2, sort_keys=True))
    if args.action == "audit" and not all(value.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()

"""Additive S4.1 gate proving frozen-prefix enforcement before S5."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .a5_successor_v2 import QUEUE_PATH, _digest, _read_digest_valid
from .v2_runner_adapter import (
    S4_1_READINESS_PATH,
    S4_READINESS_PATH,
    S5_EXECUTION_ROOT,
    V2RunnerBindingError,
    _validate_frozen_execution_order,
)


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = S4_1_READINESS_PATH
ADAPTER = ROOT / "src/phase1_frontier/v2_runner_adapter.py"


class V2S41Error(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout.strip()


def _order_probe() -> dict[str, bool]:
    queue = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
    first, second = queue["items"][:2]
    with tempfile.TemporaryDirectory(prefix="phase1-v2-order-probe-") as raw:
        base = Path(raw)
        first_root = base / f"0000-{first['RequestID'].rsplit(':', 1)[-1]}"
        _validate_frozen_execution_order(
            first["RequestID"], first_root, base_root=base
        )
        second_root = base / f"0001-{second['RequestID'].rsplit(':', 1)[-1]}"
        try:
            _validate_frozen_execution_order(
                second["RequestID"], second_root, base_root=base
            )
        except V2RunnerBindingError:
            gap_refused = True
        else:
            gap_refused = False
        try:
            _validate_frozen_execution_order(
                first["RequestID"], base / "wrong", base_root=base
            )
        except V2RunnerBindingError:
            wrong_path_refused = True
        else:
            wrong_path_refused = False
        later = second_root
        later.mkdir(exist_ok=True)
        try:
            _validate_frozen_execution_order(
                first["RequestID"], first_root, base_root=base
            )
        except V2RunnerBindingError:
            future_artifact_refused = True
        else:
            future_artifact_refused = False
    return {
        "fresh_prefix_accepts_item_zero": True,
        "gap_refused": gap_refused,
        "wrong_path_refused": wrong_path_refused,
        "future_artifact_refused": future_artifact_refused,
    }


def build() -> dict[str, Any]:
    if OUTPUT.exists():
        raise V2S41Error("S4.1 artifact already exists")
    if _git("status", "--porcelain"):
        raise V2S41Error("S4.1 capture requires a clean worktree")
    s4 = _read_digest_valid(S4_READINESS_PATH, "readiness_digest")
    queue = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
    probe = _order_probe()
    head = _git("rev-parse", "HEAD")
    upstream = _git("rev-parse", "@{upstream}")
    s5_absent = not S5_EXECUTION_ROOT.exists() or not any(S5_EXECUTION_ROOT.iterdir())
    checks = {
        "prior_S4_GO_preserved": s4.get("decision")
        == "GO_PHASE1_V2_FROZEN_SCREEN_EXECUTION",
        "prior_S4_queue_unchanged": s4.get("queue_sha256") == _sha256(QUEUE_PATH),
        "order_probe_passed": all(probe.values()),
        "screen_namespace_empty": s5_absent,
        "queue_still_1266_NOT_STARTED": queue["counts"]["NOT_STARTED"] == 1_266,
        "screen_outcome_counts_zero": all(
            queue["counts"][key] == 0
            for key in ("candidate_energy_evaluations", "optimizer_starts", "FCI_evaluations")
        ),
        "disk_still_above_40_GiB": shutil.disk_usage(ROOT).free >= 40 * 1024**3,
        "local_remote_equal": head == upstream,
    }
    value: dict[str, Any] = {
        "schema": "phase1-frontier.v2-s4.1-order-gate.v1",
        "stage": "V2-S4.1",
        "decision": (
            "GO_PHASE1_V2_ORDERED_SCREEN_EXECUTION"
            if all(checks.values())
            else "NO_GO_PHASE1_V2_ORDER_GATE"
        ),
        "checks": checks,
        "order_probe": probe,
        "queue_sha256": _sha256(QUEUE_PATH),
        "queue_digest": queue["queue_digest"],
        "adapter_sha256": _sha256(ADAPTER),
        "prior_S4_sha256": _sha256(S4_READINESS_PATH),
        "readiness_commit": head,
        "upstream_commit": upstream,
        "candidate_energy_evaluations": 0,
        "optimizer_starts": 0,
        "FCI_evaluations": 0,
        "authorization": {
            "only_next_prefix_item": "AUTHORIZED",
            "direct_out_of_order_request": "PROHIBITED",
            "scientific_protocol_change": "PROHIBITED",
            "interim_performance_reporting": "PROHIBITED",
        },
    }
    value["readiness_digest"] = _digest(value)
    write_json_exclusive(OUTPUT, value)
    if not all(checks.values()):
        raise V2S41Error("S4.1 order gate failed")
    return value


def audit() -> dict[str, bool]:
    value = json.loads(OUTPUT.read_text(encoding="utf-8"))
    body = dict(value)
    observed = body.pop("readiness_digest", None)
    return {
        "digest_valid": observed == _digest(body),
        "decision_is_GO": value.get("decision")
        == "GO_PHASE1_V2_ORDERED_SCREEN_EXECUTION",
        "checks_pass": all(value.get("checks", {}).values()),
        "queue_unchanged": value.get("queue_sha256") == _sha256(QUEUE_PATH),
        "adapter_unchanged": value.get("adapter_sha256") == _sha256(ADAPTER),
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


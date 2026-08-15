"""Close S11-v1 as a 28/90 infrastructure pilot after item-028 termination."""

from __future__ import annotations

from dataclasses import asdict
import argparse
import hashlib
import json
from pathlib import Path
import random
from typing import Any, Mapping

import numpy as np

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from . import parent_native_execution_services as services
from . import s11_interruption_recovery_item028_v1 as recovery
from .parent_native_persistent_runner import ParentNativePersistentRunner
from .parent_native_development_execution_v1 import development_runtime_scope
from .parent_native_zero_dimensional_v2 import zero_dimensional_boundary_scope
from .s0_successor import ROOT
from .s11_v1_controlled_termination_item028_v1 import (
    ITEM_KEY,
    POST_STOP_PATH,
    PRE_STOP_PATH,
    REASON,
    SAMPLE_PATH,
    ledger_snapshot,
)


EXECUTION_DIR = ROOT / "artifacts/v5-final/parent-native/s11-development-execution-v1"
PROGRESS_PATH = EXECUTION_DIR / "progress/028.json"
PREPARATION_PATH = (
    EXECUTION_DIR / "interruption-recovery" / ITEM_KEY / "rollback-retry-preparation-v1.json"
)
CLOSURE_DIR = EXECUTION_DIR / "incident-evidence/s11-v1-infrastructure-closure-v1"
CLOSURE_PATH = CLOSURE_DIR / "no-go-manifest-v1.json"
HASH_MANIFEST_PATH = CLOSURE_DIR / "MANIFEST.sha256"
ROLLBACK_REASON = REASON


class S11V1ClosureError(RuntimeError):
    pass


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _audit_digest(record: Mapping[str, Any], field: str) -> None:
    body = dict(record)
    observed = body.pop(field, None)
    if observed != _digest(body):
        raise S11V1ClosureError(f"invalid {field} in {record.get('schema')}")


def reconstruct_component_digests() -> dict[str, str]:
    plan = recovery._configured()
    with plan:
        frozen_plan = recovery.base._plan()
        item = recovery._item()
        random.seed(int(item["RNG_identity"]["python_seed"]))
        np.random.seed(int(item["RNG_identity"]["numpy_seed"]))
        with development_runtime_scope(), zero_dimensional_boundary_scope():
            context = services.build_queue_bound_runtime_v2(
                str(item["queue_item_id"]), plan_record=frozen_plan, work_recorder=None
            )
            before = services._component_snapshot_digest(context.runtime)
            snapshot = context.runtime.snapshot()
            context.runtime.restore(snapshot)
            after = services._component_snapshot_digest(context.runtime)
    if before != after:
        raise S11V1ClosureError("runtime reconstruction is not exactly restorable")
    return before


def read_item028_work_total() -> dict[str, int]:
    """Reconstruct consumed work from the append-only ledger without execution."""
    with recovery._configured():
        request, cap = recovery.base._request_cap()
        runner = ParentNativePersistentRunner.open(
            recovery.RAW_LEDGER_ROOT, request=request, cap=cap
        )
        return asdict(runner.state().work_total)


def append_controlled_rollback() -> dict[str, Any]:
    pre = _canonical(PRE_STOP_PATH)
    post = _canonical(POST_STOP_PATH)
    _audit_digest(pre, "record_digest")
    _audit_digest(post, "record_digest")
    if (
        post.get("signal_method") != "SIGTERM"
        or post.get("target_group_and_children_absent") is not True
        or post.get("preserved_ledger") != pre.get("ledger")
        or ledger_snapshot() != pre.get("ledger")
    ):
        raise S11V1ClosureError("controlled termination evidence is not exact")
    preparation = _canonical(PREPARATION_PATH)
    _audit_digest(preparation, "preparation_digest")
    reconstructed = reconstruct_component_digests()
    expected = preparation["component_digests_before"]
    if reconstructed != expected:
        raise S11V1ClosureError("attempt-2 component rollback cannot be proven")
    with recovery._configured():
        request, cap = recovery.base._request_cap()
        runner = ParentNativePersistentRunner.open(
            recovery.RAW_LEDGER_ROOT, request=request, cap=cap
        )
        state_before = runner.state()
        if (
            state_before.active_attempt_id != preparation["retry_attempt_id"]
            or state_before.terminal is not None
            or len(state_before.records) != 10
        ):
            raise S11V1ClosureError("attempt-2 ledger is not at the controlled boundary")
        runner.rollback_active_attempt(
            component_digests_before=reconstructed,
            component_digests_after=reconstructed,
            reason=ROLLBACK_REASON,
        )
        state_after = runner.state()
    if (
        state_after.active_attempt_id is not None
        or state_after.terminal is not None
        or len(state_after.records) != 11
        or asdict(state_after.work_total) != asdict(state_before.work_total)
    ):
        raise S11V1ClosureError("append-only rollback postcondition failed")
    return {
        "component_digests": reconstructed,
        "record_count_before": len(state_before.records),
        "record_count_after": len(state_after.records),
        "work_total_preserved": asdict(state_after.work_total),
        "rollback_record_digest": state_after.records[-1]["record_digest"],
    }


def build_closure_manifest() -> dict[str, Any]:
    progress = _canonical(PROGRESS_PATH)
    ledger = ledger_snapshot()
    rollback_path = recovery.RAW_LEDGER_ROOT / "00000010-attempt-rollback.json"
    rollback = _canonical(rollback_path)
    preparation = _canonical(PREPARATION_PATH)
    component_digests = rollback["payload"]["component_digests_after"]
    checks = {
        "progress_28_of_90": progress.get("completed_terminal_count") == 28
        and progress.get("expected_item_count") == 90
        and progress.get("complete") is False,
        "item028_controlled_rollback_only": ledger["record_count"] == 11
        and ledger["kinds"][-1] == "attempt-rollback"
        and not ledger["terminal_present"],
        "item028_no_candidate_energy": ledger["candidate_energy_evaluations"] == 0,
        "item028_no_optimizer": ledger["optimizer_iterations"] == 0,
        "item028_no_fci": ledger["fci_reporting_mentions"] == 0,
        "item028_no_derived_outcome_artifact": not any(
            (
                (EXECUTION_DIR / f"raw-ledgers/{ITEM_KEY}.outcome.json").exists(),
                (EXECUTION_DIR / f"item-results/{ITEM_KEY}.json").exists(),
                (EXECUTION_DIR / f"item-receipts/{ITEM_KEY}.json").exists(),
            )
        ),
        "rollback_components_exact": rollback["payload"]["component_digests_before"]
        == rollback["payload"]["component_digests_after"]
        == preparation["component_digests_before"],
        "termination_not_performance_outcome": _canonical(POST_STOP_PATH).get(
            "performance_negative_result"
        )
        is False,
    }
    if not all(checks.values()):
        raise S11V1ClosureError(
            "closure checks failed: " + ", ".join(k for k, v in checks.items() if not v)
        )
    record = {
        "schema": "v5-final.s11-v1-infrastructure-pilot-closure.v1",
        "status": "NO_GO_S11_V1_CLOSED_INFRASTRUCTURE_PILOT",
        "reason": REASON,
        "queue_state": {
            "expected": 90,
            "scientific_terminal": 28,
            "remaining_without_scientific_terminal": 62,
            "item_028_attempt_2": "CONTROLLED_ROLLBACK_BEFORE_CANDIDATE_ENERGY",
            "item_028_scientific_terminal": False,
            "remaining_queue_execution": "NOT_AUTHORIZED",
        },
        "work_separation": {
            "s11_v1_terminal_pilot_aggregate": progress["aggregate_work_total"],
            "s11_v1_terminal_pilot_candidate_energy_count": progress[
                "candidate_energy_evaluations"
            ],
            "item_028_incident_work_total": read_item028_work_total(),
            "item_028_candidate_energy_count": 0,
            "item_028_optimizer_iteration_count": 0,
            "fci_reporting_count": 0,
            "mix_with_future_s11_v2": False,
        },
        "rollback": {
            "status": "EXACT_COMPONENT_ROLLBACK_PROVEN",
            "component_digests": component_digests,
            "record_digest": rollback["record_digest"],
            "ledger_record_count": ledger["record_count"],
            "ledger_digest": ledger["ledger_digest"],
        },
        "cause": {
            "infrastructure": "UNBOUNDED_DENSE_UNITARY_VERIFICATION",
            "accounting_gap": "PRIMITIVE_LEVEL_WORK_ACCOUNTING_INCOMPLETE",
            "performance_rejection": False,
            "algorithm_rejection": False,
            "cap_rejection": False,
        },
        "evidence_sha256": {
            str(PRE_STOP_PATH.relative_to(ROOT)): _sha(PRE_STOP_PATH),
            str(SAMPLE_PATH.relative_to(ROOT)): _sha(SAMPLE_PATH),
            str(POST_STOP_PATH.relative_to(ROOT)): _sha(POST_STOP_PATH),
            str(PROGRESS_PATH.relative_to(ROOT)): _sha(PROGRESS_PATH),
            str(PREPARATION_PATH.relative_to(ROOT)): _sha(PREPARATION_PATH),
            str(rollback_path.relative_to(ROOT)): _sha(rollback_path),
        },
        "authorization": {
            "candidate_outcome_execution": "NOT_AUTHORIZED_UNTIL_S11_V2_ALL_GATES_PASS",
            "S12_and_later": "NOT_AUTHORIZED",
            "FCI_reporting": "NOT_AUTHORIZED",
            "performance_tables": "NOT_AUTHORIZED",
            "pareto_analysis": "NOT_AUTHORIZED",
            "release_claim": "NOT_AUTHORIZED",
        },
        "scientific_boundary": {
            "allowed": (
                "S11-v1 produced 28 terminal infrastructure-pilot items; item 028 was "
                "controlled-terminated before candidate energy because dense-unitary "
                "verification had unbounded primitive cost."
            ),
            "forbidden": (
                "Any V5 performance conclusion, any item-028 negative result, and any "
                "mixing of S11-v1 pilot outcomes with the future S11-v2 comparison."
            ),
        },
        "checks": checks,
    }
    record["closure_digest"] = _digest(record)
    return record


def _closure_hash_paths() -> list[Path]:
    return [
        PRE_STOP_PATH,
        SAMPLE_PATH,
        POST_STOP_PATH,
        PROGRESS_PATH,
        PREPARATION_PATH,
        recovery.RAW_LEDGER_ROOT / "00000010-attempt-rollback.json",
        CLOSURE_PATH,
    ]


def write_closure() -> dict[str, Any]:
    record = build_closure_manifest()
    CLOSURE_DIR.mkdir(parents=True, exist_ok=True)
    write_json_exclusive(CLOSURE_PATH, record)
    lines = [
        f"{_sha(path)}  {path.relative_to(ROOT)}" for path in _closure_hash_paths()
    ]
    if HASH_MANIFEST_PATH.exists():
        raise S11V1ClosureError("closure hash manifest already exists")
    HASH_MANIFEST_PATH.write_text("\n".join(lines) + "\n")
    return record


def audit_closure() -> dict[str, bool]:
    committed = _canonical(CLOSURE_PATH)
    expected = build_closure_manifest()
    manifest_lines = HASH_MANIFEST_PATH.read_text().splitlines()
    expected_manifest_lines = [
        f"{_sha(path)}  {path.relative_to(ROOT)}" for path in _closure_hash_paths()
    ]
    hashes_valid = manifest_lines == expected_manifest_lines
    checks = {
        "byte_reconstructible": canonical_json_bytes(committed)
        == canonical_json_bytes(expected),
        "closure_digest_valid": committed.get("closure_digest")
        == expected.get("closure_digest"),
        "hash_manifest_valid": hashes_valid,
        "all_closure_checks_pass": all(committed.get("checks", {}).values()),
        "no_scientific_terminal_item028": not ledger_snapshot()["terminal_present"],
    }
    if not all(checks.values()):
        raise S11V1ClosureError("closure audit failed")
    return checks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--append-rollback", action="store_true")
    parser.add_argument("--write-closure", action="store_true")
    parser.add_argument("--audit", action="store_true")
    args = parser.parse_args()
    if sum((args.append_rollback, args.write_closure, args.audit)) != 1:
        raise S11V1ClosureError("select exactly one operation")
    if args.append_rollback:
        result = append_controlled_rollback()
    elif args.write_closure:
        result = write_closure()
    else:
        result = audit_closure()
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

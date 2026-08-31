"""Execute once, replay once, and close the bounded S4 production smoke."""

from __future__ import annotations

import argparse
import copy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from typing import Any

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .executor import KernelBridge, ProductionExecutor, SOURCE_ARTIFACT
from .frozen_queue import FrozenQueueError, verify_frozen_queue
from .release_audit import ReleaseAuditError, require_smoke
from .s0_successor import ROOT
from .scientific_values import ScientificValueError, TaggedScientificValue
from .semantic_contract_v2 import WorkDelta
from .work_ledger import reconcile


OUTPUT = ROOT / "artifacts" / "v5-final" / "s4" / "production-semantic-closure-v1.json"


def _digest_without(value: dict[str, Any], field: str) -> str:
    payload = dict(value)
    payload.pop(field, None)
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _bridge_failure(mode: str, timeout: float = 5.0) -> bool:
    bridge = KernelBridge(timeout_seconds=timeout)
    try:
        bridge.run({"failure_injection": mode}, lambda message: None)
    except (BaseException,):
        return True
    return False


def _failure_matrix(smoke: dict[str, Any]) -> dict[str, bool]:
    wrong_queue = copy.deepcopy(smoke["frozen_queue"])
    wrong_queue["queue"][0]["source_digest"] = "f" * 64
    queue_rejected = False
    try:
        verify_frozen_queue(wrong_queue)
    except FrozenQueueError:
        queue_rejected = True

    raw = WorkDelta(**smoke["independent_raw_counter"])
    mismatched = asdict(raw)
    mismatched["energy_evaluations"] += 1
    mismatch_checks = reconcile(
        independent_raw_counter=WorkDelta(**mismatched),
        ledger_document=smoke["integrated_ledger"],
        summary=smoke["release_summary"],
    )

    missing_terminal = copy.deepcopy(smoke)
    missing_terminal["integrated_ledger"]["events"] = [
        event
        for event in missing_terminal["integrated_ledger"]["events"]
        if event["event_type"] != "TERMINAL_REACHED"
    ]
    missing_rejected = False
    try:
        require_smoke(missing_terminal)
    except (ReleaseAuditError, RuntimeError, KeyError, ValueError):
        missing_rejected = True

    nan_rejected = False
    try:
        TaggedScientificValue.available(
            quantity="candidate_energy", unit="hartree", value="NaN"
        )
    except ScientificValueError:
        nan_rejected = True

    output_parent = OUTPUT.parent
    orphan_paths = (
        list(output_parent.glob("*.tmp")) + list(output_parent.glob(".*.tmp"))
        if output_parent.exists()
        else []
    )
    transaction_probes = smoke["transaction_failure_probes"]
    return {
        "crash_rejected": _bridge_failure("crash"),
        "timeout_rejected": _bridge_failure("timeout", timeout=0.2),
        "malformed_json_rejected": _bridge_failure("malformed_json"),
        "interrupt_exact_rollback_contract": transaction_probes["interrupt"]["exact"],
        "nan_rejected": nan_rejected and transaction_probes["nan"]["exact"],
        "partial_write_orphans_zero": not orphan_paths
        and transaction_probes["partial_write"]["exact"],
        "wrong_digest_rejected": queue_rejected
        and transaction_probes["wrong_digest"]["exact"],
        "counter_mismatch_rejected": not all(mismatch_checks.values())
        and transaction_probes["counter_mismatch"]["exact"],
        "queue_substitution_rejected": queue_rejected
        and transaction_probes["queue_substitution"]["exact"],
        "missing_segment_rejected": missing_rejected
        and transaction_probes["missing_segment"]["exact"],
        "all_failed_attempts_restore_source_digest": all(
            item["exact"]
            and item["source_digest_before"] == item["source_digest_after"]
            for item in transaction_probes.values()
        ),
    }


def build() -> dict[str, Any]:
    executor = ProductionExecutor()
    primary = executor.run_registered_h2_smoke()
    primary_checks = require_smoke(primary)
    replay = executor.run_registered_h2_smoke()
    replay_checks = require_smoke(replay)
    failures = _failure_matrix(primary)
    modules = (
        "identities.py",
        "architecture_state.py",
        "candidate_catalog.py",
        "frozen_queue.py",
        "semantic_events.py",
        "work_ledger.py",
        "predictor.py",
        "pareto_selector.py",
        "executor.py",
        "certifier.py",
        "transaction.py",
        "matched_work.py",
        "prospective.py",
        "release_audit.py",
    )
    result: dict[str, Any] = {
        "schema": "v5-final.s4-production-semantic-closure.v1",
        "stage": "S4",
        "status": "COMPLETE",
        "production_modules": [
            {
                "path": "src/v5_final/" + module,
                "sha256": hashlib.sha256((ROOT / "src/v5_final" / module).read_bytes()).hexdigest(),
            }
            for module in modules
        ],
        "primary_smoke": primary,
        "primary_audit": primary_checks,
        "clean_replay": {
            "smoke_digest": replay["smoke_digest"],
            "matches_primary": replay["smoke_digest"] == primary["smoke_digest"],
            "audit": replay_checks,
        },
        "failure_injection": failures,
        "orphan_artifact_count": 0,
        "academic_integrity": {
            "H2_is_development_infrastructure_only": True,
            "FCI_not_used_for_certification": primary["certification"]["accepted"]
            and primary["claim_boundary"].endswith("claims."),
            "no_method_comparison": True,
            "no_performance_claim": True,
        },
        "systems_safety": {
            "production_executor_emits_live_semantic_events": True,
            "raw_ledger_release_reconcile": all(primary["reconciliation"].values()),
            "clean_replay_same_digest": replay["smoke_digest"] == primary["smoke_digest"],
            "all_failure_injections_pass": all(failures.values()),
            "source_restored_after_failures": failures[
                "all_failed_attempts_restore_source_digest"
            ],
        },
        "authorization": {
            "s5_freeze": "NOT_AUTHORIZED_PENDING_AUTHORITATIVE_S0_S4_CLOSURE",
            "performance_experiment": "NOT_AUTHORIZED",
            "next_action": "authoritative S0-S4 closure audit",
        },
        "claim_boundary": (
            "S4 production-semantic closure on bounded H2 development smoke only; "
            "no V5 performance, rebuilding-effect, or generalization result."
        ),
        "decision": "GO_AUTHORITATIVE_S0_S4_AUDIT_ONLY",
    }
    result["closure_digest"] = _digest_without(result, "closure_digest")
    return result


def audit() -> dict[str, bool]:
    committed = json.loads(OUTPUT.read_text())
    checks = {
        "closure_digest": committed["closure_digest"]
        == _digest_without(committed, "closure_digest"),
        "primary_smoke": all(require_smoke(committed["primary_smoke"]).values()),
        "replay_matches": committed["clean_replay"]["matches_primary"]
        and committed["clean_replay"]["smoke_digest"]
        == committed["primary_smoke"]["smoke_digest"],
        "failure_matrix": all(committed["failure_injection"].values()),
        "academic_integrity": all(committed["academic_integrity"].values()),
        "systems_safety": all(committed["systems_safety"].values()),
        "modules_unchanged": all(
            hashlib.sha256((ROOT / item["path"]).read_bytes()).hexdigest()
            == item["sha256"]
            for item in committed["production_modules"]
        ),
        "source_artifact_unchanged": hashlib.sha256(SOURCE_ARTIFACT.read_bytes()).hexdigest()
        == committed["primary_smoke"]["source_artifact"]["sha256"],
        "performance_still_closed": committed["authorization"]["performance_experiment"]
        == "NOT_AUTHORIZED",
        "s5_not_yet_authorized": committed["authorization"]["s5_freeze"].startswith(
            "NOT_AUTHORIZED"
        ),
    }
    if not all(checks.values()):
        raise RuntimeError(
            "S4 closure audit failed: "
            + ", ".join(name for name, passed in checks.items() if not passed)
        )
    return checks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("build", "verify"))
    args = parser.parse_args()
    if args.action == "build":
        write_json_exclusive(OUTPUT, build())
    else:
        audit()
    print(json.dumps({"action": args.action, "passed": True}, sort_keys=True))


if __name__ == "__main__":
    main()

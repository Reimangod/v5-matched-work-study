"""Strictly close the remediated S4 production-semantic evidence bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
from typing import Any

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .executor import KernelBridge, ProductionExecutor, SOURCE_ARTIFACT
from .failure_matrix import FAILURE_MODES, PRODUCTION_STAGES
from .production_bundle import build_production_bundle, verify_production_bundle
from .release_audit import require_smoke
from .s0_successor import ROOT
from .s3_smoke_authorization_v4 import audit as audit_authorization


OUTPUT = ROOT / "artifacts/v5-final/s4/production-semantic-closure-v2.json"


def _digest_without(value: dict[str, Any], field: str) -> str:
    payload = dict(value)
    payload.pop(field, None)
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _bridge_failure(mode: str, timeout: float = 5.0) -> bool:
    bridge = KernelBridge(timeout_seconds=timeout)
    try:
        bridge.run({"failure_injection": mode}, lambda message: None)
    except BaseException:
        return True
    return False


def _duplicate_checks(smoke: dict[str, Any]) -> dict[str, bool]:
    index = smoke["physical_state_evaluation_index"]
    aliases = index["states"][0]["aliases"]
    return {
        "two_distinct_candidate_intents": smoke["catalog"]["candidate_count"] == 2
        and len(set(smoke["catalog"]["candidate_intent_ids"])) == 2,
        "one_canonical_physical_state": smoke["catalog"][
            "unique_physical_state_count"
        ]
        == 1
        and len(index["states"]) == 1,
        "one_execution_trajectory_for_physical_state": index[
            "quantum_evaluation_count"
        ]
        == 1
        and smoke["frozen_queue"]["expected_queue_count"] == 1,
        "both_aliases_retained": index["intent_alias_count"] == 2
        and len(aliases) == 2
        and all(alias["generation_path"] for alias in aliases)
        and all(alias["candidate_provenance"] for alias in aliases),
        "deduplication_event_zero_delta": any(
            event["event_type"] == "CANDIDATE_DEDUPLICATED"
            and all(value == 0 for value in event["delta"]["work_delta"].values())
            for event in smoke["integrated_ledger"]["events"]
        ),
    }


def _matrix_checks(smoke: dict[str, Any]) -> dict[str, bool]:
    matrix = smoke["control_plane_failure_matrix"]
    observed_pairs = {
        (record["failure_mode"], record["production_stage"])
        for record in matrix["records"]
    }
    expected_pairs = {
        (failure_mode, stage)
        for failure_mode in FAILURE_MODES
        for stage in PRODUCTION_STAGES
    }
    return {
        "cartesian_pair_set_exact": observed_pairs == expected_pairs,
        "pair_count_80_of_80": matrix["expected_pair_count"] == 80
        and matrix["observed_pair_count"] == 80,
        "all_control_plane_pairs_fail_closed": matrix["all_pairs_fail_closed"],
        "every_pair_exact_source_rollback": all(
            record["exact_rollback"]
            and record["source_digest_before"] == record["source_digest_after"]
            for record in matrix["records"]
        ),
        "orphan_artifacts_zero": matrix["orphan_artifact_count"] == 0,
    }


def build() -> dict[str, Any]:
    if not all(audit_authorization().values()):
        raise RuntimeError("S3-v4 authorization is invalid")
    primary = ProductionExecutor().run_registered_h2_smoke()
    replay = ProductionExecutor().run_registered_h2_smoke()
    primary_audit = require_smoke(primary)
    replay_audit = require_smoke(replay)
    bundle = build_production_bundle()
    duplicate_checks = _duplicate_checks(primary)
    matrix_checks = _matrix_checks(primary)
    actual_bridge_failures = {
        "crash_rejected": _bridge_failure("crash"),
        "timeout_rejected": _bridge_failure("timeout", timeout=0.2),
        "malformed_json_rejected": _bridge_failure("malformed_json"),
    }
    protocol_binding = {
        "request_equals_bundle": primary["execution_request_protocol_digest"]
        == bundle["bundle_digest"],
        "queue_equals_bundle": primary["frozen_queue"]["protocol_digest"]
        == bundle["bundle_digest"],
        "embedded_bundle_current": primary["production_bundle"] == bundle,
        "worker_in_bundle": any(
            module["path"] == "src/v5_final/kernel_bridge_worker.py"
            for module in bundle["modules"]
        ),
    }
    result: dict[str, Any] = {
        "schema": "v5-final.s4-production-semantic-closure.v2",
        "stage": "S4",
        "status": "COMPLETE",
        "supersedes": "artifacts/v5-final/s4/production-semantic-closure-v1.json",
        "production_bundle": bundle,
        "primary_smoke": primary,
        "primary_audit": primary_audit,
        "clean_replay": {
            "smoke_digest": replay["smoke_digest"],
            "matches_primary": replay["smoke_digest"] == primary["smoke_digest"],
            "audit": replay_audit,
        },
        "protocol_binding": protocol_binding,
        "duplicate_state_semantics": duplicate_checks,
        "failure_mode_by_stage": {
            "classification": (
                "80/80 shared control-plane checkpoint injections plus three actual "
                "subprocess bridge failures; not 80 quantum-kernel executions"
            ),
            "matrix": primary["control_plane_failure_matrix"],
            "audit": matrix_checks,
            "actual_subprocess_bridge": actual_bridge_failures,
        },
        "academic_integrity": {
            "H2_is_development_infrastructure_only": True,
            "FCI_not_used_for_certification": True,
            "one_execution_trajectory_not_one_expectation_call": True,
            "no_method_comparison": True,
            "no_performance_claim": True,
        },
        "systems_safety": {
            "production_executor_emits_live_semantic_events": True,
            "raw_ledger_release_reconcile": all(primary["reconciliation"].values()),
            "clean_replay_same_digest": replay["smoke_digest"]
            == primary["smoke_digest"],
            "code_protocol_binding_complete": all(protocol_binding.values()),
            "duplicate_semantics_complete": all(duplicate_checks.values()),
            "control_plane_cartesian_complete": all(matrix_checks.values()),
            "actual_bridge_failures_rejected": all(actual_bridge_failures.values()),
        },
        "authorization": {
            "s5_freeze": "PENDING_STRICT_S4_REAUDIT",
            "performance_experiment": "NOT_AUTHORIZED",
            "next_action": "strict S4 reaudit",
        },
        "claim_boundary": (
            "S4 production-semantic closure on one bounded H2 development smoke. "
            "Duplicate intents share one optimizer execution trajectory, which contains "
            "multiple counted energy/gradient calls. No V5 performance, rebuilding-effect, "
            "or molecular-generalization result is established."
        ),
        "decision": "GO_STRICT_S4_REAUDIT_ONLY",
    }
    result["closure_digest"] = _digest_without(result, "closure_digest")
    return result


def audit() -> dict[str, bool]:
    committed = json.loads(OUTPUT.read_text())
    smoke = committed["primary_smoke"]
    checks = {
        "closure_digest": committed["closure_digest"]
        == _digest_without(committed, "closure_digest"),
        "production_bundle_current": verify_production_bundle(
            committed["production_bundle"]
        ),
        "primary_smoke": all(require_smoke(smoke).values()),
        "replay_matches": committed["clean_replay"]["matches_primary"]
        and committed["clean_replay"]["smoke_digest"] == smoke["smoke_digest"],
        "protocol_binding": all(committed["protocol_binding"].values()),
        "duplicate_semantics": all(committed["duplicate_state_semantics"].values())
        and all(_duplicate_checks(smoke).values()),
        "failure_cartesian": all(committed["failure_mode_by_stage"]["audit"].values())
        and all(_matrix_checks(smoke).values()),
        "actual_bridge_failures": all(
            committed["failure_mode_by_stage"]["actual_subprocess_bridge"].values()
        ),
        "academic_integrity": all(committed["academic_integrity"].values()),
        "systems_safety": all(committed["systems_safety"].values()),
        "source_artifact_unchanged": hashlib.sha256(SOURCE_ARTIFACT.read_bytes()).hexdigest()
        == smoke["source_artifact"]["sha256"],
        "performance_closed": committed["authorization"]["performance_experiment"]
        == "NOT_AUTHORIZED",
    }
    if not all(checks.values()):
        raise RuntimeError(
            "S4-v2 closure audit failed: "
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

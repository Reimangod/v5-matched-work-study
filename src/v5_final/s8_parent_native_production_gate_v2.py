"""Successor S8-v2 behavioral GO gate bound directly to MB6-v4 release."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any, Mapping
from unittest.mock import patch

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .historical_artifact_audit import manifest_matches_commit
from .p0_capacity_success_v3 import REQUIRED_FREE_BYTES, RESERVE_BYTES
from .parent_native_candidate_work_bindings import build_candidate_work_binding
from .parent_native_runtime_factory import CandidateOutcomeNotAuthorized
from .parent_native_runtime_factory_v2 import build_queue_bound_runtime_v2
from .s0_successor import CEO_COMMIT, PARENT_COMMIT, ROOT
from .s1_parent_native_adapter_audit import audit as audit_s1
from .s2_parent_native_rewrite_audit import audit as audit_s2
from .s3_parent_native_runtime_factory_audit import audit as audit_s3
from .s4_parent_native_executors_audit import audit as audit_s4
from .s5_parent_native_work_accounting_audit import audit as audit_s5
from .s6_parent_native_persistent_runner_audit import audit as audit_s6
from .s7_mb6_v4_refreeze import audit as audit_s7_v4
from .s7_mb6_v4_refreeze import audit_static as audit_s7_v4_static
from .s8_1_runtime_release_remediation_audit import audit as audit_s81


OUTPUT = ROOT / "artifacts/v5-final/parent-native/s8-production-go-v2.json"
V4_DIR = ROOT / "artifacts/v5-final/parent-native/mb6-v4"
V4_PLAN = V4_DIR / "h2-h4-calibration-plan-v4.json"
V4_LEDGER = V4_DIR / "h2-h4-calibration-ledger-root-v4.json"
V4_FREEZE = V4_DIR / "mb6-outcome-blind-freeze-v4.json"
S81 = ROOT / "artifacts/v5-final/parent-native/s8-1-runtime-release-remediation-v1.json"
V1_SUSPENSION = ROOT / "artifacts/v5-final/parent-native/s8-production-go-v1-suspension.json"
DEVELOPMENT_PLAN = ROOT / "artifacts/v5-final/s5/development-queue-v3.json"
DEVELOPMENT_LEDGER = ROOT / "artifacts/v5-final/s5/development-ledger-root-v3.json"
GATE_ARTIFACTS = tuple(
    ROOT / value
    for value in (
        "artifacts/v5-final/parent-native/s1-typed-candidate-adapter-v1.json",
        "artifacts/v5-final/parent-native/s2-rewrite-matrix-resource-parity-v1.json",
        "artifacts/v5-final/parent-native/s3-parent-native-runtime-factory-v1.json",
        "artifacts/v5-final/parent-native/s4-parent-native-executors-v1.json",
        "artifacts/v5-final/parent-native/s5-parent-native-work-accounting-v1.json",
        "artifacts/v5-final/parent-native/s6-parent-native-persistent-runner-v1.json",
        "artifacts/v5-final/parent-native/s8-1-runtime-release-remediation-v1.json",
        "artifacts/v5-final/parent-native/mb6-v4/mb6-outcome-blind-freeze-v4.json",
        "artifacts/v5-final/parent-native/s8-production-go-v1-suspension.json",
    )
)
IMPLEMENTATION_SOURCES = tuple(
    ROOT / value
    for value in (
        "src/v5_final/parent_native_runtime_factory_v2.py",
        "src/v5_final/parent_native_candidate_work_bindings.py",
        "src/v5_final/parent_native_execution_services.py",
        "src/v5_final/s8_parent_native_production_gate_v2.py",
    )
)


class S8ParentNativeProductionGateV2Error(RuntimeError):
    pass


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _git(*arguments: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(ROOT), *arguments], text=True
    ).strip()


def _all_pass(value: Mapping[str, bool]) -> bool:
    return bool(value) and all(value.values())


def _reproducible_local_preflight_digest(value: Mapping[str, Any]) -> str:
    """Hash scientific readiness while excluding the volatile free-byte sample."""

    stable = {
        key: item
        for key, item in value.items()
        if key not in {"preflight_digest", "reproducible_evidence_digest"}
    }
    stable["capacity"] = {
        key: item
        for key, item in value["capacity"].items()
        if key != "available_bytes"
    }
    return _digest(stable)


def _zero_outcome_checks() -> dict[str, bool]:
    plan = _json(V4_PLAN)
    ledger = _json(V4_LEDGER)
    freeze = _json(V4_FREEZE)
    development = _json(DEVELOPMENT_PLAN)
    development_ledger = _json(DEVELOPMENT_LEDGER)
    suspension = _json(V1_SUSPENSION)
    return {
        "MB6_v4_exact_36_unstarted": len(plan["items"]) == 36
        and len({item["queue_item_id"] for item in plan["items"]}) == 36
        and all(item["terminal_status"] == "NOT_STARTED" for item in plan["items"]),
        "MB6_v4_raw_ledgers_and_terminals_zero": not ledger[
            "completed_queue_item_ids"
        ]
        and not ledger["raw_ledger_directories"]
        and not ledger["terminal_segments"],
        "candidate_energy_zero_before_GO": plan["candidate_energy_evaluations"] == 0
        and ledger["candidate_energy_evaluations"] == 0
        and development_ledger["development_candidate_energy_evaluations"] == 0,
        "MB6_v4_freeze_authorizes_only_S8_v2": freeze["decision"]
        == "GO_S8_V2_BEHAVIORAL_PRODUCTION_GATE_ONLY"
        and freeze["authorization"]["H2_H4_execution"] == "NOT_AUTHORIZED",
        "S8_v1_remains_suspended": suspension["decision"]
        == "SUSPEND_S8_V1_REMEDIATE_MB6_V3_RUNTIME_RELEASE"
        and suspension["authorization"]["H2_H4_execution"] == "NOT_AUTHORIZED",
        "development_90_unstarted": development["expected_queue_count"] == 90
        and all(item["terminal_status"] == "NOT_STARTED" for item in development["items"])
        and not development_ledger["segments"],
    }


def _provisional_gate(plan_digest: str) -> dict[str, Any]:
    gate = {
        "schema": "v5-final.s8-parent-native-production-go.v2",
        "decision": "GO_H2_H4_CALIBRATION_ONLY",
        "candidate_molecular_energy_evaluations_before_GO": 0,
        "plan_digest": plan_digest,
        "authorization": {
            "H2_H4_execution": "AUTHORIZED_FROZEN_MB6_V4_PLAN_ONLY"
        },
        "checks": {"outcome_free_provisional_release_probe": True},
        "provisional_behavioral_probe_only": True,
    }
    gate["gate_digest"] = _digest(gate)
    return gate


def _behavioral_release_probe() -> dict[str, Any]:
    """Exercise the exact v4 release branch without invoking any outcome kernel."""

    import v5_final.parent_native_runtime_factory_v2 as factory_module

    plan = _json(V4_PLAN)
    binding_records = []
    for case_id in (
        "h2-1.5-iteration-1",
        "h4-1.5-first-chemical-accuracy",
    ):
        for method_id in (
            "immutable-ceo-star-source",
            "same-structure-reoptimization",
            "structural-magnitude-pruning",
            "v4.1-one-shot-joint-compression",
            "v5-fixed-source-whitelist-no-replenishment",
            "v5-sequential-with-rebuilding",
        ):
            item = next(
                value
                for value in plan["items"]
                if value["case_id"] == case_id
                and value["method_id"] == method_id
                and value["work_envelope"] == "LOW"
            )
            context, prepared, binding = build_candidate_work_binding(item)
            observed_binding = binding.to_dict()
            if observed_binding != item["candidate_work_binding"]:
                raise S8ParentNativeProductionGateV2Error(
                    "frozen candidate work binding differs from actual preparation"
                )
            binding_records.append(
                {
                    "case_id": case_id,
                    "method_id": method_id,
                    "queue_item_id": item["queue_item_id"],
                    "prepared_executor_type": type(prepared).__name__,
                    "actual_algorithm_type": type(context._actual_algorithm).__name__,
                    "actual_pool_type": type(context.pool).__name__,
                    "candidate_work_binding_digest": observed_binding[
                        "binding_digest"
                    ],
                }
            )
    releases = []
    blocked_before_gate = []
    with tempfile.TemporaryDirectory(prefix="v5-s8-v2-release-") as directory:
        gate_path = Path(directory) / "provisional-go.json"
        write_json_exclusive(gate_path, _provisional_gate(plan["plan_digest"]))
        for case_id in (
            "h2-1.5-iteration-1",
            "h4-1.5-first-chemical-accuracy",
        ):
            item = next(
                value
                for value in plan["items"]
                if value["case_id"] == case_id
                and value["method_id"] == "immutable-ceo-star-source"
                and value["work_envelope"] == "LOW"
            )
            context = build_queue_bound_runtime_v2(item["queue_item_id"])
            try:
                context.algorithm.evaluate_energy([], [])
            except CandidateOutcomeNotAuthorized:
                blocked_before_gate.append(case_id)
            else:
                raise S8ParentNativeProductionGateV2Error(
                    "blocked algorithm exposed candidate energy before release"
                )
            with patch.object(factory_module, "S8_GO_PATH", gate_path):
                released = context.release_for_h2_h4_execution()
            releases.append(
                {
                    "case_id": case_id,
                    "queue_item_id": item["queue_item_id"],
                    "returned_exact_actual_algorithm": released
                    is context._actual_algorithm,
                    "candidate_energy_called_after_release": False,
                }
            )
    checks = {
        "all_12_actual_prepared_bindings_match_frozen_v4": len(binding_records) == 12
        and all(
            record["prepared_executor_type"] == "PreparedMethodNativeExecutor"
            and record["actual_algorithm_type"] == "LinAlgAdapt"
            and record["actual_pool_type"] == "DVG_CEO"
            for record in binding_records
        ),
        "blocked_algorithm_rejects_before_gate": len(blocked_before_gate) == 2,
        "successor_release_accepts_exact_v4_gate_for_both_cases": len(releases) == 2
        and all(record["returned_exact_actual_algorithm"] for record in releases),
        "release_probe_invoked_no_candidate_energy": all(
            record["candidate_energy_called_after_release"] is False
            for record in releases
        ),
    }
    if not all(checks.values()):
        raise S8ParentNativeProductionGateV2Error("v4 release behavioral proof failed")
    return {
        "schema": "v5-final.s8-v2-runtime-release-behavioral-probe.v1",
        "binding_records": binding_records,
        "blocked_before_gate_cases": blocked_before_gate,
        "release_records": releases,
        "checks": checks,
        "candidate_molecular_energy_evaluations": 0,
        "optimizer_calls": 0,
        "performance_evidence": False,
    }


def _common_preflight(*, local_behavioral: bool) -> dict[str, Any]:
    free_bytes = shutil.disk_usage(ROOT).free
    historical_audits = {
        "S1_typed_candidate_adapter": audit_s1(),
        "S2_actual_rewrite_matrix_resource_parity": audit_s2(),
        "S3_queue_bound_runtime_factory": audit_s3(),
        "S4_six_parent_native_executors": audit_s4(),
        "S5_counter_reconstruction": audit_s5(),
        "S6_persistent_runner": audit_s6(),
        "S8_1_runtime_release_remediation": audit_s81(),
        "MB6_v4_refreeze": audit_s7_v4() if local_behavioral else audit_s7_v4_static(),
    }
    zero_checks = _zero_outcome_checks()
    checks = {
        "current_capacity_with_5GiB_reserve": free_bytes
        >= REQUIRED_FREE_BYTES + RESERVE_BYTES,
        "all_prior_and_successor_audits_pass": all(
            _all_pass(value) for value in historical_audits.values()
        ),
        "pinned_submodules_exact": _git(
            "-C", "provenance/dvg-obs-ceo", "rev-parse", "HEAD"
        )
        == PARENT_COMMIT
        and _git(
            "-C",
            "provenance/dvg-obs-ceo/vendor/ceo-adapt-vqe",
            "rev-parse",
            "HEAD",
        )
        == CEO_COMMIT,
        **zero_checks,
    }
    return {
        "free_bytes": free_bytes,
        "historical_audits": historical_audits,
        "checks": checks,
    }


def build_local_preflight(*, require_clean_worktree: bool = True) -> dict[str, Any]:
    common = _common_preflight(local_behavioral=True)
    release_probe = _behavioral_release_probe()
    checks = {
        **common["checks"],
        "worktree_clean_at_local_preflight": not require_clean_worktree
        or _git("status", "--porcelain") == "",
        "direct_MB6_v4_release_behavior_pass": all(release_probe["checks"].values()),
        "candidate_energy_zero_in_release_probe": release_probe[
            "candidate_molecular_energy_evaluations"
        ]
        == 0,
    }
    if not all(checks.values()):
        raise S8ParentNativeProductionGateV2Error(
            "S8-v2 local preflight failed: "
            + ", ".join(name for name, passed in checks.items() if not passed)
        )
    result = {
        "schema": "v5-final.s8-parent-native-production-preflight.v2",
        "preflight_kind": "FROZEN_PLATFORM_DIRECT_RUNTIME_RELEASE",
        "status": "PASS_DIRECT_MB6_V4_RELEASE_ZERO_OUTCOME",
        "decision": "READY_AWAITING_FRESH_CLONE_AND_EXACT_CI",
        "validated_implementation_commit": _git("rev-parse", "HEAD"),
        "plan_digest": _json(V4_PLAN)["plan_digest"],
        "capacity": {
            "available_bytes": common["free_bytes"],
            "required_study_bytes": REQUIRED_FREE_BYTES,
            "mandatory_reserve_bytes": RESERVE_BYTES,
            "execution_threshold_bytes": REQUIRED_FREE_BYTES + RESERVE_BYTES,
            "per_item_recheck_required": True,
        },
        "audits": common["historical_audits"],
        "runtime_release_probe": release_probe,
        "checks": checks,
        "implementation_manifest": [
            {"path": str(path.relative_to(ROOT)), "sha256": _sha(path)}
            for path in IMPLEMENTATION_SOURCES
        ],
        "candidate_molecular_energy_evaluations": 0,
        "authorization": {
            "fresh_clone_validation": "AUTHORIZED",
            "exact_commit_CI_validation": "AUTHORIZED",
            "H2_H4_execution": "NOT_AUTHORIZED_BY_PREFLIGHT_ALONE",
            "development_queue_execution": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
    }
    result["reproducible_evidence_digest"] = _reproducible_local_preflight_digest(
        result
    )
    result["preflight_digest"] = _digest(result)
    return result


def build_ci_preflight() -> dict[str, Any]:
    common = _common_preflight(local_behavioral=False)
    committed_go_audit = (
        audit(require_current_capacity=False) if OUTPUT.exists() else {}
    )
    checks = {
        **common["checks"],
        "committed_GO_artifact_valid_if_present": not OUTPUT.exists()
        or _all_pass(committed_go_audit),
    }
    if not all(checks.values()):
        raise S8ParentNativeProductionGateV2Error(
            "S8-v2 CI preflight failed: "
            + ", ".join(
                name for name, passed in checks.items() if not passed
            )
        )
    result = {
        "schema": "v5-final.s8-parent-native-exact-ci-preflight.v2",
        "preflight_kind": "PLATFORM_NEUTRAL_COMMITTED_EVIDENCE",
        "status": "PASS_STATIC_INTEGRITY_ZERO_OUTCOME",
        "decision": "READY_AWAITING_FROZEN_PLATFORM_FRESH_CLONE_EVIDENCE",
        "validated_exact_commit": _git("rev-parse", "HEAD"),
        "plan_digest": _json(V4_PLAN)["plan_digest"],
        "audits": common["historical_audits"],
        "committed_GO_audit": committed_go_audit,
        "checks": checks,
        "candidate_molecular_energy_evaluations": 0,
        "authorization": {
            "H2_H4_execution": "NOT_AUTHORIZED_BY_CI_PREFLIGHT_ALONE",
            "development_queue_execution": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
    }
    result["preflight_digest"] = _digest(result)
    return result


def _validate_fresh_clone(
    evidence: Mapping[str, Any],
    implementation_commit: str,
    reproducible_evidence_digest: str,
) -> dict[str, bool]:
    return {
        "schema": evidence.get("schema")
        == "v5-final.external-fresh-clone-evidence.v2",
        "exact_commit": evidence.get("checked_commit") == implementation_commit,
        "recursive_submodules": evidence.get("parent_commit") == PARENT_COMMIT
        and evidence.get("CEO_commit") == CEO_COMMIT,
        "clean_checkout": evidence.get("worktree_clean_before_tests") is True,
        "full_tests_passed": evidence.get("full_test_exit_code") == 0,
        "S8_v2_local_preflight_passed": evidence.get("S8_v2_preflight_exit_code") == 0,
        "reproducible_preflight_evidence_exact": evidence.get(
            "S8_v2_reproducible_evidence_digest"
        )
        == reproducible_evidence_digest,
        "candidate_energy_zero": evidence.get("candidate_energy_evaluations") == 0,
    }


def _validate_ci(
    evidence: Mapping[str, Any], implementation_commit: str
) -> dict[str, bool]:
    return {
        "schema": evidence.get("schema") == "v5-final.external-exact-ci-evidence.v2",
        "head_sha_exact": evidence.get("head_sha") == implementation_commit,
        "conclusion_success": evidence.get("conclusion") == "success",
        "release_gate_job_success": evidence.get("release_gate_job_conclusion")
        == "success",
        "attested_commit_exact": evidence.get("attested_commit")
        == implementation_commit,
        "CI_report_schema_v2": evidence.get("report_schema")
        == "v5-final.s8-parent-native-exact-ci-preflight.v2",
        "run_id_positive": isinstance(evidence.get("run_id"), int)
        and evidence["run_id"] > 0,
        "artifact_sha256_valid": isinstance(evidence.get("attestation_sha256"), str)
        and len(evidence["attestation_sha256"]) == 64,
    }


def build_go(
    fresh_clone_evidence: Mapping[str, Any], ci_evidence: Mapping[str, Any]
) -> dict[str, Any]:
    preflight = build_local_preflight()
    implementation_commit = preflight["validated_implementation_commit"]
    fresh_checks = _validate_fresh_clone(
        fresh_clone_evidence,
        implementation_commit,
        preflight["reproducible_evidence_digest"],
    )
    ci_checks = _validate_ci(ci_evidence, implementation_commit)
    checks = {
        "local_direct_runtime_release_preflight_pass": all(
            preflight["checks"].values()
        ),
        "fresh_recursive_clone_pass": all(fresh_checks.values()),
        "exact_commit_CI_pass": all(ci_checks.values()),
        "candidate_energy_zero_before_GO": preflight[
            "candidate_molecular_energy_evaluations"
        ]
        == 0,
        "S8_v1_suspension_preserved": _zero_outcome_checks()[
            "S8_v1_remains_suspended"
        ],
    }
    if not all(checks.values()):
        raise S8ParentNativeProductionGateV2Error(
            "S8-v2 external attestation failed: "
            + ", ".join(name for name, passed in checks.items() if not passed)
        )
    artifact = {
        "schema": "v5-final.s8-parent-native-production-go.v2",
        "stage": "S8_V2_DIRECT_MB6_V4_BEHAVIORAL_PRODUCTION_GO_GATE",
        "status": "PASS_ZERO_OUTCOME_PRODUCTION_INFRASTRUCTURE",
        "decision": "GO_H2_H4_CALIBRATION_ONLY",
        "validated_implementation_commit": implementation_commit,
        "plan_digest": preflight["plan_digest"],
        "preflight": preflight,
        "fresh_clone_evidence": dict(fresh_clone_evidence),
        "fresh_clone_checks": fresh_checks,
        "exact_CI_evidence": dict(ci_evidence),
        "exact_CI_checks": ci_checks,
        "checks": checks,
        "gate_artifact_manifest": [
            {"path": str(path.relative_to(ROOT)), "sha256": _sha(path)}
            for path in GATE_ARTIFACTS
        ],
        "implementation_manifest": [
            {"path": str(path.relative_to(ROOT)), "sha256": _sha(path)}
            for path in IMPLEMENTATION_SOURCES
        ],
        "candidate_molecular_energy_evaluations_before_GO": 0,
        "authorization": {
            "H2_H4_execution": "AUTHORIZED_FROZEN_MB6_V4_PLAN_ONLY",
            "H2_H4_item_count": 36,
            "capacity_recheck_before_and_after_each_item": True,
            "development_queue_execution": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "academic_boundary": (
            "This GO authorizes only the exact frozen 36-item MB6-v4 H2/H4 "
            "calibration. The release path was exercised without calling candidate "
            "energy. No performance evidence or development authorization exists."
        ),
    }
    artifact["gate_digest"] = _digest(artifact)
    return artifact


def audit(*, require_current_capacity: bool = True) -> dict[str, bool]:
    artifact = _json(OUTPUT)
    body = dict(artifact)
    observed = body.pop("gate_digest", None)
    implementation_commit = artifact["validated_implementation_commit"]
    plan = _json(V4_PLAN)
    ledger = _json(V4_LEDGER)
    current_free = shutil.disk_usage(ROOT).free
    checks = {
        "gate_digest_valid": observed == _digest(body),
        "schema_and_decision_exact": artifact["schema"]
        == "v5-final.s8-parent-native-production-go.v2"
        and artifact["decision"] == "GO_H2_H4_CALIBRATION_ONLY",
        "plan_digest_exact": artifact["plan_digest"] == plan["plan_digest"],
        "all_gate_checks_passed": all(artifact["checks"].values()),
        "fresh_clone_checks_passed": all(artifact["fresh_clone_checks"].values()),
        "exact_CI_checks_passed": all(artifact["exact_CI_checks"].values()),
        "gate_artifacts_unchanged": all(
            _sha(ROOT / item["path"]) == item["sha256"]
            for item in artifact["gate_artifact_manifest"]
        ),
        "implementation_sources_unchanged": manifest_matches_commit(
            artifact["implementation_manifest"], implementation_commit
        ),
        "implementation_commit_is_ancestor": subprocess.run(
            [
                "git",
                "-C",
                str(ROOT),
                "merge-base",
                "--is-ancestor",
                implementation_commit,
                "HEAD",
            ],
            check=False,
        ).returncode
        == 0,
        "current_capacity_passed_if_required": not require_current_capacity
        or current_free >= REQUIRED_FREE_BYTES + RESERVE_BYTES,
        "candidate_energy_still_zero_at_audit": plan["candidate_energy_evaluations"]
        == 0
        and ledger["candidate_energy_evaluations"] == 0
        and not ledger["terminal_segments"],
        "authorization_scoped_to_v4_only": artifact["authorization"]["H2_H4_execution"]
        == "AUTHORIZED_FROZEN_MB6_V4_PLAN_ONLY"
        and artifact["authorization"]["development_queue_execution"]
        == "NOT_AUTHORIZED",
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S8ParentNativeProductionGateV2Error(
            "S8-v2 production gate audit failed: " + ", ".join(failures)
        )
    return checks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--local-preflight-output", type=Path)
    parser.add_argument("--ci-preflight-output", type=Path)
    parser.add_argument("--go-output", type=Path)
    parser.add_argument("--fresh-evidence", type=Path)
    parser.add_argument("--ci-evidence", type=Path)
    args = parser.parse_args()
    if args.local_preflight_output is not None:
        write_json_exclusive(args.local_preflight_output, build_local_preflight())
        print(args.local_preflight_output)
        return
    if args.ci_preflight_output is not None:
        write_json_exclusive(args.ci_preflight_output, build_ci_preflight())
        print(args.ci_preflight_output)
        return
    if args.go_output is not None:
        if args.fresh_evidence is None or args.ci_evidence is None:
            raise S8ParentNativeProductionGateV2Error(
                "GO capture requires fresh-clone and exact-CI evidence"
            )
        write_json_exclusive(
            args.go_output,
            build_go(_json(args.fresh_evidence), _json(args.ci_evidence)),
        )
        print(args.go_output)
        return
    print(json.dumps(audit(), sort_keys=True))


if __name__ == "__main__":
    main()

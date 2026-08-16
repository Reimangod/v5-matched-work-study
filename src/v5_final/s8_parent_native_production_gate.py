"""Behavioral S8 production gate for H2/H4 calibration only."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from typing import Any, Mapping

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .p0_capacity_success_v3 import REQUIRED_FREE_BYTES, RESERVE_BYTES
from .s0_successor import CEO_COMMIT, PARENT_COMMIT, ROOT
from .s1_parent_native_adapter_audit import audit as audit_s1
from .s2_parent_native_rewrite_audit import audit as audit_s2
from .s3_parent_native_runtime_factory_audit import audit as audit_s3
from .s4_parent_native_executors_audit import audit as audit_s4
from .s5_parent_native_work_accounting_audit import audit as audit_s5
from .s6_parent_native_persistent_runner_audit import audit as audit_s6
from .s7_mb6_v3_refreeze import audit as audit_s7


OUTPUT = ROOT / "artifacts/v5-final/parent-native/s8-production-go-v1.json"
S7_DIR = ROOT / "artifacts/v5-final/parent-native/mb6-v3"
S7_PLAN = S7_DIR / "h2-h4-calibration-plan-v3.json"
S7_LEDGER = S7_DIR / "h2-h4-calibration-ledger-root-v3.json"
S7_FREEZE = S7_DIR / "mb6-outcome-blind-freeze-v3.json"
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
        "artifacts/v5-final/parent-native/mb6-v3/mb6-outcome-blind-freeze-v3.json",
    )
)


class S8ParentNativeProductionGateError(RuntimeError):
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


def _all_pass(values: Mapping[str, bool]) -> bool:
    return bool(values) and all(values.values())


def build_preflight() -> dict[str, Any]:
    plan = _json(S7_PLAN)
    ledger = _json(S7_LEDGER)
    freeze = _json(S7_FREEZE)
    development = _json(DEVELOPMENT_PLAN)
    development_ledger = _json(DEVELOPMENT_LEDGER)
    free_bytes = shutil.disk_usage(ROOT).free
    audits = {
        "S1_typed_candidate_adapter": audit_s1(),
        "S2_actual_rewrite_matrix_resource_parity": audit_s2(),
        "S3_queue_bound_runtime_factory": audit_s3(),
        "S4_six_parent_native_executors": audit_s4(),
        "S5_counter_reconstruction": audit_s5(),
        "S6_persistent_runner": audit_s6(),
        "S7_outcome_blind_MB6_v3_refreeze": audit_s7(),
    }
    checks = {
        "current_capacity_with_5GiB_reserve": free_bytes
        >= REQUIRED_FREE_BYTES + RESERVE_BYTES,
        "all_behavioral_audits_pass": all(_all_pass(value) for value in audits.values()),
        "typed_candidate_adapter_pass": _all_pass(audits["S1_typed_candidate_adapter"]),
        "actual_rewrite_applied": _all_pass(
            audits["S2_actual_rewrite_matrix_resource_parity"]
        ),
        "actual_matrices_verified": _all_pass(
            audits["S2_actual_rewrite_matrix_resource_parity"]
        ),
        "actual_resource_parity_pass": _all_pass(
            audits["S2_actual_rewrite_matrix_resource_parity"]
        ),
        "queue_bound_factory_pass": _all_pass(
            audits["S3_queue_bound_runtime_factory"]
        ),
        "six_method_native_semantics_pass": _all_pass(
            audits["S4_six_parent_native_executors"]
        ),
        "counter_reconstruction_pass": _all_pass(
            audits["S5_counter_reconstruction"]
        ),
        "persistent_runner_pass": _all_pass(audits["S6_persistent_runner"]),
        "MB6_v3_frozen_exact_36": len(plan["items"]) == 36
        and len({item["queue_item_id"] for item in plan["items"]}) == 36
        and freeze["decision"] == "GO_S8_BEHAVIORAL_PRODUCTION_GATE_ONLY",
        "calibration_unstarted": all(
            item["terminal_status"] == "NOT_STARTED" for item in plan["items"]
        )
        and not ledger["completed_queue_item_ids"]
        and not ledger["raw_ledger_directories"]
        and not ledger["terminal_segments"],
        "development_90_unstarted": development["expected_queue_count"] == 90
        and all(item["terminal_status"] == "NOT_STARTED" for item in development["items"])
        and not development_ledger["segments"],
        "candidate_energy_zero_before_GO": plan["candidate_energy_evaluations"] == 0
        and ledger["candidate_energy_evaluations"] == 0
        and development_ledger["development_candidate_energy_evaluations"] == 0,
        "pinned_submodules_exact": _git("-C", "provenance/dvg-obs-ceo", "rev-parse", "HEAD")
        == PARENT_COMMIT
        and _git(
            "-C",
            "provenance/dvg-obs-ceo/vendor/ceo-adapt-vqe",
            "rev-parse",
            "HEAD",
        )
        == CEO_COMMIT,
    }
    if not all(checks.values()):
        raise S8ParentNativeProductionGateError(
            "S8 static behavioral preflight failed: "
            + ", ".join(name for name, passed in checks.items() if not passed)
        )
    result = {
        "schema": "v5-final.s8-parent-native-production-preflight.v1",
        "status": "PASS_STATIC_BEHAVIORAL_GATES_ZERO_OUTCOME",
        "decision": "READY_AWAITING_FRESH_CLONE_AND_EXACT_CI",
        "validated_implementation_commit": _git("rev-parse", "HEAD"),
        "capacity": {
            "available_bytes": free_bytes,
            "required_study_bytes": REQUIRED_FREE_BYTES,
            "mandatory_reserve_bytes": RESERVE_BYTES,
            "execution_threshold_bytes": REQUIRED_FREE_BYTES + RESERVE_BYTES,
            "per_item_recheck_required": True,
        },
        "audits": audits,
        "checks": checks,
        "candidate_molecular_energy_evaluations": 0,
        "authorization": {
            "fresh_clone_validation": "AUTHORIZED",
            "exact_commit_CI_validation": "AUTHORIZED",
            "H2_H4_execution": "NOT_AUTHORIZED_BY_PREFLIGHT_ALONE",
            "development_queue_execution": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
    }
    result["preflight_digest"] = _digest(result)
    return result


def _validate_fresh_clone(
    evidence: Mapping[str, Any], implementation_commit: str
) -> dict[str, bool]:
    return {
        "schema": evidence.get("schema")
        == "v5-final.external-fresh-clone-evidence.v1",
        "exact_commit": evidence.get("checked_commit") == implementation_commit,
        "recursive_submodules": evidence.get("parent_commit") == PARENT_COMMIT
        and evidence.get("CEO_commit") == CEO_COMMIT,
        "clean_checkout": evidence.get("worktree_clean_before_tests") is True,
        "full_tests_passed": evidence.get("full_test_exit_code") == 0,
        "S8_preflight_passed": evidence.get("S8_preflight_exit_code") == 0,
        "candidate_energy_zero": evidence.get("candidate_energy_evaluations") == 0,
    }


def _validate_ci(
    evidence: Mapping[str, Any], implementation_commit: str
) -> dict[str, bool]:
    return {
        "schema": evidence.get("schema") == "v5-final.external-exact-ci-evidence.v1",
        "head_sha_exact": evidence.get("head_sha") == implementation_commit,
        "conclusion_success": evidence.get("conclusion") == "success",
        "release_gate_job_success": evidence.get("release_gate_job_conclusion")
        == "success",
        "attested_commit_exact": evidence.get("attested_commit")
        == implementation_commit,
        "run_id_positive": isinstance(evidence.get("run_id"), int)
        and evidence["run_id"] > 0,
        "artifact_sha256_valid": isinstance(evidence.get("attestation_sha256"), str)
        and len(evidence["attestation_sha256"]) == 64,
    }


def build_go(
    fresh_clone_evidence: Mapping[str, Any],
    ci_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    preflight = build_preflight()
    implementation_commit = preflight["validated_implementation_commit"]
    fresh_checks = _validate_fresh_clone(fresh_clone_evidence, implementation_commit)
    ci_checks = _validate_ci(ci_evidence, implementation_commit)
    external_checks = {
        "fresh_clone_pass": all(fresh_checks.values()),
        "exact_commit_CI_pass": all(ci_checks.values()),
    }
    if not all(external_checks.values()):
        raise S8ParentNativeProductionGateError(
            "S8 external attestation failed: "
            + ", ".join(
                name for name, passed in external_checks.items() if not passed
            )
        )
    artifact: dict[str, Any] = {
        "schema": "v5-final.s8-parent-native-production-go.v1",
        "stage": "S8_BEHAVIORAL_PRODUCTION_GO_GATE",
        "status": "PASS_ZERO_OUTCOME_PRODUCTION_INFRASTRUCTURE",
        "decision": "GO_H2_H4_CALIBRATION_ONLY",
        "validated_implementation_commit": implementation_commit,
        "preflight": preflight,
        "fresh_clone_evidence": dict(fresh_clone_evidence),
        "fresh_clone_checks": fresh_checks,
        "exact_CI_evidence": dict(ci_evidence),
        "exact_CI_checks": ci_checks,
        "external_checks": external_checks,
        "gate_artifact_manifest": [
            {"path": str(path.relative_to(ROOT)), "sha256": _sha(path)}
            for path in GATE_ARTIFACTS
        ],
        "candidate_molecular_energy_evaluations_before_GO": 0,
        "authorization": {
            "H2_H4_execution": "AUTHORIZED_FROZEN_MB6_V3_PLAN_ONLY",
            "H2_H4_item_count": 36,
            "capacity_recheck_before_and_after_each_item": True,
            "development_queue_execution": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "academic_boundary": (
            "This GO authorizes only the frozen 36-item H2/H4 calibration plan. "
            "It is based exclusively on zero-outcome infrastructure, structural, "
            "persistence, fresh-clone, and exact-CI evidence. It makes no performance claim."
        ),
    }
    artifact["gate_digest"] = _digest(artifact)
    return artifact


def audit(*, require_current_capacity: bool = True) -> dict[str, bool]:
    artifact = _json(OUTPUT)
    body = dict(artifact)
    observed = body.pop("gate_digest", None)
    implementation_commit = artifact["validated_implementation_commit"]
    plan = _json(S7_PLAN)
    ledger = _json(S7_LEDGER)
    current_free = shutil.disk_usage(ROOT).free
    checks = {
        "gate_digest_valid": observed == _digest(body),
        "decision_exact": artifact["decision"] == "GO_H2_H4_CALIBRATION_ONLY",
        "preflight_digest_valid": artifact["preflight"]["preflight_digest"]
        == _digest(
            {
                key: value
                for key, value in artifact["preflight"].items()
                if key != "preflight_digest"
            }
        ),
        "all_static_checks_passed": all(artifact["preflight"]["checks"].values()),
        "fresh_clone_checks_passed": all(artifact["fresh_clone_checks"].values()),
        "exact_CI_checks_passed": all(artifact["exact_CI_checks"].values()),
        "external_checks_passed": all(artifact["external_checks"].values()),
        "gate_artifacts_unchanged": all(
            _sha(ROOT / item["path"]) == item["sha256"]
            for item in artifact["gate_artifact_manifest"]
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
        "development_still_blocked": artifact["authorization"][
            "development_queue_execution"
        ]
        == "NOT_AUTHORIZED",
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S8ParentNativeProductionGateError(
            "S8 production gate audit failed: " + ", ".join(failures)
        )
    return checks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight-output", type=Path)
    parser.add_argument("--go-output", type=Path)
    parser.add_argument("--fresh-evidence", type=Path)
    parser.add_argument("--ci-evidence", type=Path)
    args = parser.parse_args()
    if args.preflight_output is not None:
        write_json_exclusive(args.preflight_output, build_preflight())
        print(args.preflight_output)
        return
    if args.go_output is not None:
        if args.fresh_evidence is None or args.ci_evidence is None:
            raise S8ParentNativeProductionGateError(
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

"""Outcome-free audit closing the S8-v1 MB6-v3 runtime-release gap."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
from typing import Any

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .s0_successor import CEO_COMMIT, PARENT_COMMIT, ROOT


OUTPUT = ROOT / "artifacts/v5-final/parent-native/s8-1-runtime-release-remediation-v1.json"
PARENT_PYTHON = ROOT / "provenance/dvg-obs-ceo/.venv/bin/python"
IMPLEMENTATION = tuple(
    ROOT / value
    for value in (
        "src/v5_final/parent_native_runtime_factory_v2.py",
        "src/v5_final/parent_native_candidate_work_bindings.py",
        "src/v5_final/parent_native_execution_services.py",
        "src/v5_final/parent_native_execution_control_probe.py",
        "src/v5_final/parent_native_execution_services_probe.py",
    )
)
FROZEN_INPUTS = tuple(
    ROOT / value
    for value in (
        "artifacts/v5-final/parent-native/s8-production-go-v1-suspension.json",
        "artifacts/v5-final/parent-native/mb6-v3/h2-h4-calibration-plan-v3.json",
        "artifacts/v5-final/parent-native/mb6-v3/execution-environment-v3.json",
        "artifacts/v5-final/parent-native/s4-parent-native-executors-v1.json",
        "artifacts/v5-final/parent-native/s6-parent-native-persistent-runner-v1.json",
    )
)


class S81RuntimeReleaseRemediationError(RuntimeError):
    pass


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _probe() -> dict[str, Any]:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        (
            str(ROOT / "src"),
            str(ROOT / "provenance/dvg-obs-ceo/src"),
            str(ROOT / "provenance/dvg-obs-ceo/vendor/ceo-adapt-vqe"),
        )
    )
    for name in ("MKL_NUM_THREADS", "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
        environment[name] = "2"
    completed = subprocess.run(
        [
            str(PARENT_PYTHON),
            "-m",
            "v5_final.parent_native_execution_services_probe",
        ],
        cwd=ROOT,
        env=environment,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return json.loads(completed.stdout)


def build() -> dict[str, Any]:
    probe = _probe()
    records = probe["records"]
    methods = {record["method_id"] for record in records}
    cases = {record["case_id"] for record in records}
    by_key = {(record["case_id"], record["method_id"]): record for record in records}
    h4 = "h4-1.5-first-chemical-accuracy"
    checks = {
        "actual_v3_factory_builds_both_cases_for_six_methods": len(records) == 12
        and len(by_key) == 12
        and len(methods) == 6
        and len(cases) == 2
        and all(record["actual_algorithm_type"] == "LinAlgAdapt" for record in records)
        and all(record["actual_pool_type"] == "DVG_CEO" for record in records),
        "prepared_executor_bound": all(
            record["prepared_executor_type"] == "PreparedMethodNativeExecutor"
            for record in records
        ),
        "candidate_generation_is_intent_count": by_key[
            (h4, "v5-sequential-with-rebuilding")
        ]["candidate_work_binding"]["candidate_generation_count"]
        == 20,
        "physical_search_states_semantically_deduplicated": by_key[
            (h4, "v5-sequential-with-rebuilding")
        ]["candidate_work_binding"]["unique_search_state_count"]
        == 16,
        "source_frozen_whitelist_has_position_independent_keys": len(
            by_key[(h4, "v5-fixed-source-whitelist-no-replenishment")][
                "candidate_work_binding"
            ]["source_whitelist_keys"]
        )
        == 20,
        "dynamic_work_has_outcome_blind_source_upper_bound": by_key[
            (h4, "v5-sequential-with-rebuilding")
        ]["candidate_work_binding"]["dynamic_catalog_generation_upper_bound"]
        == 20,
        "six_control_flows_behaviorally_distinct": all(
            probe["outcome_free_control_flow"]["checks"].values()
        )
        and probe["outcome_free_control_flow"][
            "scientific_candidate_energy_evaluations"
        ]
        == 0,
        "durable_outcome_checkpoint_recovers_without_kernel_rerun": (
            probe["outcome_free_control_flow"]["outcome_checkpoint_recovery"][
                "checkpoint_before_terminal_recovered_without_kernel_rerun"
            ]
            and probe["outcome_free_control_flow"]["outcome_checkpoint_recovery"][
                "outcome_digest_bound"
            ]
            and probe["outcome_free_control_flow"]["outcome_checkpoint_recovery"][
                "molecular_candidate_energy_events"
            ]
            == 0
        ),
        "six_execution_service_surface_bound": (
            probe["service_bindings"]["durable_boundary"] == "DurableWorkBoundary"
            and probe["service_bindings"]["actual_optimization_boundary"]
            == "ActualOptimizationBoundary"
            and "PreparedMethodNativeExecutor"
            in probe["service_bindings"]["prepared_execute_signature"]
            and "raw_ledger_root" in probe["service_bindings"][
                "production_entrypoint_signature"
            ]
        ),
        "outcome_gate_not_crossed": all(
            record["release_called"] is False for record in records
        )
        and probe["candidate_molecular_energy_evaluations"] == 0
        and probe["optimizer_calls"] == 0
        and probe["H2_H4_queue_executed"] is False
        and probe["performance_evidence"] is False,
    }
    if not all(checks.values()):
        raise S81RuntimeReleaseRemediationError("S8.1 remediation proof failed")
    artifact = {
        "schema": "v5-final.s8-1-runtime-release-remediation-audit.v1",
        "stage": "S8_1_PRE_OUTCOME_RUNTIME_RELEASE_REMEDIATION",
        "status": "PASS_ACTUAL_MB6_V3_CONSTRUCTION_EXECUTION_STILL_BLOCKED",
        "decision": "GO_MB6_V4_EXECUTOR_REFREEZE_ONLY",
        "pinned_commits": {"parent": PARENT_COMMIT, "CEO": CEO_COMMIT},
        "implementation_manifest": [
            {"path": str(path.relative_to(ROOT)), "sha256": _sha(path)}
            for path in IMPLEMENTATION
        ],
        "frozen_input_manifest": [
            {"path": str(path.relative_to(ROOT)), "sha256": _sha(path)}
            for path in FROZEN_INPUTS
        ],
        "probe": probe,
        "checks": checks,
        "authorization": {
            "MB6_v4_executor_refreeze": "AUTHORIZED_OUTCOME_FREE_ONLY",
            "molecular_candidate_energy": "NOT_AUTHORIZED",
            "H2_H4_execution": "NOT_AUTHORIZED",
            "development_queue_execution": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "academic_boundary": (
            "Both molecular sources and all six prepared executors were built from "
            "the frozen MB6-v3 plan, but release_for_h2_h4_execution was never called. "
            "No optimizer, candidate energy, or performance result exists."
        ),
    }
    artifact["audit_digest"] = _digest(artifact)
    return artifact


def verify(record: dict[str, Any]) -> dict[str, bool]:
    body = dict(record)
    observed = body.pop("audit_digest", None)
    return {
        "audit_digest_valid": observed == _digest(body),
        "implementation_unchanged": all(
            _sha(ROOT / item["path"]) == item["sha256"]
            for item in record["implementation_manifest"]
        ),
        "frozen_inputs_unchanged": all(
            _sha(ROOT / item["path"]) == item["sha256"]
            for item in record["frozen_input_manifest"]
        ),
        "all_checks_passed": all(record["checks"].values()),
        "decision_scoped": record["decision"]
        == "GO_MB6_V4_EXECUTOR_REFREEZE_ONLY",
        "candidate_energy_zero": record["probe"][
            "candidate_molecular_energy_evaluations"
        ]
        == 0,
        "H2_H4_blocked": record["authorization"]["H2_H4_execution"]
        == "NOT_AUTHORIZED",
    }


def audit() -> dict[str, bool]:
    record = json.loads(OUTPUT.read_text())
    checks = verify(record)
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S81RuntimeReleaseRemediationError(
            "S8.1 audit failed: " + ", ".join(failures)
        )
    return checks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.output is None:
        print(json.dumps(audit(), sort_keys=True))
    else:
        write_json_exclusive(args.output, build())
        print(args.output)


if __name__ == "__main__":
    main()

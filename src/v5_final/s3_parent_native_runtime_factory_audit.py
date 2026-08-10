"""S3 outcome-free audit of the queue-bound molecular runtime factory."""

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


OUTPUT = ROOT / "artifacts/v5-final/parent-native/s3-parent-native-runtime-factory-v1.json"
PARENT_PYTHON = ROOT / "provenance/dvg-obs-ceo/.venv/bin/python"
CATALOG = ROOT / "artifacts/v5-final/mb6-v2/h2-h4-source-catalog-v2.json"
QUEUE = ROOT / "artifacts/v5-final/mb6-v2/h2-h4-calibration-queue-v2.json"
ENVIRONMENT = ROOT / "artifacts/v5-final/mb6-v2/execution-environment-v2.json"
PRIMARY_SOURCES = (
    ROOT / "provenance/dvg-obs-ceo/src/dvg_obs_ceo/molecular_identity.py",
    ROOT / "provenance/dvg-obs-ceo/src/dvg_obs_ceo/resources.py",
    ROOT / "provenance/dvg-obs-ceo/src/dvg_obs_ceo/transaction.py",
    ROOT / "provenance/dvg-obs-ceo/vendor/ceo-adapt-vqe/adaptvqe/algorithms/adapt_vqe.py",
    ROOT / "provenance/dvg-obs-ceo/vendor/ceo-adapt-vqe/adaptvqe/molecules.py",
)
IMPLEMENTATION = (
    ROOT / "src/v5_final/parent_native_runtime_factory.py",
    ROOT / "src/v5_final/parent_native_runtime_environment_probe.py",
    ROOT / "src/v5_final/parent_native_runtime_factory_probe.py",
)
FROZEN_INPUTS = (
    CATALOG,
    QUEUE,
    ENVIRONMENT,
    ROOT / "provenance/dvg-obs-ceo/artifacts/s8/calibration-bundle/checkpoint-h2-1.5-iteration-1.json",
    ROOT / "provenance/dvg-obs-ceo/artifacts/s8/calibration-bundle/checkpoint-h4-1.5-first-chemical-accuracy.json",
    ROOT / "uv.lock",
    ROOT / "provenance/dvg-obs-ceo/uv.lock",
)


class S3ParentNativeRuntimeFactoryError(RuntimeError):
    pass


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _run_probe(module: str, *, threads: int) -> dict[str, Any]:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        (
            str(ROOT / "src"),
            str(ROOT / "provenance/dvg-obs-ceo/src"),
            str(ROOT / "provenance/dvg-obs-ceo/vendor/ceo-adapt-vqe"),
        )
    )
    for name in ("MKL_NUM_THREADS", "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
        environment[name] = str(threads)
    completed = subprocess.run(
        [str(PARENT_PYTHON), "-m", module],
        cwd=ROOT,
        env=environment,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return json.loads(completed.stdout)


def _all_zero(value: dict[str, Any]) -> bool:
    return all(count == 0 for count in value.values())


def build() -> dict[str, Any]:
    one_thread = _run_probe(
        "v5_final.parent_native_runtime_environment_probe", threads=1
    )
    two_thread_first = _run_probe(
        "v5_final.parent_native_runtime_environment_probe", threads=2
    )
    two_thread_second = _run_probe(
        "v5_final.parent_native_runtime_environment_probe", threads=2
    )
    factory = _run_probe(
        "v5_final.parent_native_runtime_factory_probe", threads=2
    )
    one_by_case = {case["case_id"]: case for case in one_thread["cases"]}
    correction = two_thread_first["corrected_environment"]
    cases = factory["cases"]
    checks = {
        "v2_single_thread_H4_identity_bug_reproduced": (
            one_by_case["h2-1.5-iteration-1"]["exact_match"] is True
            and one_by_case["h4-1.5-first-chemical-accuracy"]["exact_match"]
            is False
        ),
        "corrected_environment_changes_threads_only": (
            correction["required_threads"]
            == {
                "MKL_NUM_THREADS": "2",
                "OMP_NUM_THREADS": "2",
                "OPENBLAS_NUM_THREADS": "2",
            }
            and correction["correction_provenance"]["allowed_change"]
            == "required thread counts only"
            and correction["correction_provenance"]["scientific_protocol_changed"]
            is False
        ),
        "two_thread_problem_identities_exact_and_repeatable": (
            two_thread_first == two_thread_second
            and all(case["exact_match"] for case in two_thread_first["cases"])
        ),
        "environment_probes_outcome_free": (
            one_thread["candidate_energy_evaluations"] == 0
            and two_thread_first["candidate_energy_evaluations"] == 0
            and _all_zero(one_thread["molecular_kernel_guard_calls"])
            and _all_zero(two_thread_first["molecular_kernel_guard_calls"])
        ),
        "actual_parent_types_for_H2_H4": (
            {case["case_id"] for case in cases}
            == {
                "h2-1.5-iteration-1",
                "h4-1.5-first-chemical-accuracy",
            }
            and all(case["actual_algorithm_type"] == "LinAlgAdapt" for case in cases)
            and all(case["actual_pool_type"] == "DVG_CEO" for case in cases)
            and all(case["actual_runtime_type"] == "CompressionRuntime" for case in cases)
        ),
        "all_frozen_identities_and_dimensions_match": all(
            case["ProblemID"].startswith("problem-v1:")
            and case["StatePreparationID"].startswith("state-v1:")
            and len(case["Hamiltonian_digest"]) == 64
            and case["ansatz_dimension"] == case["gradient_dimension"]
            == case["inverse_hessian_dimension"]
            for case in cases
        ),
        "source_checkpoint_and_state_reconstructed": (
            factory["source_statevector_recomputations"] == 2
            and all(case["source_statevector_recomputations"] == 1 for case in cases)
            and all(len(case["source_checkpoint_digest"]) == 64 for case in cases)
            and all(len(case["source_statevector_sha256"]) == 64 for case in cases)
        ),
        "pre_GO_algorithm_guard_active": all(
            case["pre_GO_algorithm_guard_verified"] is True for case in cases
        ),
        "queue_and_checkpoint_tamper_rejected_pre_algorithm": all(
            factory["negative_preflight"].values()
        ),
        "FCI_CCSD_candidate_energy_optimizer_zero": (
            all(case["FCI_used"] is False and case["CCSD_used"] is False for case in cases)
            and factory["candidate_energy_evaluations"] == 0
            and factory["optimizer_calls"] == 0
            and _all_zero(factory["candidate_kernel_calls"])
        ),
        "projection_not_written_or_authorized": (
            factory["projected_queue_written_or_authorized"] is False
        ),
    }
    if not all(checks.values()):
        raise S3ParentNativeRuntimeFactoryError("S3 runtime factory checks failed")
    artifact: dict[str, Any] = {
        "schema": "v5-final.s3-parent-native-runtime-factory-audit.v1",
        "stage": "S3_QUEUE_BOUND_MOLECULAR_RUNTIME_FACTORY",
        "status": "PASS_OUTCOME_FREE_WITH_ADDITIVE_ENVIRONMENT_CORRECTION",
        "decision": "GO_S4_METHOD_NATIVE_EXECUTORS_ONLY",
        "pinned_commits": {"parent": PARENT_COMMIT, "CEO": CEO_COMMIT},
        "primary_source_manifest": [
            {"path": str(path.relative_to(ROOT)), "sha256": _sha(path)}
            for path in PRIMARY_SOURCES
        ],
        "implementation_manifest": [
            {"path": str(path.relative_to(ROOT)), "sha256": _sha(path)}
            for path in IMPLEMENTATION
        ],
        "frozen_input_manifest": [
            {"path": str(path.relative_to(ROOT)), "sha256": _sha(path)}
            for path in FROZEN_INPUTS
        ],
        "environment_correction": correction,
        "environment_identity_evidence": {
            "single_thread": one_thread,
            "two_thread": two_thread_first,
            "two_thread_rebuild_byte_identical": two_thread_first
            == two_thread_second,
        },
        "factory_probe": factory,
        "checks": checks,
        "authorization": {
            "S4_outcome_free_method_native_executor_implementation": "AUTHORIZED",
            "MB6_v3_freeze": "NOT_AUTHORIZED_BEFORE_S4_S6",
            "molecular_candidate_energy": "NOT_AUTHORIZED",
            "H2_H4_execution": "NOT_AUTHORIZED",
            "development_queue_execution": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "academic_boundary": (
            "The immutable MB6-v2 environment incorrectly states one thread for its "
            "frozen H4 Hamiltonian identity. Two explicit threads reproduce both "
            "frozen ProblemIDs exactly and repeatedly without FCI, CCSD, candidate "
            "energy, or optimizer calls. The correction is additive and may only be "
            "bound by the later outcome-blind MB6-v3 successor freeze."
        ),
    }
    artifact["audit_digest"] = _digest(artifact)
    return artifact


def verify(record: dict[str, Any]) -> dict[str, bool]:
    body = dict(record)
    observed = body.pop("audit_digest", None)
    correction = record["environment_correction"]
    correction_body = dict(correction)
    correction_digest = correction_body.pop("environment_digest", None)
    return {
        "audit_digest_valid": observed == _digest(body),
        "environment_correction_digest_valid": correction_digest
        == _digest(correction_body),
        "primary_sources_unchanged": all(
            _sha(ROOT / item["path"]) == item["sha256"]
            for item in record["primary_source_manifest"]
        ),
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
        == "GO_S4_METHOD_NATIVE_EXECUTORS_ONLY",
        "candidate_energy_zero": record["factory_probe"][
            "candidate_energy_evaluations"
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
        raise S3ParentNativeRuntimeFactoryError(
            "S3 audit failed: " + ", ".join(failures)
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

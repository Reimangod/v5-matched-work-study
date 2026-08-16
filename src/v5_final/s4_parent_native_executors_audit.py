"""S4 outcome-free audit of all six actual parent-native executors."""

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


OUTPUT = ROOT / "artifacts/v5-final/parent-native/s4-parent-native-executors-v1.json"
PARENT_PYTHON = ROOT / "provenance/dvg-obs-ceo/.venv/bin/python"
PRIMARY_SOURCES = tuple(
    ROOT / value
    for value in (
        "provenance/dvg-obs-ceo/src/dvg_obs_ceo/block_ir.py",
        "provenance/dvg-obs-ceo/src/dvg_obs_ceo/composition.py",
        "provenance/dvg-obs-ceo/src/dvg_obs_ceo/calibration.py",
        "provenance/dvg-obs-ceo/src/dvg_obs_ceo/resources.py",
        "provenance/dvg-obs-ceo/src/dvg_obs_ceo/v5_pareto.py",
        "provenance/dvg-obs-ceo/src/dvg_obs_ceo/transaction.py",
        "provenance/dvg-obs-ceo/src/dvg_obs_ceo/v5_nested_transaction.py",
        "provenance/dvg-obs-ceo/vendor/ceo-adapt-vqe/adaptvqe/minimize.py",
    )
)
IMPLEMENTATION = tuple(
    ROOT / value
    for value in (
        "src/v5_final/parent_native_physical_identity.py",
        "src/v5_final/parent_native_executors.py",
        "src/v5_final/parent_native_executors_probe.py",
    )
)
FROZEN_INPUTS = tuple(
    ROOT / value
    for value in (
        "artifacts/v5-final/method-native/mb4-1-protocol-drafts-v2.json",
        "artifacts/v5-final/method-native/mb4-2-owner-protocol-freeze-v1.json",
        "artifacts/v5-final/mb6-v2/h2-h4-source-catalog-v2.json",
        "artifacts/v5-final/mb6-v2/h2-h4-calibration-queue-v2.json",
        "artifacts/v5-final/parent-native/s3-parent-native-runtime-factory-v1.json",
    )
)


class S4ParentNativeExecutorsError(RuntimeError):
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
        [str(PARENT_PYTHON), "-m", "v5_final.parent_native_executors_probe"],
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
    by_key = {
        (record["case_id"], record["method_id"]): record for record in records
    }
    h2 = "h2-1.5-iteration-1"
    h4 = "h4-1.5-first-chemical-accuracy"
    magnitude = [
        record
        for record in records
        if record["method_id"] == "structural-magnitude-pruning"
    ]
    structural = [
        record
        for record in records
        if record["method_id"]
        in {
            "v4.1-one-shot-joint-compression",
            "v5-fixed-source-whitelist-no-replenishment",
            "v5-sequential-with-rebuilding",
        }
    ]
    fixed_full = probe["fixed_vs_full_initial_contrast"]
    h4_v4 = by_key[(h4, "v4.1-one-shot-joint-compression")]
    checks = {
        "six_methods_on_both_actual_cases": (
            len(records) == 12
            and len(by_key) == 12
            and set(probe["methods"])
            == {method for _, method in by_key}
            and set(probe["cases"]) == {h2, h4}
        ),
        "actual_parent_candidate_types": all(
            record["actual_candidate_types"] == ["CompressionCandidate"]
            and record["source_catalog_type"] == "ParentNativeCatalog"
            for record in structural
        ),
        "actual_parent_execution_entrypoints_bound": set(
            probe["parent_execution_bindings"]
        )
        == {
            "composition",
            "warm_start",
            "optimizer",
            "acceptance",
            "transaction",
            "resource_recount",
            "selection",
        },
        "magnitude_is_physical_deletion_with_recount": all(
            record["magnitude_deletion"]["physical_generator_deleted"] is True
            and record["magnitude_deletion"]["coefficient_zeroing_only"] is False
            and record["magnitude_deletion"]["full_circuit_rebuild_and_recount"]
            is True
            and record["magnitude_deletion"]["target_coefficients_count"]
            + 1
            == record["generated_candidate_intents"]
            for record in magnitude
        ),
        "all_rewrites_use_actual_target_and_resources": all(
            rewrite["target_indices"] != rewrite["source_indices"]
            and rewrite["parent_physical_structural_snapshot_equal"] is True
            and rewrite["physical_circuit_changed"] is True
            and rewrite["parameter_only_reduction_claimed"] is False
            for record in records
            for rewrite in record["prepared_rewrites"]
        ),
        "v4_H4_v2_incompatibility_corrected_outcome_free": (
            h4_v4["execution_directives"]["v2_binding_correction_required"] is True
            and len(h4_v4["queue_candidate_ids"]) == 4
            and len(h4_v4["selected_candidate_ids"]) == 2
            and len(h4_v4["v4_frozen_incompatible_ids"]) == 2
            and set(h4_v4["selected_candidate_ids"]).isdisjoint(
                h4_v4["v4_frozen_incompatible_ids"]
            )
            and by_key[(h2, "v4.1-one-shot-joint-compression")][
                "execution_directives"
            ]["v2_binding_correction_required"]
            is False
        ),
        "fixed_and_full_share_initial_selection_only": all(
            value["same_source_selection_digest"] is True
            and value["same_initial_selected_candidates"] is True
            and value["fixed_replenishment"] is False
            and value["full_replenishment"] is True
            and value["catalog_work_reduction_claimed"] is False
            for value in fixed_full.values()
        ),
        "generation_work_preserved_search_states_deduplicated": (
            by_key[(h4, "v5-fixed-source-whitelist-no-replenishment")][
                "generated_candidate_intents"
            ]
            == 20
            and by_key[(h4, "v5-fixed-source-whitelist-no-replenishment")][
                "unique_proposed_physical_states"
            ]
            == 16
            and by_key[(h4, "v5-sequential-with-rebuilding")][
                "generated_candidate_intents"
            ]
            == 20
            and by_key[(h4, "v5-sequential-with-rebuilding")][
                "unique_proposed_physical_states"
            ]
            == 16
        ),
        "complete_rollback_scope_declared": all(
            set(record["execution_directives"]["rollback_scope"])
            == {
                "ansatz",
                "parameters",
                "optimizer_inverse_hessian",
                "resources",
                "ledger_transaction",
            }
            for record in records
        ),
        "outcome_kernels_zero_and_execution_blocked": (
            all(value == 0 for value in probe["molecular_outcome_kernel_calls"].values())
            and probe["candidate_energy_evaluations"] == 0
            and probe["optimizer_calls"] == 0
            and all(record["execution_authorized"] is False for record in records)
            and probe["H2_H4_queue_executed"] is False
            and probe["projected_queue_written_or_authorized"] is False
            and probe["performance_evidence"] is False
        ),
    }
    if not all(checks.values()):
        raise S4ParentNativeExecutorsError("S4 parent-native executor checks failed")
    artifact: dict[str, Any] = {
        "schema": "v5-final.s4-parent-native-executors-audit.v1",
        "stage": "S4_SIX_METHOD_NATIVE_EXECUTORS",
        "status": (
            "PASS_OUTCOME_FREE_ACTUAL_PARENT_EXECUTORS_WITH_V4_BINDING_CORRECTION"
        ),
        "decision": "GO_S5_KERNEL_BOUNDARY_WORK_ACCOUNTING_ONLY",
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
        "probe": probe,
        "checks": checks,
        "required_MB6_v3_corrections": {
            "environment_threads": "2/2/2 from S3",
            "H4_v4_1_compatible_sentinels": h4_v4["selected_candidate_ids"],
            "H4_v4_1_rejected_incompatible_v2_sentinels": h4_v4[
                "v4_frozen_incompatible_ids"
            ],
            "physical_state_identity": (
                "physical-state-v3 wraps only canonical parent StatePreparationSpec; "
                "candidate intent is excluded"
            ),
        },
        "authorization": {
            "S5_outcome_free_kernel_boundary_work_accounting": "AUTHORIZED",
            "molecular_candidate_energy": "NOT_AUTHORIZED",
            "H2_H4_execution": "NOT_AUTHORIZED",
            "MB6_v3_freeze": "NOT_AUTHORIZED_BEFORE_S5_S6",
            "development_queue_execution": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "academic_boundary": (
            "All six methods are bound to actual parent types and entrypoints. "
            "Only structural preparation, matrix verification, OBS prediction, and "
            "full circuit recounts were executed. The V4.1 compatibility and physical-"
            "state identity corrections are outcome-blind. No optimizer or molecular "
            "candidate energy was executed."
        ),
    }
    artifact["audit_digest"] = _digest(artifact)
    return artifact


def verify(record: dict[str, Any]) -> dict[str, bool]:
    body = dict(record)
    observed = body.pop("audit_digest", None)
    return {
        "audit_digest_valid": observed == _digest(body),
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
        == "GO_S5_KERNEL_BOUNDARY_WORK_ACCOUNTING_ONLY",
        "candidate_energy_zero": record["probe"]["candidate_energy_evaluations"]
        == 0,
        "H2_H4_blocked": record["authorization"]["H2_H4_execution"]
        == "NOT_AUTHORIZED",
    }


def audit() -> dict[str, bool]:
    record = json.loads(OUTPUT.read_text())
    checks = verify(record)
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S4ParentNativeExecutorsError(
            "S4 audit failed: " + ", ".join(failures)
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

"""Freeze outcome caps and the complete primitive-accounting crosswalk.

The only outcome-cap input is the immutable S11-v1 *pre-outcome* development
plan.  No execution ledger, result, receipt, optimizer outcome, or molecular
candidate energy is read by this module.
"""

from __future__ import annotations

import argparse
import ast
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Mapping

from v5_matched_work.atomic_artifacts import (
    canonical_json_bytes,
    write_bytes_exclusive,
    write_json_exclusive,
)

from .parent_native_work_accounting import operation_delta, work_cap_digest
from .semantic_contract_v2 import WORK_COMPONENTS, WorkDelta
from .s0_successor import ROOT


OUTPUT_DIR = ROOT / "artifacts/v5-final/parent-native/s11-v2-outcome-cap-freeze-v1"
OUTPUT = OUTPUT_DIR / "outcome-cap-freeze-v1.json"
CROSSWALK_OUTPUT = OUTPUT_DIR / "primitive-accounting-crosswalk-v1.json"
MANIFEST = OUTPUT_DIR / "MANIFEST.sha256"
SOURCE_PLAN = (
    ROOT
    / "artifacts/v5-final/parent-native/s11-development-queue-v4/development-plan-v4.json"
)
SOURCE_FREEZE = (
    ROOT
    / "artifacts/v5-final/parent-native/s11-development-queue-v4/development-outcome-blind-freeze-v4.json"
)
DESIGN = (
    ROOT
    / "artifacts/v5-final/parent-native/s11-v2-verifier-remediation/verifier-v2-design-v1.json"
)
WORK_ACCOUNTING_SOURCE = ROOT / "src/v5_final/parent_native_work_accounting.py"
EXECUTION_SERVICES_SOURCE = ROOT / "src/v5_final/parent_native_execution_services.py"
SEMANTIC_CONTRACT_SOURCE = ROOT / "src/v5_final/semantic_contract_v2.py"
OPTIMIZER_SOURCE = (
    ROOT
    / "provenance/dvg-obs-ceo/vendor/ceo-adapt-vqe/adaptvqe/minimize.py"
)

SOURCE_PLAN_INTRODUCING_COMMIT = "8be3b819c1f19b4ca24e3d10136afb98c2ab0782"
FIRST_S11_OUTCOME_COMMIT = "dfa2b01adea7fbaa96a073828923b9e1b3a731b8"
WORK_ORDER = ("LOW", "MEDIUM", "HIGH")

SIDECAR_TELEMETRY = ("CPU_time_seconds", "wall_time_seconds", "peak_RSS_raw")
VERIFIER_ONLY_COUNTERS = (
    "N_symbolic_checks",
    "N_sparse_expm_multiply",
    "N_state_probe_vectors",
    "N_dense_expm",
    "N_circuit_operator_builds",
    "N_generator_materializations",
    "matrix_dimension",
    "qubit_count",
    "unique_semantic_candidates",
    "unique_physical_states",
)

# This registry is intentionally exhaustive.  The AST audit below fails when a
# new literal kernel operation is introduced without a corresponding entry.
OPERATION_REGISTRY: dict[str, dict[str, Any]] = {
    "optimizer-start": {"components": {"optimizer_starts": "units"}, "phase": "outcome"},
    "optimizer-iteration": {"components": {"optimizer_iterations": "units"}, "phase": "outcome"},
    "candidate-energy-evaluation": {"components": {"energy_evaluations": "units"}, "phase": "outcome"},
    "source-energy-evaluation": {"components": {"energy_evaluations": "units"}, "phase": "outcome"},
    "full-gradient-evaluation": {
        "components": {
            "gradient_vector_evaluations": "units",
            "gradient_component_equivalents": "units*dimension",
        },
        "phase": "outcome",
    },
    "gradient-component-evaluation": {"components": {"gradient_component_equivalents": "units"}, "phase": "outcome"},
    "statevector-recomputation": {"components": {"statevector_recomputations": "units"}, "phase": "both"},
    "full-physical-resource-recount": {"components": {"resource_recounts": "units"}, "phase": "both"},
    "candidate-generation": {"components": {"candidate_generations": "units"}, "phase": "both"},
    "unique-search-state-expansion": {"components": {"search_states": "units"}, "phase": "outcome"},
    "rewrite-verification": {"components": {"rewrite_verifications": "units"}, "phase": "both"},
    "hessian-vector-product": {"components": {"hvp_evaluations": "units"}, "phase": "outcome"},
    "candidate-physical-state-alias": {"components": {}, "phase": "both"},
    "cap-rejection": {"components": {}, "phase": "both"},
}


class S11V2OutcomeCapFreezeError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise S11V2OutcomeCapFreezeError(f"expected object: {path}")
    return value


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _with_digest(value: Mapping[str, Any], field: str) -> dict[str, Any]:
    result = dict(value)
    result[field] = _digest(result)
    return result


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout.strip()


def _literal_operations(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    operations: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        name = function.attr if isinstance(function, ast.Attribute) else (
            function.id if isinstance(function, ast.Name) else ""
        )
        if name not in {"invoke", "_append", "operation_delta"}:
            continue
        if node.args:
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                operations.add(first.value)
        for keyword in node.keywords:
            if (
                keyword.arg == "operation"
                and isinstance(keyword.value, ast.Constant)
                and isinstance(keyword.value.value, str)
            ):
                operations.add(keyword.value.value)
    return operations


def _validate_registry() -> dict[str, Any]:
    observed = set()
    for path in (WORK_ACCOUNTING_SOURCE, EXECUTION_SERVICES_SOURCE):
        observed.update(_literal_operations(path))
    unknown = observed - set(OPERATION_REGISTRY)
    if unknown:
        raise S11V2OutcomeCapFreezeError(
            f"actual kernel operation is unregistered: {sorted(unknown)}"
        )
    semantic_checks: dict[str, bool] = {}
    for operation, record in OPERATION_REGISTRY.items():
        if not record["components"]:
            outcome = "duplicate" if operation == "candidate-physical-state-alias" else "cap-rejected"
            delta = operation_delta(operation, units=0, dimension=None, outcome=outcome)
        else:
            dimension = 7 if operation == "full-gradient-evaluation" else None
            delta = operation_delta(
                operation, units=2, dimension=dimension, outcome="completed"
            )
        expected: dict[str, int] = {}
        for component, formula in record["components"].items():
            expected[component] = 14 if formula == "units*dimension" else 2
        semantic_checks[operation] = {
            key: value for key, value in asdict(delta).items() if value
        } == expected
    if not all(semantic_checks.values()):
        raise S11V2OutcomeCapFreezeError("operation registry and delta semantics differ")
    return {
        "actual_literal_operations": sorted(observed),
        "registry_operations": sorted(OPERATION_REGISTRY),
        "unregistered_actual_operations": sorted(unknown),
        "operation_delta_semantics": semantic_checks,
    }


def build_crosswalk() -> dict[str, Any]:
    design = _load(DESIGN)
    verifier_fields = tuple(design["counter_schema"]["fields"])
    deterministic = tuple(
        field for field in verifier_fields if field not in SIDECAR_TELEMETRY
    )
    complete = tuple(dict.fromkeys((*deterministic, *WORK_COMPONENTS)))
    registry_audit = _validate_registry()
    operations = {}
    for name, record in OPERATION_REGISTRY.items():
        operations[name] = {
            **record,
            "duplicate_event_delta": "zero only for candidate-physical-state-alias",
            "failed_call_accounting": (
                "same positive delta as completed call"
                if record["components"] else "not a counted kernel call"
            ),
            "retry_accounting": "cumulative; immutable prior attempt work is retained",
            "cap_precheck": "before kernel; CAP_REJECTED is zero-delta evidence",
        }
    body = {
        "schema": "v5-final.s11-v2-primitive-accounting-crosswalk.v1",
        "status": "FROZEN_OUTCOME_FREE_ACCOUNTING_CROSSWALK",
        "source_code": {
            str(path.relative_to(ROOT)): _sha(path)
            for path in (
                WORK_ACCOUNTING_SOURCE,
                EXECUTION_SERVICES_SOURCE,
                SEMANTIC_CONTRACT_SOURCE,
            )
        },
        "verifier_deterministic_counters": list(deterministic),
        "live_semantic_ledger_counters": list(WORK_COMPONENTS),
        "sidecar_telemetry_not_fairness_caps": list(SIDECAR_TELEMETRY),
        "complete_counter_schema": list(complete),
        "complete_counter_schema_digest": _digest(list(complete)),
        "operations": operations,
        "registry_audit": registry_audit,
        "semantic_rules": {
            "actual_operation_registry_exactly_once": True,
            "failed_kernel_calls_count": True,
            "physical_state_duplicate_key": "canonical proposed_physical_state_id",
            "duplicate_evidence_delta_zero": True,
            "retry_resets_counters": False,
            "rollback_erases_work": False,
            "path_must_be_queue_bound": True,
        },
    }
    return _with_digest(body, "crosswalk_digest")


def _extract_profiles(plan: Mapping[str, Any]) -> dict[str, dict[str, int]]:
    items = list(plan.get("items", ()))
    if len(items) != 90 or plan.get("candidate_energy_evaluations") != 0:
        raise S11V2OutcomeCapFreezeError("source is not the frozen zero-outcome grid")
    profiles: dict[str, dict[str, int]] = {}
    for envelope in WORK_ORDER:
        selected = [item for item in items if item.get("work_envelope") == envelope]
        caps = {canonical_json_bytes(item["componentwise_work_cap"]) for item in selected}
        if len(selected) != 30 or len(caps) != 1:
            raise S11V2OutcomeCapFreezeError(
                f"{envelope} cap is not identical across all cases and methods"
            )
        cap = dict(selected[0]["componentwise_work_cap"])
        if set(cap) != set(WORK_COMPONENTS):
            raise S11V2OutcomeCapFreezeError("source cap is incomplete")
        if work_cap_digest(WorkDelta(**cap)) != selected[0]["work_cap_digest"]:
            raise S11V2OutcomeCapFreezeError("source cap digest mismatch")
        profiles[envelope] = cap
    return profiles


def build_freeze(crosswalk: Mapping[str, Any]) -> dict[str, Any]:
    plan = _load(SOURCE_PLAN)
    freeze = _load(SOURCE_FREEZE)
    profiles = _extract_profiles(plan)
    source_history = _git(
        "log", "--follow", "--format=%H", "--", str(SOURCE_PLAN.relative_to(ROOT))
    ).splitlines()
    if not source_history or source_history[-1] != SOURCE_PLAN_INTRODUCING_COMMIT:
        raise S11V2OutcomeCapFreezeError("source plan introduction history differs")
    if subprocess.run(
        ["git", "merge-base", "--is-ancestor", SOURCE_PLAN_INTRODUCING_COMMIT, FIRST_S11_OUTCOME_COMMIT],
        cwd=ROOT,
    ).returncode != 0:
        raise S11V2OutcomeCapFreezeError("cap source is not ancestral to first outcome")
    if freeze["artifacts"]["plan"]["sha256"] != _sha(SOURCE_PLAN):
        raise S11V2OutcomeCapFreezeError("pre-outcome freeze does not bind source plan")
    optimizer_text = OPTIMIZER_SOURCE.read_text(encoding="utf-8")
    service_text = EXECUTION_SERVICES_SOURCE.read_text(encoding="utf-8")
    body = {
        "schema": "v5-final.s11-v2-outcome-cap-freeze.v1",
        "stage": "Q4_OUTCOME_CAP_FREEZE",
        "status": "FROZEN_PRE_OUTCOME_CAPS_NOT_EXECUTION_AUTHORIZATION",
        "source": {
            "path": str(SOURCE_PLAN.relative_to(ROOT)),
            "sha256": _sha(SOURCE_PLAN),
            "plan_digest": plan["plan_digest"],
            "pre_outcome_freeze_path": str(SOURCE_FREEZE.relative_to(ROOT)),
            "pre_outcome_freeze_sha256": _sha(SOURCE_FREEZE),
            "introducing_commit": SOURCE_PLAN_INTRODUCING_COMMIT,
            "first_S11_outcome_commit": FIRST_S11_OUTCOME_COMMIT,
            "source_precedes_first_outcome": True,
            "post_outcome_results_or_receipts_read": False,
        },
        "profiles": {
            name: {
                "componentwise_outcome_cap": cap,
                "cap_digest": work_cap_digest(WorkDelta(**cap)),
                "same_for_all_5_cases_and_6_methods": True,
                "classification": "pre-existing pre-outcome hard ceiling; not empirical runtime estimate",
            }
            for name, cap in profiles.items()
        },
        "phase_ownership": {
            "verifier_only_namespace": list(VERIFIER_ONLY_COUNTERS),
            "outcome_only_namespace": list(WORK_COMPONENTS),
            "combined_live_ledger_rule": "for shared integer counters, verifier cap + outcome cap because both disjoint sequential phases consume work",
            "max_rule_used": False,
            "unproven_manual_sum_used": False,
            "derivation": "mechanical fieldwise addition performed by the queue-v2 generator from this crosswalk",
        },
        "crosswalk": {
            "path": str(CROSSWALK_OUTPUT.relative_to(ROOT)),
            "sha256": _sha(CROSSWALK_OUTPUT) if CROSSWALK_OUTPUT.exists() else None,
            "crosswalk_digest": crosswalk["crosswalk_digest"],
            "complete_counter_schema_digest": crosswalk["complete_counter_schema_digest"],
        },
        "pinned_optimizer_audit": {
            "source_path": str(OPTIMIZER_SOURCE.relative_to(ROOT)),
            "source_sha256": _sha(OPTIMIZER_SOURCE),
            "caller_maxiter_1000": "maxiter=1000" in service_text,
            "caller_gtol_1e-8": "gtol=1e-8" in service_text,
            "wolfe_1_2_line_search": "_line_search_wolfe12" in optimizer_text,
            "callback_records_optimizer_iteration": '"optimizer-iteration"' in service_text,
            "f0_g0_counter_correction_present": "nfev_correction -= 1" in optimizer_text and "ngev_correction -= 1" in optimizer_text,
            "nfev_njev_to_ledger_runtime_parity": "REQUIRES_OUTCOME_FREE_EXECUTOR_V2_TEST_BEFORE_GO",
        },
        "scientific_boundary": {
            "candidate_outcomes_used": False,
            "S11_v1_observed_work_used": False,
            "method_specific_caps": False,
            "candidate_energy_authorized": False,
            "performance_claim_authorized": False,
        },
    }
    return _with_digest(body, "freeze_digest")


def _manifest_bytes(paths: tuple[Path, ...]) -> bytes:
    return ("".join(f"{_sha(path)}  {path.name}\n" for path in paths)).encode()


def write_artifacts() -> None:
    crosswalk = build_crosswalk()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_json_exclusive(CROSSWALK_OUTPUT, crosswalk)
    freeze = build_freeze(crosswalk)
    # The freeze binds the already-written crosswalk bytes.
    write_json_exclusive(OUTPUT, freeze)
    write_bytes_exclusive(MANIFEST, _manifest_bytes((CROSSWALK_OUTPUT, OUTPUT)))


def audit() -> dict[str, Any]:
    crosswalk = build_crosswalk()
    if not CROSSWALK_OUTPUT.exists() or _load(CROSSWALK_OUTPUT) != crosswalk:
        raise S11V2OutcomeCapFreezeError("frozen crosswalk differs")
    freeze = build_freeze(crosswalk)
    checks = {
        "crosswalk_exact": _load(CROSSWALK_OUTPUT) == crosswalk,
        "freeze_exact": OUTPUT.exists() and _load(OUTPUT) == freeze,
        "manifest_exact": MANIFEST.exists() and MANIFEST.read_bytes() == _manifest_bytes((CROSSWALK_OUTPUT, OUTPUT)),
        "all_profiles_complete": all(
            set(record["componentwise_outcome_cap"]) == set(WORK_COMPONENTS)
            for record in freeze["profiles"].values()
        ),
        "all_profiles_method_and_case_invariant": all(
            record["same_for_all_5_cases_and_6_methods"] is True
            for record in freeze["profiles"].values()
        ),
        "no_outcomes_used": not any(freeze["scientific_boundary"][key] for key in (
            "candidate_outcomes_used", "S11_v1_observed_work_used", "method_specific_caps"
        )),
        "actual_operations_registered": not crosswalk["registry_audit"]["unregistered_actual_operations"],
    }
    if not all(checks.values()):
        raise S11V2OutcomeCapFreezeError([name for name, passed in checks.items() if not passed])
    return {
        "status": "PASS_Q2_Q4_OUTCOME_CAP_AND_ACCOUNTING_FREEZE",
        "checks": checks,
        "freeze_digest": freeze["freeze_digest"],
        "crosswalk_digest": crosswalk["crosswalk_digest"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--audit", action="store_true")
    args = parser.parse_args()
    if args.write:
        write_artifacts()
    if args.audit or not args.write:
        print(json.dumps(audit(), sort_keys=True))


if __name__ == "__main__":
    main()

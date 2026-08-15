"""Outcome-blind S11-v2 queue freeze derived independently of S11-v1 results."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from v5_matched_work.atomic_artifacts import (
    canonical_json_bytes,
    write_bytes_exclusive,
    write_json_exclusive,
)

from .mb4_2_owner_protocol_freeze import CANONICAL_METHOD_IDS
from .mb6_queue_freeze import _candidate_binding
from .s0_successor import ROOT


OUTPUT_DIR = ROOT / "artifacts/v5-final/parent-native/s11-v2-queue-freeze-v1"
RECALIBRATION_PATH = OUTPUT_DIR / "h2-h4-verifier-work-recalibration-v1.json"
QUEUE_PATH = OUTPUT_DIR / "s11-v2-queue-v1.json"
IDENTITY_PATH = OUTPUT_DIR / "queue-byte-identity-v1.json"
MANIFEST_PATH = OUTPUT_DIR / "MANIFEST.sha256"

CALIBRATION_DIR = (
    ROOT / "artifacts/v5-final/parent-native/s11-v2-verifier-calibration-v1"
)
CALIBRATION_SUMMARY = CALIBRATION_DIR / "calibration-summary-v1.json"
H2_CORE = CALIBRATION_DIR / "h2-core-v2.json"
H4_CORE = CALIBRATION_DIR / "h4-core-v2.json"
DESIGN_PATH = (
    ROOT
    / "artifacts/v5-final/parent-native/s11-v2-verifier-remediation/verifier-v2-design-v1.json"
)
SOURCE_CATALOG = (
    ROOT
    / "artifacts/v5-final/parent-native/s11-development-queue-v4/development-source-catalog-v1.json"
)
EXECUTOR_MANIFEST = (
    ROOT
    / "artifacts/v5-final/parent-native/s11-development-queue-v4/development-executor-manifest-v1.json"
)
S5_PROTOCOL = ROOT / "artifacts/v5-final/s5/development-protocol-freeze-v3.json"
S11_V1_QUEUE = (
    ROOT
    / "artifacts/v5-final/parent-native/s11-development-queue-v4/development-plan-v4.json"
)
VERIFIER_CODE = ROOT / "src/v5_final/verifier_v2.py"
PARENT_ADAPTER_CODE = ROOT / "src/v5_final/parent_native_verifier_v2.py"

WORK_ORDER = ("LOW", "MEDIUM", "HIGH")
WORK_MULTIPLIERS = {"LOW": 1, "MEDIUM": 2, "HIGH": 4}
DETERMINISTIC_COUNTER_FIELDS = (
    "N_symbolic_checks",
    "N_sparse_expm_multiply",
    "N_state_probe_vectors",
    "N_dense_expm",
    "N_circuit_operator_builds",
    "N_generator_materializations",
    "matrix_dimension",
    "qubit_count",
    "candidate_generations",
    "unique_semantic_candidates",
    "unique_physical_states",
    "rewrite_verifications",
    "resource_recounts",
)


class S11V2QueueFreezeError(RuntimeError):
    pass


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _with_digest(value: dict[str, Any], field: str) -> dict[str, Any]:
    result = dict(value)
    result[field] = _digest(result)
    return result


def build_recalibration() -> dict[str, Any]:
    summary = _load(CALIBRATION_SUMMARY)
    h2 = _load(H2_CORE)["deterministic_work_counters"]
    h4 = _load(H4_CORE)["deterministic_work_counters"]
    design = _load(DESIGN_PATH)
    required_checks = (
        "old_new_pass_fail_parity",
        "h2_byte_identical",
        "h4_byte_identical",
        "all_new_cores_dense_expm_zero",
        "candidate_energy_zero",
        "optimizer_zero",
    )
    if not all(summary["checks"][name] is True for name in required_checks):
        raise S11V2QueueFreezeError("H2/H4 outcome-free calibration prerequisite failed")
    if h2["N_dense_expm"] != 0 or h4["N_dense_expm"] != 0:
        raise S11V2QueueFreezeError("production dense expm invariant failed")
    calibration_maximum = {
        field: max(h2[field], h4[field]) for field in DETERMINISTIC_COUNTER_FIELDS
    }
    body = {
        "schema": "v5-final.s11-v2-h2-h4-verifier-work-recalibration.v1",
        "status": "FROZEN_OUTCOME_FREE_VERIFIER_PRIMITIVE_RECALIBRATION",
        "inputs": {
            "calibration_summary": {
                "path": str(CALIBRATION_SUMMARY.relative_to(ROOT)),
                "sha256": _sha(CALIBRATION_SUMMARY),
                "summary_digest": summary["summary_digest"],
            },
            "h2_core": {"sha256": _sha(H2_CORE), "counters": h2},
            "h4_core": {"sha256": _sha(H4_CORE), "counters": h4},
            "verifier_design_freeze_digest": design["design_freeze_digest"],
        },
        "observed_componentwise_maximum": calibration_maximum,
        "derivation": {
            "classification": "outcome-free structural/verifier work calibration",
            "work_envelope_multipliers": WORK_MULTIPLIERS,
            "per_queue_item_formula": {
                "candidate_generations": "candidate_count * envelope_multiplier",
                "unique_semantic_candidates": "candidate_generations conservative upper bound",
                "unique_physical_states": "candidate_generations conservative upper bound",
                "rewrite_verifications": "min(K,candidate_count) * envelope_multiplier",
                "N_symbolic_checks": "(candidate_count + 5*min(K,candidate_count)) * envelope_multiplier",
                "N_sparse_expm_multiply": "9*min(K,candidate_count) * envelope_multiplier",
                "N_state_probe_vectors": "probe_count*min(K,candidate_count) * envelope_multiplier",
                "N_generator_materializations": "max_relation_terms*min(K,candidate_count) * envelope_multiplier",
                "N_circuit_operator_builds": "(source_blocks + 2*candidate_count*source_blocks + 3*min(K,candidate_count)) * envelope_multiplier",
                "resource_recounts": "(1 + 2*candidate_count) * envelope_multiplier when candidates exist",
                "matrix_dimension": "exact case descriptor 2**qubit_count; not multiplied",
                "qubit_count": "exact case descriptor; not multiplied",
                "N_dense_expm": "0 invariant",
            },
            "scientific_rationale": "H2/H4 calibrate primitive semantics and constants; case catalog size and frozen source structure scale the conservative deterministic ceilings without candidate outcomes.",
        },
        "outcome_work_cap": {
            "optimizer_iterations": None,
            "energy_evaluations": None,
            "status": "NOT_AUTHORIZED_AWAITING_SEPARATE_PRE_OUTCOME_PRODUCTION_GATE",
            "zero_calibration_not_misrepresented_as_zero_cap": True,
        },
        "counter_schema": design["counter_schema"],
        "candidate_energy_evaluations": 0,
        "FCI_evaluations": 0,
        "performance_outcomes_used": False,
    }
    return _with_digest(body, "recalibration_digest")


def _candidate_summary(method_id: str, case: dict[str, Any]) -> dict[str, Any]:
    binding = _candidate_binding(method_id, case)
    candidates = binding["candidate_set"]
    ids = [item.get("candidate_structural_id", item.get("candidate_id")) for item in candidates]
    if any(value is None for value in ids):
        raise S11V2QueueFreezeError(f"candidate ID missing for {case['case_id']} {method_id}")
    return {
        "candidate_count": len(candidates),
        "candidate_ids_digest": _digest(ids),
        "candidate_binding_digest": _digest(binding),
        "rule": binding["rule"],
        "candidate_outcomes_used": False,
    }


def _max_relation_terms(case: dict[str, Any]) -> int:
    sizes = [
        len(item["source_pool_indices"]) + len(item["target_pool_indices"])
        for item in case["source_structural_catalog"]
    ]
    return max(sizes, default=0)


def _cap(
    *, case: dict[str, Any], candidate_count: int, multiplier: int, policy: dict[str, Any]
) -> dict[str, int]:
    selected = min(policy["top_k"], candidate_count)
    blocks = case["source_resources"]["logical_block_count"]
    qubits = len(case["state_preparation_payload"]["qubit_ordering"])
    has_candidates = candidate_count > 0
    return {
        "N_symbolic_checks": (candidate_count + 5 * selected) * multiplier,
        "N_sparse_expm_multiply": 9 * selected * multiplier,
        "N_state_probe_vectors": policy["probe_count"] * selected * multiplier,
        "N_dense_expm": 0,
        "N_circuit_operator_builds": (
            (blocks + 2 * candidate_count * blocks + 3 * selected) * multiplier
            if has_candidates
            else 0
        ),
        "N_generator_materializations": _max_relation_terms(case) * selected * multiplier,
        "matrix_dimension": 2**qubits,
        "qubit_count": qubits,
        "candidate_generations": candidate_count * multiplier,
        "unique_semantic_candidates": candidate_count * multiplier,
        "unique_physical_states": candidate_count * multiplier,
        "rewrite_verifications": selected * multiplier,
        "resource_recounts": (1 + 2 * candidate_count) * multiplier if has_candidates else 0,
    }


def build_queue(recalibration: dict[str, Any]) -> dict[str, Any]:
    catalog = _load(SOURCE_CATALOG)
    executors = _load(EXECUTOR_MANIFEST)
    design = _load(DESIGN_PATH)
    protocol = _load(S5_PROTOCOL)
    policy = design["policy"]
    expected_code = {
        str(VERIFIER_CODE.relative_to(ROOT)): _sha(VERIFIER_CODE),
        str(PARENT_ADAPTER_CODE.relative_to(ROOT)): _sha(PARENT_ADAPTER_CODE),
    }
    if design["code_sha256"] != expected_code:
        raise S11V2QueueFreezeError("frozen Verifier V2 implementation hash changed")
    counter_schema_digest = _digest(design["counter_schema"])
    code_binding = {
        "verifier_v2_sha256": _sha(VERIFIER_CODE),
        "parent_native_verifier_v2_sha256": _sha(PARENT_ADAPTER_CODE),
        "method_native_executor_manifest_sha256": _sha(EXECUTOR_MANIFEST),
        "method_native_implementation_bundle_digest": executors["implementation_bundle_digest"],
        "verifier_design_freeze_digest": design["design_freeze_digest"],
        "composition": "outcome-free Verifier V2 preparation followed only after a future all-pass P7 gate by the bound method-native semantic executor",
        "legacy_dense_verifier_allowed": False,
    }
    executor_bundle_digest = _digest(code_binding)
    threshold = protocol["policy"]["acceptance"]["source_relative_energy_budget_hartree"]
    items: list[dict[str, Any]] = []
    for case in catalog["cases"]:
        for work_name in WORK_ORDER:
            multiplier = WORK_MULTIPLIERS[work_name]
            for method_id in CANONICAL_METHOD_IDS:
                candidate = _candidate_summary(method_id, case)
                cap = _cap(
                    case=case,
                    candidate_count=candidate["candidate_count"],
                    multiplier=multiplier,
                    policy=policy,
                )
                body = {
                    "case_id": case["case_id"],
                    "method_id": method_id,
                    "budget_id": f"S11-V2-{work_name}",
                    "work_envelope": work_name,
                    "work_envelope_multiplier": multiplier,
                    "source_identity": {
                        "source_checkpoint_digest": case["source_checkpoint_digest"],
                        "source_checkpoint_sha256": case["source_checkpoint_sha256"],
                        "StatePreparationID": case["StatePreparationID"],
                        "ProblemID": case["ProblemID"],
                        "Hamiltonian_digest": case["Hamiltonian_digest"],
                    },
                    "candidate_binding": candidate,
                    "method_executor_identity": executors["executor_identities"][method_id],
                    "executor_bundle_digest": executor_bundle_digest,
                    "verifier_policy": policy,
                    "seed": policy["seed"],
                    "threshold_hartree": threshold,
                    "K": policy["top_k"],
                    "tie_break": policy["tie_break"],
                    "counter_schema_digest": counter_schema_digest,
                    "verifier_componentwise_cap": cap,
                    "verifier_componentwise_cap_digest": _digest(cap),
                    "outcome_work_cap": recalibration["outcome_work_cap"],
                    "terminal_status": "NOT_STARTED",
                    "candidate_energy_evaluations": 0,
                    "optimizer_iterations": 0,
                    "FCI_evaluations": 0,
                    "authorization": "NOT_AUTHORIZED_PENDING_P7_ALL_GATES",
                }
                item = dict(body)
                item["queue_item_id"] = "s11-v2-item-v1:" + _digest(body)
                items.append(item)
    queue_body = {
        "schema": "v5-final.s11-v2-fresh-90-item-queue.v1",
        "stage": "P6_S11_V2_QUEUE_FREEZE",
        "status": "FROZEN_NOT_AUTHORIZED_FOR_EXECUTION",
        "generation_order": "source catalog case order, LOW/MEDIUM/HIGH, canonical method order",
        "frozen_item_count": len(items),
        "items": items,
        "method_order": list(CANONICAL_METHOD_IDS),
        "case_order": [case["case_id"] for case in catalog["cases"]],
        "work_envelope_order": list(WORK_ORDER),
        "recalibration_digest": recalibration["recalibration_digest"],
        "source_catalog": {"path": str(SOURCE_CATALOG.relative_to(ROOT)), "sha256": _sha(SOURCE_CATALOG)},
        "executor_code_binding": code_binding,
        "executor_bundle_digest": executor_bundle_digest,
        "counter_schema_digest": counter_schema_digest,
        "old_s11_v1_queue": {
            "path": str(S11_V1_QUEUE.relative_to(ROOT)),
            "sha256": _sha(S11_V1_QUEUE),
            "immutable_and_not_used_as_generation_input": True,
            "completed_results_copied": 0,
        },
        "scientific_boundary": {
            "final_comparison_requires_all_90_S11_v2_items_from_scratch": True,
            "S11_v1_pilot_results_must_not_be_mixed": True,
            "candidate_outcome_execution": "NOT_AUTHORIZED_PENDING_P7_ALL_GATES",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "candidate_energy_evaluations": 0,
        "optimizer_iterations": 0,
        "FCI_evaluations": 0,
    }
    return _with_digest(queue_body, "queue_digest")


def build_identity(queue: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    first_bytes = canonical_json_bytes(queue)
    second_bytes = canonical_json_bytes(second)
    body = {
        "schema": "v5-final.s11-v2-queue-byte-identity.v1",
        "first_generation_sha256": hashlib.sha256(first_bytes).hexdigest(),
        "second_generation_sha256": hashlib.sha256(second_bytes).hexdigest(),
        "byte_identical": first_bytes == second_bytes,
        "queue_digest": queue["queue_digest"],
        "candidate_outcomes_used": False,
    }
    return _with_digest(body, "identity_audit_digest")


def _manifest_bytes(paths: tuple[Path, ...]) -> bytes:
    lines = [f"{_sha(path)}  {path.name}" for path in paths]
    return ("\n".join(lines) + "\n").encode()


def write_artifacts() -> None:
    recalibration = build_recalibration()
    first = build_queue(recalibration)
    second = build_queue(build_recalibration())
    identity = build_identity(first, second)
    if identity["byte_identical"] is not True:
        raise S11V2QueueFreezeError("two fresh queue generations differ")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path, payload in (
        (RECALIBRATION_PATH, recalibration),
        (QUEUE_PATH, first),
        (IDENTITY_PATH, identity),
    ):
        write_json_exclusive(path, payload)
    write_bytes_exclusive(
        MANIFEST_PATH,
        _manifest_bytes((RECALIBRATION_PATH, QUEUE_PATH, IDENTITY_PATH)),
    )


def audit() -> dict[str, Any]:
    recalibration = build_recalibration()
    first = build_queue(recalibration)
    second = build_queue(build_recalibration())
    identity = build_identity(first, second)
    checks = {
        "recalibration_exact": RECALIBRATION_PATH.exists() and _load(RECALIBRATION_PATH) == recalibration,
        "queue_exact": QUEUE_PATH.exists() and _load(QUEUE_PATH) == first,
        "queue_generated_twice_byte_identical": identity["byte_identical"],
        "identity_exact": IDENTITY_PATH.exists() and _load(IDENTITY_PATH) == identity,
        "manifest_exact": MANIFEST_PATH.exists() and MANIFEST_PATH.read_bytes() == _manifest_bytes((RECALIBRATION_PATH, QUEUE_PATH, IDENTITY_PATH)),
        "queue_count_90": len(first["items"]) == 90,
        "queue_ids_unique": len({item["queue_item_id"] for item in first["items"]}) == 90,
        "factorial_product_exact": len({(item["case_id"], item["method_id"], item["work_envelope"]) for item in first["items"]}) == 90,
        "all_not_started": all(item["terminal_status"] == "NOT_STARTED" for item in first["items"]),
        "all_outcomes_zero": all(item["candidate_energy_evaluations"] == item["optimizer_iterations"] == item["FCI_evaluations"] == 0 for item in first["items"]),
        "all_outcome_caps_null": all(item["outcome_work_cap"]["energy_evaluations"] is None and item["outcome_work_cap"]["optimizer_iterations"] is None for item in first["items"]),
        "all_dense_caps_zero": all(item["verifier_componentwise_cap"]["N_dense_expm"] == 0 for item in first["items"]),
        "all_required_bindings_present": all(all(key in item for key in ("method_id", "case_id", "budget_id", "seed", "threshold_hartree", "K", "tie_break", "counter_schema_digest", "executor_bundle_digest")) for item in first["items"]),
        "old_queue_hash_preserved": first["old_s11_v1_queue"]["sha256"] == _sha(S11_V1_QUEUE),
        "no_s11_v1_result_linkage": all(not any(key.startswith("predecessor") or "result" in key.lower() for key in item) for item in first["items"]),
        "candidate_energy_zero": first["candidate_energy_evaluations"] == 0,
        "performance_claim_blocked": first["scientific_boundary"]["performance_claim"] == "NOT_AUTHORIZED",
    }
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise S11V2QueueFreezeError(f"P6 audit failed: {failed}")
    return {"status": "PASS_P6_S11_V2_QUEUE_FROZEN_NOT_AUTHORIZED", "checks": checks, "queue_digest": first["queue_digest"]}


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

"""MB5 audit for the six outcome-free method-native executor entrypoints."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
from typing import Any

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .mb4_2_owner_protocol_freeze import (
    CANONICAL_METHOD_IDS,
    LEGACY_QUEUE_METHOD_IDS,
    OUTPUT as FREEZE_OUTPUT,
    audit as audit_freeze,
)
from .method_native_hardening_v2 import resolve_executor_callable
from .method_native_interface import NativeExecutorIdentity
from .outcome_free_method_executors import ENTRYPOINTS, EXECUTION_MODE
from .s0_successor import CEO_COMMIT, PARENT_COMMIT, ROOT


OUTPUT = ROOT / "artifacts/v5-final/method-native/mb5-outcome-free-executors-v1.json"
IMPLEMENTATION = ROOT / "src/v5_final/outcome_free_method_executors.py"
ALLOWED_IMPLEMENTATION_IMPORTS = {
    "__future__",
    "fractions",
    "hashlib",
    "json",
    "typing",
    "v5_matched_work.atomic_artifacts",
    "v5_final.mb4_2_owner_protocol_freeze",
}


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _implementation_imports() -> list[str]:
    tree = ast.parse(IMPLEMENTATION.read_text())
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                imports.add("v5_final." + (node.module or ""))
            else:
                imports.add(node.module or "")
    return sorted(imports)


def _queue_state() -> dict[str, Any]:
    queue = json.loads((ROOT / "artifacts/v5-final/s5/development-queue-v3.json").read_text())
    ledger = json.loads(
        (ROOT / "artifacts/v5-final/s5/development-ledger-root-v3.json").read_text()
    )
    return {
        "expected_count": queue["expected_queue_count"],
        "not_started_count": sum(
            item["terminal_status"] == "NOT_STARTED" for item in queue["items"]
        ),
        "completed_count": len(ledger["completed_queue_item_ids"]),
        "segment_count": len(ledger["segments"]),
        "candidate_energy_evaluations": ledger["development_candidate_energy_evaluations"],
    }


def synthetic_fixture(
    method_id: str, protocol_digest: str, protocol_freeze_digest: str
) -> dict[str, Any]:
    fixture_body = {
        "method_id": method_id,
        "classification": "SYNTHETIC_STRUCTURAL_NO_MOLECULE",
        "protocol_digest": protocol_digest,
    }
    return {
        "execution_mode": EXECUTION_MODE,
        "canonical_method_id": method_id,
        "protocol_digest": protocol_digest,
        "protocol_freeze_digest": protocol_freeze_digest,
        "synthetic_fixture": True,
        "synthetic_fixture_id": "outcome-free-fixture-v1:" + _digest(fixture_body),
        "kernel_calls_authorized": False,
        "development_queue_bound": False,
        "H2_H4_queue_bound": False,
        "production_execution_authorized": False,
        "candidate_energy_evaluations": 0,
        "source_generators": ["generator-a", "generator-b", "generator-c"],
        "source_candidate_whitelist": ["candidate-a", "candidate-stale", "candidate-b"],
        "current_catalog": [
            {
                "structural_candidate_id": "candidate-a",
                "equivalence_class_id": "class-1",
                "available": True,
                "structurally_eligible": True,
                "rank_numerator": 5,
                "rank_denominator": 1,
            },
            {
                "structural_candidate_id": "candidate-a2",
                "equivalence_class_id": "class-1",
                "available": True,
                "structurally_eligible": True,
                "rank_numerator": 4,
                "rank_denominator": 1,
            },
            {
                "structural_candidate_id": "candidate-b",
                "equivalence_class_id": "class-2",
                "available": True,
                "structurally_eligible": True,
                "rank_numerator": 2,
                "rank_denominator": 1,
            },
            {
                "structural_candidate_id": "candidate-new",
                "equivalence_class_id": "class-0",
                "available": True,
                "structurally_eligible": True,
                "rank_numerator": 1,
                "rank_denominator": 1,
            },
            {
                "structural_candidate_id": "candidate-d",
                "equivalence_class_id": "class-3",
                "available": True,
                "structurally_eligible": True,
                "rank_numerator": 6,
                "rank_denominator": 1,
            },
            {
                "structural_candidate_id": "candidate-e",
                "equivalence_class_id": "class-4",
                "available": True,
                "structurally_eligible": True,
                "rank_numerator": 7,
                "rank_denominator": 1,
            },
            {
                "structural_candidate_id": "candidate-f",
                "equivalence_class_id": "class-5",
                "available": True,
                "structurally_eligible": True,
                "rank_numerator": 8,
                "rank_denominator": 1,
            },
        ],
        "magnitude_records": [
            {
                "generator_id": "generator-a",
                "residual_squared_numerator": 4,
                "residual_squared_denominator": 1,
                "direct_coordinate_verified": True,
            },
            {
                "generator_id": "generator-b",
                "residual_squared_numerator": 1,
                "residual_squared_denominator": 1,
                "direct_coordinate_verified": True,
            },
            {
                "generator_id": "generator-c",
                "residual_squared_numerator": 9,
                "residual_squared_denominator": 1,
                "direct_coordinate_verified": True,
            },
        ],
        "resource_model": {
            "base": {
                "cnot_count": 1,
                "cnot_depth": 1,
                "total_depth": 2,
                "parameter_count": 0,
            },
            "generator_contributions": {
                "generator-a": {
                    "cnot_count": 2,
                    "cnot_depth": 1,
                    "total_depth": 2,
                    "parameter_count": 1,
                },
                "generator-b": {
                    "cnot_count": 0,
                    "cnot_depth": 0,
                    "total_depth": 0,
                    "parameter_count": 0,
                },
                "generator-c": {
                    "cnot_count": 4,
                    "cnot_depth": 2,
                    "total_depth": 3,
                    "parameter_count": 1,
                },
            },
        },
    }


def _entrypoint_name(method_id: str) -> str:
    target = ENTRYPOINTS[method_id]
    return f"v5_final.outcome_free_method_executors:{target.__name__}"


def _executor_identity(method_id: str, implementation_sha256: str) -> NativeExecutorIdentity:
    return NativeExecutorIdentity(
        method_id=LEGACY_QUEUE_METHOD_IDS[method_id],
        classification="OUTCOME_FREE_SYNTHETIC_ONLY_NOT_MOLECULAR",
        entrypoint=_entrypoint_name(method_id),
        implementation_sha256=implementation_sha256,
        parent_repository_commit=PARENT_COMMIT,
        ceo_adapt_vqe_commit=CEO_COMMIT,
    )


def _audit_one(
    method_id: str,
    protocol_digest: str,
    protocol_freeze_digest: str,
    implementation_sha256: str,
) -> dict[str, Any]:
    identity = _executor_identity(method_id, implementation_sha256)
    target, path = resolve_executor_callable(
        identity,
        implementation_path=IMPLEMENTATION,
        expected_method_id=LEGACY_QUEUE_METHOD_IDS[method_id],
    )
    request = synthetic_fixture(method_id, protocol_digest, protocol_freeze_digest)
    first = target(request)
    second = target(request)
    counters = first["semantic_counters"]
    proofs = {
        "callable_resolves_to_declared_file": path == IMPLEMENTATION.resolve(),
        "deterministic_result": first == second,
        "protocol_digest_bound": first["protocol_digest"] == protocol_digest,
        "canonical_method_bound": first["canonical_method_id"] == method_id,
        "legacy_queue_identity_explicit": first["legacy_queue_method_id"]
        == LEGACY_QUEUE_METHOD_IDS[method_id],
        "candidate_energy_zero": counters["candidate_energy_evaluations"] == 0,
        "molecular_kernel_zero": counters["molecular_kernel_calls"] == 0,
        "development_queue_zero": counters["development_queue_events"] == 0
        and first["development_queue_touched"] is False,
        "h2_h4_zero": counters["H2_H4_queue_events"] == 0
        and first["H2_H4_execution_touched"] is False,
        "no_performance_evidence": first["performance_evidence"] is False,
        "production_not_authorized": first["production_execution_authorized"] is False,
        "result_digest": first["result_digest"]
        == _digest({key: value for key, value in first.items() if key != "result_digest"}),
    }
    return {
        "canonical_method_id": method_id,
        "legacy_queue_method_id": LEGACY_QUEUE_METHOD_IDS[method_id],
        "executor_identity": identity.to_dict(),
        "synthetic_fixture_digest": _digest(request),
        "outcome_free_result": first,
        "proofs": proofs,
    }


def _semantic_contrast(executors: list[dict[str, Any]]) -> dict[str, bool]:
    by_method = {record["canonical_method_id"]: record for record in executors}
    fixed = by_method["v5-fixed-source-whitelist-no-replenishment"]["outcome_free_result"]
    rebuild = by_method["v5-sequential-with-rebuilding"]["outcome_free_result"]
    magnitude = by_method["structural-magnitude-pruning"]["outcome_free_result"]
    sentinel = by_method["v4.1-one-shot-joint-compression"]["outcome_free_result"]
    return {
        "fixed_source_excludes_replenished_candidate": fixed["selected_candidate_ids"]
        == ["candidate-b"],
        "fixed_source_records_stale_whitelist_member": fixed["stale_candidate_ids"]
        == ["candidate-stale"],
        "full_rebuild_can_select_replenished_candidate": rebuild["selected_candidate_ids"]
        == ["candidate-new"],
        "magnitude_physically_removes_one_coordinate": magnitude["child_generators"]
        == ["generator-a", "generator-c"]
        and magnitude["selected_candidate_ids"] == ["generator-b"],
        "zero_resource_reduction_not_overclaimed": magnitude["resource_recount"]
        ["resource_reduction_success"]
        is False
        and all(
            value == 0
            for value in magnitude["resource_recount"]["reduction"].values()
        ),
        "v4_1_is_deterministic_one_per_class_max_four": sentinel["selected_candidate_ids"]
        == ["candidate-new", "candidate-a", "candidate-b", "candidate-d"],
    }


def build() -> dict[str, Any]:
    audit_freeze()
    freeze = json.loads(FREEZE_OUTPUT.read_text())
    implementation_sha256 = hashlib.sha256(IMPLEMENTATION.read_bytes()).hexdigest()
    implementation_imports = _implementation_imports()
    executors = [
        _audit_one(
            method_id,
            freeze["protocol_digests"][method_id],
            freeze["freeze_digest"],
            implementation_sha256,
        )
        for method_id in CANONICAL_METHOD_IDS
    ]
    result = {
        "schema": "v5-final.method-native.mb5-outcome-free-executors.v1",
        "stage": "MB5_OUTCOME_FREE_EXECUTORS",
        "status": "COMPLETE_OUTCOME_FREE_EXECUTOR_IMPLEMENTATION",
        "decision": "GO_MB6_QUEUE_FREEZE_ONLY",
        "protocol_freeze": {
            "path": str(FREEZE_OUTPUT.relative_to(ROOT)),
            "sha256": hashlib.sha256(FREEZE_OUTPUT.read_bytes()).hexdigest(),
            "freeze_digest": freeze["freeze_digest"],
        },
        "implementation": {
            "path": str(IMPLEMENTATION.relative_to(ROOT)),
            "sha256": implementation_sha256,
            "execution_mode": EXECUTION_MODE,
            "imports": implementation_imports,
            "allowed_imports": sorted(ALLOWED_IMPLEMENTATION_IMPORTS),
            "import_surface_outcome_free": set(implementation_imports)
            <= ALLOWED_IMPLEMENTATION_IMPORTS,
        },
        "executors": executors,
        "six_outcome_free_method_native_executors_implemented": len(executors) == 6,
        "semantic_contrast": _semantic_contrast(executors),
        "development_queue": _queue_state(),
        "H2_H4_queue_created": False,
        "molecular_candidate_energy_executed": False,
        "production_molecular_executor_execution": False,
        "authorization": {
            "MB6_queue_freeze": "AUTHORIZED_TO_CREATE_AND_AUDIT_FREEZE_ONLY",
            "molecular_candidate_energy": "NOT_AUTHORIZED",
            "H2_H4_execution": "NOT_AUTHORIZED",
            "development_queue_execution": "NOT_AUTHORIZED",
            "six_production_molecular_executors": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
            "MB7_or_later": "NOT_AUTHORIZED",
        },
        "academic_boundary": (
            "All six entrypoints were executed only on a synthetic structural fixture. No molecule, "
            "Hamiltonian, energy, development outcome, or performance evidence was loaded."
        ),
        "systems_boundary": (
            "Entrypoints reject outcome-bearing fields and production bindings; implementation "
            "identity is bound to the actual callable source and pinned provenance commits."
        ),
    }
    result["audit_digest"] = _digest(result)
    return result


def audit() -> dict[str, bool]:
    committed = json.loads(OUTPUT.read_text())
    rebuilt = build()
    checks = {
        "owner_freeze_valid": all(audit_freeze().values()),
        "deterministic_rebuild": committed == rebuilt,
        "audit_digest": committed["audit_digest"]
        == _digest({key: value for key, value in committed.items() if key != "audit_digest"}),
        "implementation_sha": committed["implementation"]["sha256"]
        == hashlib.sha256(IMPLEMENTATION.read_bytes()).hexdigest(),
        "implementation_import_surface": committed["implementation"]["imports"]
        == _implementation_imports()
        and committed["implementation"]["import_surface_outcome_free"] is True
        and set(committed["implementation"]["imports"])
        <= ALLOWED_IMPLEMENTATION_IMPORTS,
        "six_entrypoints": committed["six_outcome_free_method_native_executors_implemented"]
        is True
        and [record["canonical_method_id"] for record in committed["executors"]]
        == list(CANONICAL_METHOD_IDS),
        "all_executor_proofs": all(
            all(record["proofs"].values()) for record in committed["executors"]
        ),
        "semantic_contrast": all(committed["semantic_contrast"].values()),
        "queue_untouched": committed["development_queue"]
        == {
            "expected_count": 90,
            "not_started_count": 90,
            "completed_count": 0,
            "segment_count": 0,
            "candidate_energy_evaluations": 0,
        },
        "no_h2_h4_queue": committed["H2_H4_queue_created"] is False,
        "no_molecular_execution": committed["molecular_candidate_energy_executed"]
        is False
        and committed["production_molecular_executor_execution"] is False,
        "only_mb6_freeze_open": committed["authorization"]
        == {
            "MB6_queue_freeze": "AUTHORIZED_TO_CREATE_AND_AUDIT_FREEZE_ONLY",
            "molecular_candidate_energy": "NOT_AUTHORIZED",
            "H2_H4_execution": "NOT_AUTHORIZED",
            "development_queue_execution": "NOT_AUTHORIZED",
            "six_production_molecular_executors": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
            "MB7_or_later": "NOT_AUTHORIZED",
        },
        "terminal_decision": committed["decision"] == "GO_MB6_QUEUE_FREEZE_ONLY",
    }
    if not all(checks.values()):
        raise RuntimeError("MB5 outcome-free executor audit failed")
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

"""Outcome-blind S11 successor freeze for the historical 90-item development grid."""

from __future__ import annotations

import argparse
import copy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import struct
from typing import Any, Mapping

from dvg_obs_ceo.block_ir import (
    candidate_to_dict,
    enumerate_candidates,
    recover_dvg_blocks,
)
from dvg_obs_ceo.identity import (
    StatePreparationSpec,
    canonical_json_bytes as parent_canonical_json_bytes,
)
from dvg_obs_ceo.molecular_identity import generator_definition_digest, problem_spec
from dvg_obs_ceo.resources import (
    AnsatzStructure,
    apply_candidate_structure,
    evaluate_full_circuit_resources,
    paper_era_backend,
)
from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .mb6_queue_freeze import _candidate_binding
from .mb6_source_catalog_probe import (
    FORBIDDEN_OUTPUT_KEYS,
    _delete_coordinate,
    _molecular_kernel_guard,
    _pareto_compression,
    _resource_vector,
)
from .parent_native_candidate_work_bindings import (
    CandidateWorkBinding,
    _magnitude_bindings,
    _single_candidate_bindings,
    candidate_structural_whitelist_key,
)
from .parent_native_development_runtime_factory_v1 import (
    DEVELOPMENT_CASES,
    ENVIRONMENT_PATH,
    METHOD_IDS,
    REGISTRY_PATH,
    S11_FREEZE_DIR,
    WORK_ENVELOPES,
    _algorithm_outcome_free,
    build_queue_bound_development_runtime_v1,
)
from .parent_native_executors import prepare_method_executor
from .parent_native_physical_identity import canonical_proposed_physical_state_id
from .parent_native_work_accounting import work_cap_digest
from .s0_successor import CEO_COMMIT, PARENT_COMMIT, ROOT
from .semantic_contract_v2 import WorkDelta


CATALOG_OUTPUT = S11_FREEZE_DIR / "development-source-catalog-v1.json"
EXECUTOR_OUTPUT = S11_FREEZE_DIR / "development-executor-manifest-v1.json"
PLAN_OUTPUT = S11_FREEZE_DIR / "development-plan-v4.json"
LEDGER_OUTPUT = S11_FREEZE_DIR / "development-ledger-root-v4.json"
DIFF_OUTPUT = S11_FREEZE_DIR / "s5-v3-v4-semantic-diff-audit-v1.json"
FREEZE_OUTPUT = S11_FREEZE_DIR / "development-outcome-blind-freeze-v4.json"

S5_QUEUE = ROOT / "artifacts/v5-final/s5/development-queue-v3.json"
S5_LEDGER = ROOT / "artifacts/v5-final/s5/development-ledger-root-v3.json"
S5_PROTOCOL = ROOT / "artifacts/v5-final/s5/development-protocol-freeze-v3.json"
S10 = ROOT / "artifacts/v5-final/parent-native/s10-calibration-integrity-v1.json"
OWNER_FREEZE = (
    ROOT / "artifacts/v5-final/method-native/mb4-2-owner-protocol-freeze-v1.json"
)

METHOD_RENAME = {
    "v5-sequential-without-rebuilding": (
        "v5-fixed-source-whitelist-no-replenishment"
    )
}

EXECUTION_SOURCES = tuple(
    ROOT / value
    for value in (
        "src/v5_final/parent_native_candidate_adapter.py",
        "src/v5_final/parent_native_physical_identity.py",
        "src/v5_final/parent_native_rewrite.py",
        "src/v5_final/parent_native_executors.py",
        "src/v5_final/parent_native_work_accounting.py",
        "src/v5_final/parent_native_persistent_runner.py",
        "src/v5_final/parent_native_runtime_factory.py",
        "src/v5_final/parent_native_development_runtime_factory_v1.py",
        "src/v5_final/parent_native_candidate_work_bindings.py",
        "src/v5_final/parent_native_execution_services.py",
        "src/v5_final/parent_native_zero_dimensional_v2.py",
        "src/v5_final/parent_native_development_execution_v1.py",
        "src/v5_final/semantic_contract_v2.py",
    )
)


class S11DevelopmentFreezeError(RuntimeError):
    pass


def _json(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise S11DevelopmentFreezeError(f"invalid JSON: {path}") from error
    if not isinstance(value, dict):
        raise S11DevelopmentFreezeError(f"expected JSON object: {path}")
    return value


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _with_digest(value: Mapping[str, Any], field: str) -> dict[str, Any]:
    result = copy.deepcopy(dict(value))
    result[field] = _digest(result)
    return result


def _checkpoint_digest(checkpoint: Mapping[str, Any]) -> str:
    body = dict(checkpoint)
    observed = body.pop("checkpoint_digest", None)
    expected = hashlib.sha256(parent_canonical_json_bytes(body)).hexdigest()
    if observed != expected:
        raise S11DevelopmentFreezeError("source checkpoint digest mismatch")
    return str(observed)


def _case_record(source: Mapping[str, Any]) -> dict[str, Any]:
    case_id = str(source["case_id"])
    path = ROOT / str(source["checkpoint_path"])
    if _sha(path) != source["checkpoint_sha256"]:
        raise S11DevelopmentFreezeError(f"source checkpoint drift: {case_id}")
    checkpoint = _json(path)
    checkpoint_digest = _checkpoint_digest(checkpoint)
    structure = AnsatzStructure.create(
        checkpoint["ansatz_indices"],
        checkpoint["ansatz_coefficients"],
        checkpoint["iteration_counts"],
    )
    algorithm, pool = _algorithm_outcome_free(case_id)
    if algorithm.molecule.fci_energy is not None or algorithm.molecule.ccsd_energy is not None:
        raise S11DevelopmentFreezeError("FCI/CCSD outcome entered catalog construction")
    blocks = recover_dvg_blocks(
        pool,
        structure.indices,
        structure.coefficients,
        structure.cumulative_parameter_counts,
    )
    state = StatePreparationSpec.create(
        reference_state=algorithm.ref_det,
        generator_definition_digest=generator_definition_digest(pool),
        ansatz_block_structure=((block.family, block.pool_indices) for block in blocks),
        ansatz_indices=structure.indices,
        coefficients=structure.coefficients,
        orbital_parameters=(),
        qubit_mapping="openfermion-jordan-wigner-v1",
        qubit_ordering=range(int(algorithm.n)),
    )
    problem = problem_spec(algorithm=algorithm, case_id=case_id)
    if (
        state.state_preparation_id != source["StatePreparationID"]
        or problem.problem_id != source["ProblemID"]
    ):
        raise S11DevelopmentFreezeError(
            f"actual outcome-free molecular identity drift: {case_id}"
        )
    backend = paper_era_backend()
    source_resources_result = evaluate_full_circuit_resources(
        pool, structure, backend, coefficient_policy="deterministic-structural"
    )
    source_resources = _resource_vector(source_resources_result)
    expected_resources = {
        key: int(source["resources"][key]) for key in source_resources
    }
    if (
        source_resources != expected_resources
        or source_resources_result.snapshot.structure_digest
        != source["resources"]["structure_digest"]
    ):
        raise S11DevelopmentFreezeError(f"source resource drift: {case_id}")

    catalog: list[dict[str, Any]] = []
    for candidate in enumerate_candidates(pool, blocks):
        target = apply_candidate_structure(
            pool,
            structure,
            candidate,
            [0.0] * len(candidate.target_pool_indices),
        )
        target_resources = _resource_vector(
            evaluate_full_circuit_resources(
                pool,
                target,
                backend,
                coefficient_policy="deterministic-structural",
            )
        )
        record = candidate_to_dict(candidate)
        record.update(
            {
                "candidate_structural_id": candidate.candidate_id,
                "canonical_order_key": [
                    candidate.equivalence_class_id,
                    candidate.candidate_id,
                ],
                "structurally_eligible": _pareto_compression(
                    source_resources, target_resources
                ),
                "target_structure_digest": _digest(
                    {
                        "indices": list(target.indices),
                        "iteration_counts": list(
                            target.cumulative_parameter_counts
                        ),
                    }
                ),
                "deterministic_structural_resources": target_resources,
            }
        )
        catalog.append(record)
    catalog.sort(key=lambda item: (item["equivalence_class_id"], item["candidate_id"]))

    magnitude: list[dict[str, Any]] = []
    for position, (pool_index, coefficient) in enumerate(
        zip(structure.indices, structure.coefficients)
    ):
        target = _delete_coordinate(structure, position)
        target_resources = _resource_vector(
            evaluate_full_circuit_resources(
                pool,
                target,
                backend,
                coefficient_policy="deterministic-structural",
            )
        )
        payload = {
            "source_state_preparation_id": state.state_preparation_id,
            "position": position,
            "pool_index": pool_index,
            "constraint": "theta_i->0",
            "physical_generator_deletion": True,
        }
        magnitude.append(
            {
                "candidate_structural_id": "magnitude-delete-v1:" + _digest(payload),
                "equivalence_class_id": f"single-coordinate-position:{position}",
                "canonical_order": position,
                "ansatz_position": position,
                "pool_index": pool_index,
                "magnitude_score_float64_hex": struct.pack(
                    ">d", abs(float(coefficient)) ** 2
                ).hex(),
                "constraint": "theta_i->0",
                "constraint_valid": True,
                "physical_generator_deleted": True,
                "coefficient_zeroing_only": False,
                "full_circuit_rebuild_and_recount": True,
                "resources_after": target_resources,
                "resource_reduction_success": _pareto_compression(
                    source_resources, target_resources
                ),
                "zero_reduction_is_success": False,
            }
        )
    magnitude.sort(
        key=lambda item: (
            item["magnitude_score_float64_hex"],
            item["candidate_structural_id"],
        )
    )
    return {
        "case_id": case_id,
        "source_checkpoint_path": str(path.relative_to(ROOT)),
        "source_checkpoint_sha256": _sha(path),
        "source_checkpoint_digest": checkpoint_digest,
        "stationary_source_audit": {
            "parameter_gradient_infinity": source["parameter_gradient_infinity"],
            "threshold": source["parameter_stationarity_threshold_infinity"],
            "passed": float(source["parameter_gradient_infinity"])
            <= float(source["parameter_stationarity_threshold_infinity"]),
            "pool_gradient_convergence_not_claimed": True,
        },
        "StatePreparationID": state.state_preparation_id,
        "state_preparation_payload": state.payload(),
        "ProblemID": problem.problem_id,
        "problem_payload": problem.payload(),
        "Hamiltonian_digest": problem.hamiltonian_digest,
        "source_statevector_sha256": source["statevector_sha256"],
        "source_resources": source_resources,
        "source_structural_catalog": catalog,
        "magnitude_candidates": magnitude,
    }


def build_catalog() -> dict[str, Any]:
    registry = _json(REGISTRY_PATH)
    body = dict(registry)
    observed = body.pop("registry_digest", None)
    if observed != _digest(body):
        raise S11DevelopmentFreezeError("source registry digest mismatch")
    by_case = {source["case_id"]: source for source in registry["sources"]}
    if list(by_case) != list(DEVELOPMENT_CASES):
        raise S11DevelopmentFreezeError("source registry case/order drift")
    with _molecular_kernel_guard() as calls:
        cases = [_case_record(by_case[case_id]) for case_id in DEVELOPMENT_CASES]
    result = {
        "schema": "v5-final.s11-development-outcome-free-source-catalog.v1",
        "stage": "S11_DEVELOPMENT_SUCCESSOR_OUTCOME_FREE_SOURCE_BINDING",
        "status": "OUTCOME_FREE_STRUCTURAL_BINDING_ONLY",
        "cases": cases,
        "source_registry_path": str(REGISTRY_PATH.relative_to(ROOT)),
        "source_registry_sha256": _sha(REGISTRY_PATH),
        "source_registry_digest": registry["registry_digest"],
        "molecular_kernel_guard_calls": calls,
        "candidate_energy_evaluations": 0,
        "selection_inputs": "frozen source identities and deterministic circuit recounts only",
        "forbidden_inputs": sorted(FORBIDDEN_OUTPUT_KEYS),
        "FCI_or_CCSD_computed": False,
        "academic_boundary": (
            "Known development sources only. Catalog construction uses no candidate "
            "energy, optimizer result, FCI value, calibration selection, or performance outcome."
        ),
    }
    result["catalog_digest"] = _digest(result)
    return result


def build_executor_manifest() -> dict[str, Any]:
    sources = [
        {"path": str(path.relative_to(ROOT)), "sha256": _sha(path)}
        for path in EXECUTION_SOURCES
    ]
    gates = [
        {"path": str(path.relative_to(ROOT)), "sha256": _sha(path)}
        for path in (S10, OWNER_FREEZE, S5_PROTOCOL, ENVIRONMENT_PATH)
    ]
    bundle = _digest(
        {
            "parent_commit": PARENT_COMMIT,
            "CEO_commit": CEO_COMMIT,
            "sources": sources,
            "gates": gates,
        }
    )
    implementation = ROOT / "src/v5_final/parent_native_development_execution_v1.py"
    identities: dict[str, Any] = {}
    for method in METHOD_IDS:
        identity = {
            "schema": "v5-final.parent-native-development-executor-identity.v1",
            "method_id": method,
            "entrypoint": (
                "v5_final.parent_native_development_execution_v1:"
                "execute_development_item_v1"
            ),
            "shared_method_service_entrypoint": (
                "v5_final.parent_native_execution_services:"
                "ParentNativeExecutionServices.execute_prepared"
            ),
            "implementation_path": str(implementation.relative_to(ROOT)),
            "implementation_sha256": _sha(implementation),
            "implementation_bundle_digest": bundle,
            "parent_commit": PARENT_COMMIT,
            "CEO_commit": CEO_COMMIT,
        }
        identity["executor_id"] = "parent-native-development-executor-v1:" + _digest(identity)
        identities[method] = identity
    return _with_digest(
        {
            "schema": "v5-final.parent-native-development-executor-manifest.v1",
            "status": "OUTCOME_FREE_ACTUAL_DEVELOPMENT_SERVICE_BOUND",
            "implementation_bundle_digest": bundle,
            "source_manifest": sources,
            "gate_manifest": gates,
            "executor_identities": identities,
            "physical_state_identity": "physical-state-v3",
            "candidate_work_binding_schema": (
                "v5-final.parent-native-candidate-work-binding.v2"
            ),
            "frozen_maximum_rounds_enforced_before_next_dynamic_catalog": True,
            "molecular_candidate_energy_evaluations": 0,
        },
        "manifest_digest",
    )


def _canonical_method(method_id: str) -> str:
    return METHOD_RENAME.get(method_id, method_id)


def _base_plan(
    catalog: Mapping[str, Any], executors: Mapping[str, Any]
) -> dict[str, Any]:
    old = _json(S5_QUEUE)
    policy_artifact = _json(S5_PROTOCOL)
    policy = policy_artifact["policy"]
    registry = _json(REGISTRY_PATH)
    environment = _json(ENVIRONMENT_PATH)
    owner = _json(OWNER_FREEZE)
    s10 = _json(S10)
    if s10.get("decision") != "GO_90_ITEM_EXECUTION_BINDING_FREEZE_ONLY":
        raise S11DevelopmentFreezeError("S10 did not authorize the S11 binding freeze")
    cases = {case["case_id"]: case for case in catalog["cases"]}
    sources = {source["case_id"]: source for source in registry["sources"]}
    items: list[dict[str, Any]] = []
    for predecessor in old["items"]:
        case_id = str(predecessor["case_id"])
        method = _canonical_method(str(predecessor["method_id"]))
        envelope = str(predecessor["work_envelope"])
        case = cases[case_id]
        source = sources[case_id]
        profile = policy["work_profiles"][envelope]
        cap = copy.deepcopy(profile["semantic_work_cap"])
        cap_value = WorkDelta(**cap)
        identity = executors["executor_identities"][method]
        body = {
            "case_id": case_id,
            "method_id": method,
            "work_envelope": envelope,
            "predecessor_queue_item_id": predecessor["queue_item_id"],
            "predecessor_method_id": predecessor["method_id"],
            "predecessor_policy_digest": predecessor["policy_digest"],
            "source_checkpoint_digest": case["source_checkpoint_digest"],
            "source_checkpoint_sha256": case["source_checkpoint_sha256"],
            "StatePreparationID": case["StatePreparationID"],
            "ProblemID": case["ProblemID"],
            "Hamiltonian_digest": case["Hamiltonian_digest"],
            "executor_id": identity["executor_id"],
            "executor_source_sha256": identity["implementation_sha256"],
            "executor_bundle_digest": executors["implementation_bundle_digest"],
            "protocol_digest": owner["protocol_digests"][method],
            "candidate_binding": _candidate_binding(method, case),
            "optimizer_policy_digest": _digest(policy["optimizer"]),
            "acceptance_policy_digest": _digest(policy["acceptance"]),
            "componentwise_work_cap": cap,
            "work_cap_digest": work_cap_digest(cap_value),
            "work_cap_provenance": {
                "source": str(S5_PROTOCOL.relative_to(ROOT)),
                "profile": envelope,
                "derivation": profile["derivation"],
                "classification": (
                    "pre-existing pre-outcome hard ceiling; not an empirical runtime estimate"
                ),
            },
            "maximum_rounds": int(profile["maximum_rounds"]),
            "RNG_identity": {"python_seed": 0, "numpy_seed": 0},
            "environment_digest": environment["environment_digest"],
            "resource_policy": {
                "counter": source["resources"]["counter_version"],
                "full_ansatz_recount": True,
                "barrier_free_full_ansatz_compilation": False,
            },
            "authorization_reference": {
                "path": str(S10.relative_to(ROOT)),
                "sha256": _sha(S10),
                "audit_digest": s10["audit_digest"],
                "decision": s10["decision"],
                "scope": "S11_OUTCOME_BLIND_SUCCESSOR_BINDING_ONLY",
            },
            "retry_policy": (
                "system-failure-only; preserve prior attempt and link digest"
            ),
            "systemic_abort_policy": (
                "stop entire queue on identity/counter/schema violation"
            ),
            "terminal_status": "NOT_STARTED",
        }
        if predecessor["source_checkpoint_sha256"] != source["checkpoint_sha256"]:
            raise S11DevelopmentFreezeError("predecessor/source checkpoint drift")
        item = dict(body)
        item["queue_item_id"] = "s11-development-preparation-item-v1:" + _digest(body)
        items.append(item)
    result = {
        "schema": "v5-final.s11-development-preparation-plan.v1",
        "stage": "S11_INTERNAL_OUTCOME_FREE_BINDING_PREPARATION",
        "status": "OUTCOME_FREE_INTERNAL_PREPARATION_ONLY",
        "generation_order": "frozen S5 case x LOW/MEDIUM/HIGH x method order",
        "items": items,
        "frozen_item_count": 90,
        "catalog_digest": catalog["catalog_digest"],
        "source_registry_digest": registry["registry_digest"],
        "environment_digest": environment["environment_digest"],
        "executor_manifest_digest": executors["manifest_digest"],
        "candidate_energy_evaluations": 0,
    }
    result["plan_digest"] = _digest(result)
    return result


def _candidate_work_binding(
    context: Any,
    item: Mapping[str, Any],
    preparation_cache: dict[str, Any],
) -> dict[str, Any]:
    prepared = prepare_method_executor(
        context, item, preparation_cache=preparation_cache
    )
    method = str(item["method_id"])
    if method in {"immutable-ceo-star-source", "same-structure-reoptimization"}:
        generated: tuple[tuple[str, str], ...] = ()
        expanded: tuple[str, ...] = ()
        recounts = rewrites = dynamic_upper = 0
        whitelist: tuple[str, ...] = ()
    elif method == "structural-magnitude-pruning":
        generated = _magnitude_bindings(context, item)
        if prepared.magnitude_deletion is None:
            raise S11DevelopmentFreezeError("magnitude preparation is absent")
        expanded = (dict(generated)[prepared.magnitude_deletion.candidate_id],)
        recounts, rewrites, dynamic_upper = 3, 1, len(generated)
        whitelist = ()
    else:
        if prepared.source_catalog is None:
            raise S11DevelopmentFreezeError("structural catalog is absent")
        generated = _single_candidate_bindings(context, prepared.source_catalog)
        if method == "v4.1-one-shot-joint-compression":
            expanded = tuple(
                canonical_proposed_physical_state_id(
                    problem_id=context.problem_id,
                    state_preparation_spec=plan.proposed_state_preparation_spec,
                )
                for plan in prepared.candidate_plans
            )
            recounts = 3 * len(prepared.prepared_rewrites)
            rewrites = sum(len(plan.candidates) for plan in prepared.candidate_plans)
            dynamic_upper = 0
            whitelist = ()
        else:
            expanded = tuple(physical_id for _, physical_id in generated)
            recounts, rewrites = 3 * len(generated), len(generated)
            dynamic_upper = len(generated)
            whitelist = (
                tuple(
                    sorted(
                        candidate_structural_whitelist_key(candidate)
                        for candidate in prepared.source_catalog.candidates
                    )
                )
                if method == "v5-fixed-source-whitelist-no-replenishment"
                else ()
            )
    result = CandidateWorkBinding(
        generated,
        tuple(dict.fromkeys(expanded)),
        recounts,
        rewrites,
        dynamic_upper,
        whitelist,
    ).to_dict()
    if (
        len(generated) != prepared.generated_candidate_intents
        or len(set(expanded)) != prepared.unique_proposed_physical_states
    ):
        raise S11DevelopmentFreezeError("candidate work binding differs from executor")
    return result


def build_plan(
    catalog: Mapping[str, Any], executors: Mapping[str, Any]
) -> dict[str, Any]:
    preparation = _base_plan(catalog, executors)
    bindings: dict[tuple[str, str], dict[str, Any]] = {}
    for case_id in DEVELOPMENT_CASES:
        case_items = [item for item in preparation["items"] if item["case_id"] == case_id]
        first = case_items[0]
        context = build_queue_bound_development_runtime_v1(
            first["queue_item_id"],
            plan_record=preparation,
            catalog_record=catalog,
        )
        cache: dict[str, Any] = {}
        for method in METHOD_IDS:
            item = next(
                value
                for value in case_items
                if value["work_envelope"] == "LOW" and value["method_id"] == method
            )
            method_context = replace(
                context,
                queue_item_id=item["queue_item_id"],
                method_id=method,
            )
            bindings[(case_id, method)] = _candidate_work_binding(
                method_context, item, cache
            )
    items: list[dict[str, Any]] = []
    for old in preparation["items"]:
        item = copy.deepcopy(old)
        item["candidate_work_binding"] = copy.deepcopy(
            bindings[(str(item["case_id"]), str(item["method_id"]))]
        )
        body = {key: value for key, value in item.items() if key != "queue_item_id"}
        item["queue_item_id"] = "development-queue-item-v4:" + _digest(body)
        items.append(item)
    environment = _json(ENVIRONMENT_PATH)
    registry = _json(REGISTRY_PATH)
    result = {
        "schema": "v5-final.s11-development-plan.v4",
        "stage": "S11_OUTCOME_BLIND_90_ITEM_SUCCESSOR_FREEZE",
        "status": "FROZEN_NOT_AUTHORIZED_FOR_EXECUTION",
        "generation_order": preparation["generation_order"],
        "items": items,
        "frozen_item_count": 90,
        "catalog_path": str(CATALOG_OUTPUT.relative_to(ROOT)),
        "catalog_sha256": "BOUND_AFTER_EXCLUSIVE_WRITE",
        "catalog_digest": catalog["catalog_digest"],
        "source_registry_path": str(REGISTRY_PATH.relative_to(ROOT)),
        "source_registry_sha256": _sha(REGISTRY_PATH),
        "source_registry_digest": registry["registry_digest"],
        "environment_path": str(ENVIRONMENT_PATH.relative_to(ROOT)),
        "environment_sha256": _sha(ENVIRONMENT_PATH),
        "environment_digest": environment["environment_digest"],
        "executor_manifest_path": str(EXECUTOR_OUTPUT.relative_to(ROOT)),
        "executor_manifest_sha256": "BOUND_AFTER_EXCLUSIVE_WRITE",
        "executor_manifest_digest": executors["manifest_digest"],
        "executor_bundle_digest": executors["implementation_bundle_digest"],
        "persistent_runner_sha256": _sha(
            ROOT / "src/v5_final/parent_native_persistent_runner.py"
        ),
        "predecessor_queue": {
            "path": str(S5_QUEUE.relative_to(ROOT)),
            "sha256": _sha(S5_QUEUE),
            "queue_digest": _json(S5_QUEUE)["queue_digest"],
            "direct_execution_authorized": False,
        },
        "candidate_energy_evaluations": 0,
        "successor_provenance": {
            "allowed_changes": [
                "schema/version and queue/item IDs",
                "legacy no-rebuild label to exact fixed-source-whitelist/no-replenishment label",
                "parent-native executor/runtime/source identities",
                "outcome-free structural candidate/work bindings",
                "S10 authorization reference",
            ],
            "scientific_protocol_changed": False,
            "calibration_outcome_used_for_selection": False,
            "method_or_budget_dropped": False,
        },
    }
    result["plan_digest"] = _digest(result)
    return result


def bind_plan_artifact_sha(
    plan: Mapping[str, Any], *, catalog_sha256: str, executor_sha256: str
) -> dict[str, Any]:
    result = copy.deepcopy(dict(plan))
    result.pop("plan_digest", None)
    result["catalog_sha256"] = catalog_sha256
    result["executor_manifest_sha256"] = executor_sha256
    result["plan_digest"] = _digest(result)
    return result


def build_ledger(plan: Mapping[str, Any]) -> dict[str, Any]:
    return _with_digest(
        {
            "schema": "v5-final.s11-development-ledger-root.v4",
            "plan_path": str(PLAN_OUTPUT.relative_to(ROOT)),
            "plan_artifact_sha256": "BOUND_AFTER_EXCLUSIVE_WRITE",
            "plan_digest": plan["plan_digest"],
            "expected_queue_item_ids": [item["queue_item_id"] for item in plan["items"]],
            "expected_queue_count": 90,
            "completed_queue_item_ids": [],
            "raw_ledger_directories": [],
            "terminal_segments": [],
            "candidate_energy_evaluations": 0,
            "completeness_contract": {
                "expected_queue_nonempty": True,
                "frozen_queue_count": 90,
                "frozen_plan_artifact_sha256_required": True,
                "expected_plan_digest_must_match": True,
                "every_and_only_expected_item_terminal": True,
                "exactly_one_terminal_per_item_after_linked_retries": True,
                "raw_work_reconstructs_every_summary": True,
                "outcome_checkpoint_bound_before_terminal": True,
            },
        },
        "ledger_root_digest",
    )


def bind_ledger_plan_sha(
    ledger: Mapping[str, Any], plan_sha256: str
) -> dict[str, Any]:
    result = copy.deepcopy(dict(ledger))
    result.pop("ledger_root_digest", None)
    result["plan_artifact_sha256"] = plan_sha256
    return _with_digest(result, "ledger_root_digest")


def build_semantic_diff(plan: Mapping[str, Any]) -> dict[str, Any]:
    old = _json(S5_QUEUE)
    policy = _json(S5_PROTOCOL)["policy"]
    ledger = _json(S5_LEDGER)
    pairs = list(zip(old["items"], plan["items"], strict=True))
    expected_order = [
        (item["case_id"], item["work_envelope"], _canonical_method(item["method_id"]))
        for item in old["items"]
    ]
    observed_order = [
        (item["case_id"], item["work_envelope"], item["method_id"])
        for item in plan["items"]
    ]
    checks = {
        "exact_5x3x6_grid": len(pairs) == 90
        and len({item["case_id"] for item in plan["items"]}) == 5
        and len({item["work_envelope"] for item in plan["items"]}) == 3
        and {item["method_id"] for item in plan["items"]} == set(METHOD_IDS),
        "frozen_order_identical_after_declared_rename": expected_order == observed_order,
        "predecessor_item_identity_bound": all(
            new["predecessor_queue_item_id"] == prior["queue_item_id"]
            and new["predecessor_policy_digest"] == prior["policy_digest"]
            for prior, new in pairs
        ),
        "source_checkpoint_SHA_identical": all(
            new["source_checkpoint_sha256"] == prior["source_checkpoint_sha256"]
            for prior, new in pairs
        ),
        "componentwise_caps_identical": all(
            new["componentwise_work_cap"]
            == policy["work_profiles"][new["work_envelope"]]["semantic_work_cap"]
            for new in plan["items"]
        ),
        "maximum_rounds_identical": all(
            new["maximum_rounds"]
            == policy["work_profiles"][new["work_envelope"]]["maximum_rounds"]
            for new in plan["items"]
        ),
        "optimizer_and_acceptance_identical": all(
            new["optimizer_policy_digest"] == _digest(policy["optimizer"])
            and new["acceptance_policy_digest"] == _digest(policy["acceptance"])
            for new in plan["items"]
        ),
        "only_declared_method_rename": all(
            new["method_id"] == _canonical_method(prior["method_id"])
            for prior, new in pairs
        ),
        "FCI_and_outcomes_excluded": all(
            new["candidate_binding"].get("FCI_used", False) is False
            and new["candidate_binding"].get("candidate_energy_used", False) is False
            and new["candidate_binding"].get("development_outcome_used", False) is False
            and new["candidate_binding"].get("historical_rank_used", False) is False
            for new in plan["items"]
        ),
        "candidate_work_bindings_content_addressed": all(
            item["candidate_work_binding"]["binding_digest"]
            == _digest(
                {
                    key: value
                    for key, value in item["candidate_work_binding"].items()
                    if key != "binding_digest"
                }
            )
            for item in plan["items"]
        ),
        "candidate_work_budget_invariant": all(
            len(
                {
                    item["candidate_work_binding"]["binding_digest"]
                    for item in plan["items"]
                    if item["case_id"] == case_id and item["method_id"] == method
                }
            )
            == 1
            for case_id in DEVELOPMENT_CASES
            for method in METHOD_IDS
        ),
        "all_not_started_candidate_energy_zero": all(
            item["terminal_status"] == "NOT_STARTED" for item in plan["items"]
        )
        and plan["candidate_energy_evaluations"] == 0,
        "predecessor_queue_and_ledger_untouched": old["expected_queue_count"] == 90
        and all(item["terminal_status"] == "NOT_STARTED" for item in old["items"])
        and not ledger["segments"]
        and not ledger["completed_queue_item_ids"]
        and ledger["development_candidate_energy_evaluations"] == 0,
        "barrier_free_compilation_forbidden": all(
            item["resource_policy"]["barrier_free_full_ansatz_compilation"] is False
            for item in plan["items"]
        ),
    }
    if not all(checks.values()):
        raise S11DevelopmentFreezeError("S11 semantic diff exceeded allowed scope")
    return _with_digest(
        {
            "schema": "v5-final.s11-s5-v3-v4-semantic-diff-audit.v1",
            "predecessor_queue_path": str(S5_QUEUE.relative_to(ROOT)),
            "predecessor_queue_sha256": _sha(S5_QUEUE),
            "successor_plan_digest": plan["plan_digest"],
            "checks": checks,
            "allowed_changes_only": True,
            "method_rename": METHOD_RENAME,
            "academic_boundary": (
                "No case, source, budget, order, threshold, cap, RNG, resource "
                "policy, or FCI firewall changed. The sole method label change "
                "states the already-frozen fixed-whitelist/no-replenishment semantics."
            ),
        },
        "audit_digest",
    )


def build_freeze(
    catalog: Mapping[str, Any],
    executors: Mapping[str, Any],
    plan: Mapping[str, Any],
    ledger: Mapping[str, Any],
    semantic_diff: Mapping[str, Any],
    independently_rebuilt_plan: Mapping[str, Any],
) -> dict[str, Any]:
    s10 = _json(S10)
    checks = {
        "S10_authorized_binding_freeze_only": s10["decision"]
        == "GO_90_ITEM_EXECUTION_BINDING_FREEZE_ONLY",
        "catalog_exact_five_outcome_free_sources": len(catalog["cases"]) == 5
        and catalog["candidate_energy_evaluations"] == 0
        and not any(catalog["molecular_kernel_guard_calls"].values()),
        "executor_manifest_outcome_free": executors[
            "molecular_candidate_energy_evaluations"
        ]
        == 0,
        "plan_exact_90_unique_unstarted": len(plan["items"]) == 90
        and len({item["queue_item_id"] for item in plan["items"]}) == 90
        and all(item["terminal_status"] == "NOT_STARTED" for item in plan["items"]),
        "plan_independent_rebuild_byte_identical": canonical_json_bytes(plan)
        == canonical_json_bytes(independently_rebuilt_plan),
        "semantic_diff_exact": semantic_diff["allowed_changes_only"] is True
        and all(semantic_diff["checks"].values()),
        "ledger_frozen_queue_binding_complete": ledger["expected_queue_count"] == 90
        and ledger["plan_digest"] == plan["plan_digest"]
        and ledger["plan_artifact_sha256"] == _sha(PLAN_OUTPUT),
        "ledger_empty_and_candidate_energy_zero": not ledger[
            "completed_queue_item_ids"
        ]
        and not ledger["raw_ledger_directories"]
        and not ledger["terminal_segments"]
        and ledger["candidate_energy_evaluations"] == 0,
        "all_cross_artifact_SHA_bindings_exact": plan["catalog_sha256"]
        == _sha(CATALOG_OUTPUT)
        and plan["executor_manifest_sha256"] == _sha(EXECUTOR_OUTPUT),
    }
    if not all(checks.values()):
        raise S11DevelopmentFreezeError("S11 freeze checks failed")
    return _with_digest(
        {
            "schema": "v5-final.s11-development-outcome-blind-freeze.v4",
            "stage": "S11_90_ITEM_SUCCESSOR_FREEZE",
            "status": "PASS_OUTCOME_BLIND_SUCCESSOR_FROZEN_EXECUTION_BLOCKED",
            "decision": "READY_FOR_S11_STATIC_EXACT_CI_ONLY",
            "artifacts": {
                "catalog": {
                    "path": str(CATALOG_OUTPUT.relative_to(ROOT)),
                    "sha256": _sha(CATALOG_OUTPUT),
                    "digest": catalog["catalog_digest"],
                },
                "executors": {
                    "path": str(EXECUTOR_OUTPUT.relative_to(ROOT)),
                    "sha256": _sha(EXECUTOR_OUTPUT),
                    "digest": executors["manifest_digest"],
                },
                "plan": {
                    "path": str(PLAN_OUTPUT.relative_to(ROOT)),
                    "sha256": _sha(PLAN_OUTPUT),
                    "digest": plan["plan_digest"],
                },
                "ledger": {
                    "path": str(LEDGER_OUTPUT.relative_to(ROOT)),
                    "sha256": _sha(LEDGER_OUTPUT),
                    "digest": ledger["ledger_root_digest"],
                },
                "semantic_diff": {
                    "path": str(DIFF_OUTPUT.relative_to(ROOT)),
                    "sha256": _sha(DIFF_OUTPUT),
                    "digest": semantic_diff["audit_digest"],
                },
            },
            "checks": checks,
            "candidate_molecular_energy_evaluations": 0,
            "authorization": {
                "static_exact_CI": "AUTHORIZED_ONLY",
                "development_execution": "NOT_AUTHORIZED",
                "performance_claim": "NOT_AUTHORIZED",
                "FCI_reporting": "NOT_AUTHORIZED_UNTIL_ALL_90_TERMINAL",
                "release": "NOT_AUTHORIZED",
            },
            "academic_boundary": (
                "This artifact freezes the complete known-development grid before "
                "any S11 candidate outcome. Calibration did not select or drop a "
                "method, case, or budget. It is not performance evidence."
            ),
        },
        "freeze_digest",
    )


def _build_unbound() -> tuple[dict[str, Any], ...]:
    catalog = build_catalog()
    executors = build_executor_manifest()
    plan = build_plan(catalog, executors)
    return catalog, executors, plan


def audit_static() -> dict[str, bool]:
    catalog = _json(CATALOG_OUTPUT)
    executors = _json(EXECUTOR_OUTPUT)
    plan = _json(PLAN_OUTPUT)
    ledger = _json(LEDGER_OUTPUT)
    semantic_diff = _json(DIFF_OUTPUT)
    freeze = _json(FREEZE_OUTPUT)
    checks = {
        "catalog_digest_valid": catalog["catalog_digest"]
        == _digest({key: value for key, value in catalog.items() if key != "catalog_digest"}),
        "catalog_five_cases_zero_outcome": len(catalog["cases"]) == 5
        and catalog["candidate_energy_evaluations"] == 0
        and not any(catalog["molecular_kernel_guard_calls"].values()),
        "executor_digest_valid": executors["manifest_digest"]
        == _digest({key: value for key, value in executors.items() if key != "manifest_digest"}),
        "executor_sources_unchanged": all(
            _sha(ROOT / item["path"]) == item["sha256"]
            for item in executors["source_manifest"]
        ),
        "executor_gates_unchanged": all(
            _sha(ROOT / item["path"]) == item["sha256"]
            for item in executors["gate_manifest"]
        ),
        "plan_digest_valid": plan["plan_digest"]
        == _digest({key: value for key, value in plan.items() if key != "plan_digest"}),
        "plan_exact_90_content_addressed_unstarted": len(plan["items"]) == 90
        and len({item["queue_item_id"] for item in plan["items"]}) == 90
        and all(
            item["queue_item_id"]
            == "development-queue-item-v4:"
            + _digest({key: value for key, value in item.items() if key != "queue_item_id"})
            and item["terminal_status"] == "NOT_STARTED"
            for item in plan["items"]
        ),
        "plan_cross_artifact_bindings_exact": plan["catalog_sha256"]
        == _sha(CATALOG_OUTPUT)
        and plan["executor_manifest_sha256"] == _sha(EXECUTOR_OUTPUT)
        and plan["source_registry_sha256"] == _sha(REGISTRY_PATH)
        and plan["environment_sha256"] == _sha(ENVIRONMENT_PATH),
        "ledger_digest_and_plan_binding_valid": ledger["ledger_root_digest"]
        == _digest({key: value for key, value in ledger.items() if key != "ledger_root_digest"})
        and ledger["plan_digest"] == plan["plan_digest"]
        and ledger["plan_artifact_sha256"] == _sha(PLAN_OUTPUT)
        and ledger["expected_queue_item_ids"]
        == [item["queue_item_id"] for item in plan["items"]]
        and not ledger["completed_queue_item_ids"]
        and not ledger["terminal_segments"],
        "semantic_diff_digest_and_checks_valid": semantic_diff["audit_digest"]
        == _digest(
            {key: value for key, value in semantic_diff.items() if key != "audit_digest"}
        )
        and all(semantic_diff["checks"].values()),
        "freeze_digest_and_checks_valid": freeze["freeze_digest"]
        == _digest({key: value for key, value in freeze.items() if key != "freeze_digest"})
        and all(freeze["checks"].values()),
        "freeze_artifacts_bound": all(
            _sha(ROOT / value["path"]) == value["sha256"]
            for value in freeze["artifacts"].values()
        ),
        "execution_and_claims_blocked": freeze["authorization"][
            "development_execution"
        ]
        == "NOT_AUTHORIZED"
        and freeze["authorization"]["performance_claim"] == "NOT_AUTHORIZED"
        and freeze["candidate_molecular_energy_evaluations"] == 0,
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S11DevelopmentFreezeError(
            "S11 static audit failed: " + ", ".join(failures)
        )
    return checks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--static-audit", action="store_true")
    args = parser.parse_args()
    if args.static_audit:
        print(json.dumps(audit_static(), sort_keys=True))
        return
    if not args.write:
        raise S11DevelopmentFreezeError(
            "use --write for the one-time local outcome-free freeze or --static-audit"
        )
    if S11_FREEZE_DIR.exists():
        raise S11DevelopmentFreezeError("S11 successor namespace already exists")
    first = _build_unbound()
    second = _build_unbound()
    if any(
        canonical_json_bytes(left) != canonical_json_bytes(right)
        for left, right in zip(first, second, strict=True)
    ):
        raise S11DevelopmentFreezeError("two independent S11 builds differ")
    catalog, executors, unbound_plan = first
    S11_FREEZE_DIR.mkdir(parents=True, exist_ok=False)
    write_json_exclusive(CATALOG_OUTPUT, catalog)
    write_json_exclusive(EXECUTOR_OUTPUT, executors)
    plan = bind_plan_artifact_sha(
        unbound_plan,
        catalog_sha256=_sha(CATALOG_OUTPUT),
        executor_sha256=_sha(EXECUTOR_OUTPUT),
    )
    second_plan = bind_plan_artifact_sha(
        second[2],
        catalog_sha256=_sha(CATALOG_OUTPUT),
        executor_sha256=_sha(EXECUTOR_OUTPUT),
    )
    write_json_exclusive(PLAN_OUTPUT, plan)
    ledger = bind_ledger_plan_sha(build_ledger(plan), _sha(PLAN_OUTPUT))
    write_json_exclusive(LEDGER_OUTPUT, ledger)
    semantic_diff = build_semantic_diff(plan)
    write_json_exclusive(DIFF_OUTPUT, semantic_diff)
    freeze = build_freeze(
        catalog, executors, plan, ledger, semantic_diff, second_plan
    )
    write_json_exclusive(FREEZE_OUTPUT, freeze)
    print(FREEZE_OUTPUT)


if __name__ == "__main__":
    main()

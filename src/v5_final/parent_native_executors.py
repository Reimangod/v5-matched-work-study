"""Outcome-free preparation of six actual parent-native method executors.

This module binds the frozen method contracts to actual parent candidates,
composition, OBS warm starts, circuit recounts, optimizer, acceptance, and
transaction entrypoints.  Preparation is structural only.  Molecular outcome
kernels remain behind the S8 guard in ``QueueBoundMolecularRuntime``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import inspect
from pathlib import Path
import struct
from typing import Any, Mapping, Protocol, Sequence

import numpy as np

from dvg_obs_ceo.calibration import obs_warm_start
from dvg_obs_ceo.composition import pairwise_compatibility
from dvg_obs_ceo.identity import canonical_json_bytes as parent_canonical_json_bytes
from dvg_obs_ceo.resources import (
    AnsatzStructure,
    evaluate_full_circuit_resources,
    paper_era_backend,
)
from dvg_obs_ceo.v5_pareto import (
    RiskAwareCandidate,
    RiskDiagnostics,
    select_risk_aware_pareto,
)

from .parent_native_candidate_adapter import (
    ParentNativeCandidatePlan,
    ParentNativeCatalog,
    build_typed_catalog,
    compose_parent_native_plan,
)
from .parent_native_rewrite import PreparedParentRewrite, prepare_rewrite_for_optimizer
from .parent_native_physical_identity import canonical_proposed_physical_state_id
from .parent_native_runtime_factory import QueueBoundMolecularRuntime, ROOT


METHOD_IDS = (
    "immutable-ceo-star-source",
    "same-structure-reoptimization",
    "structural-magnitude-pruning",
    "v4.1-one-shot-joint-compression",
    "v5-fixed-source-whitelist-no-replenishment",
    "v5-sequential-with-rebuilding",
)
OUTCOME_ENTRYPOINTS = (
    "adaptvqe.minimize:minimize_bfgs",
    "dvg_obs_ceo.transaction:evaluate_acceptance",
    "dvg_obs_ceo.v5_nested_transaction:NestedRoundTransaction",
)


class ParentNativeExecutorError(RuntimeError):
    pass


class AuthorizedExecutionServices(Protocol):
    def execute_prepared(self, executor: "PreparedMethodNativeExecutor") -> Any: ...


def _digest(value: Any) -> str:
    return hashlib.sha256(parent_canonical_json_bytes(value)).hexdigest()


def _float_hex(value: float) -> str:
    return struct.pack(">d", abs(float(value)) ** 2).hex()


def _resource_vector(result: Any) -> dict[str, int]:
    snapshot = result.snapshot
    return {
        "cnot_count": int(snapshot.cnot_count),
        "cnot_depth": int(snapshot.cnot_depth),
        "total_depth": int(snapshot.total_depth),
        "parameter_count": int(snapshot.parameter_count),
        "logical_block_count": int(snapshot.logical_block_count),
    }


def _source_id_set(item: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(
        str(candidate["candidate_structural_id"])
        for candidate in item["candidate_binding"]["candidate_set"]
    )


def _validate_item(context: QueueBoundMolecularRuntime, item: Mapping[str, Any]) -> None:
    if item.get("method_id") not in METHOD_IDS:
        raise ParentNativeExecutorError("unregistered method-native queue item")
    expected = {
        "case_id": context.case_id,
        "StatePreparationID": context.state_preparation_id,
        "ProblemID": context.problem_id,
        "Hamiltonian_digest": context.hamiltonian_digest,
        "source_checkpoint_digest": context.source_checkpoint_digest,
        "environment_digest": context.environment_digest,
    }
    if any(item.get(key) != value for key, value in expected.items()):
        raise ParentNativeExecutorError("method queue item differs from bound source runtime")
    if item.get("terminal_status") != "NOT_STARTED":
        raise ParentNativeExecutorError("method queue item is not outcome-free")


@dataclass(frozen=True)
class PreparedMagnitudeDeletion:
    candidate_id: str
    position: int
    pool_index: int
    target: Any
    proposed_state_preparation_id: str
    before_resources: dict[str, int]
    after_resources: dict[str, int]

    def to_audit_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "position": self.position,
            "pool_index": self.pool_index,
            "source_indices": None,
            "target_indices": list(self.target.indices),
            "target_coefficients_count": len(self.target.coefficients),
            "proposed_state_preparation_id": self.proposed_state_preparation_id,
            "before_resources": self.before_resources,
            "after_resources": self.after_resources,
            "physical_generator_deleted": True,
            "coefficient_zeroing_only": False,
            "full_circuit_rebuild_and_recount": True,
        }


@dataclass(frozen=True)
class PreparedMethodNativeExecutor:
    method_id: str
    case_id: str
    queue_item_id: str
    context: QueueBoundMolecularRuntime
    source_catalog: ParentNativeCatalog | None
    queue_candidate_ids: tuple[str, ...]
    selected_candidate_ids: tuple[str, ...]
    candidate_plans: tuple[ParentNativeCandidatePlan, ...]
    prepared_rewrites: tuple[PreparedParentRewrite, ...]
    magnitude_deletion: PreparedMagnitudeDeletion | None
    generated_candidate_intents: int
    unique_proposed_physical_states: int
    execution_directives: dict[str, Any]
    v4_frozen_incompatible_ids: tuple[str, ...]

    def execute(self, services: AuthorizedExecutionServices) -> Any:
        return services.execute_prepared(self)

    def to_audit_dict(self) -> dict[str, Any]:
        return {
            "method_id": self.method_id,
            "case_id": self.case_id,
            "queue_item_id": self.queue_item_id,
            "source_catalog_type": (
                None if self.source_catalog is None else type(self.source_catalog).__name__
            ),
            "actual_candidate_types": (
                []
                if self.source_catalog is None
                else sorted({type(value).__name__ for value in self.source_catalog.candidates})
            ),
            "queue_candidate_ids": list(self.queue_candidate_ids),
            "selected_candidate_ids": list(self.selected_candidate_ids),
            "candidate_plans": [plan.to_audit_dict() for plan in self.candidate_plans],
            "prepared_rewrites": [value.to_audit_dict() for value in self.prepared_rewrites],
            "magnitude_deletion": (
                None if self.magnitude_deletion is None else self.magnitude_deletion.to_audit_dict()
            ),
            "generated_candidate_intents": self.generated_candidate_intents,
            "unique_proposed_physical_states": self.unique_proposed_physical_states,
            "execution_directives": self.execution_directives,
            "v4_frozen_incompatible_ids": list(self.v4_frozen_incompatible_ids),
            "candidate_energy_evaluations": 0,
            "optimizer_calls": 0,
            "execution_authorized": False,
        }


def _compose(
    context: QueueBoundMolecularRuntime,
    catalog: ParentNativeCatalog,
    candidates: Sequence[Any],
) -> ParentNativeCandidatePlan:
    return compose_parent_native_plan(
        pool=context.pool,
        source=context.runtime.ansatz,
        catalog=catalog,
        candidates=candidates,
        gradient=context.runtime.gradient,
        inverse_hessian=context.runtime.inverse_hessian,
        problem_id=context.problem_id,
        reference_state=context._actual_algorithm.ref_det,
    )


def _compatible_v4_sentinels(
    catalog: ParentNativeCatalog, frozen_ids: Sequence[str]
) -> tuple[tuple[Any, ...], tuple[str, ...]]:
    by_id = {candidate.candidate_id: candidate for candidate in catalog.candidates}
    block_by_id = {block.block_id: block for block in catalog.blocks}
    selected: list[Any] = []
    incompatible: list[str] = []
    for candidate_id in frozen_ids:
        candidate = by_id.get(candidate_id)
        if candidate is None:
            raise ParentNativeExecutorError("V4.1 frozen sentinel is absent")
        block = block_by_id[candidate.source_block_id]
        compatible = all(
            pairwise_compatibility(
                existing,
                block_by_id[existing.source_block_id],
                candidate,
                block,
            ).compatible
            for existing in selected
        )
        if compatible:
            selected.append(candidate)
        else:
            incompatible.append(candidate_id)
    if not selected:
        raise ParentNativeExecutorError("V4.1 has no compatible frozen sentinel")
    return tuple(selected), tuple(incompatible)


def _rank_parent_candidates(
    context: QueueBoundMolecularRuntime,
    catalog: ParentNativeCatalog,
    admitted_ids: set[str],
) -> tuple[tuple[ParentNativeCandidatePlan, ...], tuple[PreparedParentRewrite, ...], dict[str, Any]]:
    before = evaluate_full_circuit_resources(
        context.pool, context.runtime.ansatz, paper_era_backend()
    )
    representatives: dict[
        str,
        tuple[RiskAwareCandidate, ParentNativeCandidatePlan, PreparedParentRewrite],
    ] = {}
    proposed_ids: set[str] = set()
    for candidate in catalog.candidates:
        if candidate.candidate_id not in admitted_ids:
            continue
        plan = _compose(context, catalog, (candidate,))
        rewrite = prepare_rewrite_for_optimizer(
            pool=context.pool,
            source=context.runtime.ansatz,
            parent_plan=plan,
        )
        _, _, prediction = obs_warm_start(
            context.runtime.ansatz.coefficients,
            context.runtime.gradient,
            context.runtime.inverse_hessian,
            plan.joint_plan.transformation,
        )
        risk = RiskAwareCandidate(
            candidate_ids=(candidate.candidate_id,),
            constraint_semantic_id=plan.constraint_semantic_id,
            constraint_numerical_id=plan.constraint_numerical_id,
            predicted_loss_hartree=max(
                0.0, float(prediction.predicted_change_from_current)
            ),
            resources=rewrite.after_resources.snapshot,
            diagnostics=RiskDiagnostics(
                quality_gate_passed=True,
                uncertainty_margin_hartree=0.0,
                quality_stratum="good",
                refinement_required=False,
                evidence_digest=_digest(
                    {
                        "candidate_id": candidate.candidate_id,
                        "constraint_semantic_id": plan.constraint_semantic_id,
                        "constraint_numerical_id": plan.constraint_numerical_id,
                    }
                ),
            ),
            full_resource_recount_succeeded=True,
            semantics_validated=True,
        )
        previous = representatives.get(plan.constraint_semantic_id)
        if previous is None or risk.candidate_ids < previous[0].candidate_ids:
            representatives[plan.constraint_semantic_id] = (risk, plan, rewrite)
        proposed_ids.add(
            canonical_proposed_physical_state_id(
                problem_id=context.problem_id,
                state_preparation_spec=plan.proposed_state_preparation_spec,
            )
        )
    ordered = sorted(
        representatives.values(), key=lambda value: value[0].candidate_ids
    )
    risks = [value[0] for value in ordered]
    by_semantic = {
        value[1].constraint_semantic_id: (value[1], value[2]) for value in ordered
    }
    selection = select_risk_aware_pareto(
        risks,
        before.snapshot,
        screening_budget_hartree=1e-4,
        top_k_per_endpoint=2,
        maximum_unique_attempts=4,
        require_no_component_regression=True,
    )
    pairs = [
        by_semantic[semantic_id]
        for semantic_id in selection["unique_attempt_semantic_ids"]
    ]
    return (
        tuple(pair[0] for pair in pairs),
        tuple(pair[1] for pair in pairs),
        {
            "selection_digest": selection["selection_digest"],
            "generated_and_admitted_candidate_count": len(admitted_ids),
            "semantic_representative_count": len(risks),
            "semantic_alias_count": len(admitted_ids) - len(risks),
            "selected_attempt_count": len(pairs),
            "unique_proposed_physical_state_count": len(proposed_ids),
        },
    )


def _prepare_magnitude(
    context: QueueBoundMolecularRuntime, item: Mapping[str, Any]
) -> tuple[PreparedMagnitudeDeletion, int]:
    from dvg_obs_ceo.block_ir import recover_dvg_blocks
    from dvg_obs_ceo.identity import StatePreparationSpec
    from dvg_obs_ceo.molecular_identity import generator_definition_digest

    source = context.runtime.ansatz
    frozen = list(item["candidate_binding"]["candidate_set"])
    if len(frozen) != len(source.indices):
        raise ParentNativeExecutorError("magnitude queue does not cover every source coordinate")
    recomputed = []
    for position, (pool_index, coefficient) in enumerate(
        zip(source.indices, source.coefficients)
    ):
        payload = {
            "source_state_preparation_id": context.state_preparation_id,
            "position": position,
            "pool_index": pool_index,
            "constraint": "theta_i->0",
            "physical_generator_deletion": True,
        }
        recomputed.append(
            (
                "magnitude-delete-v1:" + _digest(payload),
                _float_hex(coefficient),
                position,
                int(pool_index),
            )
        )
    recomputed.sort(key=lambda value: (value[1], value[0]))
    observed = [
        (
            str(value["candidate_structural_id"]),
            str(value["magnitude_score_float64_hex"]),
            int(value["ansatz_position"]),
            int(value["pool_index"]),
        )
        for value in frozen
    ]
    if observed != recomputed:
        raise ParentNativeExecutorError("magnitude queue differs from actual source coordinates")
    candidate_id, _, position, pool_index = recomputed[0]
    iteration = next(
        index
        for index, stop in enumerate(source.cumulative_parameter_counts)
        if position < stop
    )
    counts = tuple(
        count if index < iteration else count - 1
        for index, count in enumerate(source.cumulative_parameter_counts)
    )
    target = AnsatzStructure.create(
        source.indices[:position] + source.indices[position + 1 :],
        source.coefficients[:position] + source.coefficients[position + 1 :],
        counts,
    )
    blocks = recover_dvg_blocks(
        context.pool,
        target.indices,
        target.coefficients,
        target.cumulative_parameter_counts,
    )
    state = StatePreparationSpec.create(
        reference_state=context._actual_algorithm.ref_det,
        generator_definition_digest=generator_definition_digest(context.pool),
        ansatz_block_structure=((block.family, block.pool_indices) for block in blocks),
        ansatz_indices=target.indices,
        coefficients=target.coefficients,
        orbital_parameters=(),
        qubit_mapping="openfermion-jordan-wigner-v1",
        qubit_ordering=range(int(context._actual_algorithm.n)),
    )
    before = evaluate_full_circuit_resources(context.pool, source, paper_era_backend())
    after = evaluate_full_circuit_resources(context.pool, target, paper_era_backend())
    structural = evaluate_full_circuit_resources(
        context.pool,
        target,
        paper_era_backend(),
        coefficient_policy="deterministic-structural",
    )
    if after.snapshot != structural.snapshot:
        raise ParentNativeExecutorError("magnitude physical/structural recount mismatch")
    return (
        PreparedMagnitudeDeletion(
            candidate_id,
            position,
            pool_index,
            target,
            state.state_preparation_id,
            _resource_vector(before),
            _resource_vector(after),
        ),
        len(recomputed),
    )


def prepare_method_executor(
    context: QueueBoundMolecularRuntime,
    item: Mapping[str, Any],
    *,
    preparation_cache: dict[str, Any] | None = None,
) -> PreparedMethodNativeExecutor:
    _validate_item(context, item)
    method = str(item["method_id"])
    queue_ids = _source_id_set(item)
    source_catalog = None
    selected_ids: tuple[str, ...] = ()
    plans: tuple[ParentNativeCandidatePlan, ...] = ()
    rewrites: tuple[PreparedParentRewrite, ...] = ()
    magnitude = None
    generated = 0
    unique_states = 0
    incompatible: tuple[str, ...] = ()
    directives: dict[str, Any] = {
        "optimizer_entrypoint": "adaptvqe.minimize:minimize_bfgs",
        "acceptance_entrypoint": "dvg_obs_ceo.transaction:evaluate_acceptance",
        "transaction_entrypoint": (
            "dvg_obs_ceo.v5_nested_transaction:NestedRoundTransaction"
        ),
        "rollback_scope": [
            "ansatz",
            "parameters",
            "optimizer_inverse_hessian",
            "resources",
            "ledger_transaction",
        ],
    }

    if method == "immutable-ceo-star-source":
        if queue_ids:
            raise ParentNativeExecutorError("immutable source queue has candidates")
        directives.update(
            selection="none",
            optimization=False,
            source_structure_preserved=True,
        )
    elif method == "same-structure-reoptimization":
        if queue_ids:
            raise ParentNativeExecutorError("same-structure queue has candidates")
        directives.update(
            selection="same source structure",
            optimization=True,
            optimizer_target="source indices and source coordinates",
            source_structure_preserved=True,
        )
    elif method == "structural-magnitude-pruning":
        magnitude, generated = _prepare_magnitude(context, item)
        selected_ids = (magnitude.candidate_id,)
        unique_states = 1
        directives.update(
            selection="minimum theta_i^2; canonical structural-ID tie break",
            optimization=True,
            sequential_commits=True,
            post_commit_score_rebuild=True,
            physical_generator_deletion=True,
            coefficient_zeroing_only=False,
        )
    else:
        cache = preparation_cache if preparation_cache is not None else {}
        source_catalog = cache.get("source_catalog")
        if source_catalog is None:
            source_catalog = build_typed_catalog(context.pool, context.runtime.ansatz)
            cache["source_catalog"] = source_catalog
        generated = source_catalog.generated_candidate_intent_count
        by_id = {candidate.candidate_id: candidate for candidate in source_catalog.candidates}
        actual_ids = tuple(candidate.candidate_id for candidate in source_catalog.candidates)
        if any(candidate_id not in by_id for candidate_id in queue_ids):
            raise ParentNativeExecutorError("frozen structural candidate is absent")
        if method == "v4.1-one-shot-joint-compression":
            selected, incompatible = _compatible_v4_sentinels(source_catalog, queue_ids)
            plan = _compose(context, source_catalog, selected)
            rewrite = prepare_rewrite_for_optimizer(
                pool=context.pool,
                source=context.runtime.ansatz,
                parent_plan=plan,
            )
            plans = (plan,)
            rewrites = (rewrite,)
            selected_ids = tuple(candidate.candidate_id for candidate in selected)
            unique_states = 1
            directives.update(
                selection=(
                    "canonical one-per-equivalence-class sentinels, then actual "
                    "pairwise structural compatibility"
                ),
                optimization=True,
                one_shot=True,
                post_commit_catalog_rebuild=False,
                predictor_used=False,
                v2_binding_correction_required=bool(incompatible),
            )
        else:
            eligible_actual = set(actual_ids)
            if method == "v5-fixed-source-whitelist-no-replenishment":
                admitted = set(queue_ids) & eligible_actual
                if len(queue_ids) != len(eligible_actual):
                    raise ParentNativeExecutorError(
                        "fixed source whitelist does not equal actual source catalog"
                    )
                replenishment = False
            else:
                admitted = eligible_actual
                replenishment = True
            ranking_key = "ranking:" + _digest(sorted(admitted))
            ranked = cache.get(ranking_key)
            if ranked is None:
                ranked = _rank_parent_candidates(context, source_catalog, admitted)
                cache[ranking_key] = ranked
            plans, rewrites, ranking = ranked
            selected_ids = tuple(
                plan.candidates[0].candidate_id for plan in plans
            )
            unique_states = int(ranking["unique_proposed_physical_state_count"])
            directives.update(
                selection="parent risk-aware Pareto ranking on current committed state",
                selection_evidence=ranking,
                optimization=True,
                sequential_commits=True,
                full_current_catalog_generated=True,
                generated_catalog_count=generated,
                admitted_catalog_count=len(admitted),
                catalog_computation_reduction_claimed=False,
                post_commit_catalog_rebuild=True,
                replenishment_allowed=replenishment,
                source_whitelist_only=not replenishment,
            )

    return PreparedMethodNativeExecutor(
        method,
        context.case_id,
        str(item["queue_item_id"]),
        context,
        source_catalog,
        queue_ids,
        selected_ids,
        plans,
        rewrites,
        magnitude,
        generated,
        unique_states,
        directives,
        incompatible,
    )


def inspect_parent_execution_bindings() -> dict[str, Any]:
    from adaptvqe.minimize import minimize_bfgs
    from dvg_obs_ceo.composition import compose_registered_candidates
    from dvg_obs_ceo.transaction import evaluate_acceptance
    from dvg_obs_ceo.v5_nested_transaction import NestedRoundTransaction

    bindings = {
        "composition": compose_registered_candidates,
        "warm_start": obs_warm_start,
        "optimizer": minimize_bfgs,
        "acceptance": evaluate_acceptance,
        "transaction": NestedRoundTransaction,
        "resource_recount": evaluate_full_circuit_resources,
        "selection": select_risk_aware_pareto,
    }
    result = {}
    for role, value in bindings.items():
        source = Path(inspect.getsourcefile(value) or "").resolve()
        if not source.is_relative_to(ROOT):
            raise ParentNativeExecutorError(f"{role} binding is outside pinned repository")
        result[role] = {
            "type": type(value).__name__,
            "module": value.__module__,
            "qualname": value.__qualname__,
            "signature": str(inspect.signature(value)),
            "source_path": str(source.relative_to(ROOT)),
            "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        }
    return result

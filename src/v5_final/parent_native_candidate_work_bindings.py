"""Outcome-blind concrete candidate-intent and physical-state work bindings."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Mapping

from v5_matched_work.atomic_artifacts import canonical_json_bytes

from .parent_native_candidate_adapter import compose_parent_native_plan
from .parent_native_executors import prepare_method_executor
from .parent_native_physical_identity import canonical_proposed_physical_state_id
from .parent_native_runtime_factory_v2 import build_queue_bound_runtime_v2


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


@dataclass(frozen=True)
class CandidateWorkBinding:
    generated_candidates: tuple[tuple[str, str], ...]
    expanded_physical_state_ids: tuple[str, ...]
    resource_recounts: int
    rewrite_verifications: int
    dynamic_catalog_generation_upper_bound: int
    source_whitelist_keys: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        body = {
            "schema": "v5-final.parent-native-candidate-work-binding.v2",
            "generated_candidates": [
                {
                    "candidate_id": candidate_id,
                    "proposed_physical_state_id": physical_id,
                }
                for candidate_id, physical_id in self.generated_candidates
            ],
            "expanded_physical_state_ids": list(self.expanded_physical_state_ids),
            "candidate_generation_count": len(self.generated_candidates),
            "unique_search_state_count": len(set(self.expanded_physical_state_ids)),
            "resource_recounts": self.resource_recounts,
            "rewrite_verifications": self.rewrite_verifications,
            "dynamic_catalog_generation_upper_bound": (
                self.dynamic_catalog_generation_upper_bound
            ),
            "source_whitelist_keys": list(self.source_whitelist_keys),
        }
        body["binding_digest"] = _digest(body)
        return body


def candidate_structural_whitelist_key(candidate: Any) -> str:
    """Identify a source-frozen transformation independent of ansatz position.

    Parent candidate IDs deliberately include the current block ID and therefore
    change after a committed child shifts later ansatz positions.  The fixed
    source whitelist must still recognize the same registered transformation,
    while never admitting a transformation family absent from the source.
    """

    transform = candidate.transformation
    payload = {
        "schema": "v5-final.source-candidate-whitelist-key.v1",
        "kind": str(candidate.kind),
        "source_pool_indices": [int(value) for value in candidate.source_pool_indices],
        "target_family": str(candidate.target_family),
        "target_pool_indices": [int(value) for value in candidate.target_pool_indices],
        "removed_source_slots": [int(value) for value in candidate.removed_source_slots],
        "target_operator_digests": list(candidate.target_operator_digests),
        "exact_generator_relation": (
            None
            if candidate.exact_generator_relation is None
            else [int(value) for value in candidate.exact_generator_relation]
        ),
        "jacobian": [
            [float(value).hex() for value in row]
            for row in transform.jacobian
        ],
        "orientation": str(transform.orientation),
        "generator_normalization": str(transform.generator_normalization),
    }
    return "source-whitelist-key-v1:" + _digest(payload)


def _single_candidate_bindings(context: Any, catalog: Any) -> tuple[tuple[str, str], ...]:
    records = []
    for candidate in catalog.candidates:
        plan = compose_parent_native_plan(
            pool=context.pool,
            source=context.runtime.ansatz,
            catalog=catalog,
            candidates=(candidate,),
            gradient=context.runtime.gradient,
            inverse_hessian=context.runtime.inverse_hessian,
            problem_id=context.problem_id,
            reference_state=context._actual_algorithm.ref_det,
        )
        records.append(
            (
                str(candidate.candidate_id),
                canonical_proposed_physical_state_id(
                    problem_id=context.problem_id,
                    state_preparation_spec=plan.proposed_state_preparation_spec,
                ),
            )
        )
    return tuple(records)


def _magnitude_bindings(context: Any, item: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    from dvg_obs_ceo.block_ir import recover_dvg_blocks
    from dvg_obs_ceo.identity import StatePreparationSpec
    from dvg_obs_ceo.molecular_identity import generator_definition_digest
    from dvg_obs_ceo.resources import AnsatzStructure

    source = context.runtime.ansatz
    candidates = {
        int(value["ansatz_position"]): str(value["candidate_structural_id"])
        for value in item["candidate_binding"]["candidate_set"]
    }
    records = []
    for position in range(len(source.indices)):
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
        records.append(
            (
                candidates[position],
                canonical_proposed_physical_state_id(
                    problem_id=context.problem_id,
                    state_preparation_spec=state,
                ),
            )
        )
    return tuple(records)


def build_candidate_work_binding(
    item: Mapping[str, Any], *, preparation_cache: dict[str, Any] | None = None
) -> tuple[Any, Any, CandidateWorkBinding]:
    context = build_queue_bound_runtime_v2(str(item["queue_item_id"]))
    prepared = prepare_method_executor(
        context, item, preparation_cache=preparation_cache
    )
    method = str(item["method_id"])
    if method in {"immutable-ceo-star-source", "same-structure-reoptimization"}:
        generated: tuple[tuple[str, str], ...] = ()
        expanded: tuple[str, ...] = ()
        recounts = 0
        rewrites = 0
        dynamic_upper_bound = 0
        whitelist_keys: tuple[str, ...] = ()
    elif method == "structural-magnitude-pruning":
        generated = _magnitude_bindings(context, item)
        chosen = str(prepared.magnitude_deletion.candidate_id)
        expanded = (dict(generated)[chosen],)
        recounts = 3
        rewrites = 1
        dynamic_upper_bound = len(generated)
        whitelist_keys = ()
    else:
        if prepared.source_catalog is None:
            raise RuntimeError("structural method lacks actual parent catalog")
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
            dynamic_upper_bound = 0
            whitelist_keys = ()
        else:
            expanded = tuple(physical_id for _, physical_id in generated)
            recounts = 3 * len(generated)
            rewrites = len(generated)
            dynamic_upper_bound = len(generated)
            whitelist_keys = (
                tuple(
                    sorted(
                        candidate_structural_whitelist_key(candidate)
                        for candidate in prepared.source_catalog.candidates
                    )
                )
                if method == "v5-fixed-source-whitelist-no-replenishment"
                else ()
            )
    binding = CandidateWorkBinding(
        generated,
        tuple(dict.fromkeys(expanded)),
        recounts,
        rewrites,
        dynamic_upper_bound,
        whitelist_keys,
    )
    if len(generated) != prepared.generated_candidate_intents:
        raise RuntimeError("candidate binding generation count differs from executor")
    if len(set(expanded)) != prepared.unique_proposed_physical_states:
        raise RuntimeError("candidate binding physical-state count differs from executor")
    return context, prepared, binding

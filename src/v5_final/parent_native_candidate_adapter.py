"""Typed adapter from pinned parent candidates to canonical V5 identities.

All scientific transformations remain parent objects.  The adapter does not
evaluate energy, optimize parameters, rank candidates, or invent identity
fields.  It only composes registered candidates, creates the parent OBS warm
start, and binds the resulting target to canonical content-addressed IDs.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import struct
from typing import Any, Mapping, Sequence

from v5_matched_work.atomic_artifacts import canonical_json_bytes

from .identities import CandidateIntent


class ParentNativeCandidateError(RuntimeError):
    pass


def _float_hex(value: float) -> str:
    number = float(value)
    if number == 0.0:
        number = 0.0
    return struct.pack(">d", number).hex()


def _matrix_hex(value: Any) -> list[list[str]]:
    return [[_float_hex(item) for item in row] for row in value]


@dataclass(frozen=True)
class ParentNativeCatalog:
    blocks: tuple[Any, ...]
    candidates: tuple[Any, ...]

    @property
    def generated_candidate_intent_count(self) -> int:
        return len(self.candidates)


@dataclass(frozen=True)
class ParentNativeCandidatePlan:
    candidates: tuple[Any, ...]
    blocks: tuple[Any, ...]
    joint_plan: Any
    target_initial_coordinates: Any
    target_inverse_hessian: Any
    candidate_intent_ids: tuple[str, ...]
    proposed_physical_state_id: str
    proposed_state_preparation_spec: Any

    @property
    def constraint_semantic_id(self) -> str:
        return str(self.joint_plan.state.constraint_semantic_id)

    @property
    def constraint_numerical_id(self) -> str:
        return str(self.joint_plan.state.constraint_numerical_id)

    def to_audit_dict(self) -> dict[str, Any]:
        transform = self.joint_plan.transformation
        return {
            "candidate_ids": [candidate.candidate_id for candidate in self.candidates],
            "equivalence_class_ids": [
                candidate.equivalence_class_id for candidate in self.candidates
            ],
            "constraint_semantic_id": self.constraint_semantic_id,
            "constraint_numerical_id": self.constraint_numerical_id,
            "source_block_ids": list(self.joint_plan.source_block_ids),
            "target_indices": list(self.joint_plan.target_indices),
            "target_iteration_counts": list(
                self.joint_plan.target_iteration_counts
            ),
            "target_selection_iterations": list(
                self.joint_plan.target_selection_iterations
            ),
            "transformation": {
                "constraint_matrix_float64_hex": _matrix_hex(
                    transform.constraint_matrix
                ),
                "constraint_rhs_float64_hex": [
                    _float_hex(value) for value in transform.constraint_rhs
                ],
                "offset_float64_hex": [
                    _float_hex(value) for value in transform.offset
                ],
                "jacobian_float64_hex": _matrix_hex(transform.jacobian),
                "source_slots": list(transform.source_slots),
                "target_slots": list(transform.target_slots),
                "generator_normalization": transform.generator_normalization,
                "orientation": transform.orientation,
                "units": transform.units,
            },
            "audit_provenance": list(self.joint_plan.audit_provenance),
            "target_initial_coordinates_float64_hex": [
                _float_hex(value) for value in self.target_initial_coordinates
            ],
            "target_inverse_hessian_float64_hex": _matrix_hex(
                self.target_inverse_hessian
            ),
            "candidate_intent_ids": list(self.candidate_intent_ids),
            "proposed_physical_state_id": self.proposed_physical_state_id,
            "proposed_state_preparation_id": self.proposed_state_preparation_spec.state_preparation_id,
        }


def build_typed_catalog(pool: Any, source: Any) -> ParentNativeCatalog:
    from dvg_obs_ceo.block_ir import (
        CompressionCandidate,
        DVGBlock,
        enumerate_candidates,
        recover_dvg_blocks,
    )

    blocks = tuple(
        recover_dvg_blocks(
            pool,
            source.indices,
            source.coefficients,
            source.cumulative_parameter_counts,
        )
    )
    candidates = tuple(enumerate_candidates(pool, blocks))
    if any(not isinstance(block, DVGBlock) for block in blocks):
        raise ParentNativeCandidateError("parent returned a non-DVGBlock value")
    if any(not isinstance(candidate, CompressionCandidate) for candidate in candidates):
        raise ParentNativeCandidateError(
            "parent returned a non-CompressionCandidate value"
        )
    if len({candidate.candidate_id for candidate in candidates}) != len(candidates):
        raise ParentNativeCandidateError("parent candidate IDs are not unique")
    return ParentNativeCatalog(blocks, candidates)


def _intent(candidate: Any, joint_plan: Any) -> CandidateIntent:
    provenance: Mapping[str, Any] = {
        "parent_candidate_id": candidate.candidate_id,
        "equivalence_class_id": candidate.equivalence_class_id,
        "constraint_semantic_id": joint_plan.state.constraint_semantic_id,
        "constraint_numerical_id": joint_plan.state.constraint_numerical_id,
        "source_pool_indices": list(candidate.source_pool_indices),
        "target_pool_indices": list(candidate.target_pool_indices),
        "removed_source_slots": list(candidate.removed_source_slots),
        "target_operator_digests": list(candidate.target_operator_digests),
        "numerical_context_digest": candidate.numerical_context_digest,
        "exact_generator_relation": (
            None
            if candidate.exact_generator_relation is None
            else list(candidate.exact_generator_relation)
        ),
    }
    return CandidateIntent(
        source_block=candidate.source_block_id,
        transformation_family=candidate.kind,
        target_family=candidate.target_family,
        candidate_provenance=provenance,
        generation_path=(
            "dvg_obs_ceo.block_ir:recover_dvg_blocks",
            "dvg_obs_ceo.block_ir:enumerate_candidates",
            "dvg_obs_ceo.composition:compose_registered_candidates",
        ),
    )


def _proposed_state_spec(
    *,
    pool: Any,
    reference_state: Sequence[int],
    target: Any,
) -> Any:
    from dvg_obs_ceo.identity import StatePreparationSpec
    from dvg_obs_ceo.molecular_identity import generator_definition_digest
    from dvg_obs_ceo.block_ir import recover_dvg_blocks

    target_blocks = recover_dvg_blocks(
        pool,
        target.indices,
        target.coefficients,
        target.cumulative_parameter_counts,
    )
    return StatePreparationSpec.create(
        reference_state=reference_state,
        generator_definition_digest=generator_definition_digest(pool),
        ansatz_block_structure=tuple(
            (block.family, block.pool_indices) for block in target_blocks
        ),
        ansatz_indices=target.indices,
        coefficients=target.coefficients,
        orbital_parameters=(),
        qubit_mapping="openfermion-jordan-wigner-v1",
        qubit_ordering=range(int(pool.n)),
    )


def compose_parent_native_plan(
    *,
    pool: Any,
    source: Any,
    catalog: ParentNativeCatalog,
    candidates: Sequence[Any],
    gradient: Any,
    inverse_hessian: Any,
    problem_id: str,
    reference_state: Sequence[int],
) -> ParentNativeCandidatePlan:
    from dvg_obs_ceo.block_ir import CompressionCandidate
    from dvg_obs_ceo.calibration import obs_warm_start
    from dvg_obs_ceo.composition import compose_registered_candidates
    from dvg_obs_ceo.resources import AnsatzStructure

    selected = tuple(candidates)
    if not selected or any(
        not isinstance(candidate, CompressionCandidate) for candidate in selected
    ):
        raise ParentNativeCandidateError(
            "composition requires actual CompressionCandidate objects"
        )
    known = {candidate.candidate_id: candidate for candidate in catalog.candidates}
    if any(known.get(candidate.candidate_id) is not candidate for candidate in selected):
        raise ParentNativeCandidateError(
            "candidate is not the typed object from the bound parent catalog"
        )
    plan = compose_registered_candidates(source, catalog.blocks, selected)
    initial, target_inverse, _ = obs_warm_start(
        source.coefficients,
        gradient,
        inverse_hessian,
        plan.transformation,
    )
    target = AnsatzStructure.create(
        plan.target_indices,
        initial,
        plan.target_iteration_counts,
    )
    proposed_spec = _proposed_state_spec(
        pool=pool,
        reference_state=reference_state,
        target=target,
    )
    intents = tuple(_intent(candidate, plan) for candidate in selected)
    proposed_payload = {
        "schema": "v5-final.parent-native-proposed-physical-state.v2",
        "ProblemID": problem_id,
        "constraint_semantic_id": plan.state.constraint_semantic_id,
        "constraint_numerical_id": plan.state.constraint_numerical_id,
        "candidate_intent_ids": [intent.candidate_intent_id for intent in intents],
        "canonical_parent_state_preparation": proposed_spec.payload(),
    }
    proposed_id = "physical-state-v2:" + hashlib.sha256(
        canonical_json_bytes(proposed_payload)
    ).hexdigest()
    if proposed_id == proposed_spec.state_preparation_id:
        raise ParentNativeCandidateError(
            "proposed and optimized state identity namespaces collided"
        )
    return ParentNativeCandidatePlan(
        selected,
        catalog.blocks,
        plan,
        initial,
        target_inverse,
        tuple(intent.candidate_intent_id for intent in intents),
        proposed_id,
        proposed_spec,
    )

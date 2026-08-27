"""Outcome-free adapter from actual parent candidates to :mod:`verifier_v2`.

This is a new S11-v2 path.  It does not alter or reinterpret S11-v1 rewrite
artifacts.  Optimizer arguments remain inaccessible until sparse verification
has completed, and this module never invokes an optimizer or energy kernel.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from dvg_obs_ceo.block_ir import operator_digest
from dvg_obs_ceo.calibration import obs_warm_start
from dvg_obs_ceo.resources import (
    AnsatzStructure,
    evaluate_full_circuit_resources,
    paper_era_backend,
)

from .parent_native_candidate_adapter import (
    ParentNativeCandidatePlan,
    ParentNativeCatalog,
    compose_parent_native_plan,
)
from .verifier_v2 import CandidateV2, VerifierV2, VerifierV2Error, VerifierV2Policy


class ParentNativeVerifierV2Error(RuntimeError):
    pass


RESOURCE_FIELDS = (
    "cnot_count",
    "cnot_depth",
    "total_depth",
    "parameter_count",
    "logical_block_count",
)


@dataclass(frozen=True)
class PreparedParentRewriteV2:
    candidate_id: str
    source: Any
    target: Any
    target_inverse_hessian: Any
    before_resources: Any
    after_resources: Any
    structural_resources: Any
    sparse_verification_digest: str
    top_k_selection_digest: str

    def optimizer_arguments_after_authorization(self) -> dict[str, Any]:
        if tuple(self.target.indices) == tuple(self.source.indices):
            raise ParentNativeVerifierV2Error("verified rewrite did not change structure")
        return {
            "indices": tuple(self.target.indices),
            "initial_coordinates": tuple(self.target.coefficients),
            "initial_inverse_hessian": self.target_inverse_hessian,
        }

    def to_audit_dict(self) -> dict[str, Any]:
        return {
            "schema": "v5-final.prepared-parent-rewrite-v2.v1",
            "candidate_id": self.candidate_id,
            "source_indices": list(self.source.indices),
            "target_indices": list(self.target.indices),
            "before_resources": {
                field: int(getattr(self.before_resources.snapshot, field))
                for field in RESOURCE_FIELDS
            },
            "after_resources": {
                field: int(getattr(self.after_resources.snapshot, field))
                for field in RESOURCE_FIELDS
            },
            "physical_structural_recount_equal": (
                self.after_resources.snapshot == self.structural_resources.snapshot
            ),
            "sparse_verification_digest": self.sparse_verification_digest,
            "top_k_selection_digest": self.top_k_selection_digest,
            "optimizer_iterations": 0,
            "candidate_energy_evaluations": 0,
            "execution_authorized": False,
        }


@dataclass
class ParentVerifierV2Bundle:
    verifier: VerifierV2
    candidates: tuple[CandidateV2, ...]
    plans: dict[str, ParentNativeCandidatePlan]
    resource_cache: dict[str, tuple[Any, Any, Any]]
    source: Any

    def preview_selected_candidate_ids(self) -> tuple[str, ...]:
        """Outcome-free structural selection before numeric verifier work."""

        return self.verifier.preview_selected_candidate_ids(self.candidates)

    def run(
        self, *, max_new_numeric_verifications: int | None = None
    ) -> dict[str, Any]:
        return self.verifier.run(
            self.candidates,
            max_new_numeric_verifications=max_new_numeric_verifications,
        )

    def prepared_rewrites(self, result: Mapping[str, Any]) -> tuple[PreparedParentRewriteV2, ...]:
        core = result["core"]
        if core["status"] != "VERIFIED_READY_AWAITING_OUTCOME_AUTHORIZATION":
            raise ParentNativeVerifierV2Error("numeric verification is incomplete")
        selection_digest = core["top_k_freeze"]["selection_digest"]
        verified = {
            value["candidate_id"]: value
            for value in core["numeric_verifications"]
        }
        prepared: list[PreparedParentRewriteV2] = []
        for candidate_id in core["top_k_freeze"]["selected_candidate_ids"]:
            if candidate_id not in verified or candidate_id not in self.resource_cache:
                raise ParentNativeVerifierV2Error("selected candidate lacks verification")
            plan = self.plans[candidate_id]
            before, after, structural = self.resource_cache[candidate_id]
            target = AnsatzStructure.create(
                plan.joint_plan.target_indices,
                plan.target_initial_coordinates,
                plan.joint_plan.target_iteration_counts,
            )
            prepared.append(
                PreparedParentRewriteV2(
                    candidate_id,
                    self.source,
                    target,
                    plan.target_inverse_hessian,
                    before,
                    after,
                    structural,
                    verified[candidate_id]["verification_digest"],
                    selection_digest,
                )
            )
        return tuple(prepared)


def build_parent_verifier_v2(
    *,
    context: Any,
    catalog: ParentNativeCatalog,
    admitted_candidate_ids: Sequence[str],
    policy: VerifierV2Policy,
    checkpoint_dir: Path,
) -> ParentVerifierV2Bundle:
    admitted = set(str(value) for value in admitted_candidate_ids)
    by_id = {candidate.candidate_id: candidate for candidate in catalog.candidates}
    if not admitted or not admitted.issubset(by_id):
        raise ParentNativeVerifierV2Error("admitted candidate set is absent or empty")

    plans: dict[str, ParentNativeCandidatePlan] = {}
    resource_cache: dict[str, tuple[Any, Any, Any]] = {}
    generator_indices: dict[str, int] = {}
    candidates: list[CandidateV2] = []
    backend = paper_era_backend()
    source_resources = evaluate_full_circuit_resources(
        context.pool, context.runtime.ansatz, backend
    )

    for candidate in catalog.candidates:
        if candidate.candidate_id not in admitted:
            continue
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
        plans[candidate.candidate_id] = plan
        _, _, prediction = obs_warm_start(
            context.runtime.ansatz.coefficients,
            context.runtime.gradient,
            context.runtime.inverse_hessian,
            plan.joint_plan.transformation,
        )
        source_digests: list[str] = []
        for index in candidate.source_pool_indices:
            digest = operator_digest(context.pool.get_q_op(int(index)))
            existing = generator_indices.setdefault(digest, int(index))
            if existing != int(index):
                left = context.pool.get_q_op(existing)
                right = context.pool.get_q_op(int(index))
                if operator_digest(left) != operator_digest(right):
                    raise ParentNativeVerifierV2Error("generator digest collision")
            source_digests.append(digest)
        target_digests: list[str] = []
        for index in candidate.target_pool_indices:
            digest = operator_digest(context.pool.get_q_op(int(index)))
            generator_indices.setdefault(digest, int(index))
            target_digests.append(digest)

        target = AnsatzStructure.create(
            plan.joint_plan.target_indices,
            plan.target_initial_coordinates,
            plan.joint_plan.target_iteration_counts,
        )

        def recount(
            *, candidate_id: str = candidate.candidate_id, target: Any = target
        ) -> Mapping[str, Any]:
            cached = resource_cache.get(candidate_id)
            if cached is None:
                after = evaluate_full_circuit_resources(context.pool, target, backend)
                structural = evaluate_full_circuit_resources(
                    context.pool,
                    target,
                    backend,
                    coefficient_policy="deterministic-structural",
                )
                if after.snapshot != structural.snapshot:
                    raise ParentNativeVerifierV2Error(
                        "physical and structural resource recounts differ"
                    )
                cached = (source_resources, after, structural)
                resource_cache[candidate_id] = cached
            _, after, _ = cached
            return {
                "resource_vector": [
                    int(getattr(after.snapshot, field)) for field in RESOURCE_FIELDS
                ],
                "resource_recounts": 2,
                "N_circuit_operator_builds": 2
                * len(target.cumulative_parameter_counts),
            }

        def circuit_state(
            coordinates: np.ndarray,
            probe: np.ndarray,
            *,
            indices: tuple[int, ...] = tuple(candidate.target_pool_indices),
        ) -> np.ndarray:
            from qiskit.quantum_info import Statevector

            circuit = context.pool.get_circuit(list(indices), list(coordinates))
            return np.asarray(Statevector(probe).evolve(circuit).data, dtype=np.complex128)

        candidates.append(
            CandidateV2(
                candidate_id=str(candidate.candidate_id),
                semantic_id=str(plan.constraint_semantic_id),
                proposed_state_preparation_id=str(
                    plan.proposed_state_preparation_spec.state_preparation_id
                ),
                source_generator_digests=tuple(source_digests),
                target_generator_digests=tuple(target_digests),
                jacobian=tuple(
                    tuple(float(value) for value in row)
                    for row in candidate.transformation.jacobian
                ),
                obs_predicted_loss=max(
                    0.0, float(prediction.predicted_change_from_current)
                ),
                matrix_dimension=1 << int(context.pool.n),
                qubit_count=int(context.pool.n),
                resource_recount=recount,
                circuit_state_factory=(
                    None if not target_digests else circuit_state
                ),
                deletion_shortcut=not target_digests,
            )
        )

    def load_generator(digest: str):
        from openfermion import get_sparse_operator

        index = generator_indices.get(digest)
        if index is None:
            raise VerifierV2Error("unbound parent generator digest")
        return get_sparse_operator(
            context.pool.get_q_op(index), n_qubits=int(context.pool.n)
        )

    verifier = VerifierV2(
        policy=policy,
        generator_loader=load_generator,
        checkpoint_dir=checkpoint_dir,
        source_binding={
            "schema": "v5-final.parent-native-verifier-v2-source-binding.v1",
            "case_id": context.case_id,
            "ProblemID": context.problem_id,
            "StatePreparationID": context.state_preparation_id,
            "Hamiltonian_digest": context.hamiltonian_digest,
            "source_checkpoint_digest": context.source_checkpoint_digest,
            "environment_digest": context.environment_digest,
            "source_resource_structure_digest": source_resources.snapshot.structure_digest,
            "admitted_candidate_ids": sorted(admitted),
            "candidate_energy_evaluations": 0,
            "optimizer_iterations": 0,
        },
        initial_counts={
            "resource_recounts": 1,
            "N_circuit_operator_builds": len(
                context.runtime.ansatz.cumulative_parameter_counts
            ),
            "matrix_dimension": 1 << int(context.pool.n),
            "qubit_count": int(context.pool.n),
        },
    )
    return ParentVerifierV2Bundle(
        verifier,
        tuple(candidates),
        plans,
        resource_cache,
        context.runtime.ansatz,
    )

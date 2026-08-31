"""Actual parent rewrite, matrix verification, and full resource recount.

This module prepares optimizer inputs but never invokes an optimizer or energy
kernel.  The target ansatz is materialized from ``JointConstraintPlan`` before
the arguments can be exposed to an optimizer.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


class ParentNativeRewriteError(RuntimeError):
    pass


@dataclass(frozen=True)
class PreparedParentRewrite:
    source: Any
    target: Any
    target_inverse_hessian: Any
    before_resources: Any
    after_resources: Any
    structural_resources: Any
    verified_candidate_ids: tuple[str, ...]
    source_matrix_count: int
    target_matrix_count: int
    target_native_circuits_verified: int

    def optimizer_arguments(self) -> dict[str, Any]:
        """Return only target-native inputs after all rewrite checks passed."""

        if tuple(self.target.indices) == tuple(self.source.indices):
            raise ParentNativeRewriteError(
                "optimizer target still equals the unrevised source indices"
            )
        return {
            "indices": tuple(self.target.indices),
            "initial_coordinates": tuple(self.target.coefficients),
            "initial_inverse_hessian": self.target_inverse_hessian,
        }

    def to_audit_dict(self) -> dict[str, Any]:
        before = self.before_resources.snapshot
        after = self.after_resources.snapshot
        deltas = {
            field: int(getattr(after, field) - getattr(before, field))
            for field in (
                "cnot_count",
                "cnot_depth",
                "total_depth",
                "parameter_count",
                "logical_block_count",
            )
        }
        circuit_metrics = ("cnot_count", "cnot_depth", "total_depth")
        physical_circuit_changed = (
            self.before_resources.circuit_qasm_digest
            != self.after_resources.circuit_qasm_digest
            and before.structure_digest != after.structure_digest
        )
        circuit_metric_reduced = any(deltas[field] < 0 for field in circuit_metrics)
        return {
            "source_indices": list(self.source.indices),
            "target_indices": list(self.target.indices),
            "target_iteration_counts": list(
                self.target.cumulative_parameter_counts
            ),
            "verified_candidate_ids": list(self.verified_candidate_ids),
            "actual_matrix_counts": {
                "source": self.source_matrix_count,
                "target": self.target_matrix_count,
            },
            "target_native_circuits_verified": self.target_native_circuits_verified,
            "before_resources": asdict(before),
            "after_resources": asdict(after),
            "resource_delta": deltas,
            "parent_physical_structural_snapshot_equal": (
                self.after_resources.snapshot == self.structural_resources.snapshot
            ),
            "physical_circuit_changed": physical_circuit_changed,
            "circuit_metric_reduced": circuit_metric_reduced,
            "parameter_only_reduction_claimed": False,
            "resource_reduction_success": physical_circuit_changed
            and circuit_metric_reduced,
            "optimizer_arguments": {
                "indices": list(self.optimizer_arguments()["indices"]),
                "coordinate_count": len(
                    self.optimizer_arguments()["initial_coordinates"]
                ),
                "inverse_hessian_dimension": len(
                    self.optimizer_arguments()["initial_inverse_hessian"]
                ),
            },
        }


def _generator_matrix(pool: Any, index: int) -> Any:
    from openfermion import get_sparse_operator

    return get_sparse_operator(
        pool.get_q_op(int(index)), n_qubits=int(pool.n)
    ).toarray()


def prepare_rewrite_for_optimizer(
    *,
    pool: Any,
    source: Any,
    parent_plan: Any,
    validate_native_circuits: bool = True,
) -> PreparedParentRewrite:
    from dvg_obs_ceo.block_ir import (
        validate_candidate_semantics,
        validate_target_circuit_semantics,
    )
    from dvg_obs_ceo.resources import (
        AnsatzStructure,
        evaluate_full_circuit_resources,
        paper_era_backend,
    )

    plan = parent_plan.joint_plan
    target = AnsatzStructure.create(
        plan.target_indices,
        parent_plan.target_initial_coordinates,
        plan.target_iteration_counts,
    )
    if tuple(target.indices) != tuple(plan.target_indices):
        raise ParentNativeRewriteError("target rewrite did not use JointConstraintPlan indices")

    source_matrix_count = 0
    target_matrix_count = 0
    native_verified = 0
    for candidate in parent_plan.candidates:
        source_matrices = tuple(
            _generator_matrix(pool, index)
            for index in candidate.source_pool_indices
        )
        target_matrices = tuple(
            _generator_matrix(pool, index)
            for index in candidate.target_pool_indices
        )
        validate_candidate_semantics(
            candidate,
            source_matrices,
            target_matrices,
            samples=5,
            seed=11,
        )
        source_matrix_count += len(source_matrices)
        target_matrix_count += len(target_matrices)
        if validate_native_circuits and target_matrices:
            from qiskit.quantum_info import Operator

            validate_target_circuit_semantics(
                target_matrices,
                lambda coordinates, indices=candidate.target_pool_indices: Operator(
                    pool.get_circuit(list(indices), list(coordinates))
                ).data,
                samples=5,
                seed=23,
            )
            native_verified += 1

    backend = paper_era_backend()
    before = evaluate_full_circuit_resources(pool, source, backend)
    after = evaluate_full_circuit_resources(pool, target, backend)
    structural = evaluate_full_circuit_resources(
        pool,
        target,
        backend,
        coefficient_policy="deterministic-structural",
    )
    if after.snapshot != structural.snapshot:
        raise ParentNativeRewriteError(
            "physical and deterministic parent resource recounts disagree"
        )
    prepared = PreparedParentRewrite(
        source,
        target,
        parent_plan.target_inverse_hessian,
        before,
        after,
        structural,
        tuple(candidate.candidate_id for candidate in parent_plan.candidates),
        source_matrix_count,
        target_matrix_count,
        native_verified,
    )
    prepared.optimizer_arguments()
    return prepared

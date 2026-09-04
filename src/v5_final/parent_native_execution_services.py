"""Actual, gate-bound execution services for the six frozen methods."""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import random
import struct
import time
from typing import Any, Mapping, Sequence

import numpy as np

from dvg_obs_ceo.resources import (
    AnsatzStructure,
    evaluate_full_circuit_resources,
    paper_era_backend,
)
from dvg_obs_ceo.telemetry import ResourceSnapshot
from dvg_obs_ceo.transaction import (
    AcceptanceCriteria,
    AcceptanceEvidence,
    OptimizerOutcome,
    evaluate_acceptance,
)
from v5_matched_work.atomic_artifacts import write_json_exclusive

from .parent_native_candidate_adapter import build_typed_catalog
from .parent_native_candidate_work_bindings import (
    _single_candidate_bindings,
    candidate_structural_whitelist_key,
)
from .parent_native_executors import (
    PreparedMethodNativeExecutor,
    _rank_parent_candidates,
    prepare_method_executor,
)
from .parent_native_persistent_runner import (
    ParentNativePersistentRunner,
    make_attempt_id,
    recover_terminal_result,
    replay_raw_ledger,
)
from .parent_native_runtime_factory_v2 import build_queue_bound_runtime_v2
from .parent_native_work_accounting import (
    ComponentwiseCapRejected,
    ParentNativeWorkRecorder,
    ParentNativeWorkRequest,
    work_cap_digest,
)
from .semantic_contract_v2 import WorkDelta


class ParentNativeExecutionError(RuntimeError):
    pass


def _digest(value: Any) -> str:
    from v5_matched_work.atomic_artifacts import canonical_json_bytes

    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _float_hex(value: float) -> str:
    return struct.pack(">d", float(value)).hex()


def _work_request(item: Mapping[str, Any], plan: Mapping[str, Any]) -> ParentNativeWorkRequest:
    return ParentNativeWorkRequest(
        queue_item_id=str(item["queue_item_id"]),
        method_id=str(item["method_id"]),
        case_id=str(item["case_id"]),
        state_preparation_id=str(item["StatePreparationID"]),
        problem_id=str(item["ProblemID"]),
        hamiltonian_digest=str(item["Hamiltonian_digest"]),
        source_checkpoint_digest=str(item["source_checkpoint_digest"]),
        frozen_queue_digest=str(plan["plan_digest"]),
        work_cap_digest=str(item["work_cap_digest"]),
    )


def _component_snapshot_digest(runtime: Any) -> dict[str, str]:
    snapshot = runtime.snapshot()
    values = {
        "ansatz": {
            "indices": list(snapshot.ansatz.indices),
            "coefficients": [_float_hex(value) for value in snapshot.ansatz.coefficients],
            "counts": list(snapshot.ansatz.cumulative_parameter_counts),
        },
        "parameters": [_float_hex(value) for value in snapshot.ansatz.coefficients],
        "optimizer_inverse_hessian": [
            [_float_hex(value) for value in row] for row in snapshot.inverse_hessian
        ],
        "resources": snapshot.metadata["resource_structure_digest"],
        "ledger_transaction": snapshot.snapshot_digest,
    }
    return {key: _digest(value) for key, value in values.items()}


class DurableWorkBoundary:
    """Persist every finished or failed kernel event before returning."""

    def __init__(
        self,
        runner: ParentNativePersistentRunner,
        recorder: ParentNativeWorkRecorder,
    ) -> None:
        self.runner = runner
        self.recorder = recorder
        self.telemetry: list[dict[str, Any]] = []

    @property
    def events(self):
        return self.recorder.events

    @property
    def total(self):
        return self.recorder.total

    def invoke(self, operation: str, kernel: Any, **values: Any) -> Any:
        started = time.perf_counter()
        try:
            result = self.recorder.invoke(operation, kernel, **values)
        finally:
            self.runner.persist_new_work_events(self.recorder.events)
            if self.recorder.events:
                self.telemetry.append(
                    {
                        "operation": operation,
                        "elapsed_seconds": time.perf_counter() - started,
                        "event_digest": self.recorder.events[-1].event_digest,
                        "outcome": self.recorder.events[-1].outcome,
                    }
                )
        return result

    def persist_structural_binding(self, binding: Mapping[str, Any]) -> None:
        generated = list(binding["generated_candidates"])
        expanded = list(binding["expanded_physical_state_ids"])
        projected = WorkDelta(
            candidate_generations=len(generated),
            search_states=len(set(expanded)),
            resource_recounts=int(binding["resource_recounts"]),
            rewrite_verifications=int(binding["rewrite_verifications"]),
        )
        self.recorder._precheck(projected, "candidate-generation")
        first_by_state: dict[str, str] = {}
        for value in generated:
            candidate_id = str(value["candidate_id"])
            physical_id = str(value["proposed_physical_state_id"])
            self.recorder._append(
                operation="candidate-generation",
                outcome="completed",
                units=1,
                candidate_id=candidate_id,
                proposed_physical_state_id=physical_id,
                evidence={"binding_digest": binding["binding_digest"]},
            )
            if physical_id in first_by_state:
                self.recorder._append(
                    operation="candidate-physical-state-alias",
                    outcome="duplicate",
                    units=0,
                    candidate_id=candidate_id,
                    proposed_physical_state_id=physical_id,
                    evidence={"deduplication_key": physical_id},
                )
            else:
                first_by_state[physical_id] = candidate_id
        generated_by_state = {
            str(value["proposed_physical_state_id"]): str(value["candidate_id"])
            for value in generated
        }
        for physical_id in dict.fromkeys(expanded):
            candidate_id = generated_by_state.get(str(physical_id), "joint-candidate-state")
            if str(physical_id) in self.recorder._seen_physical_states:
                self.recorder._append(
                    operation="candidate-physical-state-alias",
                    outcome="duplicate",
                    units=0,
                    candidate_id=candidate_id,
                    proposed_physical_state_id=str(physical_id),
                    evidence={"deduplication_key": physical_id},
                )
            else:
                self.recorder._seen_physical_states.add(str(physical_id))
                self.recorder._append(
                    operation="unique-search-state-expansion",
                    outcome="completed",
                    units=1,
                    candidate_id=candidate_id,
                    proposed_physical_state_id=str(physical_id),
                    evidence={"deduplication_key": physical_id},
                )
        if binding["resource_recounts"]:
            self.recorder._append(
                operation="full-physical-resource-recount",
                outcome="completed",
                units=int(binding["resource_recounts"]),
                evidence={"phase": "outcome-free-method-preparation"},
            )
        if binding["rewrite_verifications"]:
            self.recorder._append(
                operation="rewrite-verification",
                outcome="completed",
                units=int(binding["rewrite_verifications"]),
                evidence={"phase": "actual-matrix-and-circuit-verification"},
            )
        self.runner.persist_new_work_events(self.recorder.events)


class ActualOptimizationBoundary:
    def __init__(self, algorithm: Any, pool: Any, boundary: DurableWorkBoundary) -> None:
        self.algorithm = algorithm
        self.pool = pool
        self.boundary = boundary
        self.series: list[dict[str, Any]] = []

    def energy(self, coordinates: Sequence[float], indices: Sequence[int]) -> float:
        evidence: dict[str, Any] = {}

        def call() -> float:
            value = float(
                self.algorithm.evaluate_energy(list(coordinates), list(indices))
            )
            evidence["energy_float64"] = _float_hex(value)
            return value

        value = float(
            self.boundary.invoke(
                "candidate-energy-evaluation", call, evidence=evidence
            )
        )
        self.series.append(
            {
                "kind": "energy",
                "energy_hartree": value,
                "parameters": [float(item) for item in coordinates],
            }
        )
        return value

    def gradient(self, coordinates: Sequence[float], indices: Sequence[int]) -> np.ndarray:
        evidence: dict[str, Any] = {}

        def call() -> np.ndarray:
            value = np.asarray(
                self.algorithm.estimate_gradients(
                    list(coordinates), list(indices), method="an"
                ),
                dtype=np.float64,
            )
            evidence["gradient_float64"] = [_float_hex(item) for item in value]
            return value

        value = np.asarray(
            self.boundary.invoke(
                "full-gradient-evaluation",
                call,
                dimension=len(indices),
                evidence=evidence,
            ),
            dtype=np.float64,
        )
        self.series.append(
            {
                "kind": "gradient",
                "gradient_infinity_norm": (
                    0.0 if not len(value) else float(np.max(np.abs(value)))
                ),
                "parameters": [float(item) for item in coordinates],
            }
        )
        return value

    def optimize(
        self,
        initial: Sequence[float],
        indices: Sequence[int],
        inverse_hessian: Any,
        *,
        f0: float | None = None,
        g0: Any | None = None,
        maxiter: int = 1000,
    ) -> Any:
        initial_array = np.asarray(initial, dtype=np.float64)
        index_values = list(indices)
        if initial_array.ndim != 1 or len(index_values) != len(initial_array):
            raise ParentNativeExecutionError(
                "optimizer coordinates and gradient dimension differ"
            )
        inverse_array = np.asarray(inverse_hessian, dtype=np.float64)
        if inverse_array.shape != (len(initial_array), len(initial_array)):
            raise ParentNativeExecutionError("optimizer inverse Hessian shape differs")
        if not isinstance(maxiter, int) or isinstance(maxiter, bool) or maxiter <= 0:
            raise ParentNativeExecutionError(
                "optimizer maximum iterations must be a positive integer"
            )
        from adaptvqe.minimize import minimize_bfgs

        seeded_gradient = None if g0 is None else np.asarray(g0, dtype=np.float64)
        if seeded_gradient is not None and seeded_gradient.shape != initial_array.shape:
            raise ParentNativeExecutionError("optimizer initial gradient shape differs")
        event_offset = len(self.boundary.events)
        self.boundary.invoke("optimizer-start", lambda: None)

        energy_seed_available = f0 is not None
        gradient_seed_available = seeded_gradient is not None

        def objective(coordinates: Any, bound_indices: Sequence[int]) -> float:
            nonlocal energy_seed_available
            values = np.asarray(coordinates, dtype=np.float64)
            if energy_seed_available:
                if not np.array_equal(values, initial_array):
                    raise ParentNativeExecutionError(
                        "pinned BFGS requested a noninitial point before consuming f0"
                    )
                energy_seed_available = False
                return float(f0)
            return self.energy(values, bound_indices)

        def jacobian(coordinates: Any, bound_indices: Sequence[int]) -> np.ndarray:
            nonlocal gradient_seed_available
            values = np.asarray(coordinates, dtype=np.float64)
            if gradient_seed_available:
                if not np.array_equal(values, initial_array):
                    raise ParentNativeExecutionError(
                        "pinned BFGS requested a noninitial point before consuming g0"
                    )
                gradient_seed_available = False
                return np.asarray(seeded_gradient, dtype=np.float64).copy()
            return self.gradient(values, bound_indices)

        def callback(result: Any) -> None:
            evidence = {
                "energy_float64": _float_hex(float(result.fun)),
                "parameters_float64": [_float_hex(value) for value in result.x],
            }
            self.boundary.invoke(
                "optimizer-iteration", lambda: None, evidence=evidence
            )

        result = minimize_bfgs(
            objective,
            initial_array,
            args=(index_values,),
            jac=jacobian,
            callback=callback,
            gtol=1e-8,
            maxiter=maxiter,
            disp=False,
            initial_inv_hessian=inverse_array,
            f0=f0,
            g0=seeded_gradient,
        )
        events = self.boundary.events[event_offset:]
        counts = {
            operation: sum(event.operation == operation for event in events)
            for operation in (
                "optimizer-start",
                "optimizer-iteration",
                "candidate-energy-evaluation",
                "full-gradient-evaluation",
            )
        }
        if (
            counts["optimizer-start"] != 1
            or counts["optimizer-iteration"] != int(result.nit)
            or counts["candidate-energy-evaluation"] != int(result.nfev)
            or counts["full-gradient-evaluation"] != int(result.njev)
        ):
            raise ParentNativeExecutionError(
                "pinned BFGS result counters differ from durable kernel events"
            )
        return result

    def statevector(self, coordinates: Sequence[float], indices: Sequence[int]) -> np.ndarray:
        evidence: dict[str, Any] = {}

        def call() -> Any:
            raw = self.algorithm.compute_state(list(coordinates), list(indices))
            value = np.asarray(raw.toarray(), dtype=np.complex128).ravel()
            value /= np.linalg.norm(value)
            evidence["statevector_sha256"] = hashlib.sha256(
                np.asarray(value, dtype=">c16").tobytes()
            ).hexdigest()
            return value

        return np.asarray(
            self.boundary.invoke("statevector-recomputation", call, evidence=evidence),
            dtype=np.complex128,
        )

    def independent_statevector(
        self, coordinates: Sequence[float], indices: Sequence[int]
    ) -> np.ndarray:
        from qiskit.quantum_info import Statevector

        evidence: dict[str, Any] = {}

        def call() -> np.ndarray:
            circuit = self.pool.get_circuit(list(indices), list(coordinates))
            reference = np.asarray(self.algorithm.ref_state.toarray()).ravel()
            value = np.asarray(Statevector(reference).evolve(circuit).data)
            value /= np.linalg.norm(value)
            evidence["statevector_sha256"] = hashlib.sha256(
                np.asarray(value, dtype=">c16").tobytes()
            ).hexdigest()
            return value

        return np.asarray(
            self.boundary.invoke("statevector-recomputation", call, evidence=evidence),
            dtype=np.complex128,
        )

    def independent_energy(self, statevector: np.ndarray) -> float:
        evidence: dict[str, Any] = {"route": "direct-Hamiltonian-expectation"}

        def call() -> float:
            value = float(
                np.real(np.vdot(statevector, self.algorithm.hamiltonian @ statevector))
            )
            evidence["energy_float64"] = _float_hex(value)
            return value

        return float(
            self.boundary.invoke(
                "candidate-energy-evaluation", call, evidence=evidence
            )
        )

    def resources(self, structure: AnsatzStructure) -> Any:
        evidence: dict[str, Any] = {}

        def call() -> Any:
            value = evaluate_full_circuit_resources(
                self.pool, structure, paper_era_backend()
            )
            evidence["resources"] = asdict(value.snapshot)
            return value

        return self.boundary.invoke(
            "full-physical-resource-recount", call, evidence=evidence
        )


def _constraint_residual(plan: Any | None, coordinates: np.ndarray) -> float:
    if plan is None:
        return 0.0
    transform = plan.joint_plan.transformation
    source = np.asarray(transform.offset) + np.asarray(transform.jacobian) @ coordinates
    residual = np.asarray(transform.constraint_matrix) @ source - np.asarray(
        transform.constraint_rhs
    )
    return 0.0 if not residual.size else float(np.max(np.abs(residual)))


def _resource_snapshot(value: Any) -> ResourceSnapshot:
    return value.snapshot


def _commit_runtime(runtime: Any, attempt: Mapping[str, Any]) -> None:
    runtime.ansatz = attempt["structure"]
    runtime.energy_hartree = float(attempt["energy_hartree"])
    runtime.gradient = np.asarray(attempt["gradient"], dtype=np.float64)
    runtime.inverse_hessian = np.asarray(
        attempt["inverse_hessian"], dtype=np.float64
    )
    runtime.statevector = np.asarray(attempt["statevector"], dtype=np.complex128)
    runtime.metadata["resource_structure_digest"] = attempt["resources"][
        "structure_digest"
    ]
    runtime.validate()


def _dynamic_magnitude_preparation(
    executor: PreparedMethodNativeExecutor,
    boundary: DurableWorkBoundary,
) -> tuple[str, AnsatzStructure, np.ndarray] | None:
    from dvg_obs_ceo.block_ir import recover_dvg_blocks
    from dvg_obs_ceo.identity import StatePreparationSpec
    from dvg_obs_ceo.molecular_identity import (
        generator_definition_digest,
        state_preparation_spec,
    )
    from .parent_native_physical_identity import canonical_proposed_physical_state_id

    runtime = executor.context.runtime
    source = runtime.ansatz
    if not source.indices:
        return None
    current_state = state_preparation_spec(
        runtime,
        algorithm=executor.context._actual_algorithm,
        pool=executor.context.pool,
    )
    projected = WorkDelta(
        candidate_generations=len(source.indices),
        search_states=1,
        resource_recounts=3,
        rewrite_verifications=1,
    )
    boundary.recorder._precheck(projected, "candidate-generation")
    generated = []
    targets: dict[str, tuple[int, AnsatzStructure, str]] = {}
    scored = []
    for position, (pool_index, coefficient) in enumerate(
        zip(source.indices, source.coefficients)
    ):
        payload = {
            "source_state_preparation_id": current_state.state_preparation_id,
            "position": position,
            "pool_index": int(pool_index),
            "constraint": "theta_i->0",
            "physical_generator_deletion": True,
        }
        candidate_id = "magnitude-delete-v1:" + _digest(payload)
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
            executor.context.pool,
            target.indices,
            target.coefficients,
            target.cumulative_parameter_counts,
        )
        preparation = StatePreparationSpec.create(
            reference_state=executor.context._actual_algorithm.ref_det,
            generator_definition_digest=generator_definition_digest(
                executor.context.pool
            ),
            ansatz_block_structure=(
                (block.family, block.pool_indices) for block in blocks
            ),
            ansatz_indices=target.indices,
            coefficients=target.coefficients,
            orbital_parameters=(),
            qubit_mapping="openfermion-jordan-wigner-v1",
            qubit_ordering=range(int(executor.context._actual_algorithm.n)),
        )
        physical_id = canonical_proposed_physical_state_id(
            problem_id=executor.context.problem_id,
            state_preparation_spec=preparation,
        )
        generated.append(
            {
                "candidate_id": candidate_id,
                "proposed_physical_state_id": physical_id,
            }
        )
        targets[candidate_id] = (position, target, physical_id)
        scored.append((abs(float(coefficient)) ** 2, candidate_id))
    scored.sort(key=lambda value: (value[0], value[1]))
    selected = scored[0][1]
    binding_body = {
        "schema": "v5-final.parent-native-candidate-work-binding.v1",
        "generated_candidates": generated,
        "expanded_physical_state_ids": [targets[selected][2]],
        "candidate_generation_count": len(generated),
        "unique_search_state_count": 1,
        "resource_recounts": 0,
        "rewrite_verifications": 0,
    }
    binding = dict(binding_body)
    binding["binding_digest"] = _digest(binding_body)
    boundary.persist_structural_binding(binding)
    position, target, _ = targets[selected]
    boundary.invoke(
        "rewrite-verification",
        lambda: len(target.indices) == len(source.indices) - 1
        or (_ for _ in ()).throw(
            ParentNativeExecutionError("magnitude deletion did not remove one generator")
        ),
        evidence={"candidate_id": selected, "physical_generator_deleted": True},
    )
    for label, structure, policy in (
        ("before", source, "physical"),
        ("after", target, "physical"),
        ("after-structural", target, "deterministic-structural"),
    ):
        boundary.invoke(
            "full-physical-resource-recount",
            lambda structure=structure, policy=policy: evaluate_full_circuit_resources(
                executor.context.pool,
                structure,
                paper_era_backend(),
                **(
                    {}
                    if policy == "physical"
                    else {"coefficient_policy": policy}
                ),
            ),
            evidence={"phase": label},
        )
    inverse = np.delete(
        np.delete(runtime.inverse_hessian, position, axis=0), position, axis=1
    )
    return selected, target, inverse


def _dynamic_v5_preparation(
    executor: PreparedMethodNativeExecutor,
    boundary: DurableWorkBoundary,
) -> tuple[tuple[Any, ...], tuple[Any, ...], dict[str, Any]]:
    """Build and account a child-dependent catalog after an accepted commit."""

    binding = dict(executor.context.runtime.metadata["candidate_work_binding"])
    upper = int(binding["dynamic_catalog_generation_upper_bound"])
    if upper <= 0:
        raise ParentNativeExecutionError("dynamic V5 catalog upper bound is absent")
    # Compression cannot introduce more source blocks or source coordinates than
    # the frozen source.  This frozen source count is therefore a conservative
    # pre-kernel bound for every child catalog in this study.
    boundary.recorder._precheck(
        WorkDelta(
            candidate_generations=upper,
            search_states=upper,
        ),
        "candidate-generation",
    )
    catalog = build_typed_catalog(
        executor.context.pool, executor.context.runtime.ansatz
    )
    if catalog.generated_candidate_intent_count > upper:
        raise ParentNativeExecutionError(
            "child catalog exceeded the outcome-blind frozen source upper bound"
        )
    if executor.method_id == "v5-fixed-source-whitelist-no-replenishment":
        source_keys = set(binding["source_whitelist_keys"])
        if not source_keys:
            raise ParentNativeExecutionError("fixed V5 source whitelist is absent")
        admitted = {
            candidate.candidate_id
            for candidate in catalog.candidates
            if candidate_structural_whitelist_key(candidate) in source_keys
        }
    else:
        admitted = {candidate.candidate_id for candidate in catalog.candidates}
    boundary.recorder._precheck(
        WorkDelta(
            resource_recounts=3 * len(admitted),
            rewrite_verifications=len(admitted),
        ),
        "rewrite-verification",
    )
    generated = _single_candidate_bindings(executor.context, catalog)
    if len(generated) != catalog.generated_candidate_intent_count:
        raise ParentNativeExecutionError("child catalog work binding is incomplete")
    plans, rewrites, ranking = _rank_parent_candidates(
        executor.context, catalog, admitted
    )
    binding_body = {
        "schema": "v5-final.parent-native-dynamic-candidate-work-binding.v1",
        "generated_candidates": [
            {
                "candidate_id": candidate_id,
                "proposed_physical_state_id": physical_id,
            }
            for candidate_id, physical_id in generated
        ],
        # Computing canonical physical identities is part of the full generated
        # catalog work, including candidates later filtered by fixed whitelist.
        "expanded_physical_state_ids": [physical_id for _, physical_id in generated],
        "candidate_generation_count": len(generated),
        "unique_search_state_count": len({value for _, value in generated}),
        "resource_recounts": 3 * len(admitted),
        "rewrite_verifications": len(admitted),
        "admitted_candidate_ids": sorted(admitted),
        "catalog_parent_structure_digest": executor.context.runtime.metadata[
            "resource_structure_digest"
        ],
    }
    dynamic_binding = dict(binding_body)
    dynamic_binding["binding_digest"] = _digest(binding_body)
    boundary.persist_structural_binding(dynamic_binding)
    return plans, rewrites, ranking


def _attempt_record(attempt: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in attempt.items()
        if key
        not in {
            "structure",
            "parameters",
            "inverse_hessian",
            "gradient",
            "statevector",
        }
    }


def _plan_physical_id(executor: PreparedMethodNativeExecutor, plan: Any) -> str:
    from .parent_native_physical_identity import canonical_proposed_physical_state_id

    return canonical_proposed_physical_state_id(
        problem_id=executor.context.problem_id,
        state_preparation_spec=plan.proposed_state_preparation_spec,
    )


def _optimize_and_decide(
    *,
    executor: PreparedMethodNativeExecutor,
    algorithm: Any,
    boundary: DurableWorkBoundary,
    target: AnsatzStructure,
    inverse_hessian: Any,
    parent_plan: Any | None,
    f0: float | None = None,
    g0: Any | None = None,
    require_resource_improvement: bool = True,
) -> dict[str, Any]:
    kernels = ActualOptimizationBoundary(algorithm, executor.context.pool, boundary)
    result = kernels.optimize(
        target.coefficients,
        target.indices,
        inverse_hessian,
        f0=f0,
        g0=g0,
    )
    coordinates = np.asarray(result.x, dtype=np.float64)
    optimized = AnsatzStructure.create(
        target.indices, coordinates, target.cumulative_parameter_counts
    )
    semantic_state = kernels.statevector(coordinates, target.indices)
    physical_state = kernels.independent_statevector(coordinates, target.indices)
    independent_energy = kernels.independent_energy(physical_state)
    after_resources = kernels.resources(optimized)
    before_resources = kernels.resources(executor.context.runtime.ansatz)
    fidelity = float(abs(np.vdot(semantic_state, physical_state)) ** 2)
    gradient = np.asarray(result.jac, dtype=np.float64)
    evidence = AcceptanceEvidence(
        source_energy_hartree=float(executor.context.runtime.energy_hartree),
        budget_reference_energy_hartree=float(
            executor.context.runtime.metadata["budget_reference_energy_hartree"]
        ),
        candidate_energy_hartree=float(result.fun),
        independent_energy_hartree=independent_energy,
        independent_state_fidelity=fidelity,
        constraint_residual=_constraint_residual(parent_plan, coordinates),
        kkt_residual=0.0 if not gradient.size else float(np.max(np.abs(gradient))),
        before_resources=_resource_snapshot(before_resources),
        after_resources=_resource_snapshot(after_resources),
        full_resource_recount_succeeded=True,
        transformation_semantics_validated=True,
        primary_optimizer=OptimizerOutcome(
            success=bool(result.success),
            status=str(result.status),
            message=str(result.message),
            completed=True,
        ),
        fallback_optimizer=None,
    )
    decision = evaluate_acceptance(
        evidence,
        AcceptanceCriteria(
            cumulative_energy_budget_hartree=1e-4,
            independent_energy_tolerance_hartree=1e-10,
            minimum_state_fidelity=1.0 - 1e-10,
            maximum_constraint_residual=1e-10,
            maximum_kkt_residual=1e-8,
            guard_logical_block_count=True,
            resource_policy="componentwise-pareto-v1",
        ),
    )
    accepted = decision.accepted
    if not require_resource_improvement:
        accepted = all(
            passed
            for name, passed in decision.checks.items()
            if name != "resource_improved"
        )
    acceptance_record = asdict(decision)
    acceptance_record["method_control_resource_improvement_required"] = (
        require_resource_improvement
    )
    acceptance_record["method_control_accepted"] = accepted
    return {
        "accepted": accepted,
        "acceptance": acceptance_record,
        "optimizer": {
            "success": bool(result.success),
            "status": int(result.status),
            "message": str(result.message),
            "iterations": int(result.nit),
            "energy_evaluations_reported": int(result.nfev),
            "gradient_evaluations_reported": int(result.njev),
        },
        "energy_hartree": float(result.fun),
        "independent_energy_hartree": independent_energy,
        "state_fidelity": fidelity,
        "gradient_infinity_norm": (
            0.0 if not gradient.size else float(np.max(np.abs(gradient)))
        ),
        "structure": optimized,
        "parameters": coordinates,
        "inverse_hessian": np.asarray(result.hess_inv, dtype=np.float64),
        "gradient": gradient,
        "statevector": semantic_state,
        "resources": asdict(after_resources.snapshot),
        "time_series": kernels.series,
    }


class ParentNativeExecutionServices:
    def __init__(
        self,
        *,
        item: Mapping[str, Any],
        plan: Mapping[str, Any],
        runner: ParentNativePersistentRunner,
        boundary: DurableWorkBoundary,
        algorithm: Any,
    ) -> None:
        self.item = dict(item)
        self.plan = dict(plan)
        self.runner = runner
        self.boundary = boundary
        self.algorithm = algorithm

    def execute_prepared(self, executor: PreparedMethodNativeExecutor) -> dict[str, Any]:
        method = executor.method_id
        started = time.perf_counter()
        attempts: list[dict[str, Any]] = []
        accepted_ids: list[str] = []
        final_resources: Mapping[str, Any] = executor.context.source_resources

        def finish(stopping_reason: str) -> dict[str, Any]:
            accepted = bool(accepted_ids) or method == "immutable-ceo-star-source"
            return {
                "terminal_status": "ACCEPTED" if accepted else "ALGORITHM_REJECTED",
                "stopping_reason": stopping_reason,
                "energy_hartree": float(executor.context.runtime.energy_hartree),
                "resources": dict(final_resources),
                "accepted_candidate_ids": list(accepted_ids),
                "attempts": attempts,
                "wall_time_seconds": time.perf_counter() - started,
            }

        if method == "immutable-ceo-star-source":
            return finish("IMMUTABLE_SOURCE_CONTROL")
        if method in {
            "v5-fixed-source-whitelist-no-replenishment",
            "v5-sequential-with-rebuilding",
        } and not executor.prepared_rewrites:
            return finish("NO_OUTCOME_BLIND_PARETO_CANDIDATE")
        if method == "same-structure-reoptimization":
            target = executor.context.runtime.ansatz
            attempt = _optimize_and_decide(
                executor=executor,
                algorithm=self.algorithm,
                boundary=self.boundary,
                target=target,
                inverse_hessian=executor.context.runtime.inverse_hessian,
                parent_plan=None,
                f0=float(executor.context.runtime.energy_hartree),
                g0=executor.context.runtime.gradient,
                require_resource_improvement=False,
            )
            candidate_id = "same-structure-reoptimization"
            attempts.append(
                _attempt_record(attempt)
                | {"candidate_ids": [candidate_id], "round": 1}
            )
            if not attempt["accepted"]:
                return finish("FROZEN_ACCEPTANCE_REJECTED")
            _commit_runtime(executor.context.runtime, attempt)
            accepted_ids.append(candidate_id)
            final_resources = attempt["resources"]
            return finish("SAME_STRUCTURE_REOPTIMIZATION_ACCEPTED")

        if method == "structural-magnitude-pruning":
            deletion = executor.magnitude_deletion
            if deletion is None:
                raise ParentNativeExecutionError("magnitude target is absent")
            prepared_target: tuple[str, AnsatzStructure, np.ndarray] | None = (
                deletion.candidate_id,
                deletion.target,
                np.delete(
                    np.delete(
                        executor.context.runtime.inverse_hessian,
                        deletion.position,
                        axis=0,
                    ),
                    deletion.position,
                    axis=1,
                ),
            )
            round_index = 0
            while prepared_target is not None:
                round_index += 1
                candidate_id, target, inverse = prepared_target
                try:
                    attempt = _optimize_and_decide(
                        executor=executor,
                        algorithm=self.algorithm,
                        boundary=self.boundary,
                        target=target,
                        inverse_hessian=inverse,
                        parent_plan=None,
                    )
                except ComponentwiseCapRejected:
                    if accepted_ids:
                        return finish("WORK_CAP_REACHED_AFTER_COMMITTED_MAGNITUDE_CHILD")
                    raise
                attempts.append(
                    _attempt_record(attempt)
                    | {"candidate_ids": [candidate_id], "round": round_index}
                )
                if not attempt["accepted"]:
                    return finish("MAGNITUDE_ACCEPTANCE_REJECTED")
                _commit_runtime(executor.context.runtime, attempt)
                accepted_ids.append(candidate_id)
                final_resources = attempt["resources"]
                try:
                    prepared_target = _dynamic_magnitude_preparation(
                        executor, self.boundary
                    )
                except ComponentwiseCapRejected:
                    return finish("WORK_CAP_REACHED_AFTER_COMMITTED_MAGNITUDE_CHILD")
            return finish("MAGNITUDE_SOURCE_FULLY_PRUNED")

        if len(executor.prepared_rewrites) != len(executor.candidate_plans):
            raise ParentNativeExecutionError(
                "prepared structural executor plan/rewrite cardinality differs"
            )
        current_plans = tuple(executor.candidate_plans)
        current_rewrites = tuple(executor.prepared_rewrites)
        evaluated: dict[str, dict[str, Any]] = {}
        round_index = 0
        while current_plans:
            round_index += 1
            committed = False
            for plan, rewrite in zip(current_plans, current_rewrites):
                candidate_ids = [
                    str(candidate.candidate_id) for candidate in plan.candidates
                ]
                physical_id = _plan_physical_id(executor, plan)
                prior = evaluated.get(physical_id)
                if prior is not None:
                    attempts.append(
                        {
                            "candidate_ids": candidate_ids,
                            "proposed_physical_state_id": physical_id,
                            "round": round_index,
                            "evaluation_reused": True,
                            "accepted": bool(prior["accepted"]),
                            "reused_attempt_digest": _digest(prior),
                        }
                    )
                    if prior["accepted"]:
                        raise ParentNativeExecutionError(
                            "an already committed physical state was proposed again"
                        )
                    continue
                try:
                    attempt = _optimize_and_decide(
                        executor=executor,
                        algorithm=self.algorithm,
                        boundary=self.boundary,
                        target=rewrite.target,
                        inverse_hessian=rewrite.target_inverse_hessian,
                        parent_plan=plan,
                    )
                except ComponentwiseCapRejected:
                    if accepted_ids:
                        return finish("WORK_CAP_REACHED_AFTER_COMMITTED_V5_CHILD")
                    raise
                record = _attempt_record(attempt) | {
                    "candidate_ids": candidate_ids,
                    "proposed_physical_state_id": physical_id,
                    "round": round_index,
                    "evaluation_reused": False,
                }
                attempts.append(record)
                evaluated[physical_id] = record
                if not attempt["accepted"]:
                    continue
                _commit_runtime(executor.context.runtime, attempt)
                accepted_ids.append("+".join(candidate_ids))
                final_resources = attempt["resources"]
                committed = True
                break
            if method == "v4.1-one-shot-joint-compression":
                return finish(
                    "V4_ONE_SHOT_ACCEPTED" if committed else "V4_ONE_SHOT_REJECTED"
                )
            if not committed:
                return finish("V5_CURRENT_CATALOG_EXHAUSTED_WITHOUT_ACCEPTANCE")
            try:
                current_plans, current_rewrites, _ = _dynamic_v5_preparation(
                    executor, self.boundary
                )
            except ComponentwiseCapRejected:
                return finish("WORK_CAP_REACHED_AFTER_COMMITTED_V5_CHILD")
        return finish("V5_NO_ADMISSIBLE_CHILD_AFTER_COMMIT")


def _outcome_checkpoint_path(raw_ledger_root: Path) -> Path:
    return raw_ledger_root.parent / f"{raw_ledger_root.name}.outcome.json"


def _outcome_checkpoint(
    request: ParentNativeWorkRequest, outcome_payload: Mapping[str, Any]
) -> dict[str, Any]:
    checkpoint = {
        "schema": "v5-final.parent-native-outcome-checkpoint.v1",
        "request_id": request.request_id,
        "queue_item_id": request.queue_item_id,
        "outcome_payload": dict(outcome_payload),
    }
    checkpoint["outcome_digest"] = _digest(checkpoint["outcome_payload"])
    checkpoint["checkpoint_digest"] = _digest(checkpoint)
    return checkpoint


def _read_outcome_checkpoint(
    path: Path, request: ParentNativeWorkRequest
) -> dict[str, Any]:
    from v5_matched_work.atomic_artifacts import canonical_json_bytes

    raw = path.read_bytes()
    try:
        checkpoint = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ParentNativeExecutionError("outcome checkpoint JSON is invalid") from error
    if raw != canonical_json_bytes(checkpoint):
        raise ParentNativeExecutionError("outcome checkpoint is not canonical JSON")
    body = dict(checkpoint)
    observed_checkpoint_digest = body.pop("checkpoint_digest", None)
    if (
        checkpoint.get("schema")
        != "v5-final.parent-native-outcome-checkpoint.v1"
        or checkpoint.get("request_id") != request.request_id
        or checkpoint.get("queue_item_id") != request.queue_item_id
        or checkpoint.get("outcome_digest")
        != _digest(checkpoint.get("outcome_payload"))
        or observed_checkpoint_digest != _digest(body)
    ):
        raise ParentNativeExecutionError("outcome checkpoint binding is invalid")
    return checkpoint


def _terminalize_checkpoint(
    runner: ParentNativePersistentRunner, checkpoint: Mapping[str, Any]
) -> None:
    payload = checkpoint["outcome_payload"]
    result = payload.get("result")
    if isinstance(result, dict) and result.get("terminal_status") == "ACCEPTED":
        runner.finish("ACCEPTED", outcome_digest=str(checkpoint["outcome_digest"]))
        return
    if isinstance(result, dict) and result.get("terminal_status") == "ALGORITHM_REJECTED":
        runner.finish(
            "ALGORITHM_REJECTED",
            rejection_reason=(
                f"{result['stopping_reason']}|outcome_digest="
                f"{checkpoint['outcome_digest']}"
            ),
        )
        return
    if payload.get("terminal_status") == "CAP_REJECTED":
        runner.finish(
            "CAP_REJECTED",
            rejection_reason=(
                "COMPONENTWISE_CAP_EXCEEDED|outcome_digest="
                f"{checkpoint['outcome_digest']}"
            ),
        )
        return
    raise ParentNativeExecutionError("outcome checkpoint terminal status is invalid")


def recover_frozen_item_result(
    *,
    plan: Mapping[str, Any],
    item: Mapping[str, Any],
    raw_ledger_root: Path,
    result_output: Path,
) -> dict[str, Any]:
    """Publish or republish a result without repeating any molecular kernel."""

    cap = WorkDelta(**dict(item["componentwise_work_cap"]))
    request = _work_request(item, plan)
    checkpoint = _read_outcome_checkpoint(
        _outcome_checkpoint_path(raw_ledger_root), request
    )
    state = replay_raw_ledger(
        raw_ledger_root, request=request, cap=cap, require_terminal=False
    )
    if state.terminal is None:
        runner = ParentNativePersistentRunner.open(
            raw_ledger_root, request=request, cap=cap
        )
        _terminalize_checkpoint(runner, checkpoint)
    recovered = recover_terminal_result(raw_ledger_root, request=request, cap=cap)
    terminal = recovered["terminal"]
    bound = (
        terminal.get("outcome_digest") == checkpoint["outcome_digest"]
        if terminal["terminal_status"] == "ACCEPTED"
        else f"outcome_digest={checkpoint['outcome_digest']}"
        in str(terminal.get("rejection_reason"))
    )
    if not bound:
        raise ParentNativeExecutionError("terminal does not bind outcome checkpoint")
    artifact = {
        "schema": "v5-final.parent-native-item-result.v1",
        "request": request.payload() | {"request_id": request.request_id},
        "outcome": checkpoint["outcome_payload"],
        "outcome_checkpoint_digest": checkpoint["checkpoint_digest"],
        "recovered": recovered,
    }
    artifact["artifact_digest"] = _digest(artifact)
    if result_output.exists():
        raw = result_output.read_bytes()
        from v5_matched_work.atomic_artifacts import canonical_json_bytes

        try:
            existing = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ParentNativeExecutionError("existing result JSON is invalid") from error
        if raw != canonical_json_bytes(existing) or existing != artifact:
            raise ParentNativeExecutionError("existing result differs from raw recovery")
        return artifact
    write_json_exclusive(result_output, artifact)
    return artifact


def execute_frozen_item(
    *,
    plan: Mapping[str, Any],
    item: Mapping[str, Any],
    raw_ledger_root: Path,
    result_output: Path,
) -> dict[str, Any]:
    random.seed(int(item["RNG_identity"]["python_seed"]))
    np.random.seed(int(item["RNG_identity"]["numpy_seed"]))
    cap = WorkDelta(**dict(item["componentwise_work_cap"]))
    if work_cap_digest(cap) != item["work_cap_digest"]:
        raise ParentNativeExecutionError("queue item cap digest differs")
    request = _work_request(item, plan)
    checkpoint_path = _outcome_checkpoint_path(raw_ledger_root)
    if raw_ledger_root.exists():
        if checkpoint_path.is_file():
            return recover_frozen_item_result(
                plan=plan,
                item=item,
                raw_ledger_root=raw_ledger_root,
                result_output=result_output,
            )
        raise ParentNativeExecutionError(
            "interrupted active ledger has no outcome checkpoint; explicit rollback/retry required"
        )
    if checkpoint_path.exists() or result_output.exists():
        raise ParentNativeExecutionError("orphan outcome or result artifact exists")
    attempt_id = make_attempt_id(request, ordinal=1, nonce="frozen-production-attempt-1")
    runner = ParentNativePersistentRunner.create(
        raw_ledger_root,
        request=request,
        cap=cap,
        attempt_id=attempt_id,
    )
    recorder = runner.resume_work_recorder()
    boundary = DurableWorkBoundary(runner, recorder)
    context = None
    snapshots: dict[str, str] | None = None
    source_snapshot = None
    try:
        context = build_queue_bound_runtime_v2(
            str(item["queue_item_id"]),
            plan_record=plan,
            work_recorder=boundary,
        )
        snapshots = _component_snapshot_digest(context.runtime)
        source_snapshot = context.runtime.snapshot()
        algorithm = context.release_for_h2_h4_execution()
        binding = item["candidate_work_binding"]
        expected_binding = dict(binding)
        observed_digest = expected_binding.pop("binding_digest")
        if observed_digest != _digest(expected_binding):
            raise ParentNativeExecutionError("candidate work binding digest mismatch")
        projected = WorkDelta(
            candidate_generations=int(binding["candidate_generation_count"]),
            search_states=int(binding["unique_search_state_count"]),
            resource_recounts=int(binding["resource_recounts"]),
            rewrite_verifications=int(binding["rewrite_verifications"]),
        )
        recorder._precheck(projected, "candidate-generation")
        if binding.get("schema") != "v5-final.parent-native-candidate-work-binding.v2":
            raise ParentNativeExecutionError("candidate work binding schema mismatch")
        context.runtime.metadata["candidate_work_binding"] = dict(binding)
        prepared = prepare_method_executor(context, item)
        boundary.persist_structural_binding(binding)
        services = ParentNativeExecutionServices(
            item=item,
            plan=plan,
            runner=runner,
            boundary=boundary,
            algorithm=algorithm,
        )
        result = prepared.execute(services)
        outcome_payload = {
            "queue_item_id": item["queue_item_id"],
            "method_id": item["method_id"],
            "case_id": item["case_id"],
            "work_envelope": item["work_envelope"],
            "result": result,
            "work_total": asdict(boundary.total),
            "telemetry": boundary.telemetry,
        }
        write_json_exclusive(
            checkpoint_path, _outcome_checkpoint(request, outcome_payload)
        )
        _terminalize_checkpoint(
            runner, _read_outcome_checkpoint(checkpoint_path, request)
        )
    except ComponentwiseCapRejected:
        outcome_payload = {
            "queue_item_id": item["queue_item_id"],
            "terminal_status": "CAP_REJECTED",
            "work_total": asdict(boundary.total),
            "telemetry": boundary.telemetry,
        }
        write_json_exclusive(
            checkpoint_path, _outcome_checkpoint(request, outcome_payload)
        )
        _terminalize_checkpoint(
            runner, _read_outcome_checkpoint(checkpoint_path, request)
        )
    except BaseException as error:
        if checkpoint_path.is_file():
            raise ParentNativeExecutionError(
                "outcome is durably checkpointed; rerun recovery without molecular work"
            ) from error
        try:
            runner.persist_new_work_events(recorder.events)
            if not any(event.outcome == "failed" for event in recorder.events):
                try:
                    recorder.invoke(
                        "rewrite-verification",
                        lambda: (_ for _ in ()).throw(
                            ParentNativeExecutionError(str(error))
                        ),
                        evidence={
                            "phase": "execution-integrity-validation",
                            "original_exception_type": type(error).__name__,
                        },
                    )
                except ParentNativeExecutionError:
                    pass
                runner.persist_new_work_events(recorder.events)
            if snapshots is None:
                seed = _digest(
                    {
                        "StatePreparationID": item["StatePreparationID"],
                        "source_checkpoint_digest": item["source_checkpoint_digest"],
                    }
                )
                snapshots = {name: seed for name in (
                    "ansatz",
                    "parameters",
                    "optimizer_inverse_hessian",
                    "resources",
                    "ledger_transaction",
                )}
            after = snapshots
            if context is not None and source_snapshot is not None:
                context.runtime.restore(source_snapshot)
                after = _component_snapshot_digest(context.runtime)
            runner.rollback_active_attempt(
                component_digests_before=snapshots,
                component_digests_after=after,
                reason=type(error).__name__,
            )
            runner.finish("KERNEL_FAILURE", rejection_reason=type(error).__name__)
        except BaseException as terminal_error:
            raise ParentNativeExecutionError(
                "kernel failed and exact terminalization also failed"
            ) from terminal_error
        raise
    return recover_frozen_item_result(
        plan=plan,
        item=item,
        raw_ledger_root=raw_ledger_root,
        result_output=result_output,
    )

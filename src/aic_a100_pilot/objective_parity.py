"""Paired CPU/A100 parity for the optimizer's actual energy objective.

This isolated pilot adapter leaves the production executor unchanged.  It uses
the pinned BFGS and CPU analytic gradient, but every GPU-side objective call
prepares the candidate state with Aer GPU in double precision before applying
the exact transferred sparse Hamiltonian on the host.
"""

from __future__ import annotations

from dataclasses import asdict
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import struct
import time
from types import SimpleNamespace
from typing import Any, Mapping, Sequence

import numpy as np

from .aer_gpu_backend import (
    RouteCounters,
    build_gpu_backend,
    gpu_statevector,
    hybrid_gpu_state_cpu_sparse_energy,
    phase_aligned_max_error,
)
from .benchmark import _gpu_observation
from .common import A100PilotError, digest, embedded_digest_valid, load_json
from .p3_objective_contract import CONTRACT
from .parity import build_context


class PilotBoundary:
    """Minimal in-memory boundary retaining the production optimizer accounting."""

    def __init__(self) -> None:
        self.events: list[Any] = []
        self.telemetry: list[dict[str, Any]] = []

    def invoke(self, operation: str, kernel: Any, **values: Any) -> Any:
        started = time.perf_counter()
        result = kernel()
        self.events.append(
            SimpleNamespace(
                operation=operation,
                outcome="completed",
                evidence=dict(values.get("evidence", {})),
            )
        )
        self.telemetry.append(
            {
                "operation": operation,
                "elapsed_seconds": time.perf_counter() - started,
            }
        )
        return result


def _float_hex(value: float) -> str:
    return struct.pack(">d", float(value)).hex()


def _boundary_classes() -> tuple[Any, Any, Any]:
    from v5_final.parent_native_execution_services import ActualOptimizationBoundary
    from v5_final.parent_native_zero_dimensional_v2 import ActualOptimizationBoundaryV2

    class CountedCPUOptimizationBoundary(ActualOptimizationBoundaryV2):
        capture: list[Any] | None = None

        def __init__(self, algorithm: Any, pool: Any, boundary: Any) -> None:
            super().__init__(algorithm, pool, boundary)
            self.routes = RouteCounters()
            if self.capture is None:
                raise A100PilotError("counted CPU boundary used outside isolated scope")
            self.capture.append(self)

        def energy(self, coordinates: Sequence[float], indices: Sequence[int]) -> float:
            value = super().energy(coordinates, indices)
            self.routes.N_cpu_statevector += 1
            self.routes.N_cpu_energy += 1
            return value

        def gradient(self, coordinates: Sequence[float], indices: Sequence[int]) -> np.ndarray:
            value = super().gradient(coordinates, indices)
            self.routes.N_cpu_gradient_component += len(value)
            return value

        def statevector(self, coordinates: Sequence[float], indices: Sequence[int]) -> np.ndarray:
            value = super().statevector(coordinates, indices)
            self.routes.N_cpu_statevector += 1
            return value

        def independent_statevector(
            self, coordinates: Sequence[float], indices: Sequence[int]
        ) -> np.ndarray:
            value = super().independent_statevector(coordinates, indices)
            self.routes.N_cpu_statevector += 1
            return value

        def independent_energy(self, statevector: np.ndarray) -> float:
            value = super().independent_energy(statevector)
            self.routes.N_cpu_energy += 1
            return value

    class GPUObjectiveOptimizationBoundary(ActualOptimizationBoundaryV2):
        def __init__(self, algorithm: Any, pool: Any, boundary: Any) -> None:
            super().__init__(algorithm, pool, boundary)
            self.backend = build_gpu_backend()
            self.routes = RouteCounters()
            self.metadata: list[dict[str, str]] = []
            self.reference = np.asarray(
                algorithm.ref_state.toarray(), dtype=np.complex128
            ).ravel()

        def energy(self, coordinates: Sequence[float], indices: Sequence[int]) -> float:
            evidence: dict[str, Any] = {
                "route": "AER_GPU_STATEVECTOR_PLUS_HOST_SPARSE_EXPECTATION"
            }

            def call() -> float:
                circuit = self.pool.get_circuit(list(indices), list(coordinates))
                value, _, metadata = hybrid_gpu_state_cpu_sparse_energy(
                    self.reference,
                    circuit,
                    self.algorithm.hamiltonian,
                    backend=self.backend,
                    counters=self.routes,
                )
                evidence["energy_float64"] = _float_hex(value)
                self.metadata.append(
                    {
                        "device": str(metadata.get("device", "")),
                        "method": str(metadata.get("method", "")),
                    }
                )
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
                    "route": evidence["route"],
                }
            )
            return value

        def gradient(self, coordinates: Sequence[float], indices: Sequence[int]) -> np.ndarray:
            value = super().gradient(coordinates, indices)
            self.routes.N_cpu_gradient_component += len(value)
            return value

        def statevector(self, coordinates: Sequence[float], indices: Sequence[int]) -> np.ndarray:
            value = super().statevector(coordinates, indices)
            self.routes.N_cpu_statevector += 1
            return value

        def independent_statevector(
            self, coordinates: Sequence[float], indices: Sequence[int]
        ) -> np.ndarray:
            evidence: dict[str, Any] = {
                "route": "AER_GPU_STATEVECTOR_INDEPENDENT_ACCEPTANCE_CHECK"
            }

            def call() -> np.ndarray:
                circuit = self.pool.get_circuit(list(indices), list(coordinates))
                value, metadata = gpu_statevector(
                    self.reference,
                    circuit,
                    backend=self.backend,
                    counters=self.routes,
                )
                evidence["statevector_sha256"] = hashlib.sha256(
                    np.asarray(value, dtype=">c16").tobytes()
                ).hexdigest()
                self.metadata.append(
                    {
                        "device": str(metadata.get("device", "")),
                        "method": str(metadata.get("method", "")),
                    }
                )
                return value

            return np.asarray(
                self.boundary.invoke(
                    "statevector-recomputation", call, evidence=evidence
                ),
                dtype=np.complex128,
            )

        def independent_energy(self, statevector: np.ndarray) -> float:
            evidence: dict[str, Any] = {
                "route": "HOST_SPARSE_EXPECTATION_OF_AER_GPU_STATEVECTOR"
            }

            def call() -> float:
                value = float(
                    np.real(
                        np.vdot(
                            statevector, self.algorithm.hamiltonian @ statevector
                        )
                    )
                )
                if not np.isfinite(value):
                    raise A100PilotError("independent GPU-state energy is nonfinite")
                evidence["energy_float64"] = _float_hex(value)
                self.routes.record_hybrid_energy()
                return value

            return float(
                self.boundary.invoke(
                    "candidate-energy-evaluation", call, evidence=evidence
                )
            )

    return (
        ActualOptimizationBoundary,
        CountedCPUOptimizationBoundary,
        GPUObjectiveOptimizationBoundary,
    )


@contextmanager
def counted_cpu_boundary_scope(original: Any, counted: Any):
    from v5_final import parent_native_execution_services as execution_v1

    if execution_v1.ActualOptimizationBoundary is not original:
        raise A100PilotError("unexpected production optimization-boundary override")
    captured: list[Any] = []
    counted.capture = captured
    execution_v1.ActualOptimizationBoundary = counted
    try:
        yield captured
    finally:
        execution_v1.ActualOptimizationBoundary = original
        counted.capture = None


def _attempt_with_kernels(
    *,
    context: Any,
    kernels: Any,
    target: Any,
    inverse_hessian: Any,
    parent_plan: Any,
) -> dict[str, Any]:
    from dvg_obs_ceo.resources import AnsatzStructure
    from dvg_obs_ceo.transaction import (
        AcceptanceCriteria,
        AcceptanceEvidence,
        OptimizerOutcome,
        evaluate_acceptance,
    )
    from v5_final.parent_native_execution_services import (
        _constraint_residual,
        _resource_snapshot,
    )
    result = kernels.optimize(
        target.coefficients,
        target.indices,
        inverse_hessian,
    )
    coordinates = np.asarray(result.x, dtype=np.float64)
    optimized = AnsatzStructure.create(
        target.indices, coordinates, target.cumulative_parameter_counts
    )
    semantic_state = kernels.statevector(coordinates, target.indices)
    physical_state = kernels.independent_statevector(coordinates, target.indices)
    independent_energy = kernels.independent_energy(physical_state)
    after_resources = kernels.resources(optimized)
    before_resources = kernels.resources(context.runtime.ansatz)
    fidelity = float(abs(np.vdot(semantic_state, physical_state)) ** 2)
    gradient = np.asarray(result.jac, dtype=np.float64)
    evidence = AcceptanceEvidence(
        source_energy_hartree=float(context.runtime.energy_hartree),
        budget_reference_energy_hartree=float(
            context.runtime.metadata["budget_reference_energy_hartree"]
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
    return {
        "accepted": bool(decision.accepted),
        "acceptance": asdict(decision),
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
        "gradient": gradient,
        "parameters": coordinates,
        "statevector": semantic_state,
        "independent_statevector": physical_state,
        "resources": asdict(after_resources.snapshot),
    }


def _contract_case(alias: str) -> tuple[dict[str, Any], dict[str, Any]]:
    contract = load_json(CONTRACT)
    if not embedded_digest_valid(contract, "contract_digest"):
        raise A100PilotError("P3 objective contract digest is invalid")
    matches = [
        case for case in contract["selection_policy"]["cases"] if case["alias"] == alias
    ]
    if len(matches) != 1:
        raise A100PilotError(f"P3 objective case is not unique: {alias}")
    return contract, matches[0]


def _prepare(alias: str, specification: Mapping[str, Any]) -> tuple[Any, Any, Any]:
    from v5_final.parent_native_candidate_adapter import (
        build_typed_catalog,
        compose_parent_native_plan,
    )
    from v5_final.parent_native_rewrite import prepare_rewrite_for_optimizer

    context = build_context(alias)
    catalog = build_typed_catalog(context.pool, context.runtime.ansatz)
    by_id = {candidate.candidate_id: candidate for candidate in catalog.candidates}
    ids = [str(value) for value in specification["composition_candidate_ids"]]
    if any(candidate_id not in by_id for candidate_id in ids):
        raise A100PilotError("frozen composition candidate is absent")
    selected = tuple(by_id[candidate_id] for candidate_id in ids)
    plan = compose_parent_native_plan(
        pool=context.pool,
        source=context.runtime.ansatz,
        catalog=catalog,
        candidates=selected,
        gradient=context.runtime.gradient,
        inverse_hessian=context.runtime.inverse_hessian,
        problem_id=context.problem_id,
        reference_state=context._actual_algorithm.ref_det,
    )
    rewrite = prepare_rewrite_for_optimizer(
        pool=context.pool,
        source=context.runtime.ansatz,
        parent_plan=plan,
    )
    if list(rewrite.verified_candidate_ids) != ids:
        raise A100PilotError("prepared rewrite candidate order differs")
    return context, plan, rewrite


def _serialize_attempt(value: Mapping[str, Any]) -> dict[str, Any]:
    gradient = np.asarray(value["gradient"], dtype=np.float64)
    return {
        "terminal_decision": "ACCEPTED" if value["accepted"] else "REJECTED",
        "acceptance_checks": dict(value["acceptance"]["checks"]),
        "acceptance_rejection_reasons": list(
            value["acceptance"]["rejection_reasons"]
        ),
        "optimizer_terminal": dict(value["optimizer"]),
        "energy_hartree": float(value["energy_hartree"]),
        "independent_energy_hartree": float(value["independent_energy_hartree"]),
        "state_fidelity": float(value["state_fidelity"]),
        "gradient": gradient.tolist(),
        "gradient_infinity_norm": (
            0.0 if not gradient.size else float(np.max(np.abs(gradient)))
        ),
        "parameters": np.asarray(value["parameters"], dtype=np.float64).tolist(),
        "resources": dict(value["resources"]),
    }


def run_case(alias: str) -> dict[str, Any]:
    from v5_final import parent_native_execution_services as execution_v1

    contract, specification = _contract_case(alias)
    context, plan, rewrite = _prepare(alias, specification)
    executor = SimpleNamespace(context=context)

    cpu_boundary = PilotBoundary()
    cpu_started = time.perf_counter()
    original_boundary, counted_class, gpu_class = _boundary_classes()
    with counted_cpu_boundary_scope(original_boundary, counted_class) as captured_cpu:
        cpu_raw = execution_v1._optimize_and_decide(
            executor=executor,
            algorithm=context._actual_algorithm,
            boundary=cpu_boundary,
            target=rewrite.target,
            inverse_hessian=rewrite.target_inverse_hessian,
            parent_plan=plan,
        )
    cpu_wall = time.perf_counter() - cpu_started
    if len(captured_cpu) != 1:
        raise A100PilotError("production CPU helper did not construct one boundary")
    counted_cpu = captured_cpu[0]

    gpu_boundary = PilotBoundary()
    gpu_kernels = gpu_class(
        context._actual_algorithm, context.pool, gpu_boundary
    )
    gpu_started = time.perf_counter()
    gpu_raw = _attempt_with_kernels(
        context=context,
        kernels=gpu_kernels,
        target=rewrite.target,
        inverse_hessian=rewrite.target_inverse_hessian,
        parent_plan=plan,
    )
    gpu_wall = time.perf_counter() - gpu_started

    cpu = _serialize_attempt(cpu_raw)
    gpu = _serialize_attempt(gpu_raw)
    frozen_resources = dict(specification["frozen_CPU_resource_vector"])
    checks = {
        "candidate_ids_exact": list(rewrite.verified_candidate_ids)
        == list(specification["composition_candidate_ids"]),
        "cpu_matches_frozen_terminal_decision": cpu["terminal_decision"]
        == specification["frozen_CPU_terminal_decision"],
        "gpu_matches_frozen_terminal_decision": gpu["terminal_decision"]
        == specification["frozen_CPU_terminal_decision"],
        "cpu_gpu_terminal_decision": cpu["terminal_decision"]
        == gpu["terminal_decision"],
        "cpu_gpu_acceptance_checks": cpu["acceptance_checks"]
        == gpu["acceptance_checks"],
        "resources_exact": cpu["resources"] == gpu["resources"] == frozen_resources,
        "energy": abs(cpu["energy_hartree"] - gpu["energy_hartree"]) <= 1e-10,
        "independent_energy": abs(
            cpu["independent_energy_hartree"] - gpu["independent_energy_hartree"]
        )
        <= 1e-10,
        "gradient": (
            max(
                (
                    abs(left - right)
                    for left, right in zip(cpu["gradient"], gpu["gradient"])
                ),
                default=0.0,
            )
            <= 1e-8
            and len(cpu["gradient"]) == len(gpu["gradient"])
        ),
        "state": phase_aligned_max_error(
            cpu_raw["independent_statevector"], gpu_raw["independent_statevector"]
        )
        <= 1e-10,
        "explicit_GPU_metadata": bool(gpu_kernels.metadata)
        and all(
            value["device"].upper() == "GPU"
            and "statevector" in value["method"].lower()
            for value in gpu_kernels.metadata
        ),
        "no_CPU_fallback": gpu_kernels.routes.N_cpu_fallback == 0,
        "GPU_objective_was_invoked": gpu_kernels.routes.N_gpu_energy
        == gpu["optimizer_terminal"]["energy_evaluations_reported"] + 1,
    }
    result = {
        "schema": "aic-a100-pilot.p3-production-objective-case-parity.v1",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "alias": alias,
        "case_id": specification["case_id"],
        "candidate_id": specification["candidate_id"],
        "composition_candidate_ids": specification["composition_candidate_ids"],
        "reference_class": specification["reference_class"],
        "P3_objective_contract_digest": contract["contract_digest"],
        "checks": checks,
        "cpu": cpu,
        "gpu": gpu,
        "differences": {
            "energy_hartree": abs(cpu["energy_hartree"] - gpu["energy_hartree"]),
            "independent_energy_hartree": abs(
                cpu["independent_energy_hartree"]
                - gpu["independent_energy_hartree"]
            ),
            "max_gradient_component": max(
                (
                    abs(left - right)
                    for left, right in zip(cpu["gradient"], gpu["gradient"])
                ),
                default=0.0,
            ),
            "phase_aligned_independent_state": phase_aligned_max_error(
                cpu_raw["independent_statevector"], gpu_raw["independent_statevector"]
            ),
        },
        "wall_time_seconds": {
            "production_CPU_helper": cpu_wall,
            "GPU_objective_adapter": gpu_wall,
            "counted_CPU_reconciliation_excluded": True,
        },
        "route_counters": {
            "cpu": counted_cpu.routes.as_dict(),
            "gpu": gpu_kernels.routes.as_dict(),
        },
        "optimizer_terminal_exact_fields_equal": cpu["optimizer_terminal"]
        == gpu["optimizer_terminal"],
        "hardware": {
            "gpu": _gpu_observation(),
            "slurm_job_id": int(os.environ["SLURM_JOB_ID"]),
            "node": os.environ.get("SLURMD_NODENAME"),
        },
        "scientific_boundary": {
            "new_paired_CPU_candidate_outcomes": 1,
            "new_GPU_candidate_outcomes": 1,
            "FCI_evaluations": 0,
            "P5_limited_scientific_pilot": "NOT_AUTHORIZED",
            "V5_performance_claim": "NOT_AUTHORIZED",
        },
    }
    result["record_digest"] = digest(result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=("h2", "h4", "lih", "h6", "beh2"), required=True)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    output = arguments.output
    if output is None:
        raw = os.environ.get("A100_OBJECTIVE_PARITY_OUTPUT")
        if not raw:
            raise RuntimeError("set --output or A100_OBJECTIVE_PARITY_OUTPUT")
        output = Path(raw)
    result = run_case(arguments.case)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    if result["status"] != "PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    main()

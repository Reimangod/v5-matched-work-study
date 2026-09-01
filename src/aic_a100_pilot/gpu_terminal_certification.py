"""GPU-backed VQE optimization with terminal-only CPU certification.

Unlike the historical objective-parity route, this route does not perform a
second full optimization on CPU.  It runs the registered GPU-backed objective
once, then evaluates the terminal coordinates once through the production CPU
energy/gradient/state/resource boundary.  It is an engineering qualification;
FCI and performance claims remain prohibited.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

import numpy as np

from .aer_gpu_backend import phase_aligned_max_error
from .common import digest
from .objective_parity import (
    PilotBoundary,
    _attempt_with_kernels,
    _boundary_classes,
    _contract_case,
    _prepare,
    _serialize_attempt,
)


def _cpu_terminal_certificate(
    *, context: Any, plan: Any, rewrite: Any, gpu_raw: dict[str, Any]
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
    from v5_final.parent_native_zero_dimensional_v2 import ActualOptimizationBoundaryV2

    coordinates = np.asarray(gpu_raw["parameters"], dtype=np.float64)
    indices = list(rewrite.target.indices)
    boundary = PilotBoundary()
    cpu = ActualOptimizationBoundaryV2(
        context._actual_algorithm, context.pool, boundary
    )
    energy = float(cpu.energy(coordinates, indices))
    gradient = np.asarray(cpu.gradient(coordinates, indices), dtype=np.float64)
    semantic_state = np.asarray(cpu.statevector(coordinates, indices), dtype=np.complex128)
    independent_state = np.asarray(
        cpu.independent_statevector(coordinates, indices), dtype=np.complex128
    )
    independent_energy = float(cpu.independent_energy(independent_state))
    optimized = AnsatzStructure.create(
        indices, coordinates, rewrite.target.cumulative_parameter_counts
    )
    before_resources = cpu.resources(context.runtime.ansatz)
    after_resources = cpu.resources(optimized)
    fidelity = float(abs(np.vdot(semantic_state, independent_state)) ** 2)
    optimizer = gpu_raw["optimizer"]
    evidence = AcceptanceEvidence(
        source_energy_hartree=float(context.runtime.energy_hartree),
        budget_reference_energy_hartree=float(
            context.runtime.metadata["budget_reference_energy_hartree"]
        ),
        candidate_energy_hartree=energy,
        independent_energy_hartree=independent_energy,
        independent_state_fidelity=fidelity,
        constraint_residual=_constraint_residual(plan, coordinates),
        kkt_residual=0.0 if not gradient.size else float(np.max(np.abs(gradient))),
        before_resources=_resource_snapshot(before_resources),
        after_resources=_resource_snapshot(after_resources),
        full_resource_recount_succeeded=True,
        transformation_semantics_validated=True,
        primary_optimizer=OptimizerOutcome(
            success=bool(optimizer["success"]),
            status=str(optimizer["status"]),
            message=str(optimizer["message"]),
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
        "terminal_decision": "ACCEPTED" if decision.accepted else "REJECTED",
        "acceptance_checks": dict(decision.checks),
        "acceptance_rejection_reasons": list(decision.rejection_reasons),
        "energy_hartree": energy,
        "independent_energy_hartree": independent_energy,
        "gradient": gradient,
        "gradient_infinity_norm": (
            0.0 if not gradient.size else float(np.max(np.abs(gradient)))
        ),
        "parameters": coordinates,
        "independent_statevector": independent_state,
        "resources": asdict(after_resources.snapshot),
        "event_operations": [event.operation for event in boundary.events],
        "full_cpu_optimization_performed": False,
    }


def _max_component_delta(left: Any, right: Any) -> float:
    first = np.asarray(left, dtype=np.float64).reshape(-1)
    second = np.asarray(right, dtype=np.float64).reshape(-1)
    if first.shape != second.shape:
        return float("inf")
    return 0.0 if not first.size else float(np.max(np.abs(first - second)))


def run_case(alias: str) -> dict[str, Any]:
    contract, specification = _contract_case(alias)
    context, plan, rewrite = _prepare(alias, specification)
    _, _, gpu_class = _boundary_classes()
    gpu_boundary = PilotBoundary()
    gpu_kernel = gpu_class(context._actual_algorithm, context.pool, gpu_boundary)
    gpu_raw = _attempt_with_kernels(
        context=context,
        kernels=gpu_kernel,
        target=rewrite.target,
        inverse_hessian=rewrite.target_inverse_hessian,
        parent_plan=plan,
    )
    gpu = _serialize_attempt(gpu_raw)
    cpu = _cpu_terminal_certificate(
        context=context, plan=plan, rewrite=rewrite, gpu_raw=gpu_raw
    )
    frozen_resources = dict(specification["frozen_CPU_resource_vector"])
    checks = {
        "candidate_ids_exact": list(rewrite.verified_candidate_ids)
        == list(specification["composition_candidate_ids"]),
        "no_full_cpu_optimization": cpu["full_cpu_optimization_performed"] is False,
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
        "gradient": _max_component_delta(cpu["gradient"], gpu["gradient"]) <= 1e-8,
        "state": phase_aligned_max_error(
            cpu["independent_statevector"], gpu_raw["independent_statevector"]
        )
        <= 1e-10,
        "explicit_GPU_metadata": bool(gpu_kernel.metadata)
        and all(
            value["device"].upper() == "GPU"
            and "statevector" in value["method"].lower()
            for value in gpu_kernel.metadata
        ),
        "no_CPU_fallback": gpu_kernel.routes.N_cpu_fallback == 0,
        "GPU_objective_was_invoked": gpu_kernel.routes.N_gpu_energy
        == gpu["optimizer_terminal"]["energy_evaluations_reported"] + 1,
    }
    result = {
        "schema": "aic-a100-dual-optimizer.gpu-terminal-certificate.v1",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "alias": alias,
        "case_id": specification["case_id"],
        "candidate_id": specification["candidate_id"],
        "composition_candidate_ids": specification["composition_candidate_ids"],
        "P3_objective_contract_digest": contract["contract_digest"],
        "checks": checks,
        "gpu": gpu,
        "cpu_terminal_certificate": {
            key: value
            for key, value in cpu.items()
            if key not in {"gradient", "parameters", "independent_statevector"}
        },
        "differences": {
            "energy_hartree": abs(cpu["energy_hartree"] - gpu["energy_hartree"]),
            "independent_energy_hartree": abs(
                cpu["independent_energy_hartree"] - gpu["independent_energy_hartree"]
            ),
            "max_gradient_component": _max_component_delta(
                cpu["gradient"], gpu["gradient"]
            ),
            "phase_aligned_independent_state": phase_aligned_max_error(
                cpu["independent_statevector"], gpu_raw["independent_statevector"]
            ),
        },
        "route_counters": {"gpu": gpu_kernel.routes.as_dict()},
        "scientific_boundary": {
            "new_GPU_candidate_outcomes": 1,
            "CPU_terminal_certificates": 1,
            "full_CPU_optimization_outcomes": 0,
            "FCI_evaluations": 0,
            "performance_claim": "NOT_AUTHORIZED",
        },
    }
    result["record_digest"] = digest(result)
    return result

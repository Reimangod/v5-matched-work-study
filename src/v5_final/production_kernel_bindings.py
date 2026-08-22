"""Pinned CEO*/DVG production kernel bindings with exact boundary callbacks.

This module can be imported under the pinned parent virtual environment.  It
does not instantiate a molecule or call a scientific kernel during MB5.1.
"""

from __future__ import annotations

import hashlib
import importlib
import inspect
from pathlib import Path
import sys
from typing import Any, Callable, Mapping, Sequence

from .s0_successor import CEO_COMMIT, LOCK_SHA256, PARENT_COMMIT, ROOT


PARENT_ROOT = ROOT / "provenance/dvg-obs-ceo"
PARENT_PYTHON = PARENT_ROOT / ".venv/bin/python"
PARENT_LOCK = PARENT_ROOT / "uv.lock"
API_SPECS = {
    "recover_blocks": (
        "dvg_obs_ceo.block_ir",
        "recover_dvg_blocks",
        "src/dvg_obs_ceo/block_ir.py",
    ),
    "enumerate_candidates": (
        "dvg_obs_ceo.block_ir",
        "enumerate_candidates",
        "src/dvg_obs_ceo/block_ir.py",
    ),
    "verify_rewrite": (
        "dvg_obs_ceo.block_ir",
        "validate_candidate_semantics",
        "src/dvg_obs_ceo/block_ir.py",
    ),
    "verify_target_circuit": (
        "dvg_obs_ceo.block_ir",
        "validate_target_circuit_semantics",
        "src/dvg_obs_ceo/block_ir.py",
    ),
    "get_state": (
        "adaptvqe.algorithms.adapt_vqe",
        "AdaptVQE.get_state",
        "vendor/ceo-adapt-vqe/adaptvqe/algorithms/adapt_vqe.py",
    ),
    "compute_state": (
        "adaptvqe.algorithms.adapt_vqe",
        "AdaptVQE.compute_state",
        "vendor/ceo-adapt-vqe/adaptvqe/algorithms/adapt_vqe.py",
    ),
    "evaluate_energy": (
        "adaptvqe.algorithms.adapt_vqe",
        "AdaptVQE.evaluate_energy",
        "vendor/ceo-adapt-vqe/adaptvqe/algorithms/adapt_vqe.py",
    ),
    "estimate_gradients": (
        "adaptvqe.algorithms.adapt_vqe",
        "AdaptVQE.estimate_gradients",
        "vendor/ceo-adapt-vqe/adaptvqe/algorithms/adapt_vqe.py",
    ),
    "optimize": (
        "adaptvqe.algorithms.adapt_vqe",
        "AdaptVQE.optimize",
        "vendor/ceo-adapt-vqe/adaptvqe/algorithms/adapt_vqe.py",
    ),
    "minimize_bfgs": (
        "adaptvqe.minimize",
        "minimize_bfgs",
        "vendor/ceo-adapt-vqe/adaptvqe/minimize.py",
    ),
    "get_qasm": (
        "adaptvqe.op_conv",
        "get_qasm",
        "vendor/ceo-adapt-vqe/adaptvqe/op_conv.py",
    ),
    "cnot_count": (
        "adaptvqe.circuits",
        "cnot_count",
        "vendor/ceo-adapt-vqe/adaptvqe/circuits.py",
    ),
    "cnot_depth": (
        "adaptvqe.circuits",
        "cnot_depth",
        "vendor/ceo-adapt-vqe/adaptvqe/circuits.py",
    ),
    "total_depth": (
        "adaptvqe.circuits",
        "get_gate_depth",
        "vendor/ceo-adapt-vqe/adaptvqe/circuits.py",
    ),
}


class ProductionKernelBindingError(RuntimeError):
    pass


def _resolve(module_name: str, qualified_name: str) -> tuple[Any, Any]:
    module = importlib.import_module(module_name)
    value: Any = module
    for part in qualified_name.split("."):
        value = getattr(value, part)
    if not callable(value):
        raise ProductionKernelBindingError(f"pinned API is not callable: {qualified_name}")
    return module, value


def inspect_pinned_api() -> dict[str, Any]:
    records: dict[str, Any] = {}
    for role, (module_name, qualified_name, expected_relative_path) in API_SPECS.items():
        _, value = _resolve(module_name, qualified_name)
        source_file = Path(inspect.getsourcefile(value) or "").resolve()
        expected = (PARENT_ROOT / expected_relative_path).resolve()
        if source_file != expected:
            raise ProductionKernelBindingError(
                f"pinned API source path mismatch for {role}: {source_file}"
            )
        records[role] = {
            "module": module_name,
            "qualified_name": qualified_name,
            "qualified_entrypoint": f"{module_name}:{qualified_name}",
            "source_path": str(source_file.relative_to(ROOT)),
            "source_sha256": hashlib.sha256(source_file.read_bytes()).hexdigest(),
            "signature": str(inspect.signature(value)),
            "callable": True,
        }
    lock_sha256 = hashlib.sha256(PARENT_LOCK.read_bytes()).hexdigest()
    return {
        "schema": "v5-final.mb5-1-pinned-production-api.v1",
        "parent_commit": PARENT_COMMIT,
        "CEO_commit": CEO_COMMIT,
        "root_dependency_lock_sha256": LOCK_SHA256,
        "parent_dependency_lock_sha256": lock_sha256,
        "python_executable": str(PARENT_PYTHON.relative_to(ROOT)),
        "environment": {
            "python_version": ".".join(str(item) for item in sys.version_info[:3]),
            "python_implementation": sys.implementation.name,
            "byte_order": sys.byteorder,
            "platform_policy": "exact execution platform is frozen with the MB6 queue",
        },
        "APIs": records,
        "molecular_kernel_called": False,
        "candidate_energy_evaluations": 0,
    }


class PinnedCEOProductionKernelBindings:
    """Actual upstream calls, exposed only at counted method-native boundaries.

    Construction requires already identity-validated algorithm and pool objects.
    The callback receives the operation before each call so cap rejection can
    happen before computation.  MB5.1 only audits this call graph; it does not
    construct this class with a molecular object.
    """

    def __init__(
        self,
        *,
        algorithm: Any,
        pool: Any,
        before_call: Callable[[str, int | None], None],
    ) -> None:
        if algorithm is None or pool is None or not callable(before_call):
            raise ProductionKernelBindingError("validated algorithm, pool, and counter are required")
        self.algorithm = algorithm
        self.pool = pool
        self.before_call = before_call
        self.api = {
            role: _resolve(module, qualified)[1]
            for role, (module, qualified, _) in API_SPECS.items()
        }

    def statevector(self, coefficients: Sequence[float], indices: Sequence[int]) -> Any:
        self.before_call("statevector-recomputation", None)
        return self.algorithm.compute_state(list(coefficients), list(indices))

    def energy(self, coefficients: Sequence[float], indices: Sequence[int], *, source: bool) -> float:
        self.before_call(
            "source-energy-evaluation" if source else "candidate-energy-evaluation", None
        )
        return float(self.algorithm.evaluate_energy(list(coefficients), list(indices)))

    def gradient(self, coefficients: Sequence[float], indices: Sequence[int]) -> Any:
        self.before_call("full-gradient-evaluation", len(indices))
        return self.algorithm.estimate_gradients(list(coefficients), list(indices), method="an")

    def optimize_bfgs(
        self,
        coefficients: Sequence[float],
        indices: Sequence[int],
        *,
        initial_inverse_hessian: Any,
        maximum_iterations: int,
    ) -> Any:
        """Run the pinned optimizer with counted energy, gradient, and iteration calls."""

        self.before_call("optimizer-start", None)

        def energy(parameters: Any, bound_indices: Sequence[int]) -> float:
            return self.energy(parameters, bound_indices, source=False)

        def gradient(parameters: Any, bound_indices: Sequence[int]) -> Any:
            return self.gradient(parameters, bound_indices)

        def iteration(_: Any) -> None:
            self.before_call("optimizer-iteration", None)

        return self.api["minimize_bfgs"](
            energy,
            list(coefficients),
            args=(list(indices),),
            jac=gradient,
            callback=iteration,
            maxiter=maximum_iterations,
            initial_inv_hessian=initial_inverse_hessian,
        )

    def hessian_vector_product(
        self,
        coefficients_plus: Sequence[float],
        coefficients_minus: Sequence[float],
        indices: Sequence[int],
    ) -> tuple[Any, Any]:
        self.before_call("hessian-vector-product", None)
        plus = self.gradient(coefficients_plus, indices)
        minus = self.gradient(coefficients_minus, indices)
        return plus, minus

    def catalog(
        self,
        indices: Sequence[int],
        coefficients: Sequence[float],
        cumulative_counts: Sequence[int],
    ) -> tuple[Any, Any]:
        self.before_call("candidate-generation", None)
        blocks = self.api["recover_blocks"](
            self.pool, indices, coefficients, cumulative_counts
        )
        return blocks, self.api["enumerate_candidates"](self.pool, blocks)

    def verify_rewrite(
        self, candidate: Any, source_matrices: Sequence[Any], target_matrices: Sequence[Any]
    ) -> None:
        self.before_call("rewrite-verification", None)
        self.api["verify_rewrite"](candidate, source_matrices, target_matrices)

    def resource_recount(
        self, coefficients: Sequence[float], indices: Sequence[int], qubit_count: int
    ) -> Mapping[str, int]:
        self.before_call("full-physical-resource-recount", None)
        try:
            circuit = self.pool.get_circuit(list(coefficients), list(indices))
        except TypeError:
            circuit = self.pool.get_circuit(list(indices), list(coefficients))
        qasm = self.api["get_qasm"](circuit)
        return {
            "cnot_count": int(self.api["cnot_count"](qasm)),
            "cnot_depth": int(self.api["cnot_depth"](qasm, qubit_count)),
            "total_depth": int(circuit.depth()),
            "parameter_count": len(coefficients),
            "logical_block_count": len(indices),
        }

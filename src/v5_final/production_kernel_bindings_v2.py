"""Behaviorally auditable successor bindings for pinned CEO*/DVG kernels."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
import hashlib
import importlib
import inspect
from pathlib import Path
import sys
from typing import Any, Protocol, runtime_checkable

from .s0_successor import CEO_COMMIT, LOCK_SHA256, PARENT_COMMIT, ROOT


PARENT_ROOT = ROOT / "provenance/dvg-obs-ceo"
PARENT_LOCK = PARENT_ROOT / "uv.lock"
API_SPECS = {
    "recover_blocks": ("dvg_obs_ceo.block_ir", "recover_dvg_blocks", "src/dvg_obs_ceo/block_ir.py"),
    "enumerate_candidates": ("dvg_obs_ceo.block_ir", "enumerate_candidates", "src/dvg_obs_ceo/block_ir.py"),
    "verify_rewrite": ("dvg_obs_ceo.block_ir", "validate_candidate_semantics", "src/dvg_obs_ceo/block_ir.py"),
    "compute_state": ("adaptvqe.algorithms.adapt_vqe", "AdaptVQE.compute_state", "vendor/ceo-adapt-vqe/adaptvqe/algorithms/adapt_vqe.py"),
    "evaluate_energy": ("adaptvqe.algorithms.adapt_vqe", "AdaptVQE.evaluate_energy", "vendor/ceo-adapt-vqe/adaptvqe/algorithms/adapt_vqe.py"),
    "estimate_gradients": ("adaptvqe.algorithms.adapt_vqe", "AdaptVQE.estimate_gradients", "vendor/ceo-adapt-vqe/adaptvqe/algorithms/adapt_vqe.py"),
    "minimize_bfgs": ("adaptvqe.minimize", "minimize_bfgs", "vendor/ceo-adapt-vqe/adaptvqe/minimize.py"),
    "get_qasm": ("adaptvqe.op_conv", "get_qasm", "vendor/ceo-adapt-vqe/adaptvqe/op_conv.py"),
    "cnot_count": ("adaptvqe.circuits", "cnot_count", "vendor/ceo-adapt-vqe/adaptvqe/circuits.py"),
    "cnot_depth": ("adaptvqe.circuits", "cnot_depth", "vendor/ceo-adapt-vqe/adaptvqe/circuits.py"),
}


class KernelBindingError(RuntimeError):
    pass


def _resolve(module_name: str, qualified_name: str) -> Any:
    value: Any = importlib.import_module(module_name)
    for part in qualified_name.split("."):
        value = getattr(value, part)
    if not callable(value):
        raise KernelBindingError(f"pinned API is not callable: {module_name}:{qualified_name}")
    return value


def inspect_pinned_api_v2() -> dict[str, Any]:
    apis: dict[str, Any] = {}
    for role, (module, qualified, relative_path) in API_SPECS.items():
        value = _resolve(module, qualified)
        source = Path(inspect.getsourcefile(value) or "").resolve()
        expected = (PARENT_ROOT / relative_path).resolve()
        if source != expected:
            raise KernelBindingError(f"source path mismatch for {role}: {source}")
        apis[role] = {
            "entrypoint": f"{module}:{qualified}",
            "callable": True,
            "signature": str(inspect.signature(value)),
            "source_path": str(source.relative_to(ROOT)),
            "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        }
    return {
        "schema": "v5-final.mb5-2-pinned-production-api.v1",
        "parent_commit": PARENT_COMMIT,
        "CEO_commit": CEO_COMMIT,
        "root_dependency_lock_sha256": LOCK_SHA256,
        "parent_dependency_lock_sha256": hashlib.sha256(PARENT_LOCK.read_bytes()).hexdigest(),
        "python": ".".join(str(item) for item in sys.version_info[:3]),
        "APIs": apis,
    }


@runtime_checkable
class KernelBindingProtocol(Protocol):
    binding_kind: str
    trace: list[dict[str, Any]]

    def statevector(self, coefficients: Sequence[float], indices: Sequence[int]) -> Any: ...
    def energy(self, coefficients: Sequence[float], indices: Sequence[int], *, source: bool) -> float: ...
    def gradient(self, coefficients: Sequence[float], indices: Sequence[int]) -> Any: ...
    def optimize_bfgs(self, coefficients: Sequence[float], indices: Sequence[int], *, initial_inverse_hessian: Any, maximum_iterations: int) -> Any: ...
    def hessian_vector_product(self, coefficients_plus: Sequence[float], coefficients_minus: Sequence[float], indices: Sequence[int]) -> tuple[Any, Any]: ...
    def catalog(self, indices: Sequence[int], coefficients: Sequence[float], cumulative_counts: Sequence[int], *, parent_digest: str) -> tuple[Any, list[dict[str, Any]]]: ...
    def verify_rewrite(self, candidate: Any, source_matrices: Sequence[Any], target_matrices: Sequence[Any]) -> None: ...
    def resource_recount(self, coefficients: Sequence[float], indices: Sequence[int], qubit_count: int) -> Mapping[str, int]: ...


class PinnedCEOProductionKernelBindings:
    """Actual pinned calls. Every operation is delegated through recorder.invoke."""

    binding_kind = "PINNED_ACTUAL_CEO_DVG_KERNELS"

    def __init__(self, *, algorithm: Any, pool: Any, recorder: Any) -> None:
        if algorithm is None or pool is None or not callable(getattr(recorder, "invoke", None)):
            raise KernelBindingError("validated algorithm, pool, and persistent recorder are required")
        self.algorithm = algorithm
        self.pool = pool
        self.recorder = recorder
        self.trace: list[dict[str, Any]] = []
        self.api = {role: _resolve(module, qualified) for role, (module, qualified, _) in API_SPECS.items()}

    def _invoke(self, operation: str, thunk: Callable[[], Any], *, units: int | None = None, evidence: Mapping[str, Any] | None = None) -> Any:
        self.trace.append({"operation": operation, "units": units})
        return self.recorder.invoke(operation, thunk, units=units, evidence=evidence or {})

    def statevector(self, coefficients: Sequence[float], indices: Sequence[int]) -> Any:
        return self._invoke("statevector-recomputation", lambda: self.algorithm.compute_state(list(coefficients), list(indices)))

    def energy(self, coefficients: Sequence[float], indices: Sequence[int], *, source: bool) -> float:
        operation = "source-energy-evaluation" if source else "candidate-energy-evaluation"
        return float(self._invoke(operation, lambda: self.algorithm.evaluate_energy(list(coefficients), list(indices))))

    def gradient(self, coefficients: Sequence[float], indices: Sequence[int]) -> Any:
        return self._invoke("full-gradient-evaluation", lambda: self.algorithm.estimate_gradients(list(coefficients), list(indices), method="an"), units=len(indices))

    def optimize_bfgs(self, coefficients: Sequence[float], indices: Sequence[int], *, initial_inverse_hessian: Any, maximum_iterations: int) -> Any:
        self._invoke("optimizer-start", lambda: None)

        def energy(parameters: Any, bound_indices: Sequence[int]) -> float:
            return self.energy(parameters, bound_indices, source=False)

        def gradient(parameters: Any, bound_indices: Sequence[int]) -> Any:
            return self.gradient(parameters, bound_indices)

        def iteration(_: Any) -> None:
            self._invoke("optimizer-iteration", lambda: None)

        return self.api["minimize_bfgs"](
            energy,
            list(coefficients),
            args=(list(indices),),
            jac=gradient,
            callback=iteration,
            maxiter=maximum_iterations,
            initial_inv_hessian=initial_inverse_hessian,
        )

    def hessian_vector_product(self, coefficients_plus: Sequence[float], coefficients_minus: Sequence[float], indices: Sequence[int]) -> tuple[Any, Any]:
        self._invoke("hessian-vector-product", lambda: None)
        return self.gradient(coefficients_plus, indices), self.gradient(coefficients_minus, indices)

    def catalog(self, indices: Sequence[int], coefficients: Sequence[float], cumulative_counts: Sequence[int], *, parent_digest: str) -> tuple[Any, list[dict[str, Any]]]:
        def call() -> tuple[Any, list[dict[str, Any]]]:
            blocks = self.api["recover_blocks"](self.pool, indices, coefficients, cumulative_counts)
            return blocks, list(self.api["enumerate_candidates"](self.pool, blocks))

        return self._invoke("candidate-generation", call, evidence={"catalog_parent_digest": parent_digest})

    def verify_rewrite(self, candidate: Any, source_matrices: Sequence[Any], target_matrices: Sequence[Any]) -> None:
        self._invoke("rewrite-verification", lambda: self.api["verify_rewrite"](candidate, source_matrices, target_matrices))

    def resource_recount(self, coefficients: Sequence[float], indices: Sequence[int], qubit_count: int) -> Mapping[str, int]:
        def call() -> Mapping[str, int]:
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

        return self._invoke("full-physical-resource-recount", call)


class FakeBehavioralKernelBindings:
    """Outcome-free behavioral double with the exact production method surface."""

    binding_kind = "OUTCOME_FREE_BEHAVIORAL_FAKE"

    def __init__(self, *, recorder: Any, catalog: Sequence[Mapping[str, Any]], fail_operation: str | None = None) -> None:
        self.recorder = recorder
        self.catalog_fixture = [dict(item) for item in catalog]
        self.fail_operation = fail_operation
        self.trace: list[dict[str, Any]] = []

    def _call(self, operation: str, value: Any, *, units: int | None = None, evidence: Mapping[str, Any] | None = None) -> Any:
        self.trace.append({"operation": operation, "units": units, "synthetic": True})

        def thunk() -> Any:
            if self.fail_operation == operation:
                raise RuntimeError(f"injected fake failure: {operation}")
            return value() if callable(value) else value

        return self.recorder.invoke(operation, thunk, units=units, evidence={"synthetic_behavioral": True, **dict(evidence or {})})

    def statevector(self, coefficients: Sequence[float], indices: Sequence[int]) -> dict[str, Any]:
        return self._call("statevector-recomputation", {"opaque_state": True})

    def energy(self, coefficients: Sequence[float], indices: Sequence[int], *, source: bool) -> float:
        return float(self._call("source-energy-evaluation" if source else "candidate-energy-evaluation", 0.0))

    def gradient(self, coefficients: Sequence[float], indices: Sequence[int]) -> list[float]:
        return list(self._call("full-gradient-evaluation", [0.0] * len(indices), units=len(indices)))

    def optimize_bfgs(self, coefficients: Sequence[float], indices: Sequence[int], *, initial_inverse_hessian: Any, maximum_iterations: int) -> dict[str, Any]:
        self._call("optimizer-start", None)
        self.energy(coefficients, indices, source=False)
        self.gradient(coefficients, indices)
        self._call("optimizer-iteration", None)
        return {"parameters": list(coefficients), "iterations": 1, "synthetic": True}

    def hessian_vector_product(self, coefficients_plus: Sequence[float], coefficients_minus: Sequence[float], indices: Sequence[int]) -> tuple[Any, Any]:
        self._call("hessian-vector-product", None)
        return self.gradient(coefficients_plus, indices), self.gradient(coefficients_minus, indices)

    def catalog(self, indices: Sequence[int], coefficients: Sequence[float], cumulative_counts: Sequence[int], *, parent_digest: str) -> tuple[list[Any], list[dict[str, Any]]]:
        candidates = [dict(item, catalog_parent_digest=parent_digest) for item in self.catalog_fixture]
        return self._call("candidate-generation", ([], candidates), evidence={"catalog_parent_digest": parent_digest})

    def verify_rewrite(self, candidate: Any, source_matrices: Sequence[Any], target_matrices: Sequence[Any]) -> None:
        self._call("rewrite-verification", None)

    def resource_recount(self, coefficients: Sequence[float], indices: Sequence[int], qubit_count: int) -> Mapping[str, int]:
        return self._call("full-physical-resource-recount", {
            "cnot_count": max(0, 2 * len(indices)),
            "cnot_depth": max(0, len(indices)),
            "total_depth": max(0, 3 * len(indices)),
            "parameter_count": len(coefficients),
            "logical_block_count": len(indices),
        })

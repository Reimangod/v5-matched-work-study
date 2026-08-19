"""Fail-closed CuPy sparse exponential action for the frozen CEO* kernel.

The degree and scaling parameters are selected by the pinned SciPy 1.10.1
Al-Mohy--Higham implementation on the CPU.  Only the Taylor sparse matrix-vector
work is moved to CUDA.  Backend telemetry is deliberately separate from the
frozen matched-work scientific counters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import math
from typing import Any, Mapping, Sequence

import numpy as np
from scipy import sparse
from scipy.sparse.linalg._expm_multiply import (
    LazyOperatorNormInfo,
    _exact_1_norm,
    _fragment_3_1,
)


class GPUSparseActionError(RuntimeError):
    pass


PLANNED_CPU_OPERATIONS = {
    "cpu-norm-and-taylor-parameter-selection",
    "host-to-device-matrix-materialization",
    "host-to-device-vector-transfer",
    "device-to-host-result-transfer",
    "gpu-scalar-convergence-readback",
}
GPU_OPERATIONS = {
    "gpu-sparse-matvec",
    "gpu-vector-update",
    "gpu-hamiltonian-matvec",
    "gpu-inner-product",
}


@dataclass
class HybridBackendLedger:
    events: list[dict[str, Any]] = field(default_factory=list)
    unexpected_cpu_fallbacks: int = 0

    def record(self, operation: str, *, units: int = 1, evidence: Mapping[str, Any] | None = None) -> None:
        if isinstance(units, bool) or not isinstance(units, int) or units < 0:
            raise GPUSparseActionError("backend telemetry units are invalid")
        if operation not in PLANNED_CPU_OPERATIONS | GPU_OPERATIONS:
            self.unexpected_cpu_fallbacks += 1
            raise GPUSparseActionError(f"unregistered backend operation: {operation}")
        self.events.append(
            {
                "sequence": len(self.events),
                "operation": operation,
                "units": units,
                "evidence": dict(evidence or {}),
            }
        )

    def totals(self) -> dict[str, int]:
        totals = {name: 0 for name in sorted(PLANNED_CPU_OPERATIONS | GPU_OPERATIONS)}
        for event in self.events:
            totals[event["operation"]] += int(event["units"])
        return totals


def _sparse_digest(matrix: sparse.csr_matrix) -> str:
    value = matrix.tocsr().astype(np.complex128)
    digest = hashlib.sha256()
    digest.update(np.asarray(value.shape, dtype=">i8").tobytes())
    digest.update(value.indptr.astype(">i8", copy=False).tobytes())
    digest.update(value.indices.astype(">i8", copy=False).tobytes())
    digest.update(value.data.astype(">c16", copy=False).tobytes())
    return digest.hexdigest()


@dataclass(frozen=True)
class TaylorPlan:
    coefficient: float
    mu: complex
    degree: int
    scaling: int
    tolerance: float


class CuPySparseExpmActionV1:
    def __init__(self, matrix: Any, ledger: HybridBackendLedger) -> None:
        import cupy as cp
        import cupyx.scipy.sparse as cupy_sparse

        cpu = sparse.csr_matrix(matrix, dtype=np.complex128)
        if cpu.ndim != 2 or cpu.shape[0] != cpu.shape[1]:
            raise GPUSparseActionError("generator must be a square sparse matrix")
        if not np.all(np.isfinite(cpu.data)):
            raise GPUSparseActionError("generator contains nonfinite values")
        self.cp = cp
        self.ledger = ledger
        self.dimension = int(cpu.shape[0])
        self.matrix_digest = _sparse_digest(cpu)
        self.mu = complex(cpu.diagonal().sum() / float(self.dimension))
        shifted = cpu - self.mu * sparse.identity(
            self.dimension, dtype=np.complex128, format="csr"
        )
        self.shifted_cpu = shifted.tocsr()
        self.one_norm = float(_exact_1_norm(self.shifted_cpu))
        self.shifted_gpu = cupy_sparse.csr_matrix(self.shifted_cpu)
        self.ledger.record(
            "host-to-device-matrix-materialization",
            evidence={"matrix_digest": self.matrix_digest, "dimension": self.dimension},
        )
        self._plan_cache: dict[tuple[str, int], TaylorPlan] = {}

    def plan(self, coefficient: float, *, columns: int = 1) -> TaylorPlan:
        coefficient = float(coefficient)
        if not math.isfinite(coefficient) or columns <= 0:
            raise GPUSparseActionError("exponential action input is invalid")
        key = (coefficient.hex(), int(columns))
        cached = self._plan_cache.get(key)
        if cached is not None:
            return cached
        scaled_norm = abs(coefficient) * self.one_norm
        if scaled_norm == 0.0:
            degree, scaling = 0, 1
        else:
            tolerance = 2**-53
            norm_info = LazyOperatorNormInfo(
                coefficient * self.shifted_cpu,
                A_1_norm=scaled_norm,
                ell=2,
            )
            degree, scaling = _fragment_3_1(
                norm_info, int(columns), tolerance, ell=2
            )
        plan = TaylorPlan(
            coefficient=coefficient,
            mu=self.mu,
            degree=int(degree),
            scaling=int(scaling),
            tolerance=2**-53,
        )
        self._plan_cache[key] = plan
        self.ledger.record(
            "cpu-norm-and-taylor-parameter-selection",
            evidence={
                "matrix_digest": self.matrix_digest,
                "coefficient_float64_hex": coefficient.hex(),
                "degree": plan.degree,
                "scaling": plan.scaling,
            },
        )
        return plan

    def to_device(self, vector: Any):
        array = np.asarray(vector, dtype=np.complex128)
        if array.ndim not in (1, 2) or array.shape[0] != self.dimension:
            raise GPUSparseActionError("state shape differs from generator dimension")
        self.ledger.record(
            "host-to-device-vector-transfer", evidence={"shape": list(array.shape)}
        )
        return self.cp.asarray(array)

    def apply_device(self, coefficient: float, vector: Any):
        cp = self.cp
        if not isinstance(vector, cp.ndarray):
            raise GPUSparseActionError("device action requires a CuPy array")
        if vector.ndim not in (1, 2) or int(vector.shape[0]) != self.dimension:
            raise GPUSparseActionError("device state shape differs")
        columns = 1 if vector.ndim == 1 else int(vector.shape[1])
        plan = self.plan(coefficient, columns=columns)
        state = vector.astype(cp.complex128, copy=True)
        accumulated = state.copy()
        eta = cp.exp(plan.coefficient * plan.mu / float(plan.scaling))
        for _ in range(plan.scaling):
            c1 = float(cp.linalg.norm(state, ord=cp.inf).item())
            self.ledger.record("gpu-scalar-convergence-readback")
            for step in range(plan.degree):
                factor = plan.coefficient / float(plan.scaling * (step + 1))
                state = factor * self.shifted_gpu.dot(state)
                self.ledger.record("gpu-sparse-matvec")
                c2 = float(cp.linalg.norm(state, ord=cp.inf).item())
                self.ledger.record("gpu-scalar-convergence-readback")
                accumulated = accumulated + state
                self.ledger.record("gpu-vector-update")
                norm_f = float(cp.linalg.norm(accumulated, ord=cp.inf).item())
                self.ledger.record("gpu-scalar-convergence-readback")
                if c1 + c2 <= plan.tolerance * norm_f:
                    break
                c1 = c2
            accumulated = eta * accumulated
            self.ledger.record("gpu-vector-update")
            state = accumulated
        return accumulated

    def apply(self, coefficient: float, vector: Any) -> np.ndarray:
        result = self.apply_device(coefficient, self.to_device(vector))
        self.ledger.record(
            "device-to-host-result-transfer", evidence={"shape": list(result.shape)}
        )
        return np.asarray(self.cp.asnumpy(result), dtype=np.complex128)


class CuPyCEOStateKernelV1:
    """GPU state/energy/analytic-gradient kernel with frozen CPU control semantics."""

    def __init__(
        self,
        *,
        hamiltonian: Any,
        generators: Mapping[int, Any],
        reference_state: Any,
        ledger: HybridBackendLedger | None = None,
    ) -> None:
        import cupy as cp
        import cupyx.scipy.sparse as cupy_sparse

        self.cp = cp
        self.ledger = ledger or HybridBackendLedger()
        hamiltonian_cpu = sparse.csr_matrix(hamiltonian, dtype=np.complex128)
        if hamiltonian_cpu.shape[0] != hamiltonian_cpu.shape[1]:
            raise GPUSparseActionError("Hamiltonian must be square")
        self.dimension = int(hamiltonian_cpu.shape[0])
        reference = np.asarray(
            reference_state.toarray() if sparse.issparse(reference_state) else reference_state,
            dtype=np.complex128,
        ).ravel()
        if reference.shape != (self.dimension,) or np.linalg.norm(reference) == 0.0:
            raise GPUSparseActionError("reference state is invalid")
        self.reference_gpu = cp.asarray(reference / np.linalg.norm(reference))
        self.ledger.record(
            "host-to-device-vector-transfer", evidence={"role": "reference_state"}
        )
        self.hamiltonian_gpu = cupy_sparse.csr_matrix(hamiltonian_cpu)
        self.ledger.record(
            "host-to-device-matrix-materialization", evidence={"role": "hamiltonian"}
        )
        self.actions = {
            int(index): CuPySparseExpmActionV1(matrix, self.ledger)
            for index, matrix in generators.items()
        }

    def _action(self, index: int) -> CuPySparseExpmActionV1:
        try:
            return self.actions[int(index)]
        except KeyError as error:
            raise GPUSparseActionError("unbound generator index") from error

    def compute_state_device(
        self,
        coefficients: Sequence[float],
        indices: Sequence[int],
        *,
        reference_device: Any | None = None,
        bra: bool = False,
    ):
        if len(coefficients) != len(indices):
            raise GPUSparseActionError("coefficient/index length differs")
        state = (
            self.reference_gpu.copy()
            if reference_device is None
            else reference_device.astype(self.cp.complex128, copy=True)
        )
        pairs = list(zip(coefficients, indices))
        if bra:
            pairs = [(-float(value), index) for value, index in reversed(pairs)]
        for coefficient, index in pairs:
            state = self._action(int(index)).apply_device(float(coefficient), state)
        return state

    def statevector(self, coefficients: Sequence[float], indices: Sequence[int]) -> np.ndarray:
        state = self.compute_state_device(coefficients, indices)
        self.ledger.record("device-to-host-result-transfer", evidence={"role": "statevector"})
        return np.asarray(self.cp.asnumpy(state), dtype=np.complex128)

    def energy(self, coefficients: Sequence[float], indices: Sequence[int]) -> float:
        state = self.compute_state_device(coefficients, indices)
        h_state = self.hamiltonian_gpu.dot(state)
        self.ledger.record("gpu-hamiltonian-matvec")
        value = self.cp.vdot(state, h_state)
        self.ledger.record("gpu-inner-product")
        return float(value.real.item())

    def gradient(self, coefficients: Sequence[float], indices: Sequence[int]) -> np.ndarray:
        if not indices:
            return np.asarray([], dtype=np.float64)
        state = self.compute_state_device(coefficients, indices)
        h_state = self.hamiltonian_gpu.dot(state)
        self.ledger.record("gpu-hamiltonian-matvec")
        left = self.compute_state_device(
            coefficients, indices, reference_device=h_state, bra=True
        )
        right = self.reference_gpu.copy()
        gradients: list[float] = []
        for coefficient, index in zip(coefficients, indices):
            action = self._action(int(index))
            left = action.apply_device(float(coefficient), left)
            right = action.apply_device(float(coefficient), right)
            generator_right = action.shifted_gpu.dot(right) + action.mu * right
            self.ledger.record("gpu-sparse-matvec")
            value = self.cp.vdot(left, generator_right)
            self.ledger.record("gpu-inner-product")
            gradients.append(2.0 * float(value.real.item()))
        return np.asarray(gradients, dtype=np.float64)

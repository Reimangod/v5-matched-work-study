from __future__ import annotations

import numpy as np

from v5_final import gpu_rtx2080ti_s5_backend_implementation_v1 as s5


def test_synthetic_problem_is_hermitian_and_generators_antihermitian() -> None:
    hamiltonian, generators, reference = s5.synthetic_problem(32)
    h_residual = hamiltonian - hamiltonian.getH()
    assert not h_residual.nnz or np.max(np.abs(h_residual.data)) <= 1e-15
    for matrix in generators.values():
        residual = matrix + matrix.getH()
        assert not residual.nnz or np.max(np.abs(residual.data)) <= 1e-15
    assert np.linalg.norm(reference) == 1.0


def test_cpu_synthetic_energy_is_finite() -> None:
    hamiltonian, generators, reference = s5.synthetic_problem(32)
    value = s5._cpu_energy(
        np.asarray([0.23, -0.31]), hamiltonian, generators, reference
    )
    assert np.isfinite(value)

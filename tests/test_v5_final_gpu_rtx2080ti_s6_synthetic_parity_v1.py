from __future__ import annotations

import numpy as np

from v5_final import gpu_rtx2080ti_s6_synthetic_parity_v1 as s6
from v5_final.gpu_rtx2080ti_s5_backend_implementation_v1 import synthetic_problem


def test_cpu_analytic_gradient_matches_finite_difference() -> None:
    hamiltonian, generators, reference = synthetic_problem(32)
    coordinates = np.asarray([0.23, -0.31], dtype=np.float64)
    gradient = s6._cpu_gradient(
        coordinates, [0, 1], hamiltonian, generators, reference
    )
    step = 1e-6
    finite = []
    for position in range(2):
        plus = coordinates.copy()
        minus = coordinates.copy()
        plus[position] += step
        minus[position] -= step
        plus_state = s6._cpu_state(plus, [0, 1], generators, reference)
        minus_state = s6._cpu_state(minus, [0, 1], generators, reference)
        plus_energy = float(np.vdot(plus_state, hamiltonian @ plus_state).real)
        minus_energy = float(np.vdot(minus_state, hamiltonian @ minus_state).real)
        finite.append((plus_energy - minus_energy) / (2 * step))
    assert np.max(np.abs(gradient - np.asarray(finite))) <= 1e-7


def test_array_digest_is_repeatable() -> None:
    value = np.asarray([1 + 2j, 3 - 4j], dtype=np.complex128)
    assert s6._array_sha(value) == s6._array_sha(value.copy())

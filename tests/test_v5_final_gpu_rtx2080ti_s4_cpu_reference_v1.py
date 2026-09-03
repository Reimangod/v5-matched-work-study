from __future__ import annotations

import numpy as np
from scipy.sparse.linalg import norm as sparse_norm

from v5_final import gpu_rtx2080ti_s4_cpu_reference_v1 as s4


def test_synthetic_matrix_is_exactly_antihermitian() -> None:
    matrix = s4._antihermitian_matrix(32)
    assert matrix.shape == (32, 32)
    assert sparse_norm(matrix + matrix.getH()) <= 1e-14


def test_probe_vector_is_complex128_and_normalized() -> None:
    vector = s4._probe_vector(32)
    assert vector.dtype == np.complex128
    assert abs(np.linalg.norm(vector) - 1.0) <= 1e-15


def test_small_cpu_reference_preserves_norm() -> None:
    result = s4._single_benchmark(32, 2)
    assert result["repetitions"] == 2
    assert result["median_wall_seconds"] > 0
    assert abs(result["output_norm"] - 1.0) <= 1e-12

from __future__ import annotations

import numpy as np
import pytest
from scipy import sparse

from v5_final.gpu_sparse_action_v1 import (
    GPUSparseActionError,
    HybridBackendLedger,
    _sparse_digest,
)


def test_sparse_digest_is_content_addressed() -> None:
    matrix = sparse.csr_matrix([[0, 1], [-1, 0]], dtype=np.complex128)
    assert _sparse_digest(matrix) == _sparse_digest(matrix.copy())
    changed = matrix.copy()
    changed.data[0] += 1e-12
    assert _sparse_digest(matrix) != _sparse_digest(changed)


def test_backend_ledger_rejects_unknown_fallback() -> None:
    ledger = HybridBackendLedger()
    with pytest.raises(GPUSparseActionError, match="unregistered"):
        ledger.record("silent-numpy-fallback")
    assert ledger.unexpected_cpu_fallbacks == 1


def test_backend_ledger_keeps_operational_counts_separate() -> None:
    ledger = HybridBackendLedger()
    ledger.record("gpu-sparse-matvec", units=3)
    ledger.record("cpu-norm-and-taylor-parameter-selection")
    totals = ledger.totals()
    assert totals["gpu-sparse-matvec"] == 3
    assert totals["cpu-norm-and-taylor-parameter-selection"] == 1
    assert ledger.unexpected_cpu_fallbacks == 0

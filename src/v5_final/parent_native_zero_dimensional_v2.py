"""Additive zero-dimensional optimizer compatibility for the S9-v2 rerun.

The frozen S9-v1 execution service remains byte-for-byte unchanged.  This module
installs a narrowly scoped replacement only while one v2 item executes.  The
replacement differs from v1 solely when the target has zero variational
coordinates; non-empty targets delegate to the frozen v1 implementation.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import threading
from types import SimpleNamespace
from typing import Any, Iterator, Mapping, Sequence

import numpy as np

from . import parent_native_execution_services as v1


class ZeroDimensionalBoundaryError(v1.ParentNativeExecutionError):
    pass


class ActualOptimizationBoundaryV2(v1.ActualOptimizationBoundary):
    """Treat an empty target as a measured zero-step optimization."""

    def optimize(
        self,
        initial: Sequence[float],
        indices: Sequence[int],
        inverse_hessian: Any,
        *,
        f0: float | None = None,
        g0: Any | None = None,
    ) -> Any:
        if len(indices) != 0:
            return super().optimize(
                initial,
                indices,
                inverse_hessian,
                f0=f0,
                g0=g0,
            )
        coordinates = np.asarray(initial, dtype=np.float64)
        inverse = np.asarray(inverse_hessian, dtype=np.float64)
        if coordinates.shape != (0,):
            raise ZeroDimensionalBoundaryError(
                "zero-dimensional target must have an empty coordinate vector"
            )
        if inverse.shape != (0, 0):
            raise ZeroDimensionalBoundaryError(
                "zero-dimensional target must have a 0x0 inverse Hessian"
            )
        if g0 is not None and np.asarray(g0, dtype=np.float64).shape != (0,):
            raise ZeroDimensionalBoundaryError(
                "zero-dimensional target may only bind an empty initial gradient"
            )
        self.boundary.invoke(
            "optimizer-start",
            lambda: None,
            evidence={
                "remediation": "s9-v2-zero-dimensional-boundary-v1",
                "parameter_dimension": 0,
            },
        )
        energy = self.energy(coordinates, ())
        return SimpleNamespace(
            x=coordinates,
            fun=energy,
            jac=np.empty((0,), dtype=np.float64),
            hess_inv=inverse,
            success=True,
            status=0,
            message=(
                "zero-dimensional target evaluated without gradient or optimizer "
                "iteration"
            ),
            nit=0,
            nfev=1,
            njev=0,
        )


_LOCK = threading.RLock()
_V1_BOUNDARY = v1.ActualOptimizationBoundary


@contextmanager
def zero_dimensional_boundary_scope() -> Iterator[None]:
    """Install and always restore the additive boundary in one isolated process."""

    with _LOCK:
        if v1.ActualOptimizationBoundary is not _V1_BOUNDARY:
            raise ZeroDimensionalBoundaryError(
                "unexpected execution-boundary override already active"
            )
        v1.ActualOptimizationBoundary = ActualOptimizationBoundaryV2
        try:
            yield
        finally:
            if v1.ActualOptimizationBoundary is not ActualOptimizationBoundaryV2:
                v1.ActualOptimizationBoundary = _V1_BOUNDARY
                raise ZeroDimensionalBoundaryError(
                    "execution-boundary override changed during v2 item"
                )
            v1.ActualOptimizationBoundary = _V1_BOUNDARY


def execute_frozen_item_v2(
    *,
    plan: Mapping[str, Any],
    item: Mapping[str, Any],
    raw_ledger_root: Path,
    result_output: Path,
) -> dict[str, Any]:
    with zero_dimensional_boundary_scope():
        return v1.execute_frozen_item(
            plan=plan,
            item=item,
            raw_ledger_root=raw_ledger_root,
            result_output=result_output,
        )

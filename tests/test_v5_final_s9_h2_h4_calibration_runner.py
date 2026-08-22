from __future__ import annotations

import numpy as np
import pytest

from v5_final import parent_native_execution_services as execution_services_v1
from v5_final.parent_native_zero_dimensional_v2 import (
    ActualOptimizationBoundaryV2,
    zero_dimensional_boundary_scope,
)
from v5_final.s9_h2_h4_calibration_runner import (
    THRESHOLD_BYTES,
    _capacity_observation,
    _item_key,
    _plan,
    build_ci_audit,
)
from v5_final.s9_h2_h4_calibration_runner_v2 import (
    RUNNER_SOURCES as V2_RUNNER_SOURCES,
    RUN_NAMESPACE,
    S9_V2_DIR,
    build_ci_audit as build_v2_ci_audit,
)
from v5_final.s9_v1_zero_dimensional_halt import (
    HALT_PATH,
    audit_failure_state,
    audit_halt,
)


def test_s9_capacity_guard_and_frozen_paths_are_exact():
    assert _capacity_observation(THRESHOLD_BYTES)["passed"] is True
    assert _capacity_observation(THRESHOLD_BYTES - 1)["passed"] is False
    plan = _plan()
    keys = [_item_key(index, item) for index, item in enumerate(plan["items"])]
    assert len(keys) == len(set(keys)) == 36
    assert keys[0].startswith("000-")
    assert keys[-1].startswith("035-")


def test_s9_ci_audit_never_authorizes_development_or_performance():
    report = build_ci_audit()
    assert all(report["checks"].values())
    assert report["authorization"]["development_queue_execution"] == "NOT_AUTHORIZED"
    assert report["authorization"]["performance_claim"] == "NOT_AUTHORIZED"


def test_s9_v1_failure_is_preserved_and_blocks_later_dispatch():
    state = audit_failure_state()
    assert all(state["checks"].values())
    assert state["report"]["progress"]["completed_terminal_count"] == 3
    assert state["report"]["progress"]["terminal_status_counts"][
        "KERNEL_FAILURE"
    ] == 1
    assert state["result"]["outcome"]["performance_evidence"] is False
    if HALT_PATH.exists():
        assert all(audit_halt().values())


class _ZeroDimensionalAlgorithm:
    def __init__(self):
        self.energy_calls = []

    def evaluate_energy(self, coordinates, indices):
        self.energy_calls.append((coordinates, indices))
        return -1.0

    def estimate_gradients(self, *_args, **_kwargs):
        raise AssertionError("zero-dimensional optimization must not request a gradient")


class _RecordingBoundary:
    def __init__(self):
        self.operations = []

    def invoke(self, operation, kernel, **values):
        self.operations.append((operation, values))
        return kernel()


def test_s9_v2_zero_dimensional_rule_is_shape_only_and_exactly_counted():
    algorithm = _ZeroDimensionalAlgorithm()
    boundary = _RecordingBoundary()
    optimizer = ActualOptimizationBoundaryV2(algorithm, None, boundary)
    result = optimizer.optimize([], [], np.empty((0, 0), dtype=np.float64))
    assert algorithm.energy_calls == [([], [])]
    assert [operation for operation, _ in boundary.operations] == [
        "optimizer-start",
        "candidate-energy-evaluation",
    ]
    assert result.x.shape == (0,)
    assert result.jac.shape == (0,)
    assert result.hess_inv.shape == (0, 0)
    assert result.fun == -1.0
    assert result.nit == 0
    assert result.nfev == 1
    assert result.njev == 0


def test_s9_v2_scoped_override_restores_v1_and_namespaces_outputs():
    original = execution_services_v1.ActualOptimizationBoundary
    with zero_dimensional_boundary_scope():
        assert (
            execution_services_v1.ActualOptimizationBoundary
            is ActualOptimizationBoundaryV2
        )
    assert execution_services_v1.ActualOptimizationBoundary is original
    with pytest.raises(RuntimeError, match="sentinel"):
        with zero_dimensional_boundary_scope():
            raise RuntimeError("sentinel")
    assert execution_services_v1.ActualOptimizationBoundary is original
    assert S9_V2_DIR.name == RUN_NAMESPACE
    assert all(path.is_file() for path in V2_RUNNER_SOURCES)


def test_s9_v2_ci_audit_isolated_and_never_claims_v1_performance():
    v2_report = build_v2_ci_audit()
    assert all(v2_report["checks"].values())
    assert all(v2_report["halt_audit"].values())
    assert all(v2_report["v2_checks"].values())
    assert v2_report["run_namespace"] == RUN_NAMESPACE
    assert v2_report["remediation"]["v1_results_are_performance_evidence"] is False
    assert v2_report["authorization"]["development_queue_execution"] == "NOT_AUTHORIZED"
    assert v2_report["authorization"]["performance_claim"] == "NOT_AUTHORIZED"
    v1_report = build_ci_audit()
    assert v1_report["progress"]["completed_terminal_count"] == 3
    assert v1_report["progress"]["terminal_status_counts"]["KERNEL_FAILURE"] == 1

from __future__ import annotations

import numpy as np
import pytest

from v5_final.parent_native_execution_services import ActualOptimizationBoundary
from v5_final.parent_native_work_accounting import (
    ComponentwiseCapRejected,
    ParentNativeWorkRecorder,
    ParentNativeWorkRequest,
    work_cap_digest,
)
from v5_final.semantic_contract_v2 import WorkDelta


class _RecorderBoundary:
    def __init__(self, recorder: ParentNativeWorkRecorder):
        self.recorder = recorder

    @property
    def events(self):
        return self.recorder.events

    def invoke(self, operation, kernel, **values):
        return self.recorder.invoke(operation, kernel, **values)


class _Quadratic:
    def __init__(self, diagonal=(1.0, 3.0), *, fail_energy_call=None):
        self.diagonal = np.asarray(diagonal, dtype=np.float64)
        self.energy_calls = 0
        self.gradient_calls = 0
        self.fail_energy_call = fail_energy_call

    def evaluate_energy(self, coordinates, _indices):
        self.energy_calls += 1
        if self.energy_calls == self.fail_energy_call:
            raise RuntimeError("injected toy energy failure")
        values = np.asarray(coordinates, dtype=np.float64)
        return 0.5 * float(np.dot(values, self.diagonal * values))

    def estimate_gradients(self, coordinates, _indices, *, method):
        assert method == "an"
        self.gradient_calls += 1
        return self.diagonal * np.asarray(coordinates, dtype=np.float64)


def _cap(**overrides):
    values = {
        "energy_evaluations": 100,
        "gradient_vector_evaluations": 100,
        "gradient_component_equivalents": 200,
        "optimizer_starts": 10,
        "optimizer_iterations": 100,
    }
    values.update(overrides)
    return WorkDelta(**values)


def _request(cap):
    return ParentNativeWorkRequest(
        queue_item_id="s11-v2-item-v2:" + "1" * 64,
        method_id="same-structure-reoptimization",
        case_id="toy-quadratic",
        state_preparation_id="state-v1:" + "2" * 64,
        problem_id="problem-v1:" + "3" * 64,
        hamiltonian_digest="4" * 64,
        source_checkpoint_digest="5" * 64,
        frozen_queue_digest="6" * 64,
        work_cap_digest=work_cap_digest(cap),
    )


def _boundary(algorithm, cap=None, events=()):
    frozen_cap = cap or _cap()
    request = _request(frozen_cap)
    recorder = ParentNativeWorkRecorder.resume(
        request=request, cap=frozen_cap, events=events
    )
    return (
        ActualOptimizationBoundary(algorithm, None, _RecorderBoundary(recorder)),
        recorder,
    )


def _operation_count(recorder, operation):
    return sum(event.operation == operation for event in recorder.events)


@pytest.mark.parametrize(
    ("provide_f0", "provide_g0"),
    ((False, False), (True, False), (False, True), (True, True)),
)
def test_bfgs_reported_counts_equal_ledger_for_all_seed_combinations(
    provide_f0, provide_g0
):
    algorithm = _Quadratic()
    optimizer, recorder = _boundary(algorithm)
    initial = np.asarray([1.5, -0.75])
    f0 = algorithm.evaluate_energy(initial, [0, 1]) if provide_f0 else None
    g0 = algorithm.estimate_gradients(initial, [0, 1], method="an") if provide_g0 else None
    algorithm.energy_calls = 0
    algorithm.gradient_calls = 0
    result = optimizer.optimize(
        initial,
        [0, 1],
        np.eye(2),
        f0=f0,
        g0=g0,
    )
    assert result.success
    assert result.nfev == _operation_count(recorder, "candidate-energy-evaluation")
    assert result.njev == _operation_count(recorder, "full-gradient-evaluation")
    assert result.nit == _operation_count(recorder, "optimizer-iteration")
    assert _operation_count(recorder, "optimizer-start") == 1
    assert recorder.total.gradient_component_equivalents == 2 * result.njev
    assert recorder.total.gradient_vector_evaluations == result.njev


def test_initial_point_convergence_with_f0_g0_has_zero_kernel_evaluations():
    algorithm = _Quadratic()
    optimizer, recorder = _boundary(algorithm)
    result = optimizer.optimize(
        [0.0, 0.0], [0, 1], np.eye(2), f0=0.0, g0=np.zeros(2)
    )
    assert result.success and result.nit == 0
    assert result.nfev == result.njev == 0
    assert recorder.total.optimizer_starts == 1
    assert recorder.total.energy_evaluations == 0
    assert recorder.total.gradient_vector_evaluations == 0


def test_line_search_failure_preserves_exact_result_ledger_parity(monkeypatch):
    import adaptvqe.minimize as pinned

    def fail_line_search(*_args, **_kwargs):
        raise pinned._LineSearchError()

    monkeypatch.setattr(pinned, "_line_search_wolfe12", fail_line_search)
    algorithm = _Quadratic()
    optimizer, recorder = _boundary(algorithm)
    result = optimizer.optimize([1.0, -1.0], [0, 1], np.eye(2))
    assert not result.success and result.status == 2 and result.nit == 0
    assert result.nfev == _operation_count(recorder, "candidate-energy-evaluation")
    assert result.njev == _operation_count(recorder, "full-gradient-evaluation")
    assert _operation_count(recorder, "optimizer-iteration") == 0


def test_mid_optimization_cap_rejection_is_pre_kernel_and_preserves_work():
    cap = _cap(
        energy_evaluations=1,
        gradient_vector_evaluations=100,
        gradient_component_equivalents=200,
    )
    algorithm = _Quadratic()
    optimizer, recorder = _boundary(algorithm, cap)
    with pytest.raises(ComponentwiseCapRejected):
        optimizer.optimize([1.0, -1.0], [0, 1], np.eye(2))
    assert recorder.total.energy_evaluations == 1
    rejection = recorder.events[-1]
    assert rejection.operation == "cap-rejection"
    assert rejection.delta == WorkDelta()
    assert rejection.evidence["kernel_executed"] is False


def test_failed_call_is_counted_and_retry_does_not_reset_prior_work():
    cap = _cap()
    failed_algorithm = _Quadratic(fail_energy_call=1)
    first, recorder = _boundary(failed_algorithm, cap)
    with pytest.raises(RuntimeError, match="injected"):
        first.optimize([1.0, -1.0], [0, 1], np.eye(2))
    failed_events = recorder.events
    assert recorder.total.energy_evaluations == 1
    assert any(
        event.operation == "candidate-energy-evaluation"
        and event.outcome == "failed"
        for event in failed_events
    )

    retry_algorithm = _Quadratic()
    retry, resumed = _boundary(retry_algorithm, cap, failed_events)
    result = retry.optimize(
        [0.0, 0.0], [0, 1], np.eye(2), f0=0.0, g0=np.zeros(2)
    )
    assert result.success
    assert resumed.total.energy_evaluations == 1
    assert resumed.total.optimizer_starts == 2
    assert resumed.events[: len(failed_events)] == failed_events

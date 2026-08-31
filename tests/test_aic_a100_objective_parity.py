from __future__ import annotations

from types import SimpleNamespace

from aic_a100_pilot.objective_parity import PilotBoundary


def test_pilot_boundary_preserves_optimizer_event_cardinality():
    boundary = PilotBoundary()
    assert boundary.invoke("optimizer-start", lambda: None) is None
    assert boundary.invoke("candidate-energy-evaluation", lambda: 1.25) == 1.25
    assert [event.operation for event in boundary.events] == [
        "optimizer-start",
        "candidate-energy-evaluation",
    ]
    assert all(event.outcome == "completed" for event in boundary.events)


def test_pilot_boundary_does_not_record_failed_kernel_as_completed():
    boundary = PilotBoundary()

    def fail():
        raise RuntimeError("expected")

    try:
        boundary.invoke("candidate-energy-evaluation", fail)
    except RuntimeError:
        pass
    else:
        raise AssertionError("failed kernel was not propagated")
    assert boundary.events == []

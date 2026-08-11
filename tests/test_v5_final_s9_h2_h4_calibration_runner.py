from __future__ import annotations

from v5_final.s9_h2_h4_calibration_runner import (
    THRESHOLD_BYTES,
    _capacity_observation,
    _item_key,
    _plan,
    build_ci_audit,
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

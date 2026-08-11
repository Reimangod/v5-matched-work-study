from __future__ import annotations

from v5_final.s9_h2_h4_calibration_runner import (
    THRESHOLD_BYTES,
    _capacity_observation,
    _item_key,
    _plan,
    build_ci_audit,
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

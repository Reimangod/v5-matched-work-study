from __future__ import annotations

import pytest


pytest.importorskip("numpy")

from v5_final.s9_v3_capacity_halt import (
    HALT_PATH,
    audit_failure_state,
    audit_halt,
)


def test_v3_capacity_failure_state_is_exact_and_incomplete() -> None:
    state = audit_failure_state()

    assert all(state["checks"].values())
    assert state["progress"]["completed_terminal_count"] == 23
    assert state["progress"]["expected_item_count"] == 36
    assert state["progress"]["candidate_energy_evaluations"] == 40
    assert state["progress"]["all_post_item_capacity_checks_passed"] is False
    assert state["progress"]["terminal_status_counts"]["KERNEL_FAILURE"] == 0
    assert state["receipt"]["capacity_before_dispatch"]["passed"] is True
    assert state["receipt"]["capacity_after_terminal"]["passed"] is False


def test_v3_capacity_halt_is_valid_if_frozen() -> None:
    if HALT_PATH.exists():
        assert all(audit_halt().values())

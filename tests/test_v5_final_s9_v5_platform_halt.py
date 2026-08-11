from __future__ import annotations

import pytest


pytest.importorskip("numpy")

from v5_final.s9_v5_platform_halt import HALT_PATH, audit_failure_state, audit_halt


def test_v5_platform_failure_is_pre_candidate() -> None:
    state = audit_failure_state()

    assert all(state["checks"].values())
    assert state["progress"]["completed_terminal_count"] == 1
    assert state["progress"]["candidate_energy_evaluations"] == 0
    assert state["receipt"]["terminal_status"] == "KERNEL_FAILURE"
    assert state["environment"]["runtime"]["system"] == "darwin"
    assert state["environment"]["runtime"]["machine"] == "arm64"


def test_v5_platform_halt_is_valid_if_frozen() -> None:
    if HALT_PATH.exists():
        assert all(audit_halt().values())

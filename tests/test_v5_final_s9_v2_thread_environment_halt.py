from __future__ import annotations

from v5_final.s9_v2_thread_environment_halt import (
    HALT_PATH,
    audit_failure_state,
    audit_halt,
)


def test_v2_failure_state_is_exact_and_pre_candidate() -> None:
    state = audit_failure_state()

    assert all(state["checks"].values())
    assert state["report"]["candidate_molecular_energy_evaluations"] == 0
    assert state["receipt"]["terminal_status"] == "KERNEL_FAILURE"
    assert state["receipt"]["work_total"]["energy_evaluations"] == 0
    assert state["receipt"]["work_total"]["rewrite_verifications"] == 1


def test_v2_halt_is_valid_if_frozen() -> None:
    if HALT_PATH.exists():
        assert all(audit_halt().values())

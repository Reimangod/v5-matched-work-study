from __future__ import annotations

import pytest


pytest.importorskip("numpy")

from v5_final.s9_v4_preauthorization_halt import (
    AUTHORIZATION_PATH,
    HALT_PATH,
    audit_failure_state,
    audit_halt,
)


def test_v4_failure_is_outcome_free_and_preauthorization() -> None:
    state = audit_failure_state()

    assert all(state["checks"].values())
    assert state["readiness"]["candidate_molecular_energy_evaluations"] == 0
    assert not AUTHORIZATION_PATH.exists()


def test_v4_preauthorization_halt_is_valid_if_frozen() -> None:
    if HALT_PATH.exists():
        assert all(audit_halt().values())

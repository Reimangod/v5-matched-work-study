from __future__ import annotations

from v5_final.s7_mb6_v4_refreeze import audit


def test_mb6_v4_is_rebuildable_outcome_blind_and_execution_blocked():
    checks = audit()
    assert all(checks.values())

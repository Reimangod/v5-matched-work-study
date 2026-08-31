from __future__ import annotations

import platform

from v5_final.s7_mb6_v4_refreeze import audit, audit_static


def test_mb6_v4_is_rebuildable_outcome_blind_and_execution_blocked():
    checks = audit() if platform.machine().lower() == "arm64" else audit_static()
    assert all(checks.values())

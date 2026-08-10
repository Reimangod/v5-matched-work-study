from __future__ import annotations

import platform

from v5_final.s8_parent_native_production_gate_v2 import (
    build_ci_preflight,
    build_local_preflight,
)


def test_s8_v2_preflight_is_zero_outcome_and_does_not_authorize_execution():
    report = (
        build_local_preflight(require_clean_worktree=False)
        if platform.machine().lower() == "arm64"
        else build_ci_preflight()
    )
    assert all(report["checks"].values())
    assert report["candidate_molecular_energy_evaluations"] == 0
    assert report["authorization"]["H2_H4_execution"].startswith("NOT_AUTHORIZED")

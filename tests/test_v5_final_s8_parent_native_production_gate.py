from __future__ import annotations

from v5_final.s8_parent_native_production_gate import OUTPUT, audit, build_preflight


def test_s8_static_preflight_is_behavioral_and_zero_outcome():
    preflight = build_preflight()
    assert all(preflight["checks"].values())
    assert preflight["decision"] == "READY_AWAITING_FRESH_CLONE_AND_EXACT_CI"
    assert preflight["candidate_molecular_energy_evaluations"] == 0


def test_s8_committed_go_is_strict_when_present():
    if not OUTPUT.exists():
        return
    checks = audit(require_current_capacity=False)
    assert all(checks.values())

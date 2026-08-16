from __future__ import annotations

import platform

from v5_final.s4_parent_native_executors_audit import audit, build, verify


def test_six_parent_native_executors_are_outcome_free_and_scoped():
    if platform.machine().lower() != "arm64":
        assert all(audit().values())
        return
    built = build()
    assert all(verify(built).values())
    assert len(built["probe"]["records"]) == 12
    assert built["probe"]["candidate_energy_evaluations"] == 0
    assert built["authorization"]["H2_H4_execution"] == "NOT_AUTHORIZED"
    assert all(audit().values())

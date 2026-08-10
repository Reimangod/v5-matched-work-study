from __future__ import annotations

import platform

from v5_final.s8_1_runtime_release_remediation_audit import audit, build, verify


def test_successor_factory_and_service_are_actual_but_outcome_blocked():
    if platform.machine().lower() != "arm64":
        assert all(audit().values())
        return
    built = build()
    assert all(verify(built).values())
    assert built["probe"]["candidate_molecular_energy_evaluations"] == 0
    assert built["authorization"]["H2_H4_execution"] == "NOT_AUTHORIZED"
    assert all(audit().values())

from __future__ import annotations

import json

from v5_final.mb7_pre_calibration_audit_v2 import OUTPUT, audit, verify


def test_mb7_v2_stops_before_first_outcome_on_actual_surface_gap() -> None:
    artifact = json.loads(OUTPUT.read_text())
    assert artifact["decision"] == "NO_GO_MB7_V2_UNRESOLVED_METHOD_NATIVE_PRODUCTION_SEMANTICS"
    assert all(artifact["passed_checks"].values())
    assert artifact["blockers"]
    assert artifact["actual_catalog_surface_probe"]["candidate_energy_evaluations"] == 0
    assert artifact["queue_state"]["H2_H4"] == {
        "expected": 36,
        "terminal": 0,
        "candidate_energy": 0,
    }
    assert artifact["authorization"]["H2_H4_execution"] == "NOT_AUTHORIZED"
    assert all(verify(artifact).values())
    assert all(audit().values())

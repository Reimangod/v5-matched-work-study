from __future__ import annotations

import json

from v5_final.pre_calibration_gate import OUTPUT, audit


def test_pre_calibration_gate_rejects_proxy_method_execution() -> None:
    value = json.loads(OUTPUT.read_text())
    assert value["status"] == "NO_GO"
    assert value["production_requirements"][
        "six_method_native_molecular_backend_entrypoints"
    ] is False
    assert value["authorization"]["H2_H4_candidate_execution"] == "NOT_AUTHORIZED"
    assert value["academic_integrity"]["proxy_method_substitution_rejected"] is True
    assert all(audit().values())

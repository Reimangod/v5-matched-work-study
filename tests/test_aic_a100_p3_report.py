from __future__ import annotations

from aic_a100_pilot.common import embedded_digest_valid, load_json
from aic_a100_pilot.p3_report import REPORT


def test_p3_report_is_five_case_source_only_go():
    value = load_json(REPORT)
    assert embedded_digest_valid(value, "report_digest")
    assert value["status"] == "GO_P4_SOURCE_ROUTE_SPEED_GATE"
    assert value["case_order"] == ["h2", "h4", "lih", "h6", "beh2"]
    assert len(value["cases"]) == 5
    assert all(case["status"] == "PASS" for case in value["cases"])
    assert value["route_counters"]["N_cpu_fallback"] == 0
    boundary = value["scientific_boundary"]
    assert boundary["candidate_terminal_decision_parity"] == "NOT_EXECUTED"
    assert boundary["optimizer_parity"] == "NOT_EXECUTED"
    assert boundary["candidate_molecular_energy_evaluations"] == 0
    assert boundary["optimizer_runs"] == 0
    assert boundary["FCI_evaluations"] == 0
    assert value["successor_authorization"]["P4_same_node_source_route_benchmark"] == "AUTHORIZED"

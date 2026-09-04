from __future__ import annotations

import json

from phase1_frontier.v2_s4_1_order_gate import OUTPUT, audit


def test_s4_1_authorizes_only_the_next_prefix_item() -> None:
    value = json.loads(OUTPUT.read_text(encoding="utf-8"))
    assert value["decision"] == "GO_PHASE1_V2_ORDERED_SCREEN_EXECUTION"
    assert all(value["order_probe"].values())
    assert value["authorization"]["only_next_prefix_item"] == "AUTHORIZED"
    assert value["authorization"]["direct_out_of_order_request"] == "PROHIBITED"
    assert value["candidate_energy_evaluations"] == 0
    assert all(audit().values())


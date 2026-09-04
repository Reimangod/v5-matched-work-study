from __future__ import annotations

import json

from phase1_frontier.v2_s4_readiness import OUTPUT, audit


def test_s4_authorizes_only_the_exact_queue() -> None:
    value = json.loads(OUTPUT.read_text(encoding="utf-8"))
    assert value["decision"] == "GO_PHASE1_V2_FROZEN_SCREEN_EXECUTION"
    assert value["authorization"]["exact_queue_only"] == "AUTHORIZED"
    assert value["authorization"]["queue_order_change"] == "PROHIBITED"
    assert value["authorization"]["cap_change"] == "PROHIBITED"
    assert value["authorization"]["FCI_before_1266_terminal"] == "PROHIBITED"
    assert all(audit().values())


def test_s4_does_not_claim_full_historical_suite_green() -> None:
    value = json.loads(OUTPUT.read_text(encoding="utf-8"))
    assert value["full_historical_suite"]["green_claimed"] is False
    assert value["scoped_test_evidence"]["returncode"] == 0


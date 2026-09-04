from __future__ import annotations

import json

from phase1_frontier.v2_s4_2_authority import OUTPUT, audit


def test_s4_2_is_the_only_current_execution_authority() -> None:
    value = json.loads(OUTPUT.read_text(encoding="utf-8"))
    assert value["decision"] == "GO_PHASE1_V2_S4_2_EXECUTION"
    assert value["frozen_terminal_prefix"]["terminal_count"] == 5
    assert value["supersession"]["live_execution_authority"] == "S4.2_ONLY"
    assert value["authorization"]["parallel_execution"] == "NOT_AUTHORIZED"
    assert value["authorization"]["S6_aggregation"] == (
        "NOT_AUTHORIZED_UNTIL_1266_TERMINAL"
    )
    assert all(audit().values())

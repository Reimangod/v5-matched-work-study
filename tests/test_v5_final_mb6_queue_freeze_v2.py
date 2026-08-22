from __future__ import annotations

import json

from v5_final.mb6_queue_freeze_v2 import DIFF_OUTPUT, FREEZE_OUTPUT, QUEUE_OUTPUT, audit


def test_mb6_v2_is_identity_only_successor_and_still_blocks_execution() -> None:
    queue = json.loads(QUEUE_OUTPUT.read_text())
    freeze = json.loads(FREEZE_OUTPUT.read_text())
    semantic_diff = json.loads(DIFF_OUTPUT.read_text())
    assert len(queue["items"]) == 36
    assert len({item["queue_item_id"] for item in queue["items"]}) == 36
    assert all(item["terminal_status"] == "NOT_STARTED" for item in queue["items"])
    assert queue["candidate_energy_evaluations"] == 0
    assert semantic_diff["allowed_changes_only"] is True
    assert all(semantic_diff["checks"].values())
    assert freeze["decision"] == "GO_MB7_V2_PRE_CALIBRATION_AUDIT_ONLY"
    assert freeze["authorization"]["H2_H4_execution"] == "NOT_AUTHORIZED"
    assert all(audit().values())

from __future__ import annotations

import json

from v5_final.s0_successor import ROOT
from v5_final.s5_freeze import audit_committed


def test_s5_freezes_exact_sources_policy_and_90_item_queue() -> None:
    freeze = json.loads(
        (ROOT / "artifacts/v5-final/s5/development-protocol-freeze-v3.json").read_text()
    )
    queue = json.loads(
        (ROOT / "artifacts/v5-final/s5/development-queue-v3.json").read_text()
    )
    ledger = json.loads(
        (ROOT / "artifacts/v5-final/s5/development-ledger-root-v3.json").read_text()
    )
    assert queue["expected_queue_count"] == 90
    assert len(queue["items"]) == 90
    assert ledger["completeness"]["complete"] is False
    assert ledger["development_candidate_energy_evaluations"] == 0
    assert freeze["decision"] == "GO_S6_IMPLEMENTATION_ONLY"
    assert freeze["authorization"]["performance_experiment"] == "NOT_AUTHORIZED"
    assert all(audit_committed().values())

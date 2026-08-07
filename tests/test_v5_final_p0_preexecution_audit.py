from __future__ import annotations

import json

from v5_final.p0_preexecution_audit import (
    FORMULA_REQUIRED_FREE_BYTES,
    LOW_DISK_WATERMARK_BYTES,
    OUTPUT,
    REQUIRED_FREE_BYTES,
    audit,
    verify,
)


def test_p0_capacity_no_go_is_internally_consistent_and_fail_closed() -> None:
    record = json.loads(OUTPUT.read_text())
    assert record["status"] == "NO_GO_INSUFFICIENT_SAFE_DISK_CAPACITY"
    assert record["decision"] == "NO_GO_PERFORMANCE_EXECUTION_CAPACITY"
    assert record["storage_policy"]["formula_required_free_bytes"] == FORMULA_REQUIRED_FREE_BYTES
    assert record["storage_policy"]["effective_required_free_bytes"] == REQUIRED_FREE_BYTES
    assert record["storage_policy"]["low_disk_watermark_bytes"] == LOW_DISK_WATERMARK_BYTES
    assert record["blocker"]["deficit_bytes"] > 0
    assert all(verify(record).values())


def test_p0_preserves_queue_and_all_molecular_prohibitions() -> None:
    record = json.loads(OUTPUT.read_text())
    assert record["queue_state"]["not_started_count"] == 90
    assert record["queue_state"]["candidate_energy_evaluations"] == 0
    assert record["queue_state"]["H2_H4_queue_created"] is False
    assert record["authorization"] == {
        "MB5_1_outcome_free_code_and_dry_run": "AUTHORIZED",
        "MB6_outcome_blind_queue_freeze": "NOT_AUTHORIZED_UNTIL_MB5_1_AUDIT",
        "molecular_candidate_energy": "NOT_AUTHORIZED",
        "H2_H4_execution": "NOT_AUTHORIZED",
        "development_queue_execution": "NOT_AUTHORIZED",
        "performance_claim": "NOT_AUTHORIZED",
    }
    assert all(audit().values())

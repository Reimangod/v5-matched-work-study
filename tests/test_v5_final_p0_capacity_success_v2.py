from __future__ import annotations

import json

from v5_final.p0_capacity_success_v2 import OUTPUT, REQUIRED_FREE_BYTES, audit, verify


def test_committed_capacity_success_is_self_consistent() -> None:
    record = json.loads(OUTPUT.read_text())
    assert record["decision"] == "GO_MB5_2_ACTUAL_BINDING_IMPLEMENTATION_ONLY"
    assert record["storage"]["filesystem_available_bytes_after_cleanup"] >= REQUIRED_FREE_BYTES
    assert all(verify(record).values())
    assert all(audit().values())


def test_r0_preserves_zero_outcome_boundary() -> None:
    record = json.loads(OUTPUT.read_text())
    assert record["execution_state"]["H2_H4"] == {
        "expected": 36,
        "terminal": 0,
        "candidate_energy": 0,
        "raw_segments": 0,
    }
    assert record["execution_state"]["development"] == {
        "expected": 90,
        "terminal": 0,
        "candidate_energy": 0,
        "raw_segments": 0,
    }
    assert record["authorization"]["molecular_candidate_energy"] == "NOT_AUTHORIZED"

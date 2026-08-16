from __future__ import annotations

import json

from v5_final.s0_successor import ROOT
from v5_final.s4_closure_v2 import audit as audit_closure
from v5_final.s4_strict_audit_v3 import audit as audit_strict, build as build_strict


def test_s4_v2_closes_code_duplicate_and_failure_gaps() -> None:
    closure = json.loads(
        (ROOT / "artifacts/v5-final/s4/production-semantic-closure-v2.json").read_text()
    )
    assert all(closure["protocol_binding"].values())
    assert all(closure["duplicate_state_semantics"].values())
    assert all(closure["failure_mode_by_stage"]["audit"].values())
    assert closure["failure_mode_by_stage"]["matrix"]["observed_pair_count"] == 80
    assert closure["authorization"]["performance_experiment"] == "NOT_AUTHORIZED"
    assert all(audit_closure().values())


def test_strict_s4_v3_authorizes_s5_freeze_only() -> None:
    value = build_strict()
    assert value["status"] == "GO_S5_FREEZE_ONLY"
    assert all(value["strict_gate_checks"].values())
    assert value["authorization"]["candidate_molecular_execution"] == "NOT_AUTHORIZED"
    assert value["authorization"]["performance_experiment"] == "NOT_AUTHORIZED"
    assert all(audit_strict().values())

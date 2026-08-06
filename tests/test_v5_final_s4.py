from __future__ import annotations

import json

import pytest

from v5_final.matched_work import MatchedWorkNotAuthorized, run_matched_work
from v5_final.prospective import ProspectiveNotAuthorized, run_prospective
from v5_final.s0_successor import ROOT
from v5_final.s4_closure import audit as audit_claimed_closure
from v5_final.s4_strict_audit import audit as audit_strict, build as build_strict


def test_actual_h2_smoke_artifact_reconciles_and_replays() -> None:
    closure = json.loads(
        (ROOT / "artifacts/v5-final/s4/production-semantic-closure-v1.json").read_text()
    )
    assert closure["clean_replay"]["matches_primary"] is True
    assert all(closure["primary_smoke"]["reconciliation"].values())
    assert closure["primary_smoke"]["upstream"]["commit"] == (
        "a3f89d03e6a03c89767d3cf8ee7657a57653dda0"
    )
    assert all(audit_claimed_closure().values())


def test_strict_s4_audit_keeps_s5_closed_on_unproven_gates() -> None:
    value = build_strict()
    assert value["status"] == "NO_GO"
    assert "failure_mode_by_stage_cartesian_coverage" in value["failed_checks"]
    assert "production_duplicate_state_evaluated_once" in value["failed_checks"]
    assert value["authorization"]["s5_freeze"] == "NOT_AUTHORIZED"
    assert all(audit_strict().values())


def test_performance_entry_points_remain_fail_closed() -> None:
    with pytest.raises(MatchedWorkNotAuthorized):
        run_matched_work()
    with pytest.raises(ProspectiveNotAuthorized):
        run_prospective()

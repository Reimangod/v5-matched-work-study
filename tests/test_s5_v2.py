from v5_matched_work.s5_freeze_v2 import audit, build


def test_s5_v2_is_readiness_first_and_event_derived() -> None:
    freeze = build()
    result = audit(freeze)
    assert freeze["candidate_energy_evaluations_at_s5"]["value"] == 0
    assert freeze["literature_ledger"][2]["status"] == "peer-reviewed-version-of-record"
    assert len(freeze["queue"]) == 90
    assert result["passed"]

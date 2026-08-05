from v5_matched_work.pre_s5_readiness_v2 import build


def test_readiness_precedes_authorization_and_reconstructs_zero_events() -> None:
    zero, readiness = build()
    assert zero["events"] == []
    assert readiness["decision"] == "READY_TO_FREEZE_S5_V2"
    assert all(readiness["checks"].values())

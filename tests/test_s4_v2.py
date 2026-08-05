from v5_matched_work.s4_build_v2 import build


def test_s4_v2_has_six_executors_one_counter_api_and_integration_evidence() -> None:
    integration, protocol = build()
    assert integration["status"] == "PASS"
    assert protocol["decision"] == "GO_PRE_S5_READINESS_V2"
    assert len({item["counter_binding"] for item in protocol["comparators"]}) == 1

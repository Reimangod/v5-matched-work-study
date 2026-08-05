from v5_matched_work.s3_build_v2 import build


def test_s3_v2_caps_are_reconstructed_from_raw_comparable_events() -> None:
    raw, protocol = build()
    assert protocol["decision"] == "GO_S4_V2"
    assert protocol["checks"]["rewrite_bound_to_each_search_state"]
    assert raw["events"]

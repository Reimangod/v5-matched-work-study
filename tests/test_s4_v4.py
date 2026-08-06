from v5_matched_work.s4_build_v4 import build


def test_distinct_candidate_ids_same_proposed_state_are_one_unique_state() -> None:
    integration, protocol = build()
    assert integration["checks"]["different_candidate_ids_same_proposed_state_deduplicated"]
    assert protocol["checks"]["different_candidate_ids_same_proposed_state_excluded"]
    assert protocol["production_readiness"]["post_rewrite_canonical_state_identity"] is False
    assert protocol["s5_authorization_permitted"] is False

from v5_matched_work.s4_build_v3 import build


def test_duplicate_candidates_do_not_increment_unique_state_count() -> None:
    integration, protocol = build()
    assert integration["checks"]["duplicates_do_not_increment_n_states"]
    assert integration["checks"]["duplicate_detection_is_zero_delta_evidence"]
    by_method = {
        record["method_id"]: record["work"]["N_states"]
        for record in integration["records"]
        if record["case_id"] == "toy-structural-integration"
    }
    assert by_method["structural-magnitude-pruning"] == 2
    assert by_method["v4.1-one-shot-joint-compression"] == 2
    assert by_method["v5-sequential-without-rebuilding"] == 2
    assert by_method["v5-sequential-with-rebuilding"] == 5
    assert protocol["s5_authorization_permitted"] is False

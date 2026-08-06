from v5_matched_work.s3_build_v4 import build


def test_s3_v4_requires_semantic_events_and_nonempty_frozen_queue() -> None:
    kernel, protocol = build()
    assert all(protocol["checks"].values())
    assert protocol["production_completeness_manifest"] is None
    assert protocol["production_candidate_energy_reconstruction"] is None
    assert "nonempty frozen queue" in kernel["queue_binding"]

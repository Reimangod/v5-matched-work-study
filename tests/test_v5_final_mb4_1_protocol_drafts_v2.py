from __future__ import annotations

from v5_final.mb4_1_protocol_drafts_v2 import audit, build, build_review_template


def test_no_rebuild_v2_is_only_structural_replenishment_ablation() -> None:
    protocol = build()["protocols"]["no_rebuild"]
    assert protocol["causal_variable"] == "structural candidate replenishment after accepted children"
    assert "source structural candidate-ID whitelist only" in protocol["source_freeze"]
    assert "source ordering is not frozen" in protocol["ordering_rule"]
    assert any(
        "same current-state selection and ranking rule as full V5" in rule
        for rule in protocol["child_round"]
    )
    assert "frozen-catalog-order" in protocol["forbidden_compound_ablation"]


def test_magnitude_v2_is_single_coordinate_physical_control() -> None:
    protocol = build()["protocols"]["magnitude_control"]
    assert protocol["batch_size"] == 1
    assert "one ansatz generator" in protocol["deletion_unit"]
    assert "theta_i^2" in protocol["score"]
    assert "setting its coefficient to zero is insufficient" in protocol["physical_deletion"]
    assert "measure full CNOT count" in protocol["resource_recount"]
    assert "zero resource reduction" in protocol["resource_zero_rule"]
    assert "block deletion" in protocol["excluded_protocols"]


def test_v4_1_v2_has_deterministic_outcome_blind_sentinel_selection() -> None:
    protocol = build()["protocols"]["v4_1_h2_h4_sentinel"]
    assert "lowest lowercase" in protocol["representative_selection"]
    assert "at most four sentinels per case" in protocol["sentinel_count"]
    assert "first four" in protocol["overflow_rule"]
    assert "no predictor" in protocol["predictor_policy"]
    assert "candidate energy" in protocol["forbidden_inputs"]
    assert "historical success or sentinel rank" in protocol["forbidden_inputs"]


def test_review_template_is_empty_and_no_go_is_deterministic() -> None:
    artifact = build()
    review = build_review_template(artifact)
    assert artifact["decision"] == "NO_GO_MB4_1_V2_AWAITING_INDEPENDENT_HUMAN_APPROVAL"
    assert artifact["v1_disposition"]["status"] == "SUPERSEDED_BY_MB4_1_PROTOCOL_DRAFTS_V2"
    assert review["reviewer"] is None
    assert review["review_date"] is None
    assert review["decision"] is None
    assert all(value is None for value in review["checklist"].values())
    assert all(audit().values())

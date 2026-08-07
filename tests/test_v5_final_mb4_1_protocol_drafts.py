from __future__ import annotations

from v5_final.mb4_1_protocol_drafts import audit, build


def test_protocol_drafts_are_deterministic_unapproved_and_outcome_blind() -> None:
    artifact = build()
    assert artifact["decision"] == "NO_GO_MB4_1_PROTOCOLS_PROPOSED_NOT_APPROVED"
    assert all(
        protocol["approval_status"]
        == "PROPOSED_AWAITING_INDEPENDENT_HUMAN_APPROVAL"
        for protocol in artifact["protocols"].values()
    )
    assert all(
        protocol["outcome_status"] == "OUTCOME_BLIND_NO_CANDIDATE_ENERGY_USED"
        for protocol in artifact["protocols"].values()
    )
    assert artifact["approval_record"]["approved_protocol_digests"] == []
    assert artifact["molecular_candidate_energy_executed"] is False
    assert artifact["development_queue"]["candidate_energy_evaluations"] == 0
    assert all(audit().values())


def test_proposals_preserve_the_scientific_method_distinctions() -> None:
    protocols = build()["protocols"]
    no_rebuild = protocols["no_rebuild"]
    assert "structural candidate IDs" in no_rebuild["source_freeze"]
    assert "rebuild a current-runtime catalog" in no_rebuild["child_rebinding"]
    assert "current numerical values never rerank" in no_rebuild["ordering_rule"]

    magnitude = protocols["magnitude_control"]
    assert magnitude["batch_size"] == 1
    assert magnitude["classification"].endswith("NOT_PARENT_NATIVE")
    assert "full resource recount" in magnitude["physical_rule"]

    sentinel = protocols["v4_1_h2_h4_sentinel"]
    assert "candidate energy" in sentinel["screening_inputs_forbidden"]
    assert "FCI or exact reference energy" in sentinel["screening_inputs_forbidden"]
    assert "separate from the 90-item development queue" in sentinel["scope"]

from __future__ import annotations

import json

from v5_final.mb6_queue_freeze import (
    CATALOG_OUTPUT,
    FREEZE_OUTPUT,
    LEDGER_OUTPUT,
    QUEUE_OUTPUT,
    audit,
)


def test_mb6_queue_is_nonempty_complete_and_separate_from_development() -> None:
    queue = json.loads(QUEUE_OUTPUT.read_text())
    ledger = json.loads(LEDGER_OUTPUT.read_text())
    assert queue["frozen_item_count"] == 36
    assert len(queue["items"]) == 36
    assert queue["existing_development_queue"]["separate_and_untouched"] is True
    assert ledger["expected_queue_count"] == 36
    assert len(ledger["expected_queue_item_ids"]) == 36
    assert ledger["completed_queue_item_ids"] == []
    assert ledger["segments"] == []
    assert ledger["completeness_contract"]["expected_queue_nonempty"] is True


def test_mb6_catalog_guarded_all_molecular_outcomes() -> None:
    catalog = json.loads(CATALOG_OUTPUT.read_text())
    assert catalog["candidate_energy_evaluations"] == 0
    assert not any(catalog["molecular_kernel_guard_calls"].values())
    serialized = json.dumps(catalog, sort_keys=True)
    for forbidden in catalog["forbidden_inputs"]:
        assert f'"{forbidden}":' not in serialized


def test_v4_sentinels_and_magnitude_are_structurally_frozen() -> None:
    queue = json.loads(QUEUE_OUTPUT.read_text())
    v4 = [
        item for item in queue["items"]
        if item["method_id"] == "v4.1-one-shot-joint-compression"
    ]
    assert v4
    for item in v4:
        binding = item["candidate_binding"]
        assert len(binding["candidate_set"]) <= 4
        assert binding["FCI_used"] is False
        assert binding["candidate_energy_used"] is False
        assert len({candidate["equivalence_class_id"] for candidate in binding["candidate_set"]}) == len(binding["candidate_set"])

    magnitude = [
        item for item in queue["items"]
        if item["method_id"] == "structural-magnitude-pruning"
    ]
    assert magnitude
    for item in magnitude:
        for candidate in item["candidate_binding"]["candidate_set"]:
            assert candidate["constraint"] == "theta_i->0"
            assert candidate["physical_generator_deleted"] is True
            assert candidate["coefficient_zeroing_only"] is False
            assert candidate["full_circuit_rebuild_and_recount"] is True
            assert candidate["zero_reduction_is_success"] is False


def test_mb6_artifacts_are_immutable_at_historical_commit_and_stop_before_execution() -> None:
    freeze = json.loads(FREEZE_OUTPUT.read_text())
    assert freeze["decision"] == "GO_MB7_PRE_CALIBRATION_AUDIT_ONLY"
    assert freeze["authorization"]["molecular_candidate_energy"] == "NOT_AUTHORIZED"
    assert freeze["authorization"]["H2_H4_execution"] == "NOT_AUTHORIZED"
    checks = audit()
    assert all(checks.values())
    assert checks["historical_artifacts_are_exact_git_blobs"]
    assert checks["historical_freeze_commit_is_ancestor"]
    assert checks["historical_rebuild_not_attempted_from_current_source"]

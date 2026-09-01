from __future__ import annotations

import hashlib
import json

from phase1_frontier.a2_source_lock import (
    A2_ROOT,
    CASES,
    STARTS,
    _digest,
    audit,
    legacy_start_path,
    source_path,
    start_path,
)


def _verified_record(path, digest_key: str) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    digest = value.pop(digest_key)
    assert digest == _digest(value)
    return value


def test_all_A2_starts_and_sources_are_immutable_and_digest_valid() -> None:
    for case_id in CASES:
        for start in STARTS:
            record = _verified_record(start_path(case_id, start), "record_digest")
            assert record["case_id"] == case_id
            assert record["start"] == start
            assert record["candidate_generation_count"] == 0
            assert record["FCI_evaluations"] == 0
        source = _verified_record(source_path(case_id), "source_digest")
        assert source["status"] == "B2_ELIGIBLE"
        assert source["start_record_sha256"] == {
            start: hashlib.sha256(start_path(case_id, start).read_bytes()).hexdigest()
            for start in STARTS
        }


def test_resource_vector_width_defect_is_preserved_and_corrected_additively() -> None:
    legacy = _verified_record(
        legacy_start_path("lih-3.0", "mapped-warm-start"), "record_digest"
    )
    corrected = _verified_record(
        start_path("lih-3.0", "mapped-warm-start"), "record_digest"
    )
    assert legacy["checks"]["resources_unchanged"] is False
    assert corrected["checks"]["resources_unchanged"] is True
    correction = corrected.pop("additive_correction")
    legacy["schema"] = corrected["schema"]
    legacy["checks"]["resources_unchanged"] = True
    legacy["valid"] = True
    legacy["terminal_status"] = "COMPLETED_CERTIFIED"
    assert corrected == legacy
    assert correction["kind"] == "RESOURCE_VECTOR_KEY_PROJECTION_ONLY"
    assert correction["candidate_or_optimizer_rerun"] is False
    assert correction["scientific_semantics_changed"] is False


def test_interrupted_attempt_is_preserved_without_outcome_or_retry_bias() -> None:
    incident = json.loads(
        (
            A2_ROOT
            / "incidents"
            / "h6-1.5-zero-target-coordinate-attempt-1.json"
        ).read_text(encoding="utf-8")
    )
    assert incident["terminal_status"] == "FAILED_ENGINEERING_PRESERVED"
    assert incident["optimizer_endpoint_recorded"] is False
    assert incident["decision_basis"].startswith("ENGINEERING_MONITORING")
    assert incident["retry_authorization"] == "SAME_CASE_SAME_START_ONLY_WITH_UNCHANGED_PROTOCOL"
    assert incident["candidate_generation_count"] == 0
    assert incident["FCI_evaluations"] == 0
    assert start_path("h6-1.5", "zero-target-coordinate").is_file()


def test_A2_audit_authorizes_only_grammar_and_identity_stage() -> None:
    result = audit()
    assert result["passed"] is True
    assert result["eligible_count"] == 4
    assert result["decision"] == "GO_A3_GRAMMAR_AND_IDENTITIES"


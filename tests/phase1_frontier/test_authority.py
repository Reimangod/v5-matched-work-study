from __future__ import annotations

import json
import subprocess

import pytest

from phase1_frontier.authority import (
    ARTIFACT_PATH,
    PLAN_SHA256,
    audit_committed_manifest,
    build_manifest,
    live_audit,
)


def test_manifest_freezes_the_primary_scientific_contract() -> None:
    contract = build_manifest()["scientific_contract"]
    assert contract["accuracy_threshold_hartree"] == "0.0001"
    assert contract["joint_cardinality_K"] == 2
    assert contract["joint_locality_L"] == 1
    assert contract["joint_source_depth_D"] == 1
    assert contract["FCI_role"] == "reporting-only-after-terminal-E3"


def test_manifest_keeps_all_outcomes_closed_at_A0() -> None:
    authorization = build_manifest()["authorization"]
    assert authorization["candidate_molecular_energy"] == "NOT_AUTHORIZED"
    assert authorization["optimizer_endpoint"] == "NOT_AUTHORIZED"
    assert authorization["FCI_evaluation"] == "NOT_AUTHORIZED"
    assert authorization["E3_execution"] == "NOT_AUTHORIZED"
    assert authorization["Phase2"] == "NOT_AUTHORIZED"


def test_every_authoritative_plan_has_a_frozen_digest() -> None:
    assert set(PLAN_SHA256) == {
        "docs/CEO_PHASE1_SCIENTIFIC_PROTOCOL_V1.md",
        "docs/CEO_PHASE1_ENGINEERING_PROTOCOL_V1.md",
        "docs/CEO_PHASE1_SCOPE_REDUCTION_RATIONALE_V1.md",
        "docs/CEO_PHASE1_AGENT_EXECUTION_PROTOCOL_V1.md",
        "docs/CEO_PHASE1_PHASE2_PLAN_INDEX_V1.md",
    }
    assert all(len(digest) == 64 for digest in PLAN_SHA256.values())


_ON_V1_BRANCH = (
    subprocess.check_output(["git", "branch", "--show-current"], text=True).strip()
    == "feature/phase1-joint-frontier-v1"
)


@pytest.mark.skipif(
    not _ON_V1_BRANCH,
    reason="the immutable v1 live authority intentionally rejects successor branches",
)
def test_live_A0_audit_passes_without_candidate_outcomes() -> None:
    result = live_audit()
    assert result["passed"] is True
    assert result["checks"]["phase1_candidate_outcome_count_zero"] is True
    assert result["observed"]["outcome_files"] == []


@pytest.mark.skipif(
    not _ON_V1_BRANCH,
    reason="the immutable v1 live authority intentionally rejects successor branches",
)
def test_committed_authority_artifact_matches_rebuild() -> None:
    assert ARTIFACT_PATH.is_file()
    committed = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
    assert committed == build_manifest()
    assert audit_committed_manifest()["passed"] is True

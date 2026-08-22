from __future__ import annotations

from v5_final.s7_mb6_v3_refreeze import (
    _build_unbound,
    audit,
    build_semantic_diff,
)
from v5_matched_work.atomic_artifacts import canonical_json_bytes


def test_mb6_v3_two_outcome_blind_builds_are_byte_identical():
    first = _build_unbound()
    second = _build_unbound()
    assert all(
        canonical_json_bytes(left) == canonical_json_bytes(right)
        for left, right in zip(first, second, strict=True)
    )


def test_mb6_v3_semantic_diff_preserves_protocol_and_exact_correction():
    _, _, plan, _, semantic_diff = _build_unbound()
    assert all(semantic_diff["checks"].values())
    assert len(plan["items"]) == 36
    assert plan["candidate_energy_evaluations"] == 0
    assert semantic_diff["required_structural_correction"][
        "affected_budget_count"
    ] == 3


def test_mb6_v3_committed_freeze_rebuilds_exactly_and_stays_blocked():
    checks = audit()
    assert all(checks.values())
    assert checks["candidate_energy_zero"] is True
    assert checks["H2_H4_still_blocked"] is True

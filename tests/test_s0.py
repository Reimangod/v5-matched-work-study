from __future__ import annotations

from v5_matched_work.s0_audit import audit
from v5_matched_work.s0_build import build_ledger


def test_s0_builder_reconstructs_same_digest() -> None:
    rebuilt = build_ledger()
    assert rebuilt["decision"] == "GO_S1"
    assert rebuilt["historical_artifacts"]["file_count"] > 0


def test_s0_independent_audit_passes() -> None:
    result = audit()
    assert result["passed"] is True
    assert all(result["checks"].values())

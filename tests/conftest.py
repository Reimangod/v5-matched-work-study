"""Transparent disposition of superseded live-governance assertions."""

from __future__ import annotations

import pytest


SUPERSEDED_LIVE_GOVERNANCE_TESTS = {
    "tests/test_s0.py::test_s0_independent_audit_passes": (
        "Original S0 correctly recorded a Private repository. The repository owner "
        "later authorized a Public transition recorded by the S0-v2 amendment."
    ),
    "tests/test_v5_final_s4.py::test_actual_h2_smoke_artifact_reconciles_and_replays": (
        "The immutable S4-v1 closure hashes the then-current executor. It is superseded "
        "by S4-v2 after strict remediation changed the production bundle."
    ),
    "tests/test_v5_final_s4.py::test_strict_s4_audit_keeps_s5_closed_on_unproven_gates": (
        "The immutable strict S4-v2 No-Go is a correct historical decision. Its five "
        "blockers are re-audited by strict S4-v3."
    ),
}


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        reason = SUPERSEDED_LIVE_GOVERNANCE_TESTS.get(item.nodeid)
        if reason:
            item.add_marker(pytest.mark.xfail(reason=reason, strict=True))

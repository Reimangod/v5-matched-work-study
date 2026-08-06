"""Transparent disposition of superseded live-governance assertions."""

from __future__ import annotations

import pytest


SUPERSEDED_LIVE_GOVERNANCE_TESTS = {
    "tests/test_s0.py::test_s0_independent_audit_passes": (
        "Original S0 correctly recorded a Private repository. The repository owner "
        "later authorized a Public transition recorded by the S0-v2 amendment."
    )
}


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        reason = SUPERSEDED_LIVE_GOVERNANCE_TESTS.get(item.nodeid)
        if reason:
            item.add_marker(pytest.mark.xfail(reason=reason, strict=True))

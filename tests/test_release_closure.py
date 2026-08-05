from __future__ import annotations
from v5_matched_work.release_closure import audit,build


def test_release_has_no_performance_claim()->None:
    value=build();assert all(audit(value).values());assert value["result"]["molecular_performance_conclusion"] is None

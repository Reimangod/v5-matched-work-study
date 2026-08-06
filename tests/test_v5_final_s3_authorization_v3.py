from __future__ import annotations

from v5_final.s3_smoke_authorization_v3 import audit, build


def test_rebuild_work_is_explicitly_charged_without_opening_performance() -> None:
    value = build()
    assert value["scope"]["catalog_build_count"] == 1
    assert value["scope"]["catalog_rebuild_count"] == 1
    assert value["work_cap"]["candidate_generations"] == 2
    assert value["performance_experiment"] == "NOT_AUTHORIZED"
    assert all(audit().values())

from __future__ import annotations

from v5_final.s3_smoke_authorization import audit, build


def test_s4_smoke_authorization_is_narrow_and_keeps_performance_closed() -> None:
    value = build()
    assert value["scope"]["queue_item_count"] == 1
    assert value["scope"]["execution_request_count"] == 1
    assert value["performance_experiment"] == "NOT_AUTHORIZED"
    assert value["s5_freeze"] == "NOT_AUTHORIZED"
    assert all(audit().values())

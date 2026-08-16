from __future__ import annotations

from v5_final.mb4_fail_closed import audit


def test_mb4_stops_before_semantically_ambiguous_native_execution() -> None:
    assert all(audit().values())

from __future__ import annotations

from v5_final.mb0_baseline import audit


def test_mb0_baseline_is_immutable_and_queue_is_untouched() -> None:
    assert all(audit().values())

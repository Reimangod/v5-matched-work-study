from __future__ import annotations

from v5_matched_work.integration_gate import build


def test_toy_h2_h4_adapter_integration_gate() -> None:
    result = build()
    assert result["status"] == "PASS"
    assert all(result["checks"].values())

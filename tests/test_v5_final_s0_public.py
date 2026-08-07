from __future__ import annotations

from v5_final.s0_public_amendment import audit, build


def test_public_transition_preserves_history_and_closes_performance() -> None:
    value = build()
    assert value["transition"]["from"] == "PRIVATE"
    assert value["transition"]["to"] == "PUBLIC"
    assert value["transition"]["history_and_tags_rewritten"] is False
    assert value["authorization"]["performance_experiment"] == "NOT_AUTHORIZED"
    result = audit(require_clean=False)
    assert result["passed"] is True
    assert result["sensitive_path_matches"] == []

from __future__ import annotations

from v5_final.ci_release_gate import audit


def test_ci_release_gate_passes_only_as_no_go_with_untouched_queue() -> None:
    result = audit()
    assert result["status"] == "PASS_NO_GO"
    assert result["decision"] == "NO_GO_MB4_1_PROTOCOLS_PROPOSED_NOT_APPROVED"
    assert all(result["checks"].values())
    assert result["queue_artifacts"] == [
        "artifacts/v5-final/s5/development-queue-v3.json"
    ]
    assert all(value == "NOT_AUTHORIZED" for value in result["authorization"].values())

from __future__ import annotations

from v5_final.ci_release_gate import audit


def test_ci_release_gate_opens_only_mb6_freeze_with_untouched_queue() -> None:
    result = audit()
    assert result["status"] == "PASS_GO_MB6_QUEUE_FREEZE_ONLY"
    assert result["decision"] == "GO_MB6_QUEUE_FREEZE_ONLY"
    assert all(result["checks"].values())
    assert result["queue_artifacts"] == [
        "artifacts/v5-final/s5/development-queue-v3.json"
    ]
    assert result["authorization"] == {
        "MB6_queue_freeze": "AUTHORIZED_TO_CREATE_AND_AUDIT_FREEZE_ONLY",
        "molecular_candidate_energy": "NOT_AUTHORIZED",
        "H2_H4_execution": "NOT_AUTHORIZED",
        "development_queue_execution": "NOT_AUTHORIZED",
        "six_production_molecular_executors": "NOT_AUTHORIZED",
        "performance_claim": "NOT_AUTHORIZED",
        "MB7_or_later": "NOT_AUTHORIZED",
    }

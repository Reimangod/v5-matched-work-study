from __future__ import annotations

from v5_final.ci_release_gate import audit


def test_ci_release_gate_opens_only_mb7_audit_with_untouched_development_queue() -> None:
    result = audit()
    assert result["status"] == "PASS_GO_MB7_PRE_CALIBRATION_AUDIT_ONLY"
    assert result["decision"] == "GO_MB7_PRE_CALIBRATION_AUDIT_ONLY"
    assert all(result["checks"].values())
    assert result["queue_artifacts"] == [
        "artifacts/v5-final/mb6/h2-h4-calibration-queue-v1.json",
        "artifacts/v5-final/s5/development-queue-v3.json"
    ]
    assert result["authorization"] == {
        "MB6_queue_freeze": "COMPLETE_FROZEN_NOT_EXECUTED",
        "MB7_pre_calibration_audit": "AUTHORIZED_ONLY",
        "molecular_candidate_energy": "NOT_AUTHORIZED",
        "H2_H4_execution": "NOT_AUTHORIZED",
        "development_queue_execution": "NOT_AUTHORIZED",
        "six_production_molecular_executors": "IMPLEMENTED_BINDING_ONLY_NOT_EXECUTION_AUTHORIZED",
        "P0_capacity": "NO_GO_BLOCKS_ALL_MOLECULAR_EXECUTION",
        "performance_claim": "NOT_AUTHORIZED",
        "MB8_or_later": "NOT_AUTHORIZED",
    }

from __future__ import annotations

from v5_final.mb3_1_hardening_audit import audit, build


def test_mb3_1_audit_is_deterministic_synthetic_and_keeps_execution_closed() -> None:
    artifact = build()
    assert all(artifact["proofs"].values())
    assert artifact["molecular_candidate_energy_executed"] is False
    assert artifact["development_queue"]["candidate_energy_evaluations"] == 0
    assert artifact["decision"] == "GO_MB4_1_PROTOCOL_REVIEW_ONLY"
    assert all(value == "NOT_AUTHORIZED" for value in artifact["authorization"].values())
    assert all(audit().values())

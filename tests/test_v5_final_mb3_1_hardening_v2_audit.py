from __future__ import annotations

from v5_final.mb3_1_hardening_v2_audit import audit, build


def test_mb3_1_residual_hardening_v2_is_synthetic_and_fail_closed() -> None:
    artifact = build()
    assert all(artifact["proofs"].values())
    assert artifact["synthetic_probe"]["replay"]["candidate_energy_evaluations"] == 0
    assert artifact["molecular_candidate_energy_executed"] is False
    assert artifact["development_queue"]["not_started_count"] == 90
    assert artifact["decision"] == "GO_MB4_1_V2_PROTOCOL_DRAFTING_ONLY"
    assert all(audit().values())

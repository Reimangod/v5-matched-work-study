from __future__ import annotations

from v5_final.s2_parent_native_rewrite_audit import audit, build, verify


def test_s2_parent_native_rewrite_artifact_is_reproducible_and_fail_closed():
    built = build()
    checks = verify(built)
    assert all(checks.values())
    assert built["decision"] == "GO_S3_QUEUE_BOUND_FACTORY_ONLY"
    assert built["probe"]["candidate_energy_evaluations"] == 0
    assert built["authorization"]["optimizer_execution"] == "NOT_AUTHORIZED"
    assert built["authorization"]["molecular_candidate_energy"] == "NOT_AUTHORIZED"

    frozen_checks = audit()
    assert all(frozen_checks.values())

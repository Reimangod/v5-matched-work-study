from __future__ import annotations

import platform

from v5_final.s3_parent_native_runtime_factory_audit import audit, build, verify


def test_s3_runtime_factory_audit_is_reproducible_and_scoped():
    if platform.machine().lower() != "arm64":
        # Exact molecular rebuilds are intentionally confined to the frozen
        # platform.  Cross-platform CI audits the committed evidence instead.
        assert all(audit().values())
        return
    built = build()
    assert all(verify(built).values())
    assert built["decision"] == "GO_S4_METHOD_NATIVE_EXECUTORS_ONLY"
    assert built["factory_probe"]["candidate_energy_evaluations"] == 0
    assert built["authorization"]["H2_H4_execution"] == "NOT_AUTHORIZED"
    assert all(audit().values())

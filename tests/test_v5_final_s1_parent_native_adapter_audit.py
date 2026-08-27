from __future__ import annotations

import json

from v5_final.s1_parent_native_adapter_audit import OUTPUT, audit, verify


def test_s1_actual_parent_adapter_is_outcome_free_and_scoped() -> None:
    artifact = json.loads(OUTPUT.read_text())
    assert artifact["decision"] == "GO_S2_REWRITE_MATRIX_RESOURCE_PARITY_ONLY"
    assert artifact["probe"]["candidate_type"] == "CompressionCandidate"
    assert artifact["probe"]["candidate_is_mapping"] is False
    assert artifact["probe"]["candidate_energy_evaluations"] == 0
    assert all(verify(artifact).values())
    assert all(audit().values())

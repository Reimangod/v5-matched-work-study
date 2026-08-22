from __future__ import annotations

import json

from v5_final.mb5_2_actual_binding_audit import OUTPUT, audit, verify


def test_committed_mb5_2_audit_is_scoped_runtime_go() -> None:
    artifact = json.loads(OUTPUT.read_text())
    assert artifact["decision"] == "GO_MB6_V2_OUTCOME_BLIND_REFREEZE_ONLY"
    assert artifact["scientific_state"]["candidate_molecular_energy_evaluations"] == 0
    assert len(artifact["executor_identities"]) == 6
    assert all(verify(artifact).values())
    assert all(audit().values())

from __future__ import annotations

from v5_final.ci_release_gate_v2 import audit as audit_successor
from v5_final.historical_artifact_audit import blob_at, is_ancestor


V1_GATE_COMMIT = "4c3ff6f61a3f3a5faea789b7423ec07180de943e"


def test_historical_ci_release_gate_is_preserved_at_its_exact_commit() -> None:
    source = blob_at(V1_GATE_COMMIT, "src/v5_final/ci_release_gate.py")
    assert is_ancestor(V1_GATE_COMMIT)
    assert b'"schema": "v5-final.ci-release-gate.v1"' in source
    assert b'"NO_GO_V5_MATCHED_WORK_UNRESOLVED_INFRASTRUCTURE_V1"' in source
    assert b'artifacts/v5-final/mb6-v2/h2-h4-calibration-queue-v2.json' in source
    assert b'artifacts/v5-final/mb6/h2-h4-calibration-queue-v1.json' in source
    assert b'artifacts/v5-final/s5/development-queue-v3.json' in source


def test_current_commit_uses_additive_successor_gate() -> None:
    result = audit_successor()
    assert result["status"] == "PASS_V2_SUCCESSOR_INFRASTRUCTURE_ONLY"
    assert result["decision"] == "NO_GO_V5_MATCHED_WORK_INFRASTRUCTURE_V2"
    assert all(result["checks"].values())
    assert result["authorization"]["molecular_candidate_energy"] == "NOT_AUTHORIZED"
    assert result["authorization"]["H2_H4_execution"] == "NOT_AUTHORIZED"
    assert result["authorization"]["development_queue_execution"] == "NOT_AUTHORIZED"
    assert result["authorization"]["performance_claim"] == "NOT_AUTHORIZED"

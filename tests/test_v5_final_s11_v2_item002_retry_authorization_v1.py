from v5_final.historical_artifact_audit import (
    artifact_is_immutable_git_blob,
    is_ancestor,
    manifest_matches_commit,
)
from v5_final.s11_v2_item002_retry_authorization_v1 import (
    DECISION,
    OUTPUT,
    RESULT,
    _embedded_digest,
    _load,
)


def test_item002_retry_predicts_zero_outcome_cumulative_cap_rejection() -> None:
    artifact = _load(OUTPUT)
    source_manifest = [
        {"path": path, "sha256": expected}
        for path, expected in artifact["bindings"]["source_sha256"].items()
    ]
    assert artifact_is_immutable_git_blob(OUTPUT)
    assert _embedded_digest(artifact, "authorization_digest")
    assert artifact["decision"] == DECISION
    assert all(artifact["checks"].values())
    assert manifest_matches_commit(source_manifest, artifact["repository_head"])
    assert is_ancestor(artifact["repository_head"])
    assert artifact["observed"]["candidate_energy_evaluations"] == 0
    assert artifact["observed"]["optimizer_starts"] == 0
    assert artifact["observed"]["FCI_evaluations"] == 0
    assert artifact["observed"]["N_dense_expm"] == 0
    assert artifact["observed"]["candidate_count"] == 15
    assert artifact["observed"]["predicted_cap_rejection_reason"].startswith(
        "verifier cap rejected before session:"
    )
    result = _load(RESULT)
    assert result["terminal_status"] == "CAP_REJECTED"
    assert result["candidate_energy_evaluations"] == 0
    assert result["raw_work_total"]["optimizer_starts"] == 0
    assert result["FCI_evaluations"] == 0
    assert result["N_dense_expm"] == 0
    assert result["verifier_work_total"] == artifact["observed"]["prior_verifier_total"]

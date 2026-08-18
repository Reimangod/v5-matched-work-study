from v5_final.historical_artifact_audit import (
    artifact_is_immutable_git_blob,
    is_ancestor,
    manifest_matches_commit,
)
from v5_final.parent_native_development_runtime_factory_v1 import (
    build_queue_bound_development_runtime_v1,
)
from v5_final.parent_native_runtime_factory import QueueBoundRuntimeError
from v5_final.s11_v2_execution_readiness_v3 import (
    DECISION,
    OUTPUT,
    _digest,
    _embedded_digest,
    _load,
)
from v5_final.s11_v2_item002_candidate_identity_incident_v1 import (
    audit_frozen as audit_item002_incident,
)
from v5_final.s11_v2_item002_retry_authorization_v1 import (
    OUTPUT as ITEM002_RETRY,
    _embedded_digest as retry_digest_valid,
    _load as load_retry,
)


ITEM000_PREDECESSOR = (
    "development-queue-item-v4:"
    "7e9fb84e4398661a325bc2e75ccbe81a0130e6761b73872183edebf052c42553"
)


def test_historical_post_item000_readiness_is_valid_at_captured_commit() -> None:
    artifact = _load(OUTPUT)
    captured_commit = artifact["captured_repository_state"]["local_head"]
    source_sha256 = artifact["binding"]["source_sha256"]
    source_manifest = [
        {"path": path, "sha256": expected}
        for path, expected in source_sha256.items()
    ]

    assert artifact_is_immutable_git_blob(OUTPUT)
    assert _embedded_digest(artifact, "readiness_digest")
    assert artifact["decision"] == DECISION
    assert artifact["binding"]["source_bundle_digest"] == _digest(source_sha256)
    assert manifest_matches_commit(source_manifest, captured_commit)
    assert is_ancestor(captured_commit)
    assert artifact["observed_outcomes"] == {
        "FAILED_ENGINEERING_PRESERVED": 1,
        "FCI_evaluations": 0,
        "N_dense_expm": 0,
        "candidate_energy_evaluations": 0,
        "optimizer_iterations": 0,
        "terminal_count": 1,
    }


def test_current_tree_preserves_v3_supersession_chain() -> None:
    incident = audit_item002_incident()
    retry = load_retry(ITEM002_RETRY)
    retry_manifest = [
        {"path": path, "sha256": expected}
        for path, expected in retry["bindings"]["source_sha256"].items()
    ]
    assert all(incident["checks"].values())
    assert incident["decision"].startswith("SUSPEND_S11_V2_READINESS_V3")
    assert artifact_is_immutable_git_blob(ITEM002_RETRY)
    assert retry_digest_valid(retry, "authorization_digest")
    assert manifest_matches_commit(retry_manifest, retry["repository_head"])
    assert retry["decision"] == (
        "AUTHORIZE_S11_V2_ITEM002_SAME_ITEM_APPEND_ONLY_RETRY"
    )


def test_exact_one_thread_queue_environment_rebuilds_source_without_outcomes() -> None:
    try:
        context = build_queue_bound_development_runtime_v1(ITEM000_PREDECESSOR)
    except QueueBoundRuntimeError as error:
        assert str(error) == "runtime platform differs from frozen environment"
        return
    assert context._actual_algorithm.molecule.fci_energy is None
    assert context._actual_algorithm.molecule.ccsd_energy is None
    assert context.runtime.metadata["source_checkpoint_digest"]

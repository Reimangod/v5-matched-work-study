from copy import deepcopy

from v5_final.s12_offline_fci_result_audit_v1 import (
    DECISION,
    EXPECTED_CASES,
    _digest,
    _embedded_digest,
    build_artifact,
    inspect_result,
)


def test_result_inspection_binds_exact_identity_provenance_and_firewalls() -> None:
    inspected = inspect_result()
    assert all(inspected["checks"].values())
    assert tuple(inspected["observed"]["case_ids"]) == EXPECTED_CASES
    assert inspected["observed"]["counters"] == {
        "FCI_evaluations": 5,
        "candidate_energy_evaluations": 0,
        "optimizer_starts": 0,
        "S11_items_rerun": 0,
        "production_N_dense_expm": 0,
    }
    assert len(inspected["bindings"]["result_sha256"]) == 64
    assert inspected["bindings"]["result_commit_evidence"][
        "result_is_only_path_in_commit"
    ]


def test_result_audit_successor_keeps_aggregation_and_performance_closed() -> None:
    artifact = build_artifact("a" * 40)
    assert artifact["decision"] == DECISION
    assert _embedded_digest(artifact, "audit_digest")
    assert artifact["authorization"]["aggregation_gate_creation"] == "AUTHORIZED"
    assert artifact["authorization"]["aggregation"] == (
        "NOT_AUTHORIZED_UNTIL_SEPARATE_GATE"
    )
    assert artifact["authorization"]["FCI_reexecution"] == "NOT_AUTHORIZED"
    assert artifact["authorization"]["performance_claim"] == "NOT_AUTHORIZED"


def test_result_audit_digest_rejects_tamper() -> None:
    artifact = build_artifact("b" * 40)
    tampered = deepcopy(artifact)
    tampered["observed"]["counters"]["FCI_evaluations"] = 4
    assert not _embedded_digest(tampered, "audit_digest")
    body = {key: value for key, value in tampered.items() if key != "audit_digest"}
    tampered["audit_digest"] = _digest(body)
    assert _embedded_digest(tampered, "audit_digest")
    assert tampered["observed"]["counters"]["FCI_evaluations"] != 5


def test_result_publication_is_single_commit_and_parent_absent() -> None:
    evidence = inspect_result()["bindings"]["result_commit_evidence"]
    assert evidence["parent_had_no_result"]
    assert evidence["commit_changed_paths"] == [
        "artifacts/v5-final/parent-native/s12-offline-fci-reference-v1/"
        "offline-fci-reference-result-v1.json"
    ]
    assert len(evidence["commit"]) == 40
    assert len(evidence["git_blob_oid"]) == 40

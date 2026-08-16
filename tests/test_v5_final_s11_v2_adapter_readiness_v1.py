import json

from v5_final.s11_v2_adapter_readiness_v1 import OUTPUT, audit


def test_adapter_readiness_is_additive_zero_outcome_and_still_blocked() -> None:
    report = audit()
    artifact = json.loads(OUTPUT.read_text())
    assert report["status"] == "PASS_ADAPTER_READINESS_ARTIFACT"
    assert all(report["checks"].values())
    assert artifact["semantic_diff_classification"] == (
        "TRANSPORT_ONLY_QUEUE_V2_SCIENTIFIC_SEMANTICS_UNCHANGED"
    )
    assert artifact["binding"]["queue_v2"]["modified"] is False
    assert artifact["candidate_energy_evaluations"] == 0
    assert artifact["optimizer_iterations"] == 0
    assert artifact["FCI_evaluations"] == 0
    assert all(
        value.startswith("NOT_AUTHORIZED")
        for value in artifact["authorization"].values()
    )

from __future__ import annotations

from v5_final import s11_v1_infrastructure_closure_v1 as subject


def test_closure_reconstructs_byte_identically_when_present():
    if not subject.CLOSURE_PATH.exists():
        return
    committed = subject._canonical(subject.CLOSURE_PATH)
    assert committed == subject.build_closure_manifest()


def test_closure_forbids_performance_and_future_execution():
    if not subject.CLOSURE_PATH.exists():
        return
    record = subject._canonical(subject.CLOSURE_PATH)
    assert all(value == "NOT_AUTHORIZED" or value.startswith("NOT_AUTHORIZED_") for value in record["authorization"].values())
    assert record["cause"]["performance_rejection"] is False
    assert record["queue_state"]["scientific_terminal"] == 28
    assert record["work_separation"]["mix_with_future_s11_v2"] is False


def test_component_reconstruction_matches_retry_preparation():
    preparation = subject._canonical(subject.PREPARATION_PATH)
    assert subject.reconstruct_component_digests() == preparation["component_digests_before"]

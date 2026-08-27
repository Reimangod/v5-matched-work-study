from __future__ import annotations

import copy

import pytest

from v5_final.s3_execution_ledger import _delta, synthetic_reconciliation_probe
from v5_final.semantic_contract_v2 import WorkDelta
from v5_final.semantic_events import SemanticEventError, SemanticEventType, event_from_dict_strict
from v5_final.work_ledger import (
    IntegratedWorkLedger,
    WorkLedgerError,
    reconcile,
    reconstruct_work,
    release_summary,
)


def _ledger(cap: WorkDelta | None = None) -> IntegratedWorkLedger:
    return IntegratedWorkLedger(
        cap=cap or WorkDelta(energy_evaluations=10),
        root_digest="0" * 64,
        producer="v5_final.executor.test_double",
    )


def test_all_components_reconcile_in_synthetic_nonmolecular_probe() -> None:
    probe = synthetic_reconciliation_probe()
    assert probe["all_components_nonzero"] is True
    assert all(probe["reconciliation_checks"].values())
    assert probe["probe_classification"].startswith("synthetic")


def test_cap_rejection_occurs_before_event_and_raw_counter_mutation() -> None:
    ledger = _ledger(WorkDelta(energy_evaluations=1))
    with pytest.raises(WorkLedgerError, match="componentwise work cap"):
        ledger.record_operation(
            event_type=SemanticEventType.ENERGY_EVALUATED,
            queue_item_id="q1",
            delta=_delta(WorkDelta(energy_evaluations=2), energy_available=True),
            evidence={"raw_counter_source": "nfev"},
        )
    assert ledger.events == ()
    assert ledger.raw_total == WorkDelta()


def test_event_rejects_operation_delta_semantic_mismatch() -> None:
    ledger = _ledger(WorkDelta(energy_evaluations=10, resource_recounts=10))
    with pytest.raises(WorkLedgerError, match="cannot charge"):
        ledger.record_operation(
            event_type=SemanticEventType.ENERGY_EVALUATED,
            queue_item_id="q1",
            delta=_delta(WorkDelta(resource_recounts=1), energy_available=True),
            evidence={"raw_counter_source": "counter"},
        )


def test_digest_valid_but_semantically_wrong_event_is_rejected() -> None:
    ledger = _ledger()
    event = ledger.record_operation(
        event_type=SemanticEventType.ENERGY_EVALUATED,
        queue_item_id="q1",
        delta=_delta(WorkDelta(energy_evaluations=1), energy_available=True),
        evidence={"raw_counter_source": "nfev"},
    )
    forged = event.to_dict()
    forged["delta"]["work_delta"]["energy_evaluations"] = 0
    with pytest.raises(SemanticEventError, match="digest or canonical content"):
        event_from_dict_strict(forged)


def test_reconciliation_rejects_independent_raw_counter_mismatch() -> None:
    ledger = _ledger()
    ledger.record_operation(
        event_type=SemanticEventType.ENERGY_EVALUATED,
        queue_item_id="q1",
        delta=_delta(WorkDelta(energy_evaluations=1), energy_available=True),
        evidence={"raw_counter_source": "nfev"},
    )
    document = ledger.close()
    summary = release_summary(document)
    checks = reconcile(
        independent_raw_counter=WorkDelta(energy_evaluations=2),
        ledger_document=document,
        summary=summary,
    )
    assert checks["raw_equals_semantic_ledger"] is False
    assert checks["every_component_reconciled"] is False


def test_reconciliation_rejects_forged_release_summary() -> None:
    ledger = _ledger()
    ledger.record_operation(
        event_type=SemanticEventType.ENERGY_EVALUATED,
        queue_item_id="q1",
        delta=_delta(WorkDelta(energy_evaluations=1), energy_available=True),
        evidence={"raw_counter_source": "nfev"},
    )
    document = ledger.close()
    summary = release_summary(document)
    forged = copy.deepcopy(summary)
    forged["work_total"]["energy_evaluations"] = 0
    checks = reconcile(
        independent_raw_counter=WorkDelta(energy_evaluations=1),
        ledger_document=document,
        summary=forged,
    )
    assert checks["semantic_ledger_equals_release_summary"] is False
    assert checks["release_summary_digest_valid"] is False


def test_reconstruction_rejects_wrong_chain_root() -> None:
    ledger = _ledger()
    ledger.record_operation(
        event_type=SemanticEventType.ENERGY_EVALUATED,
        queue_item_id="q1",
        delta=_delta(WorkDelta(energy_evaluations=1), energy_available=True),
        evidence={"raw_counter_source": "nfev"},
    )
    with pytest.raises(WorkLedgerError, match="digest chain"):
        reconstruct_work(ledger.events, root_digest="f" * 64)


def test_release_summary_rejects_forged_ledger_digest() -> None:
    ledger = _ledger()
    ledger.record_operation(
        event_type=SemanticEventType.ENERGY_EVALUATED,
        queue_item_id="q1",
        delta=_delta(WorkDelta(energy_evaluations=1), energy_available=True),
        evidence={"raw_counter_source": "nfev"},
    )
    document = ledger.close()
    document["ledger_digest"] = "f" * 64
    with pytest.raises(WorkLedgerError, match="digest mismatch"):
        release_summary(document)

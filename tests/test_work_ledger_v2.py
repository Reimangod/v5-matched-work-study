from __future__ import annotations

from dataclasses import asdict
import pytest

from v5_matched_work.work_ledger import (
    WorkLedger, WorkLedgerError, WorkVector, event_from_dict, event_to_dict,
    raw_ledger_document, reconstruct_candidate_energy_evaluations,
)


def test_shared_counter_api_and_zero_event_reconstruction() -> None:
    empty = raw_ledger_document(ledger_id="zero", phase="pre-s5", cap=WorkVector(), events=[])
    assert empty["events"] == []
    assert empty["reconstructed_candidate_energy_evaluations"] == 0
    ledger = WorkLedger(WorkVector(N_E=1, N_G=1, N_gradcomp=3))
    event = ledger.charge(
        "candidate-energy-evaluation", method_id="m", case_id="c",
        candidate_id="x", path_id="p",
    )
    assert event_from_dict(event_to_dict(event)) == event
    assert reconstruct_candidate_energy_evaluations(ledger.events) == 1
    with pytest.raises(WorkLedgerError):
        ledger.charge("candidate-energy-evaluation", method_id="m", case_id="c",
                      candidate_id="y", path_id="p")


def test_full_gradient_has_one_vector_and_dimension_components() -> None:
    ledger = WorkLedger(WorkVector(N_G=1, N_gradcomp=7))
    ledger.charge("full-gradient-evaluation", method_id="m", case_id="c",
                  candidate_id=None, path_id="p", dimension=7)
    assert asdict(ledger.total) == {
        "N_E": 0, "N_G": 1, "N_gradcomp": 7, "N_HVP": 0, "N_exact": 0,
        "N_recount": 0, "N_rewrite": 0, "N_states": 0, "N_rounds": 0,
    }

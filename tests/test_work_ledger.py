from __future__ import annotations
import pytest
from v5_matched_work.work_ledger import WorkLedger, WorkLedgerError, WorkVector, reconstruct


def test_componentwise_cap_is_checked_before_operation() -> None:
    ledger=WorkLedger(WorkVector(N_E=2,N_exact=1))
    values={"method_id":"m","case_id":"x","candidate_id":"c","path_id":"p","cache":"not-applicable"}
    ledger.record(**values,operation="attempt",outcome="rejected",delta=WorkVector(N_E=2,N_exact=1))
    with pytest.raises(WorkLedgerError): ledger.record(**values,operation="extra",outcome="failed",delta=WorkVector(N_E=1))
    assert reconstruct(ledger.events)==WorkVector(N_E=2,N_exact=1)

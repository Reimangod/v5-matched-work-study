from __future__ import annotations

import pytest

from v5_final.parent_native_work_accounting import (
    ParentNativeWorkError,
    operation_delta,
)
from v5_final.parent_native_work_accounting_probe import run_probe
from v5_final.s5_parent_native_work_accounting_audit import audit, build, verify


def test_s5_behavioral_probe_reconstructs_every_counter_without_outcomes():
    probe = run_probe()
    assert probe["raw_total"] == probe["expected_total"]
    assert probe["reconstructed_total"] == probe["expected_total"]
    assert probe["release_total"] == probe["expected_total"]
    assert probe["molecular_candidate_energy_evaluations"] == 0


def test_s5_rejects_invalid_outcome_semantics():
    with pytest.raises(ParentNativeWorkError, match="completed or failed"):
        operation_delta(
            "candidate-energy-evaluation",
            units=1,
            dimension=None,
            outcome="duplicate",
        )


def test_s5_audit_is_scoped_and_immutable():
    built = build()
    assert all(verify(built).values())
    assert built["decision"] == "GO_S6_PERSISTENT_RUNNER_ONLY"
    assert all(audit().values())

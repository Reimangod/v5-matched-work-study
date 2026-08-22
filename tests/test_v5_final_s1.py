from __future__ import annotations

from dataclasses import replace

import pytest

from v5_final.scientific_values import (
    ScientificValueError,
    ScientificValueState,
    TaggedScientificValue,
)
from v5_final.semantic_contract import (
    ResourceDelta,
    ScientificValueDelta,
    SemanticContractError,
    SemanticDelta,
    StateDelta,
    TerminalRecord,
    TerminalStatus,
    WorkDelta,
)


DIGEST_A = "a" * 64
DIGEST_B = "b" * 64


def _not_evaluated(reason: str = "not_run") -> TaggedScientificValue:
    return TaggedScientificValue.not_evaluated(
        quantity="candidate_energy", unit="hartree", reason=reason
    )


def _delta(*, current: TaggedScientificValue | None = None) -> SemanticDelta:
    prior = _not_evaluated()
    return SemanticDelta(
        state_delta=StateDelta(DIGEST_A, DIGEST_A),
        resource_delta=ResourceDelta(),
        scientific_value_delta=ScientificValueDelta(prior, current or prior),
        work_delta=WorkDelta(),
    )


def test_legacy_zero_is_never_promoted_to_scientific_zero() -> None:
    imported = TaggedScientificValue.from_legacy_energy(0)
    assert imported.state is ScientificValueState.LEGACY_SENTINEL_NOT_EVALUATED
    assert imported.value is None
    actual_zero = TaggedScientificValue.available(
        quantity="energy_difference", unit="hartree", value="0"
    )
    assert actual_zero.state is ScientificValueState.AVAILABLE
    assert actual_zero.value == "0"


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_nonfinite_scientific_values_are_rejected(value: str) -> None:
    with pytest.raises(ScientificValueError):
        TaggedScientificValue.available(
            quantity="candidate_energy", unit="hartree", value=value
        )


def test_nonavailable_state_cannot_carry_numeric_value() -> None:
    with pytest.raises(ScientificValueError):
        TaggedScientificValue(
            quantity="candidate_energy",
            unit="hartree",
            state=ScientificValueState.NOT_EVALUATED,
            value="0",
            reason="not_run",
        )


def test_uncommitted_transition_must_restore_exact_source_digest() -> None:
    with pytest.raises(SemanticContractError):
        StateDelta(DIGEST_A, DIGEST_B, committed=False)


def test_deduplicated_terminal_is_zero_charge_and_evidence_complete() -> None:
    record = TerminalRecord(
        status=TerminalStatus.DEDUPLICATED,
        delta=_delta(current=_not_evaluated("canonical_state_reused")),
        evidence={
            "candidate_intent_id": "intent-v1:x",
            "proposed_physical_state_id": "state-v1:y",
            "canonical_evaluation_event_id": "event-v1:z",
            "alias_record_digest": DIGEST_A,
        },
    )
    assert record.delta.resource_delta.is_zero()
    assert record.delta.work_delta.is_zero()


def test_deduplicated_terminal_rejects_hidden_work_charge() -> None:
    delta = replace(_delta(), work_delta=WorkDelta(N_states=1))
    with pytest.raises(SemanticContractError):
        TerminalRecord(
            status=TerminalStatus.DEDUPLICATED,
            delta=delta,
            evidence={
                "candidate_intent_id": "intent-v1:x",
                "proposed_physical_state_id": "state-v1:y",
                "canonical_evaluation_event_id": "event-v1:z",
                "alias_record_digest": DIGEST_A,
            },
        )


def test_failed_terminal_requires_exact_rollback_and_invalid_value() -> None:
    invalid = TaggedScientificValue(
        quantity="candidate_energy",
        unit="hartree",
        state=ScientificValueState.INVALID,
        reason="nan_from_kernel",
    )
    record = TerminalRecord(
        status=TerminalStatus.FAILED,
        delta=_delta(current=invalid),
        evidence={
            "execution_request_id": "request-v1:r",
            "error_code": "NONFINITE_RESULT",
            "incident_segment_digest": DIGEST_B,
            "rollback_evidence_digest": DIGEST_B,
            "source_digest_before": DIGEST_A,
            "source_digest_after": DIGEST_A,
        },
    )
    assert record.status is TerminalStatus.FAILED


def test_terminal_state_rejects_missing_evidence() -> None:
    with pytest.raises(SemanticContractError, match="missing evidence"):
        TerminalRecord(
            status=TerminalStatus.CANCELLED,
            delta=_delta(),
            evidence={"execution_request_id": "request-v1:r"},
        )


def test_budget_rejection_cannot_hide_a_work_charge() -> None:
    with pytest.raises(SemanticContractError, match="pre-operation zero charge"):
        TerminalRecord(
            status=TerminalStatus.BUDGET_REJECTED,
            delta=replace(_delta(), work_delta=WorkDelta(N_E=1)),
            evidence={
                "execution_request_id": "request-v1:r",
                "cap": {"N_E": 0},
                "projected_total": {"N_E": 1},
                "ledger_digest": DIGEST_A,
            },
        )

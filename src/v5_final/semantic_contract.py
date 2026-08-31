"""S1 semantic delta partitions and evidence-complete terminal states."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import re
from typing import Any, Mapping

from .scientific_values import ScientificValueState, TaggedScientificValue


class SemanticContractError(ValueError):
    pass


COUNTER_COMPONENTS = (
    "N_E",
    "N_G",
    "N_gradcomp",
    "N_HVP",
    "N_exact",
    "N_recount",
    "N_rewrite",
    "N_states",
    "N_rounds",
)


def _validate_nonnegative_integers(instance: object) -> None:
    for field in COUNTER_COMPONENTS:
        value = getattr(instance, field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise SemanticContractError("counter components must be nonnegative integers")


@dataclass(frozen=True)
class ResourceDelta:
    N_E: int = 0
    N_G: int = 0
    N_gradcomp: int = 0
    N_HVP: int = 0
    N_exact: int = 0
    N_recount: int = 0
    N_rewrite: int = 0
    N_states: int = 0
    N_rounds: int = 0

    def __post_init__(self) -> None:
        _validate_nonnegative_integers(self)

    def is_zero(self) -> bool:
        return not any(asdict(self).values())


@dataclass(frozen=True)
class WorkDelta:
    N_E: int = 0
    N_G: int = 0
    N_gradcomp: int = 0
    N_HVP: int = 0
    N_exact: int = 0
    N_recount: int = 0
    N_rewrite: int = 0
    N_states: int = 0
    N_rounds: int = 0

    def __post_init__(self) -> None:
        _validate_nonnegative_integers(self)

    def is_zero(self) -> bool:
        return not any(asdict(self).values())


@dataclass(frozen=True)
class StateDelta:
    source_before_digest: str
    source_after_digest: str
    created_physical_state_ids: tuple[str, ...] = ()
    removed_physical_state_ids: tuple[str, ...] = ()
    committed: bool = False

    def __post_init__(self) -> None:
        for digest in (self.source_before_digest, self.source_after_digest):
            if not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise SemanticContractError("source digests must be SHA-256 values")
        if len(set(self.created_physical_state_ids)) != len(self.created_physical_state_ids):
            raise SemanticContractError("created physical states must be unique")
        if len(set(self.removed_physical_state_ids)) != len(self.removed_physical_state_ids):
            raise SemanticContractError("removed physical states must be unique")
        if not self.committed and self.source_before_digest != self.source_after_digest:
            raise SemanticContractError("uncommitted state delta must restore the source digest")

    def is_zero(self) -> bool:
        return (
            self.source_before_digest == self.source_after_digest
            and not self.created_physical_state_ids
            and not self.removed_physical_state_ids
            and not self.committed
        )


@dataclass(frozen=True)
class ScientificValueDelta:
    previous: TaggedScientificValue
    current: TaggedScientificValue

    def __post_init__(self) -> None:
        if (self.previous.quantity, self.previous.unit) != (
            self.current.quantity,
            self.current.unit,
        ):
            raise SemanticContractError("scientific delta cannot change quantity or unit")


@dataclass(frozen=True)
class SemanticDelta:
    state_delta: StateDelta
    resource_delta: ResourceDelta
    scientific_value_delta: ScientificValueDelta
    work_delta: WorkDelta

    def to_dict(self) -> dict[str, Any]:
        return {
            "state_delta": asdict(self.state_delta),
            "resource_delta": asdict(self.resource_delta),
            "scientific_value_delta": {
                "previous": self.scientific_value_delta.previous.to_dict(),
                "current": self.scientific_value_delta.current.to_dict(),
            },
            "work_delta": asdict(self.work_delta),
        }


class TerminalStatus(str, Enum):
    EXECUTED = "EXECUTED"
    DEDUPLICATED = "DEDUPLICATED"
    STRUCTURALLY_REJECTED = "STRUCTURALLY_REJECTED"
    BUDGET_REJECTED = "BUDGET_REJECTED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


REQUIRED_TERMINAL_EVIDENCE: dict[TerminalStatus, frozenset[str]] = {
    TerminalStatus.EXECUTED: frozenset(
        {
            "execution_request_id",
            "semantic_event_ids",
            "kernel_segment_digest",
            "result_artifact_digest",
        }
    ),
    TerminalStatus.DEDUPLICATED: frozenset(
        {
            "candidate_intent_id",
            "proposed_physical_state_id",
            "canonical_evaluation_event_id",
            "alias_record_digest",
        }
    ),
    TerminalStatus.STRUCTURALLY_REJECTED: frozenset(
        {"candidate_intent_id", "reason_code", "structural_evidence_digest"}
    ),
    TerminalStatus.BUDGET_REJECTED: frozenset(
        {"execution_request_id", "cap", "projected_total", "ledger_digest"}
    ),
    TerminalStatus.FAILED: frozenset(
        {
            "execution_request_id",
            "error_code",
            "incident_segment_digest",
            "rollback_evidence_digest",
            "source_digest_before",
            "source_digest_after",
        }
    ),
    TerminalStatus.CANCELLED: frozenset(
        {"execution_request_id", "reason_code", "no_commit_evidence_digest"}
    ),
}


@dataclass(frozen=True)
class TerminalRecord:
    status: TerminalStatus
    delta: SemanticDelta
    evidence: Mapping[str, Any]

    def __post_init__(self) -> None:
        missing = REQUIRED_TERMINAL_EVIDENCE[self.status] - self.evidence.keys()
        if missing:
            raise SemanticContractError(
                f"{self.status.value} missing evidence: {sorted(missing)}"
            )
        empty = [
            key
            for key in REQUIRED_TERMINAL_EVIDENCE[self.status]
            if self.evidence[key] is None or self.evidence[key] == ""
        ]
        if empty:
            raise SemanticContractError(
                f"{self.status.value} has empty evidence: {sorted(empty)}"
            )
        self._validate_semantics()

    def _validate_semantics(self) -> None:
        current = self.delta.scientific_value_delta.current.state
        if self.status is TerminalStatus.EXECUTED:
            if current is not ScientificValueState.AVAILABLE:
                raise SemanticContractError("EXECUTED requires an AVAILABLE scientific value")
        elif self.status is TerminalStatus.DEDUPLICATED:
            if not self.delta.state_delta.is_zero():
                raise SemanticContractError("DEDUPLICATED must have zero state delta")
            if not self.delta.resource_delta.is_zero() or not self.delta.work_delta.is_zero():
                raise SemanticContractError("DEDUPLICATED must not charge resources or work")
            if current is not ScientificValueState.NOT_EVALUATED:
                raise SemanticContractError("DEDUPLICATED carries no new scientific evaluation")
        elif self.status in {
            TerminalStatus.STRUCTURALLY_REJECTED,
            TerminalStatus.BUDGET_REJECTED,
            TerminalStatus.CANCELLED,
        }:
            if not self.delta.state_delta.is_zero():
                raise SemanticContractError(f"{self.status.value} must not mutate source state")
            if current is not ScientificValueState.NOT_EVALUATED:
                raise SemanticContractError(
                    f"{self.status.value} must retain NOT_EVALUATED scientific state"
                )
            if self.status is TerminalStatus.BUDGET_REJECTED and (
                not self.delta.resource_delta.is_zero() or not self.delta.work_delta.is_zero()
            ):
                raise SemanticContractError("BUDGET_REJECTED must be a pre-operation zero charge")
        elif self.status is TerminalStatus.FAILED:
            if not self.delta.state_delta.is_zero():
                raise SemanticContractError("FAILED must restore the exact source state")
            if self.evidence["source_digest_before"] != self.evidence["source_digest_after"]:
                raise SemanticContractError("FAILED rollback evidence has unequal source digests")
            if current is not ScientificValueState.INVALID:
                raise SemanticContractError("FAILED requires an INVALID scientific value")

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "delta": self.delta.to_dict(),
            "evidence": dict(self.evidence),
        }

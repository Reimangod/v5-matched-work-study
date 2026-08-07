"""Corrected S1 delta semantics: architecture resources are not computation work."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

from .scientific_values import ScientificValueState
from .semantic_contract import (
    REQUIRED_TERMINAL_EVIDENCE,
    ScientificValueDelta,
    SemanticContractError,
    StateDelta,
    TerminalStatus,
)


RESOURCE_COMPONENTS = (
    "cnot_count",
    "cnot_depth",
    "total_depth",
    "parameter_count",
    "logical_block_count",
)

WORK_COMPONENTS = (
    "energy_evaluations",
    "gradient_vector_evaluations",
    "gradient_component_equivalents",
    "hvp_evaluations",
    "optimizer_starts",
    "optimizer_iterations",
    "resource_recounts",
    "candidate_generations",
    "search_states",
    "rewrite_verifications",
    "statevector_recomputations",
)


@dataclass(frozen=True)
class ResourceDelta:
    """Signed changes to the produced circuit/architecture resources."""

    cnot_count: int = 0
    cnot_depth: int = 0
    total_depth: int = 0
    parameter_count: int = 0
    logical_block_count: int = 0

    def __post_init__(self) -> None:
        if any(
            isinstance(getattr(self, field), bool)
            or not isinstance(getattr(self, field), int)
            for field in RESOURCE_COMPONENTS
        ):
            raise SemanticContractError("resource deltas must be signed integers")

    def is_zero(self) -> bool:
        return not any(asdict(self).values())


@dataclass(frozen=True)
class WorkDelta:
    """Nonnegative computation performed under the matched-work envelope."""

    energy_evaluations: int = 0
    gradient_vector_evaluations: int = 0
    gradient_component_equivalents: int = 0
    hvp_evaluations: int = 0
    optimizer_starts: int = 0
    optimizer_iterations: int = 0
    resource_recounts: int = 0
    candidate_generations: int = 0
    search_states: int = 0
    rewrite_verifications: int = 0
    statevector_recomputations: int = 0

    def __post_init__(self) -> None:
        if any(
            isinstance(getattr(self, field), bool)
            or not isinstance(getattr(self, field), int)
            or getattr(self, field) < 0
            for field in WORK_COMPONENTS
        ):
            raise SemanticContractError("work deltas must be nonnegative integers")

    def is_zero(self) -> bool:
        return not any(asdict(self).values())


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
        if any(
            self.evidence[key] is None or self.evidence[key] == ""
            for key in REQUIRED_TERMINAL_EVIDENCE[self.status]
        ):
            raise SemanticContractError(f"{self.status.value} contains empty evidence")
        self._validate_semantics()

    def _validate_semantics(self) -> None:
        current = self.delta.scientific_value_delta.current.state
        if self.status is TerminalStatus.EXECUTED:
            if current is not ScientificValueState.AVAILABLE:
                raise SemanticContractError("EXECUTED requires an AVAILABLE scientific value")
            return
        if self.status is TerminalStatus.DEDUPLICATED:
            if (
                not self.delta.state_delta.is_zero()
                or not self.delta.resource_delta.is_zero()
                or not self.delta.work_delta.is_zero()
            ):
                raise SemanticContractError("DEDUPLICATED event itself must be zero delta")
            if current is not ScientificValueState.NOT_EVALUATED:
                raise SemanticContractError("DEDUPLICATED adds no new scientific value")
            return
        if self.status in {
            TerminalStatus.STRUCTURALLY_REJECTED,
            TerminalStatus.BUDGET_REJECTED,
            TerminalStatus.CANCELLED,
        }:
            if not self.delta.state_delta.is_zero():
                raise SemanticContractError(f"{self.status.value} must not mutate source state")
            if current is not ScientificValueState.NOT_EVALUATED:
                raise SemanticContractError(f"{self.status.value} must be NOT_EVALUATED")
            if self.status is TerminalStatus.BUDGET_REJECTED and (
                not self.delta.resource_delta.is_zero() or not self.delta.work_delta.is_zero()
            ):
                raise SemanticContractError("BUDGET_REJECTED must be pre-operation zero delta")
            return
        if self.status is TerminalStatus.FAILED:
            if not self.delta.state_delta.is_zero():
                raise SemanticContractError("FAILED must restore the exact source state")
            if self.evidence["source_digest_before"] != self.evidence["source_digest_after"]:
                raise SemanticContractError("FAILED rollback source digests differ")
            if current is not ScientificValueState.INVALID:
                raise SemanticContractError("FAILED requires an INVALID scientific value")


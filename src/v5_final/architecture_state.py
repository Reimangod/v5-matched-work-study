"""Immutable production architecture state with exact content digests."""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
from typing import Any, Mapping

from v5_matched_work.atomic_artifacts import canonical_json_bytes

from .identities import ProposedPhysicalState


class ArchitectureStateError(ValueError):
    pass


RESOURCE_FIELDS = (
    "cnot_count",
    "cnot_depth",
    "total_depth",
    "parameter_count",
    "logical_block_count",
)


@dataclass(frozen=True)
class ArchitectureState:
    problem_id: str
    physical_state: ProposedPhysicalState
    ansatz_indices: tuple[int, ...]
    coefficient_bytes: tuple[str, ...]
    cumulative_parameter_counts: tuple[int, ...]
    energy_hartree: str
    gradient_infinity: str
    resources: Mapping[str, int]
    statevector_digest: str
    circuit_digest: str
    generation: int = 0

    def __post_init__(self) -> None:
        if self.problem_id != self.physical_state.problem_id:
            raise ArchitectureStateError("problem and physical state identities differ")
        if len(self.ansatz_indices) != len(self.coefficient_bytes):
            raise ArchitectureStateError("ansatz indices and coefficients differ in length")
        if not self.cumulative_parameter_counts or self.cumulative_parameter_counts[-1] != len(
            self.ansatz_indices
        ):
            raise ArchitectureStateError("cumulative counts do not terminate at ansatz length")
        if any(
            field not in self.resources
            or isinstance(self.resources[field], bool)
            or not isinstance(self.resources[field], int)
            or self.resources[field] < 0
            for field in RESOURCE_FIELDS
        ):
            raise ArchitectureStateError("architecture resources are incomplete or invalid")
        for digest in (self.statevector_digest, self.circuit_digest):
            if len(digest) != 64:
                raise ArchitectureStateError("statevector and circuit digests must be SHA-256")
        if isinstance(self.generation, bool) or self.generation < 0:
            raise ArchitectureStateError("generation must be nonnegative")

    @property
    def proposed_physical_state_id(self) -> str:
        return self.physical_state.proposed_physical_state_id

    def payload(self) -> dict[str, Any]:
        return {
            "problem_id": self.problem_id,
            "proposed_physical_state_id": self.proposed_physical_state_id,
            "ansatz_indices": list(self.ansatz_indices),
            "coefficient_bytes": list(self.coefficient_bytes),
            "cumulative_parameter_counts": list(self.cumulative_parameter_counts),
            "energy_hartree": self.energy_hartree,
            "gradient_infinity": self.gradient_infinity,
            "resources": {field: self.resources[field] for field in RESOURCE_FIELDS},
            "statevector_digest": self.statevector_digest,
            "circuit_digest": self.circuit_digest,
            "generation": self.generation,
        }

    @property
    def source_digest(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.payload())).hexdigest()

    def committed_successor(self, **changes: Any) -> "ArchitectureState":
        return replace(self, generation=self.generation + 1, **changes)

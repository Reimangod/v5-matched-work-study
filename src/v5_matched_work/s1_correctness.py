"""Outcome-independent V5 correctness baseline and historical reporting view."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Iterable, Mapping


RESOURCE_FIELDS = (
    "cnot_count",
    "cnot_depth",
    "total_depth",
    "parameter_count",
    "logical_block_count",
)


class CorrectnessBaselineError(RuntimeError):
    """Raised when a correctness-only record is incomplete or nonfinite."""


@dataclass(frozen=True)
class FrontierPoint:
    point_id: str
    energy_increase_hartree: float
    cnot_count: int
    cnot_depth: int
    total_depth: int
    parameter_count: int
    logical_block_count: int

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "FrontierPoint":
        identifier = value.get("id") or value.get("point_id")
        if not isinstance(identifier, str) or not identifier:
            raise CorrectnessBaselineError("frontier point ID is absent")
        energy = value.get("energy_increase_hartree")
        if isinstance(energy, bool) or not isinstance(energy, (int, float)) or not math.isfinite(float(energy)):
            raise CorrectnessBaselineError("frontier energy is nonfinite or invalid")
        resources: dict[str, int] = {}
        for field in RESOURCE_FIELDS:
            observed = value.get(field)
            if isinstance(observed, bool) or not isinstance(observed, int) or observed < 0:
                raise CorrectnessBaselineError(f"invalid physical resource: {field}")
            resources[field] = observed
        return cls(identifier, float(energy), **resources)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.point_id,
            "energy_increase_hartree": self.energy_increase_hartree,
            **{field: getattr(self, field) for field in RESOURCE_FIELDS},
        }


def dominates(left: FrontierPoint, right: FrontierPoint) -> bool:
    left_values = (left.energy_increase_hartree,) + tuple(
        getattr(left, field) for field in RESOURCE_FIELDS
    )
    right_values = (right.energy_increase_hartree,) + tuple(
        getattr(right, field) for field in RESOURCE_FIELDS
    )
    return all(a <= b for a, b in zip(left_values, right_values)) and any(
        a < b for a, b in zip(left_values, right_values)
    )


def accepted_pareto_frontier(values: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    points = [FrontierPoint.from_mapping(value) for value in values]
    identifiers = [point.point_id for point in points]
    if len(identifiers) != len(set(identifiers)):
        raise CorrectnessBaselineError("duplicate accepted frontier point ID")
    frontier = [
        point
        for point in points
        if not any(dominates(other, point) for other in points if other is not point)
    ]
    return [
        point.to_dict()
        for point in sorted(
            frontier,
            key=lambda item: (
                item.energy_increase_hartree,
                item.cnot_count,
                item.cnot_depth,
                item.total_depth,
                item.parameter_count,
                item.logical_block_count,
                item.point_id,
            ),
        )
    ]


def source_relative_budget(
    *, source_energy_hartree: float, committed_energy_hartree: float, total_budget_hartree: float
) -> float:
    values = (source_energy_hartree, committed_energy_hartree, total_budget_hartree)
    if any(not math.isfinite(value) for value in values) or total_budget_hartree < 0:
        raise CorrectnessBaselineError("source-relative energy budget inputs are invalid")
    return max(0.0, total_budget_hartree - (committed_energy_hartree - source_energy_hartree))


@dataclass(frozen=True)
class RuntimeEndpointProvenance:
    candidate_id: str
    runtime_selection_endpoint: str
    catalog_parent_digest: str

    def __post_init__(self) -> None:
        if not self.candidate_id or self.runtime_selection_endpoint not in RESOURCE_FIELDS:
            raise CorrectnessBaselineError("runtime endpoint provenance is incomplete")
        if len(self.catalog_parent_digest) != 64 or any(
            character not in "0123456789abcdef" for character in self.catalog_parent_digest
        ):
            raise CorrectnessBaselineError("catalog parent digest is invalid")


GRADIENT_FIELD_DICTIONARY = {
    "source_checkpoint_parameter_gradient_infinity": {
        "evaluation_point": "immutable source checkpoint",
        "coordinate_system": "source ansatz parameters",
    },
    "candidate_full_source_coordinate_gradient_infinity": {
        "evaluation_point": "mapped candidate point",
        "coordinate_system": "full source coordinates",
    },
    "candidate_target_coordinate_gradient_infinity": {
        "evaluation_point": "optimized candidate point",
        "coordinate_system": "target coordinates",
    },
    "candidate_orthonormal_tangent_gradient_infinity": {
        "evaluation_point": "optimized candidate point",
        "coordinate_system": "orthonormal basis of target tangent space",
    },
}


def risk_semantics(uncertainty_margin_hartree: float) -> str:
    if not math.isfinite(uncertainty_margin_hartree) or uncertainty_margin_hartree < 0:
        raise CorrectnessBaselineError("uncertainty margin is invalid")
    return (
        "risk-neutral-zero-uncertainty-margin"
        if uncertainty_margin_hartree == 0.0
        else "risk-adjusted-nonzero-uncertainty-margin"
    )

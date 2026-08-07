"""Nondominated outcome-blind selector that never scalarizes primary axes."""

from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from .predictor_v2 import PredictorResult


RESOURCE_AXES = (
    "cnot_count",
    "cnot_depth",
    "total_depth",
    "parameter_count",
    "logical_block_count",
)


class ParetoSelectorV2Error(ValueError):
    pass


def _dominates(left: PredictorResult, right: PredictorResult) -> bool:
    if (
        left.predicted_energy_change_hartree is None
        or right.predicted_energy_change_hartree is None
    ):
        return False
    left_axes = (
        Decimal(left.predicted_energy_change_hartree),
        *(left.predicted_resource_delta[axis] for axis in RESOURCE_AXES),
    )
    right_axes = (
        Decimal(right.predicted_energy_change_hartree),
        *(right.predicted_resource_delta[axis] for axis in RESOURCE_AXES),
    )
    return all(a <= b for a, b in zip(left_axes, right_axes)) and any(
        a < b for a, b in zip(left_axes, right_axes)
    )


def nondominated_predictions(
    values: Iterable[PredictorResult],
) -> tuple[PredictorResult, ...]:
    materialized = tuple(values)
    if not materialized:
        raise ParetoSelectorV2Error("selector requires candidates")
    if len({value.candidate_intent_id for value in materialized}) != len(materialized):
        raise ParetoSelectorV2Error("candidate intent IDs must be unique")
    retained = [
        candidate
        for candidate in materialized
        if not any(
            other is not candidate and _dominates(other, candidate)
            for other in materialized
        )
    ]
    return tuple(sorted(retained, key=lambda value: value.candidate_intent_id))

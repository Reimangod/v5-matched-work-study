"""Deterministic outcome-blind queue selection."""

from __future__ import annotations

from typing import Iterable

from .predictor import CandidatePrediction


class ParetoSelectorError(ValueError):
    pass


def select_prediction(values: Iterable[CandidatePrediction]) -> CandidatePrediction:
    materialized = tuple(values)
    if not materialized:
        raise ParetoSelectorError("selector requires at least one prediction")
    if any(value.predicted_energy.value is not None for value in materialized):
        raise ParetoSelectorError("pre-outcome selector cannot observe candidate energy")
    return min(
        materialized,
        key=lambda value: (
            value.predicted_resource_delta["cnot_count"],
            value.predicted_resource_delta["parameter_count"],
            value.predicted_resource_delta["cnot_depth"],
            value.predicted_resource_delta["total_depth"],
            value.predicted_resource_delta["logical_block_count"],
            value.candidate_intent_id,
        ),
    )

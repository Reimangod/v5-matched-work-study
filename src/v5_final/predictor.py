"""Outcome-blind structural predictor used only before candidate execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .architecture_state import ArchitectureState, RESOURCE_FIELDS
from .candidate_catalog import CatalogCandidate
from .scientific_values import TaggedScientificValue


@dataclass(frozen=True)
class CandidatePrediction:
    candidate_intent_id: str
    proposed_physical_state_id: str
    predicted_resource_delta: Mapping[str, int]
    predicted_energy: TaggedScientificValue


def predict_structural(
    source: ArchitectureState, candidate: CatalogCandidate
) -> CandidatePrediction:
    return CandidatePrediction(
        candidate.candidate_intent_id,
        candidate.proposed_physical_state_id,
        {
            field: candidate.actual_resources[field] - source.resources[field]
            for field in RESOURCE_FIELDS
        },
        TaggedScientificValue.not_evaluated(
            quantity="candidate_energy",
            unit="hartree",
            reason="outcome_blind_structural_prediction",
        ),
    )

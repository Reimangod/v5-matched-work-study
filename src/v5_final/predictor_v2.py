"""Outcome-blind quadratic predictor with explicit validity diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping


class PredictorV2Error(ValueError):
    pass


FORBIDDEN_OUTCOME_KEYS = frozenset(
    {
        "actual_energy",
        "actual_energy_hartree",
        "candidate_energy",
        "fci_energy",
        "accepted",
        "winner",
    }
)


@dataclass(frozen=True)
class PredictorInput:
    candidate_intent_id: str
    proposed_physical_state_id: str
    displacement_decimal: str
    directional_gradient_decimal: str
    directional_curvature_decimal: str
    condition_number_decimal: str
    secant_residual_decimal: str
    direction_coverage_decimal: str
    hessian_age_commits: int
    predicted_resource_delta: Mapping[str, int]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "PredictorInput":
        forbidden = FORBIDDEN_OUTCOME_KEYS & set(value)
        if forbidden:
            raise PredictorV2Error(
                "predictor input contains outcome fields: " + ", ".join(sorted(forbidden))
            )
        try:
            return cls(**dict(value))
        except TypeError as error:
            raise PredictorV2Error("predictor input schema mismatch") from error

    def decimals(self) -> tuple[Decimal, ...]:
        try:
            values = tuple(
                Decimal(value)
                for value in (
                    self.displacement_decimal,
                    self.directional_gradient_decimal,
                    self.directional_curvature_decimal,
                    self.condition_number_decimal,
                    self.secant_residual_decimal,
                    self.direction_coverage_decimal,
                )
            )
        except InvalidOperation as error:
            raise PredictorV2Error("predictor scalars must be decimal text") from error
        if not all(value.is_finite() for value in values):
            raise PredictorV2Error("predictor scalars must be finite")
        return values


@dataclass(frozen=True)
class PredictorResult:
    candidate_intent_id: str
    proposed_physical_state_id: str
    status: str
    predicted_energy_change_hartree: str | None
    uncertainty_hartree: None
    predicted_resource_delta: Mapping[str, int]
    diagnostics: Mapping[str, Any]


def predict_quadratic(value: PredictorInput) -> PredictorResult:
    displacement, gradient, curvature, condition, residual, coverage = value.decimals()
    valid = (
        curvature > 0
        and condition > 0
        and condition <= Decimal("1e8")
        and residual >= 0
        and residual <= Decimal("0.25")
        and coverage >= Decimal("0.5")
        and coverage <= 1
        and 0 <= value.hessian_age_commits <= 1
    )
    prediction = gradient * displacement + Decimal("0.5") * curvature * displacement**2
    return PredictorResult(
        candidate_intent_id=value.candidate_intent_id,
        proposed_physical_state_id=value.proposed_physical_state_id,
        status="VALID_POINT_PREDICTION" if valid else "INVALID_DIAGNOSTICS",
        predicted_energy_change_hartree=str(prediction) if valid else None,
        uncertainty_hartree=None,
        predicted_resource_delta=dict(value.predicted_resource_delta),
        diagnostics={
            "nonzero_gradient_model": gradient != 0,
            "condition_number": str(condition),
            "secant_residual": str(residual),
            "direction_coverage": str(coverage),
            "hessian_age_commits": value.hessian_age_commits,
            "stale_hessian": value.hessian_age_commits > 1,
            "uncertainty_calibrated": False,
        },
    )

"""Independent energy/gradient/resource certification without FCI access."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Mapping

from .architecture_state import ArchitectureState, RESOURCE_FIELDS


class CertificationError(ValueError):
    pass


@dataclass(frozen=True)
class CertificationResult:
    accepted: bool
    reason: str
    energy_hartree: str
    gradient_infinity: str
    resources: Mapping[str, int]


def certify_candidate(
    source: ArchitectureState,
    *,
    energy_hartree: str,
    gradient_infinity: str,
    resources: Mapping[str, int],
    energy_budget_hartree: str,
    stationarity_threshold: str,
) -> CertificationResult:
    try:
        energy = Decimal(energy_hartree)
        gradient = Decimal(gradient_infinity)
        source_energy = Decimal(source.energy_hartree)
        budget = Decimal(energy_budget_hartree)
        threshold = Decimal(stationarity_threshold)
    except InvalidOperation as error:
        raise CertificationError("certification scalars must be decimal text") from error
    if not all(value.is_finite() for value in (energy, gradient, source_energy, budget, threshold)):
        raise CertificationError("certification scalars must be finite")
    if gradient < 0 or budget < 0 or threshold < 0:
        raise CertificationError("gradient, budget, and threshold must be nonnegative")
    if any(
        field not in resources
        or isinstance(resources[field], bool)
        or not isinstance(resources[field], int)
        or resources[field] < 0
        for field in RESOURCE_FIELDS
    ):
        raise CertificationError("certification resources are invalid")
    if energy - source_energy > budget:
        return CertificationResult(False, "ENERGY_BUDGET_EXCEEDED", energy_hartree, gradient_infinity, resources)
    if gradient > threshold:
        return CertificationResult(False, "STATIONARITY_THRESHOLD_EXCEEDED", energy_hartree, gradient_infinity, resources)
    return CertificationResult(True, "CERTIFIED", energy_hartree, gradient_infinity, resources)

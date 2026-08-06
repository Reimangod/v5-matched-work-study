"""Strict independent certification evidence contract with no FCI dependency."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Mapping

from .architecture_state import RESOURCE_FIELDS


class CertificationV2Error(ValueError):
    pass


@dataclass(frozen=True)
class IndependentCertificationEvidence:
    source_energy_hartree: str
    optimizer_energy_hartree: str
    independent_energy_hartree: str
    gradient_path_a_infinity: str
    gradient_path_b_infinity: str
    constraint_residual: str
    resources: Mapping[str, int]
    statevector_recomputed: bool
    transformation_semantics_verified: bool
    resource_recount_verified: bool
    work_ledger_closed: bool
    raw_ledger_release_reconciled: bool
    atomic_transaction_ready: bool


@dataclass(frozen=True)
class CertificationDecisionV2:
    accepted: bool
    failed_checks: tuple[str, ...]


def certify_independently(
    evidence: IndependentCertificationEvidence,
    *,
    energy_budget_hartree: str,
    stationarity_threshold: str,
    energy_agreement_tolerance: str,
    gradient_agreement_tolerance: str,
    constraint_tolerance: str,
) -> CertificationDecisionV2:
    try:
        source = Decimal(evidence.source_energy_hartree)
        optimizer = Decimal(evidence.optimizer_energy_hartree)
        independent = Decimal(evidence.independent_energy_hartree)
        gradient_a = Decimal(evidence.gradient_path_a_infinity)
        gradient_b = Decimal(evidence.gradient_path_b_infinity)
        constraint = Decimal(evidence.constraint_residual)
        budget = Decimal(energy_budget_hartree)
        stationarity = Decimal(stationarity_threshold)
        energy_agreement = Decimal(energy_agreement_tolerance)
        gradient_agreement = Decimal(gradient_agreement_tolerance)
        constraint_limit = Decimal(constraint_tolerance)
    except InvalidOperation as error:
        raise CertificationV2Error("certification values must be decimal text") from error
    scalars = (
        source,
        optimizer,
        independent,
        gradient_a,
        gradient_b,
        constraint,
        budget,
        stationarity,
        energy_agreement,
        gradient_agreement,
        constraint_limit,
    )
    if not all(value.is_finite() for value in scalars):
        raise CertificationV2Error("certification values must be finite")
    checks = {
        "energy_budget": independent - source <= budget,
        "independent_energy_agreement": abs(independent - optimizer) <= energy_agreement,
        "gradient_path_a_stationary": abs(gradient_a) <= stationarity,
        "gradient_path_b_stationary": abs(gradient_b) <= stationarity,
        "two_path_gradient_agreement": abs(gradient_a - gradient_b)
        <= gradient_agreement,
        "constraint_residual": abs(constraint) <= constraint_limit,
        "resources_complete": all(
            field in evidence.resources
            and isinstance(evidence.resources[field], int)
            and not isinstance(evidence.resources[field], bool)
            and evidence.resources[field] >= 0
            for field in RESOURCE_FIELDS
        ),
        "statevector_recomputed": evidence.statevector_recomputed,
        "transformation_semantics_verified": evidence.transformation_semantics_verified,
        "resource_recount_verified": evidence.resource_recount_verified,
        "work_ledger_closed": evidence.work_ledger_closed,
        "raw_ledger_release_reconciled": evidence.raw_ledger_release_reconciled,
        "atomic_transaction_ready": evidence.atomic_transaction_ready,
    }
    failed = tuple(name for name, passed in checks.items() if not passed)
    return CertificationDecisionV2(not failed, failed)

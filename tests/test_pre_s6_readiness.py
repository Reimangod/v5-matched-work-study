from __future__ import annotations
from v5_matched_work.pre_s6_readiness import DEPENDENT_STAGES,build,not_authorized


def test_pre_s6_fails_before_outcomes_and_closes_dependents()->None:
    incident=build();assert incident["candidate_energy_evaluations"]==0;assert incident["failed_checks"];assert incident["decision"].startswith("NO_GO")
    assert all(not_authorized(stage,incident)["status"]=="NOT_AUTHORIZED" for stage in DEPENDENT_STAGES)

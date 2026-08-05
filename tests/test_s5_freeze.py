from __future__ import annotations
from v5_matched_work.s5_freeze import audit,build


def test_s5_queue_and_outcome_firewall()->None:
    value=build();assert all(audit(value).values());assert value["candidate_energy_evaluations_at_s5"]==0;assert len(value["queue"])==90

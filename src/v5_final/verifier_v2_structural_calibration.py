"""Calibration-only structural preparation for frozen Verifier V2 candidates.

This wrapper intentionally stops before resource ranking and numeric probes.
It exists for the all-catalog H6 preparation audit; production execution must
use the frozen :class:`v5_final.verifier_v2.VerifierV2` pipeline instead.
"""

from __future__ import annotations

from typing import Any, Sequence

from .verifier_v2 import (
    CandidateV2,
    VerifierV2,
    VerifierV2Error,
    _digest,
    _empty_counts,
    _merge_counts,
)


def prepare_structural_only(
    verifier: VerifierV2, candidates: Sequence[CandidateV2]
) -> dict[str, Any]:
    ordered = tuple(sorted(candidates, key=lambda value: value.candidate_id))
    binding = verifier._binding(ordered)
    verifier._ensure_binding(binding)
    counts = _empty_counts()
    _merge_counts(counts, verifier.initial_counts)
    counts["candidate_generations"] = len(ordered)
    semantic_representatives: dict[str, CandidateV2] = {}
    semantic_aliases: dict[str, list[str]] = {}
    for candidate in ordered:
        certificate = verifier._structural_certificate(candidate)
        counts["N_symbolic_checks"] += 1
        cached = verifier._semantic_cache.get(candidate.semantic_id)
        if cached is not None and cached != certificate:
            raise VerifierV2Error("semantic ID aliases incompatible certificates")
        verifier._semantic_cache[candidate.semantic_id] = certificate
        verifier._cache_semantic_certificate(certificate)
        semantic_aliases.setdefault(candidate.semantic_id, []).append(
            candidate.candidate_id
        )
        semantic_representatives.setdefault(candidate.semantic_id, candidate)
    counts["unique_semantic_candidates"] = len(semantic_representatives)
    physical_representatives: dict[str, CandidateV2] = {}
    physical_aliases: dict[str, list[str]] = {}
    for candidate in semantic_representatives.values():
        physical_aliases.setdefault(
            candidate.proposed_state_preparation_id, []
        ).append(candidate.candidate_id)
        physical_representatives.setdefault(
            candidate.proposed_state_preparation_id, candidate
        )
    counts["unique_physical_states"] = len(physical_representatives)
    core = {
        "schema": "v5-final.verifier-v2-structural-calibration-core.v1",
        "status": "STRUCTURAL_PREPARATION_COMPLETE_OUTCOME_FREE",
        "session_binding": binding,
        "semantic_aliases": {
            key: sorted(value) for key, value in sorted(semantic_aliases.items())
        },
        "physical_aliases": {
            key: sorted(value) for key, value in sorted(physical_aliases.items())
        },
        "physical_representative_candidate_ids": sorted(
            candidate.candidate_id for candidate in physical_representatives.values()
        ),
        "deterministic_work_counters": counts,
        "ranking_performed": False,
        "numeric_verification_performed": False,
        "authorization": {
            "outcome_blind_calibration_subset_freeze": "AUTHORIZED",
            "production_ranking": "NOT_AUTHORIZED",
            "optimizer": "NOT_AUTHORIZED",
            "candidate_energy": "NOT_AUTHORIZED",
            "FCI_reporting": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
    }
    core["core_digest"] = _digest(core)
    return core

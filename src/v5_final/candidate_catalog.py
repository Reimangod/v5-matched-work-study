"""Actual-circuit candidate catalog and physical-state deduplication."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Iterable, Mapping

from v5_matched_work.atomic_artifacts import canonical_json_bytes

from .identities import CandidateIntent, ProposedPhysicalState


class CandidateCatalogError(ValueError):
    pass


@dataclass(frozen=True)
class CatalogCandidate:
    intent: CandidateIntent
    physical_state: ProposedPhysicalState
    initial_coefficient_bytes: tuple[str, ...]
    actual_circuit_digest: str
    actual_resources: Mapping[str, int]

    @property
    def candidate_intent_id(self) -> str:
        return self.intent.candidate_intent_id

    @property
    def proposed_physical_state_id(self) -> str:
        return self.physical_state.proposed_physical_state_id

    def payload(self) -> dict[str, Any]:
        return {
            "candidate_intent_id": self.candidate_intent_id,
            "proposed_physical_state_id": self.proposed_physical_state_id,
            "initial_coefficient_bytes": list(self.initial_coefficient_bytes),
            "actual_circuit_digest": self.actual_circuit_digest,
            "actual_resources": dict(sorted(self.actual_resources.items())),
        }

    @property
    def candidate_digest(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.payload())).hexdigest()


@dataclass(frozen=True)
class CandidateAliasGroup:
    proposed_physical_state_id: str
    canonical_candidate: CatalogCandidate
    aliases: tuple[CatalogCandidate, ...]


@dataclass(frozen=True)
class CandidateCatalog:
    source_digest: str
    candidates: tuple[CatalogCandidate, ...]
    alias_groups: tuple[CandidateAliasGroup, ...]

    @classmethod
    def build(
        cls, source_digest: str, candidates: Iterable[CatalogCandidate]
    ) -> "CandidateCatalog":
        materialized = tuple(candidates)
        if len(source_digest) != 64 or not materialized:
            raise CandidateCatalogError("catalog requires a source digest and candidates")
        intent_ids = [candidate.candidate_intent_id for candidate in materialized]
        if len(intent_ids) != len(set(intent_ids)):
            raise CandidateCatalogError("CandidateIntentIDs must be unique")
        grouped: dict[str, list[CatalogCandidate]] = {}
        for candidate in materialized:
            grouped.setdefault(candidate.proposed_physical_state_id, []).append(candidate)
        groups = tuple(
            CandidateAliasGroup(
                state_id,
                sorted(values, key=lambda value: value.candidate_intent_id)[0],
                tuple(sorted(values, key=lambda value: value.candidate_intent_id)),
            )
            for state_id, values in sorted(grouped.items())
        )
        return cls(
            source_digest,
            tuple(sorted(materialized, key=lambda value: value.candidate_intent_id)),
            groups,
        )

    @property
    def unique_physical_state_count(self) -> int:
        return len(self.alias_groups)

    @property
    def catalog_digest(self) -> str:
        payload = {
            "source_digest": self.source_digest,
            "candidates": [candidate.payload() for candidate in self.candidates],
            "alias_groups": [
                {
                    "proposed_physical_state_id": group.proposed_physical_state_id,
                    "candidate_intent_ids": [
                        alias.candidate_intent_id for alias in group.aliases
                    ],
                }
                for group in self.alias_groups
            ],
        }
        return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()

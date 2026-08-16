"""Canonical proposed-physical-state identity independent of candidate intent."""

from __future__ import annotations

import hashlib
from typing import Any

from v5_matched_work.atomic_artifacts import canonical_json_bytes


def canonical_proposed_physical_state_id(
    *, problem_id: str, state_preparation_spec: Any
) -> str:
    """Identify the proposed state, not the path that proposed it.

    Candidate intent, equivalence-class, and constraint IDs are deliberately
    excluded.  Aliases that materialize the same canonical parent state thus
    share one search-state identity while retaining every generation event.
    """

    if not problem_id.startswith("problem-v1:"):
        raise ValueError("canonical ProblemID required")
    payload = {
        "schema": "v5-final.parent-native-proposed-physical-state.v3",
        "ProblemID": problem_id,
        "canonical_parent_state_preparation": state_preparation_spec.payload(),
    }
    return "physical-state-v3:" + hashlib.sha256(
        canonical_json_bytes(payload)
    ).hexdigest()

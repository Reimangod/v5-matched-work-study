from __future__ import annotations

from v5_final.mb1_parent_semantics import audit


def test_mb1_parent_semantics_are_hash_bound_and_outcome_free() -> None:
    assert all(audit().values())

"""Immutable-source comparator contracts for matched-work execution."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Callable, Iterable

from .atomic_artifacts import canonical_json_bytes


PRIMARY_METHODS = (
    "immutable-ceo-star-source",
    "same-structure-reoptimization",
    "structural-magnitude-pruning",
    "v4.1-one-shot-joint-compression",
    "v5-sequential-without-rebuilding",
    "v5-sequential-with-rebuilding",
)


class ComparatorError(RuntimeError):
    pass


@dataclass(frozen=True)
class ImmutableSource:
    state_preparation_id: str
    problem_id: str
    coefficients: tuple[float, ...]
    ansatz_indices: tuple[int, ...]
    structure_digest: str

    def __post_init__(self) -> None:
        if not self.state_preparation_id.startswith("state-v1:") or not self.problem_id.startswith("problem-v1:"):
            raise ComparatorError("source identities are invalid")
        if len(self.coefficients) != len(self.ansatz_indices):
            raise ComparatorError("source coordinates and indices differ in length")
        observed = hashlib.sha256(canonical_json_bytes({"coefficients": self.coefficients, "indices": self.ansatz_indices})).hexdigest()
        if observed != self.structure_digest:
            raise ComparatorError("source digest does not bind coordinates and indices")


@dataclass(frozen=True)
class StructuralCandidate:
    candidate_id: str
    removed_positions: tuple[int, ...]
    physically_removed_generator_indices: tuple[int, ...]

    def __post_init__(self) -> None:
        if not self.candidate_id or not self.removed_positions or not self.physically_removed_generator_indices:
            raise ComparatorError("structural pruning cannot be coefficient-only")
        if len(self.removed_positions) != len(self.physically_removed_generator_indices):
            raise ComparatorError("removed coordinates must bind removed generators")


@dataclass(frozen=True)
class CatalogSnapshot:
    parent_state_id: str
    candidate_ids: tuple[str, ...]


def catalog_sequence(
    source: CatalogSnapshot,
    accepted_child_ids: Iterable[str],
    *,
    rebuild: bool,
    builder: Callable[[str], CatalogSnapshot],
) -> tuple[CatalogSnapshot, ...]:
    """Return per-round catalogs; only full V5 rebuilds after acceptance."""

    snapshots = [source]
    for child_id in accepted_child_ids:
        snapshots.append(builder(child_id) if rebuild else source)
    return tuple(snapshots)


def comparator_registry() -> list[dict[str, object]]:
    return [
        {"method_id": PRIMARY_METHODS[0], "rounds": 0, "catalog_policy": "not-applicable", "physical_recount": True},
        {"method_id": PRIMARY_METHODS[1], "rounds": 0, "catalog_policy": "same-structure", "physical_recount": True},
        {"method_id": PRIMARY_METHODS[2], "rounds": 1, "catalog_policy": "original-structural-magnitude", "physical_recount": True, "coefficient_only_zeroing_forbidden": True},
        {"method_id": PRIMARY_METHODS[3], "rounds": 1, "catalog_policy": "original-one-shot", "physical_recount": True},
        {"method_id": PRIMARY_METHODS[4], "rounds": "sequential", "catalog_policy": "original-snapshot-after-every-accepted-child", "physical_recount": True},
        {"method_id": PRIMARY_METHODS[5], "rounds": "sequential", "catalog_policy": "rebuild-from-every-accepted-child", "physical_recount": True},
    ]

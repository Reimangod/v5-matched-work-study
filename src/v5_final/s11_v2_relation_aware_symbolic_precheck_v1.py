"""Outcome-free symbolic-check bounds derived from registered relation arity.

The frozen queue-v2 cap remains immutable.  This module only replaces the
unsafe execution-time assumption that every selected relation costs five
symbolic checks.  It mirrors the registered Verifier V2 operations without
loading a generator, expanding a state, evaluating an energy, or starting an
optimizer.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from numbers import Real
from typing import Any, Iterable, Mapping, Sequence


class RelationAwareSymbolicPrecheckError(RuntimeError):
    pass


# This is the complete relation catalog frozen by the five queue-v2 source
# cases.  New kinds or arities are not guessed: they require an additive audit.
REGISTERED_RELATION_ARITIES: Mapping[str, frozenset[tuple[int, int]]] = {
    "block-deletion": frozenset({(1, 0)}),
    "mvp-whole-deletion": frozenset({(2, 0), (3, 0)}),
    "mvp-constituent-deletion": frozenset({(2, 1), (3, 2)}),
    "mvp-to-ovp-diff": frozenset({(2, 1), (3, 1)}),
    "mvp-to-ovp-sum": frozenset({(2, 1), (3, 1)}),
    "mvp-to-single-qe": frozenset({(2, 1), (3, 1)}),
}

MAX_COUNTER = (1 << 63) - 1


@dataclass(frozen=True)
class RelationSymbolicCostV1:
    candidate_id: str
    relation_kind: str
    source_arity: int
    target_arity: int
    deletion_shortcut: bool
    symbolic_check_cost: int
    sparse_expm_per_probe: int
    state_probe_vectors_per_probe: int
    generator_materialization_upper_bound: int
    circuit_operator_builds_per_probe: int
    rewrite_verifications: int


def _checked_nonnegative_int(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise RelationAwareSymbolicPrecheckError(f"invalid {field}")
    if value > MAX_COUNTER:
        raise RelationAwareSymbolicPrecheckError(f"overflowing {field}")
    return value


def symbolic_check_cost_from_arity(
    *, source_arity: int, target_arity: int, deletion_shortcut: bool
) -> int:
    """Return the exact registered Verifier V2 numeric symbolic-check cost."""

    source = _checked_nonnegative_int(source_arity, field="source arity")
    target = _checked_nonnegative_int(target_arity, field="target arity")
    if not isinstance(deletion_shortcut, bool):
        raise RelationAwareSymbolicPrecheckError("invalid deletion shortcut")
    if source == 0:
        raise RelationAwareSymbolicPrecheckError("relation source arity is zero")
    if deletion_shortcut:
        if target != 0:
            raise RelationAwareSymbolicPrecheckError(
                "deletion shortcut has target generators"
            )
        return 0
    if target == 0:
        raise RelationAwareSymbolicPrecheckError(
            "non-deletion relation has no target generator"
        )
    # Verifier V2 checks every source/target generator for anti-Hermiticity,
    # every unordered source pair for commutation, and reconstructs each target.
    source_pairs = source * (source - 1) // 2
    cost = source + target + source_pairs + target
    if cost > MAX_COUNTER:
        raise RelationAwareSymbolicPrecheckError("symbolic check cost overflow")
    return cost


def _normalized_jacobian(value: Any) -> tuple[tuple[float, ...], ...]:
    try:
        rows = tuple(tuple(row) for row in value)
    except (TypeError, ValueError) as error:
        raise RelationAwareSymbolicPrecheckError(
            "relation Jacobian is invalid"
        ) from error
    normalized: list[tuple[float, ...]] = []
    for row in rows:
        converted: list[float] = []
        for entry in row:
            if isinstance(entry, bool) or not isinstance(entry, Real):
                raise RelationAwareSymbolicPrecheckError(
                    "relation Jacobian contains a non-real value"
                )
            number = float(entry)
            if not math.isfinite(number):
                raise RelationAwareSymbolicPrecheckError(
                    "relation Jacobian contains a non-finite value"
                )
            converted.append(number)
        normalized.append(tuple(converted))
    return tuple(normalized)


def _relation_jacobian(candidate: Any) -> tuple[tuple[float, ...], ...]:
    missing = object()
    direct = getattr(candidate, "jacobian", missing)
    transformation = getattr(candidate, "transformation", missing)
    nested = (
        missing
        if transformation is missing
        else getattr(transformation, "jacobian", missing)
    )
    if direct is missing and nested is missing:
        raise RelationAwareSymbolicPrecheckError(
            "relation metadata is incomplete"
        )
    direct_value = None if direct is missing else _normalized_jacobian(direct)
    nested_value = None if nested is missing else _normalized_jacobian(nested)
    if (
        direct_value is not None
        and nested_value is not None
        and direct_value != nested_value
    ):
        raise RelationAwareSymbolicPrecheckError(
            "direct and nested relation Jacobians differ"
        )
    if direct_value is not None:
        return direct_value
    if nested_value is None:
        raise RelationAwareSymbolicPrecheckError(
            "relation metadata is incomplete"
        )
    return nested_value


def relation_symbolic_cost(candidate: Any) -> RelationSymbolicCostV1:
    """Validate one parent-native relation and derive its outcome-free cost."""

    try:
        candidate_id = candidate.candidate_id
        kind = candidate.kind
        source_indices = tuple(candidate.source_pool_indices)
        target_indices = tuple(candidate.target_pool_indices)
    except (AttributeError, TypeError) as error:
        raise RelationAwareSymbolicPrecheckError(
            "relation metadata is incomplete"
        ) from error
    jacobian = _relation_jacobian(candidate)
    if not isinstance(candidate_id, str) or not candidate_id:
        raise RelationAwareSymbolicPrecheckError("candidate ID is invalid")
    if not isinstance(kind, str) or kind not in REGISTERED_RELATION_ARITIES:
        raise RelationAwareSymbolicPrecheckError("unknown relation kind")
    source = len(source_indices)
    target = len(target_indices)
    if (source, target) not in REGISTERED_RELATION_ARITIES[kind]:
        raise RelationAwareSymbolicPrecheckError(
            f"unregistered relation arity for {kind}: ({source}, {target})"
        )
    if len(jacobian) != source or any(len(row) != target for row in jacobian):
        raise RelationAwareSymbolicPrecheckError(
            "relation Jacobian dimensions differ from arity"
        )
    transformation = getattr(candidate, "transformation", None)
    if transformation is not None:
        try:
            source_slots = tuple(transformation.source_slots)
            target_slots = tuple(transformation.target_slots)
        except (AttributeError, TypeError) as error:
            raise RelationAwareSymbolicPrecheckError(
                "nested relation slot metadata is incomplete"
            ) from error
        if len(source_slots) != source or len(target_slots) != target:
            raise RelationAwareSymbolicPrecheckError(
                "nested relation slot dimensions differ from arity"
            )
    deletion = target == 0
    numeric_arity = 0 if deletion else source + target
    return RelationSymbolicCostV1(
        candidate_id=candidate_id,
        relation_kind=kind,
        source_arity=source,
        target_arity=target,
        deletion_shortcut=deletion,
        symbolic_check_cost=symbolic_check_cost_from_arity(
            source_arity=source,
            target_arity=target,
            deletion_shortcut=deletion,
        ),
        sparse_expm_per_probe=numeric_arity,
        state_probe_vectors_per_probe=0 if deletion else 1,
        generator_materialization_upper_bound=numeric_arity,
        circuit_operator_builds_per_probe=0 if deletion else 1,
        rewrite_verifications=1,
    )


def selected_relation_costs(
    *, catalog: Any, selected_candidate_ids: Sequence[str]
) -> tuple[RelationSymbolicCostV1, ...]:
    """Resolve an already semantic/physical-deduplicated selected relation set."""

    selected = tuple(selected_candidate_ids)
    if not selected or any(
        not isinstance(value, str) or not value for value in selected
    ):
        raise RelationAwareSymbolicPrecheckError("selected relation set is invalid")
    if len(set(selected)) != len(selected):
        raise RelationAwareSymbolicPrecheckError(
            "selected relation set contains duplicate candidate IDs"
        )
    try:
        candidates = tuple(catalog.candidates)
    except (AttributeError, TypeError) as error:
        raise RelationAwareSymbolicPrecheckError(
            "candidate catalog is invalid"
        ) from error
    by_id: dict[str, Any] = {}
    for candidate in candidates:
        candidate_id = getattr(candidate, "candidate_id", None)
        if not isinstance(candidate_id, str) or candidate_id in by_id:
            raise RelationAwareSymbolicPrecheckError(
                "candidate catalog IDs are invalid or duplicated"
            )
        by_id[candidate_id] = candidate
    if any(candidate_id not in by_id for candidate_id in selected):
        raise RelationAwareSymbolicPrecheckError(
            "selected relation is absent from the catalog"
        )
    return tuple(
        relation_symbolic_cost(by_id[candidate_id]) for candidate_id in selected
    )


def relation_aware_symbolic_upper_bound(
    *, candidate_count: int, selected_costs: Iterable[int]
) -> int:
    """Add one structural certificate per candidate and exact selected costs."""

    total = _checked_nonnegative_int(candidate_count, field="candidate count")
    costs = tuple(selected_costs)
    for value in costs:
        cost = _checked_nonnegative_int(value, field="selected relation cost")
        if total > MAX_COUNTER - cost:
            raise RelationAwareSymbolicPrecheckError("symbolic upper bound overflow")
        total += cost
    return total

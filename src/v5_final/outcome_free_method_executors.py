"""Six concrete outcome-free method-native structural executor entrypoints.

The entrypoints execute deterministic structural semantics against synthetic,
non-molecular fixtures.  They contain no Hamiltonian, energy, optimizer, or
production-queue kernel and fail closed if an outcome-bearing field is supplied.
"""

from __future__ import annotations

from fractions import Fraction
import hashlib
import json
from typing import Any, Callable, Mapping, Sequence

from v5_matched_work.atomic_artifacts import canonical_json_bytes

from .mb4_2_owner_protocol_freeze import (
    CANONICAL_METHOD_IDS,
    LEGACY_QUEUE_METHOD_IDS,
    OUTPUT as OWNER_FREEZE_OUTPUT,
)


class OutcomeFreeExecutorError(ValueError):
    pass


EXECUTION_MODE = "OUTCOME_FREE_SYNTHETIC_STRUCTURAL_VALIDATION"
FORBIDDEN_OUTCOME_KEYS = {
    "candidate_energy",
    "energy",
    "energies",
    "hamiltonian",
    "molecule",
    "molecular_geometry",
    "fci",
    "exact_reference",
    "development_result",
    "historical_rank",
    "performance",
    "optimizer_outcome",
}
RESOURCE_COMPONENTS = ("cnot_count", "cnot_depth", "total_depth", "parameter_count")


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _require_digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise OutcomeFreeExecutorError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _walk_forbidden(value: Any, path: str = "request") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).lower()
            outcome_token = any(
                token in normalized
                for token in (
                    "energy",
                    "hamiltonian",
                    "molecule",
                    "molecular",
                    "fci",
                    "performance",
                    "outcome",
                    "development_result",
                    "historical_rank",
                )
            )
            if normalized != "candidate_energy_evaluations" and (
                normalized in FORBIDDEN_OUTCOME_KEYS or outcome_token
            ):
                raise OutcomeFreeExecutorError(f"outcome-bearing field is forbidden: {path}.{key}")
            _walk_forbidden(child, f"{path}.{key}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, child in enumerate(value):
            _walk_forbidden(child, f"{path}[{index}]")


def _validate_request(
    request: Mapping[str, Any],
    *,
    canonical_method_id: str,
) -> dict[str, Any]:
    value = dict(request)
    _walk_forbidden(value)
    if canonical_method_id not in CANONICAL_METHOD_IDS:
        raise OutcomeFreeExecutorError("canonical method ID is not frozen")
    if value.get("execution_mode") != EXECUTION_MODE:
        raise OutcomeFreeExecutorError("only outcome-free synthetic execution mode is accepted")
    if value.get("canonical_method_id") != canonical_method_id:
        raise OutcomeFreeExecutorError("request was routed to the wrong outcome-free executor")
    _require_digest(value.get("protocol_digest"), "protocol")
    _require_digest(value.get("protocol_freeze_digest"), "protocol freeze")
    freeze = json.loads(OWNER_FREEZE_OUTPUT.read_text())
    if value["protocol_freeze_digest"] != freeze["freeze_digest"]:
        raise OutcomeFreeExecutorError("request does not bind the committed owner freeze")
    if value["protocol_digest"] != freeze["protocol_digests"][canonical_method_id]:
        raise OutcomeFreeExecutorError("request protocol digest differs from the owner freeze")
    if value.get("synthetic_fixture") is not True:
        raise OutcomeFreeExecutorError("a declared synthetic fixture is required")
    for field in (
        "kernel_calls_authorized",
        "development_queue_bound",
        "H2_H4_queue_bound",
        "production_execution_authorized",
    ):
        if value.get(field) is not False:
            raise OutcomeFreeExecutorError(f"{field} must be false")
    if value.get("candidate_energy_evaluations") != 0:
        raise OutcomeFreeExecutorError("candidate energy count must remain zero")
    generators = value.get("source_generators")
    if (
        not isinstance(generators, list)
        or not generators
        or len(generators) != len(set(generators))
        or any(not isinstance(item, str) or not item for item in generators)
    ):
        raise OutcomeFreeExecutorError("source generators must be nonempty and unique")
    catalog = value.get("current_catalog")
    if not isinstance(catalog, list):
        raise OutcomeFreeExecutorError("current structural catalog is required")
    candidate_ids = [item.get("structural_candidate_id") for item in catalog]
    if len(candidate_ids) != len(set(candidate_ids)) or any(
        not isinstance(item, str) or not item for item in candidate_ids
    ):
        raise OutcomeFreeExecutorError("structural candidate IDs must be unique")
    canonical_json_bytes(value)
    return value


def _rank_key(candidate: Mapping[str, Any]) -> tuple[Fraction, str]:
    numerator = candidate.get("rank_numerator")
    denominator = candidate.get("rank_denominator")
    if not isinstance(numerator, int) or not isinstance(denominator, int) or denominator <= 0:
        raise OutcomeFreeExecutorError("structural rank must be an integer rational")
    return Fraction(numerator, denominator), candidate["structural_candidate_id"]


def _structurally_eligible(candidate: Mapping[str, Any]) -> bool:
    return candidate.get("available") is True and candidate.get("structurally_eligible") is True


def _rank_current_catalog(
    candidates: Sequence[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    return sorted(candidates, key=_rank_key)


def _recount_resources(
    generators: Sequence[str], resource_model: Mapping[str, Any]
) -> dict[str, int]:
    base = resource_model.get("base")
    contributions = resource_model.get("generator_contributions")
    if not isinstance(base, Mapping) or not isinstance(contributions, Mapping):
        raise OutcomeFreeExecutorError("synthetic structural resource model is incomplete")
    result: dict[str, int] = {}
    for component in RESOURCE_COMPONENTS:
        base_value = base.get(component)
        if not isinstance(base_value, int) or base_value < 0:
            raise OutcomeFreeExecutorError("resource base must contain nonnegative integers")
        total = base_value
        for generator in generators:
            record = contributions.get(generator)
            if not isinstance(record, Mapping):
                raise OutcomeFreeExecutorError("every generator needs a resource contribution")
            contribution = record.get(component)
            if not isinstance(contribution, int) or contribution < 0:
                raise OutcomeFreeExecutorError("resource contribution must be nonnegative")
            total += contribution
        result[component] = total
    return result


def _result(
    request: Mapping[str, Any],
    *,
    canonical_method_id: str,
    entrypoint: str,
    actions: list[dict[str, Any]],
    child_generators: list[str] | None,
    selected_candidate_ids: list[str] | None = None,
    stale_candidate_ids: list[str] | None = None,
    resource_recount: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    result = {
        "schema": "v5-final.outcome-free-method-native-result.v1",
        "execution_mode": EXECUTION_MODE,
        "status": "OUTCOME_FREE_STRUCTURAL_VALIDATION_COMPLETE",
        "canonical_method_id": canonical_method_id,
        "legacy_queue_method_id": LEGACY_QUEUE_METHOD_IDS[canonical_method_id],
        "entrypoint": entrypoint,
        "protocol_digest": request["protocol_digest"],
        "synthetic_fixture_id": request["synthetic_fixture_id"],
        "parent_generators": list(request["source_generators"]),
        "child_generators": child_generators,
        "selected_candidate_ids": selected_candidate_ids or [],
        "stale_candidate_ids": stale_candidate_ids or [],
        "actions": actions,
        "resource_recount": dict(resource_recount or {"status": "NOT_APPLICABLE"}),
        "semantic_counters": {
            "candidate_energy_evaluations": 0,
            "molecular_kernel_calls": 0,
            "H2_H4_queue_events": 0,
            "development_queue_events": 0,
        },
        "development_queue_touched": False,
        "H2_H4_execution_touched": False,
        "production_execution_authorized": False,
        "performance_evidence": False,
        "claim_boundary": (
            "synthetic structural executor semantics only; no molecular or performance evidence"
        ),
    }
    result["result_digest"] = _digest(result)
    return result


def execute_immutable_source(request: Mapping[str, Any]) -> dict[str, Any]:
    method_id = "immutable-ceo-star-source"
    value = _validate_request(request, canonical_method_id=method_id)
    return _result(
        value,
        canonical_method_id=method_id,
        entrypoint="v5_final.outcome_free_method_executors:execute_immutable_source",
        actions=[
            {
                "operation": "RECORD_IMMUTABLE_SOURCE_STRUCTURE",
                "candidate_construction": "NOT_PERFORMED",
                "child_state": "NOT_CREATED",
            }
        ],
        child_generators=None,
    )


def execute_same_structure_reoptimization(request: Mapping[str, Any]) -> dict[str, Any]:
    method_id = "same-structure-reoptimization"
    value = _validate_request(request, canonical_method_id=method_id)
    return _result(
        value,
        canonical_method_id=method_id,
        entrypoint=(
            "v5_final.outcome_free_method_executors:execute_same_structure_reoptimization"
        ),
        actions=[
            {
                "operation": "PREPARE_SAME_STRUCTURE_REOPTIMIZATION_TRANSACTION",
                "structure_preserved": True,
                "optimizer_kernel": "NOT_CALLED_OUTCOME_FREE",
                "commit": "NOT_AUTHORIZED",
            }
        ],
        child_generators=list(value["source_generators"]),
    )


def execute_structural_magnitude_pruning(request: Mapping[str, Any]) -> dict[str, Any]:
    method_id = "structural-magnitude-pruning"
    value = _validate_request(request, canonical_method_id=method_id)
    records = value.get("magnitude_records")
    if not isinstance(records, list) or not records:
        raise OutcomeFreeExecutorError("magnitude executor requires registered synthetic scores")
    by_generator: dict[str, Mapping[str, Any]] = {}
    for record in records:
        generator = record.get("generator_id")
        if generator not in value["source_generators"] or generator in by_generator:
            raise OutcomeFreeExecutorError("magnitude record generator is invalid or duplicated")
        if record.get("direct_coordinate_verified") is not True:
            raise OutcomeFreeExecutorError("theta_i squared equivalence must be verified")
        numerator = record.get("residual_squared_numerator")
        denominator = record.get("residual_squared_denominator")
        if (
            not isinstance(numerator, int)
            or numerator < 0
            or not isinstance(denominator, int)
            or denominator <= 0
        ):
            raise OutcomeFreeExecutorError("magnitude score must be a nonnegative rational")
        by_generator[generator] = record
    if set(by_generator) != set(value["source_generators"]):
        raise OutcomeFreeExecutorError("every source generator needs a current magnitude score")
    selected = min(
        by_generator,
        key=lambda generator: (
            Fraction(
                by_generator[generator]["residual_squared_numerator"],
                by_generator[generator]["residual_squared_denominator"],
            ),
            generator,
        ),
    )
    child = [generator for generator in value["source_generators"] if generator != selected]
    before = _recount_resources(value["source_generators"], value["resource_model"])
    after = _recount_resources(child, value["resource_model"])
    reduction = {component: before[component] - after[component] for component in RESOURCE_COMPONENTS}
    return _result(
        value,
        canonical_method_id=method_id,
        entrypoint=(
            "v5_final.outcome_free_method_executors:execute_structural_magnitude_pruning"
        ),
        actions=[
            {
                "operation": "SELECT_LOWEST_SINGLE_COORDINATE_SCORE",
                "generator_id": selected,
                "batch_size": 1,
            },
            {
                "operation": "PHYSICALLY_REMOVE_GENERATOR_FROM_SYNTHETIC_STRUCTURE",
                "generator_id": selected,
                "coefficient_zeroing_only": False,
            },
            {
                "operation": "PREPARE_REOPTIMIZATION_AND_SCORE_RECOMPUTE",
                "optimizer_kernel": "NOT_CALLED_OUTCOME_FREE",
            },
        ],
        child_generators=child,
        selected_candidate_ids=[selected],
        resource_recount={
            "status": "SYNTHETIC_FULL_STRUCTURAL_RECOUNT",
            "before": before,
            "after": after,
            "reduction": reduction,
            "resource_reduction_success": any(value > 0 for value in reduction.values()),
        },
    )


def execute_v4_1_one_shot_joint_compression(request: Mapping[str, Any]) -> dict[str, Any]:
    method_id = "v4.1-one-shot-joint-compression"
    value = _validate_request(request, canonical_method_id=method_id)
    eligible = [
        candidate
        for candidate in value["current_catalog"]
        if _structurally_eligible(candidate)
    ]
    representatives: dict[str, str] = {}
    for candidate in eligible:
        equivalence_class = candidate.get("equivalence_class_id")
        if not isinstance(equivalence_class, str) or not equivalence_class:
            raise OutcomeFreeExecutorError("equivalence class identity is required")
        candidate_id = candidate["structural_candidate_id"]
        previous = representatives.get(equivalence_class)
        if previous is None or candidate_id < previous:
            representatives[equivalence_class] = candidate_id
    ordered = [representatives[key] for key in sorted(representatives)][:4]
    return _result(
        value,
        canonical_method_id=method_id,
        entrypoint=(
            "v5_final.outcome_free_method_executors:execute_v4_1_one_shot_joint_compression"
        ),
        actions=[
            {
                "operation": "SELECT_CANONICAL_EQUIVALENCE_CLASS_REPRESENTATIVES",
                "one_per_class": True,
                "maximum_count": 4,
                "predictor": "NOT_USED",
            },
            {
                "operation": "PREPARE_ONE_SHOT_JOINT_COMPRESSION",
                "kernel": "NOT_CALLED_OUTCOME_FREE",
            },
        ],
        child_generators=None,
        selected_candidate_ids=ordered,
    )


def execute_v5_fixed_source_whitelist_no_replenishment(
    request: Mapping[str, Any],
) -> dict[str, Any]:
    method_id = "v5-fixed-source-whitelist-no-replenishment"
    value = _validate_request(request, canonical_method_id=method_id)
    whitelist = value.get("source_candidate_whitelist")
    if not isinstance(whitelist, list) or not whitelist or len(whitelist) != len(set(whitelist)):
        raise OutcomeFreeExecutorError("a unique nonempty source candidate whitelist is required")
    catalog_by_id = {
        candidate["structural_candidate_id"]: candidate for candidate in value["current_catalog"]
    }
    stale = sorted(
        candidate_id
        for candidate_id in whitelist
        if candidate_id not in catalog_by_id
        or not _structurally_eligible(catalog_by_id[candidate_id])
    )
    eligible = [
        catalog_by_id[candidate_id]
        for candidate_id in whitelist
        if candidate_id in catalog_by_id and _structurally_eligible(catalog_by_id[candidate_id])
    ]
    ranked = _rank_current_catalog(eligible)
    selected = [] if not ranked else [ranked[0]["structural_candidate_id"]]
    return _result(
        value,
        canonical_method_id=method_id,
        entrypoint=(
            "v5_final.outcome_free_method_executors:"
            "execute_v5_fixed_source_whitelist_no_replenishment"
        ),
        actions=[
            {
                "operation": "BUILD_CURRENT_RUNTIME_CATALOG",
                "catalog_size": len(value["current_catalog"]),
            },
            {
                "operation": "FILTER_TO_FROZEN_SOURCE_WHITELIST",
                "source_order_frozen": False,
                "replenishment": "FORBIDDEN",
            },
            {
                "operation": "RERANK_SURVIVING_WHITELISTED_CANDIDATES",
                "ranking_context": "CURRENT_SYNTHETIC_CHILD",
            },
        ],
        child_generators=None,
        selected_candidate_ids=selected,
        stale_candidate_ids=stale,
    )


def execute_v5_sequential_with_rebuilding(request: Mapping[str, Any]) -> dict[str, Any]:
    method_id = "v5-sequential-with-rebuilding"
    value = _validate_request(request, canonical_method_id=method_id)
    ranked = _rank_current_catalog(
        [candidate for candidate in value["current_catalog"] if _structurally_eligible(candidate)]
    )
    selected = [] if not ranked else [ranked[0]["structural_candidate_id"]]
    return _result(
        value,
        canonical_method_id=method_id,
        entrypoint=(
            "v5_final.outcome_free_method_executors:execute_v5_sequential_with_rebuilding"
        ),
        actions=[
            {
                "operation": "REBUILD_CURRENT_RUNTIME_STRUCTURAL_CATALOG",
                "replenishment": "ALLOWED_FOR_STRUCTURALLY_ELIGIBLE_CANDIDATES",
            },
            {
                "operation": "RANK_CURRENT_CATALOG",
                "ranking_context": "CURRENT_SYNTHETIC_CHILD",
            },
        ],
        child_generators=None,
        selected_candidate_ids=selected,
    )


ENTRYPOINTS: dict[str, Callable[[Mapping[str, Any]], dict[str, Any]]] = {
    "immutable-ceo-star-source": execute_immutable_source,
    "same-structure-reoptimization": execute_same_structure_reoptimization,
    "structural-magnitude-pruning": execute_structural_magnitude_pruning,
    "v4.1-one-shot-joint-compression": execute_v4_1_one_shot_joint_compression,
    "v5-fixed-source-whitelist-no-replenishment": (
        execute_v5_fixed_source_whitelist_no_replenishment
    ),
    "v5-sequential-with-rebuilding": execute_v5_sequential_with_rebuilding,
}


if tuple(ENTRYPOINTS) != CANONICAL_METHOD_IDS:
    raise RuntimeError("outcome-free executor registry differs from the frozen method order")

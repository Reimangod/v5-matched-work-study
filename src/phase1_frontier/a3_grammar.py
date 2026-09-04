"""Outcome-free Phase-1 singleton/joint grammar and identity freeze."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import asdict
import hashlib
import itertools
import json
import os
from pathlib import Path
import struct
from typing import Any, Mapping, Sequence

import numpy as np

from dvg_obs_ceo.block_ir import (
    CompressionCandidate,
    DVGBlock,
    block_to_dict,
    candidate_to_dict,
    enumerate_candidates,
    operator_digest,
    recover_dvg_blocks,
)
from dvg_obs_ceo.composition import (
    JointConstraintPlan,
    compose_registered_candidates,
    pairwise_compatibility,
)
from dvg_obs_ceo.resources import AnsatzStructure
from v5_matched_work.atomic_artifacts import canonical_json_bytes

from .a2_source_lock import (
    CASES,
    ROOT,
    THREAD_POLICY,
    _context,
    _digest,
    _verify_authority,
    source_path,
)


GRAMMAR_VERSION = "phase1-complete-singleton-bounded-joint-grammar-v1"
IDENTITY_VERSION = "phase1-target-plan-initialization-identity-v1"
A3_ROOT = ROOT / "artifacts" / "phase1-v1" / "a3-grammar-identities"
A3_AUDIT = A3_ROOT / "a3-grammar-identity-audit-v1.json"
ALLOWED_AFFINE_KINDS = (
    "block-deletion",
    "mvp-whole-deletion",
    "mvp-constituent-deletion",
    "mvp-to-single-qe",
    "mvp-to-ovp-sum",
    "mvp-to-ovp-diff",
)


class A3GrammarError(RuntimeError):
    """Raised when the frozen Phase-1 grammar or identity layer is invalid."""


def _write_exclusive(path: Path, value: Mapping[str, Any]) -> None:
    payload = canonical_json_bytes(dict(value)) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    try:
        offset = 0
        while offset < len(payload):
            count = os.write(descriptor, payload[offset:])
            if count <= 0:
                raise A3GrammarError("A3 artifact write made no forward progress")
            offset += count
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _decode(value: str) -> float:
    return struct.unpack(">d", bytes.fromhex(value))[0]


def case_path(case_id: str) -> Path:
    return A3_ROOT / "cases-v5" / f"{case_id}-grammar-v5.json"


def legacy_v4_case_path(case_id: str) -> Path:
    return A3_ROOT / "cases-v4" / f"{case_id}-grammar-v4.json"


def _compact_case_storage(value: Mapping[str, Any]) -> dict[str, Any]:
    compact = dict(value)
    compact.pop("case_digest", None)
    singletons = [dict(item) for item in compact["singletons"]]
    ordinal_by_candidate = {
        item["candidate_ids"][0]: ordinal
        for ordinal, item in enumerate(singletons)
    }
    joints = []
    for item in compact["joints"]:
        ordinals = sorted(ordinal_by_candidate[value] for value in item["candidate_ids"])
        joints.append(
            {
                "StructuralTargetID": item["StructuralTargetID"],
                "CandidatePlanID": item["CandidatePlanID"],
                "singleton_ordinals": ordinals,
                "constraint_semantic_id": item["constraint_semantic_id"],
                "constraint_numerical_id": item["constraint_numerical_id"],
                "target_materialization_digest": item[
                    "target_materialization_digest"
                ],
                "target_parameter_count": item["target_parameter_count"],
                "dependency_reason": item["dependency_reason"],
            }
        )
    compact["schema"] = "phase1-frontier.a3-grammar-identities.v5"
    compact["singletons"] = singletons
    compact["joints"] = joints
    compact["grammar_contract"] = dict(compact["grammar_contract"])
    compact["grammar_contract"]["normalized_storage"] = (
        "v5 dictionary encoding: joint candidate/equivalence/source-block identity "
        "is reconstructed from two singleton_ordinals; unique joint IDs and target "
        "materialization digest remain inline"
    )
    compact["case_digest"] = _digest(compact)
    return compact


def _verified_source(case_id: str) -> dict[str, Any]:
    value = json.loads(source_path(case_id).read_text(encoding="utf-8"))
    digest = value.pop("source_digest", None)
    if digest != _digest(value) or value.get("status") != "B2_ELIGIBLE":
        raise A3GrammarError(f"A2 source is not eligible or digest-valid: {case_id}")
    value["source_digest"] = digest
    return value


def _source_structure(source: Mapping[str, Any]) -> AnsatzStructure:
    b2 = source["B2"]
    return AnsatzStructure.create(
        source["ansatz_indices"],
        [_decode(value) for value in b2["parameters_float64"]],
        source["iteration_counts"],
    )


def _representatives(
    candidates: Sequence[CompressionCandidate],
) -> tuple[tuple[CompressionCandidate, ...], dict[str, list[str]]]:
    grouped: dict[str, list[CompressionCandidate]] = defaultdict(list)
    for candidate in candidates:
        grouped[candidate.equivalence_class_id].append(candidate)
    aliases: dict[str, list[str]] = {}
    representatives: list[CompressionCandidate] = []
    for equivalence_id, group in sorted(grouped.items()):
        ordered = sorted(group, key=lambda value: value.candidate_id)
        representatives.append(ordered[0])
        aliases[equivalence_id] = [value.candidate_id for value in ordered]
    return tuple(representatives), aliases


def _target_generator_digests(pool: Any, indices: Sequence[int]) -> list[str]:
    return [operator_digest(pool.get_q_op(int(index))) for index in indices]


def structural_target_id(pool: Any, plan: JointConstraintPlan) -> str:
    payload = {
        "version": IDENTITY_VERSION,
        "target_generator_digests": _target_generator_digests(
            pool, plan.target_indices
        ),
        "target_iteration_counts": list(plan.target_iteration_counts),
        "target_selection_iterations": list(plan.target_selection_iterations),
    }
    return "structural-target-v1:" + _digest(payload)


def candidate_plan_id(
    b2_source_id: str,
    plan: JointConstraintPlan,
) -> str:
    payload = {
        "version": IDENTITY_VERSION,
        "grammar_version": GRAMMAR_VERSION,
        "B2SourceID": b2_source_id,
        "candidate_ids": sorted(plan.candidate_ids),
        "equivalence_class_ids": sorted(plan.equivalence_class_ids),
        "constraint_semantic_id": plan.state.constraint_semantic_id,
        "constraint_numerical_id": plan.state.constraint_numerical_id,
    }
    return "candidate-plan-v1:" + _digest(payload)


def _source_selection_iterations(source: AnsatzStructure) -> tuple[int, ...]:
    result: list[int] = []
    start = 0
    for iteration, stop in enumerate(source.cumulative_parameter_counts, 1):
        result.extend([iteration] * (stop - start))
        start = stop
    if len(result) != len(source.indices):
        raise A3GrammarError("source iteration boundaries are invalid")
    return tuple(result)


def _fast_disjoint_pair_record(
    pool: Any,
    source: AnsatzStructure,
    b2_source_id: str,
    blocks: Sequence[DVGBlock],
    left: CompressionCandidate,
    right: CompressionCandidate,
) -> dict[str, Any]:
    """Compose a disjoint K=2 pair without rebuilding a dense global IR.

    Each atomic map has already proved complete affine-manifold parity.  The
    source blocks are disjoint by the compatibility gate, so their direct sum
    is complete and its rank is additive.  This is the same materialized
    topology as the general composer but avoids serializing an O(n^2) global
    numerical payload for every pair.
    """

    block_by_id = {block.block_id: block for block in blocks}
    selected = sorted(
        ((block_by_id[left.source_block_id], left),
         (block_by_id[right.source_block_id], right)),
        key=lambda pair: pair[0].ansatz_positions,
    )
    occupied = {
        position
        for block, _candidate in selected
        for position in block.ansatz_positions
    }
    if len(occupied) != sum(len(block.ansatz_positions) for block, _ in selected):
        raise A3GrammarError("fast pair composer received overlapping blocks")
    by_start = {block.ansatz_positions[0]: (block, candidate) for block, candidate in selected}
    source_iterations = _source_selection_iterations(source)
    target_indices: list[int] = []
    target_iterations: list[int] = []
    consumed: set[int] = set()
    for position, source_index in enumerate(source.indices):
        if position in consumed:
            continue
        replacement = by_start.get(position)
        if replacement is None:
            target_indices.append(int(source_index))
            target_iterations.append(source_iterations[position])
            continue
        block, candidate = replacement
        consumed.update(block.ansatz_positions)
        if len(set(block.selection_iterations)) != 1:
            raise A3GrammarError("one source block spans multiple ADAPT iterations")
        target_indices.extend(int(value) for value in candidate.target_pool_indices)
        target_iterations.extend(
            [block.selection_iterations[0]] * len(candidate.target_pool_indices)
        )
    counts = tuple(
        sum(iteration <= current for iteration in target_iterations)
        for current in range(1, len(source.cumulative_parameter_counts) + 1)
    )
    if not counts or counts[-1] != len(target_indices):
        raise A3GrammarError("fast pair target boundaries are invalid")
    candidate_ids = sorted((left.candidate_id, right.candidate_id))
    equivalence_ids = sorted(
        (left.equivalence_class_id, right.equivalence_class_id)
    )
    semantic_id = "phase1-direct-sum-semantic-v1:" + _digest(
        {
            "version": GRAMMAR_VERSION,
            "B2SourceID": b2_source_id,
            "equivalence_class_ids": equivalence_ids,
            "source_block_ids": sorted((left.source_block_id, right.source_block_id)),
            "direct_sum": True,
        }
    )
    numerical_id = "phase1-direct-sum-numerical-v1:" + _digest(
        {
            "version": GRAMMAR_VERSION,
            "candidate_ids": candidate_ids,
            "atomic_constraint_numerical_ids": sorted(
                (
                    left.transformation.orientation + ":" + left.equivalence_class_id,
                    right.transformation.orientation + ":" + right.equivalence_class_id,
                )
            ),
            "target_indices": target_indices,
            "target_iteration_counts": counts,
        }
    )
    target_payload = {
        "version": IDENTITY_VERSION,
        "target_generator_digests": _target_generator_digests(pool, target_indices),
        "target_iteration_counts": list(counts),
        "target_selection_iterations": target_iterations,
    }
    structural_id = "structural-target-v1:" + _digest(target_payload)
    plan_id = "candidate-plan-v1:" + _digest(
        {
            "version": IDENTITY_VERSION,
            "grammar_version": GRAMMAR_VERSION,
            "B2SourceID": b2_source_id,
            "candidate_ids": candidate_ids,
            "equivalence_class_ids": equivalence_ids,
            "constraint_semantic_id": semantic_id,
            "constraint_numerical_id": numerical_id,
        }
    )
    removed_dimensions = sum(
        len(candidate.source_pool_indices) - len(candidate.target_pool_indices)
        for candidate in (left, right)
    )
    return {
        "StructuralTargetID": structural_id,
        "CandidatePlanID": plan_id,
        "candidate_ids": candidate_ids,
        "equivalence_class_ids": equivalence_ids,
        "source_block_ids": sorted((left.source_block_id, right.source_block_id)),
        "constraint_semantic_id": semantic_id,
        "constraint_numerical_id": numerical_id,
        "target_materialization_digest": _digest(target_payload),
        "target_parameter_count": len(target_indices),
        "affine_diagnostics": {
            "source_dimension": len(source.indices),
            "target_dimension": len(target_indices),
            "exact_rank": removed_dimensions,
            "direct_sum_of_disjoint_complete_atomic_manifolds": True,
        },
        "certificate_class": "globally-unitary-exact-affine-direct-sum",
    }


def _fast_singleton_record(
    pool: Any,
    source: AnsatzStructure,
    b2_source_id: str,
    block: DVGBlock,
    candidate: CompressionCandidate,
) -> dict[str, Any]:
    transform = candidate.transformation
    transform.validate(len(block.ansatz_positions))
    a = np.asarray(transform.constraint_matrix, dtype=np.float64)
    j = np.asarray(transform.jacobian, dtype=np.float64)
    if np.linalg.matrix_rank(a, tol=1e-12) + j.shape[1] != j.shape[0]:
        raise A3GrammarError("atomic affine map is not a complete manifold")
    source_iterations = _source_selection_iterations(source)
    target_indices: list[int] = []
    target_iterations: list[int] = []
    consumed = set(block.ansatz_positions)
    if len(set(block.selection_iterations)) != 1:
        raise A3GrammarError("one source block spans multiple ADAPT iterations")
    for position, source_index in enumerate(source.indices):
        if position == block.ansatz_positions[0]:
            target_indices.extend(int(value) for value in candidate.target_pool_indices)
            target_iterations.extend(
                [block.selection_iterations[0]] * len(candidate.target_pool_indices)
            )
        elif position in consumed:
            continue
        else:
            target_indices.append(int(source_index))
            target_iterations.append(source_iterations[position])
    counts = tuple(
        sum(iteration <= current for iteration in target_iterations)
        for current in range(1, len(source.cumulative_parameter_counts) + 1)
    )
    target_payload = {
        "version": IDENTITY_VERSION,
        "target_generator_digests": _target_generator_digests(pool, target_indices),
        "target_iteration_counts": list(counts),
        "target_selection_iterations": target_iterations,
    }
    structural_id = "structural-target-v1:" + _digest(target_payload)
    numerical_id = "phase1-atomic-numerical-v1:" + _digest(
        candidate_to_dict(candidate)
    )
    plan_id = "candidate-plan-v1:" + _digest(
        {
            "version": IDENTITY_VERSION,
            "grammar_version": GRAMMAR_VERSION,
            "B2SourceID": b2_source_id,
            "candidate_ids": [candidate.candidate_id],
            "equivalence_class_ids": [candidate.equivalence_class_id],
            "constraint_semantic_id": candidate.equivalence_class_id,
            "constraint_numerical_id": numerical_id,
        }
    )
    return {
        "StructuralTargetID": structural_id,
        "CandidatePlanID": plan_id,
        "candidate_ids": [candidate.candidate_id],
        "equivalence_class_ids": [candidate.equivalence_class_id],
        "source_block_ids": [candidate.source_block_id],
        "constraint_semantic_id": candidate.equivalence_class_id,
        "constraint_numerical_id": numerical_id,
        "target_materialization_digest": _digest(target_payload),
        "target_parameter_count": len(target_indices),
        "affine_diagnostics": {
            "source_dimension": len(source.indices),
            "target_dimension": len(target_indices),
            "exact_rank": len(block.ansatz_positions)
            - len(candidate.target_pool_indices),
            "complete_atomic_manifold_validated": True,
        },
        "certificate_class": "globally-unitary-exact-affine-atomic",
    }


def optimization_initialization_id(
    candidate_plan: str,
    start: str,
    coordinate_float64: Sequence[str],
) -> str:
    if start not in {"mapped-warm-start", "zero-target-coordinate"}:
        raise A3GrammarError("unregistered optimization initialization")
    return "optimization-initialization-v1:" + _digest(
        {
            "version": IDENTITY_VERSION,
            "CandidatePlanID": candidate_plan,
            "start": start,
            "target_coordinate_float64": list(coordinate_float64),
        }
    )


def _plan_record(
    pool: Any,
    b2_source_id: str,
    plan: JointConstraintPlan,
) -> dict[str, Any]:
    structural = structural_target_id(pool, plan)
    candidate_plan = candidate_plan_id(b2_source_id, plan)
    return {
        "StructuralTargetID": structural,
        "CandidatePlanID": candidate_plan,
        "candidate_ids": sorted(plan.candidate_ids),
        "equivalence_class_ids": sorted(plan.equivalence_class_ids),
        "source_block_ids": sorted(plan.source_block_ids),
        "constraint_semantic_id": plan.state.constraint_semantic_id,
        "constraint_numerical_id": plan.state.constraint_numerical_id,
        "target_indices": list(plan.target_indices),
        "target_generator_digests": _target_generator_digests(
            pool, plan.target_indices
        ),
        "target_iteration_counts": list(plan.target_iteration_counts),
        "target_selection_iterations": list(plan.target_selection_iterations),
        "affine_diagnostics": plan.state.diagnostics,
        "certificate_class": "globally-unitary-exact-affine",
    }


def _dependency_reason(left: DVGBlock, right: DVGBlock) -> str | None:
    if left.block_id == right.block_id:
        return "common-source-CEO-block"
    if set(left.support_qubits) & set(right.support_qubits):
        return "shared-canonical-CNOT-support-dependency"
    return None


def _assert_affine_manifold(plan: JointConstraintPlan) -> None:
    transform = plan.transformation
    transform.validate(len(transform.source_slots))
    a = np.asarray(transform.constraint_matrix, dtype=np.float64)
    b = np.asarray(transform.constraint_rhs, dtype=np.float64)
    c = np.asarray(transform.offset, dtype=np.float64)
    j = np.asarray(transform.jacobian, dtype=np.float64)
    if a.size and np.max(np.abs(a @ c - b), initial=0.0) > 1e-10:
        raise A3GrammarError("affine offset is outside the exact manifold")
    if a.size and j.size and np.max(np.abs(a @ j), initial=0.0) > 1e-10:
        raise A3GrammarError("affine Jacobian is outside the exact null space")
    if np.linalg.matrix_rank(a, tol=1e-12) + j.shape[1] != j.shape[0]:
        raise A3GrammarError("affine map does not span the complete feasible manifold")


def _build_case_from_catalog(
    case_id: str,
    source_record: Mapping[str, Any],
    context: Any,
    source: AnsatzStructure,
    blocks: Sequence[DVGBlock],
    raw: Sequence[CompressionCandidate],
) -> dict[str, Any]:
    """Generate canonical bytes from one already certified structural catalog."""

    raw = tuple(raw)
    unexpected = sorted({candidate.kind for candidate in raw} - set(ALLOWED_AFFINE_KINDS))
    if unexpected:
        raise A3GrammarError(f"unregistered affine candidate kinds: {unexpected}")
    representatives, aliases = _representatives(raw)
    block_by_id = {block.block_id: block for block in blocks}

    singleton_records: list[dict[str, Any]] = []
    for candidate in sorted(representatives, key=lambda value: value.candidate_id):
        block = block_by_id[candidate.source_block_id]
        singleton_records.append(
            {
                **_fast_singleton_record(
                    context.pool,
                    source,
                    source_record["B2SourceID"],
                    block,
                    candidate,
                ),
                "kind": candidate.kind,
                "source_support_qubits": list(
                    block.support_qubits
                ),
                "semantic_alias_candidate_ids": aliases[
                    candidate.equivalence_class_id
                ],
            }
        )

    joint_records: list[dict[str, Any]] = []
    rejected_counts: Counter[str] = Counter()
    for left, right in itertools.combinations(
        sorted(representatives, key=lambda value: value.candidate_id), 2
    ):
        left_block = block_by_id[left.source_block_id]
        right_block = block_by_id[right.source_block_id]
        dependency = _dependency_reason(left_block, right_block)
        if dependency is None:
            rejected_counts["not-one-hop-structurally-dependent"] += 1
            continue
        compatibility = pairwise_compatibility(left, left_block, right, right_block)
        if not compatibility.compatible:
            for reason in compatibility.reasons:
                rejected_counts[reason] += 1
            continue
        record = _fast_disjoint_pair_record(
            context.pool,
            source,
            source_record["B2SourceID"],
            blocks,
            left,
            right,
        )
        record["dependency_reason"] = dependency
        record["K"] = 2
        record["L"] = 1
        record["D"] = 1
        joint_records.append(record)

    singleton_records.sort(key=lambda value: value["CandidatePlanID"])
    joint_records.sort(key=lambda value: value["CandidatePlanID"])
    singleton_ids = [value["CandidatePlanID"] for value in singleton_records]
    joint_ids = [value["CandidatePlanID"] for value in joint_records]
    if len(singleton_ids) != len(set(singleton_ids)):
        raise A3GrammarError("singleton CandidatePlanID collision")
    if len(joint_ids) != len(set(joint_ids)):
        raise A3GrammarError("joint CandidatePlanID collision")
    if set(singleton_ids) & set(joint_ids):
        raise A3GrammarError("singleton and joint CandidatePlanID namespaces collided")

    value: dict[str, Any] = {
        "schema": "phase1-frontier.a3-grammar-identities.v4-intermediate",
        "stage": "A3",
        "case_id": case_id,
        "grammar_contract": {
            "version": GRAMMAR_VERSION,
            "allowed_affine_kinds": list(ALLOWED_AFFINE_KINDS),
            "semantic_closure": "one-lexicographic-representative-per-equivalence-class",
            "joint_cardinality_K": 2,
            "joint_locality_L": 1,
            "source_rewrite_depth_D": 1,
            "dependency_edge_predicate": [
                "common-source-CEO-block",
                "nonempty-source-block-qubit-support-intersection",
            ],
            "same_source_candidates": "edge-generated-then-conflict-rejected",
            "joint_affine_composition": (
                "exact direct sum of two disjoint complete atomic affine manifolds"
            ),
            "singleton_affine_composition": (
                "direct validation and materialization of the atomic ConstraintTargetIR"
            ),
            "normalized_storage": (
                "target arrays are content-addressed by StructuralTargetID and "
                "target_materialization_digest; they are deterministically rebuilt "
                "from B2 plus registered candidate IDs"
            ),
            "ranking_or_top_k": None,
            "historical_or_candidate_energy_input": False,
            "exact_non_affine_families": [],
            "excluded_families": {
                "approximate-non-affine": "not admissible",
                "cross-iteration-exact-fusion": (
                    "separate historical transformation family; not a member of "
                    "the frozen block-local singleton grammar"
                ),
            },
        },
        "B2SourceID": source_record["B2SourceID"],
        "ProblemID": source_record["ProblemID"],
        "StatePreparationID": source_record["B2"]["StatePreparationID"],
        "source_digest": source_record["source_digest"],
        "blocks": [block_to_dict(block) for block in blocks],
        "raw_candidate_count": len(raw),
        "raw_candidate_kind_counts": dict(sorted(Counter(value.kind for value in raw).items())),
        "semantic_alias_groups": aliases,
        "canonical_singleton_count": len(singleton_records),
        "singletons": singleton_records,
        "CompleteSingletonUniverseID": "singleton-universe-v1:"
        + _digest(
            {
                "grammar": GRAMMAR_VERSION,
                "B2SourceID": source_record["B2SourceID"],
                "CandidatePlanIDs": singleton_ids,
                "aliases": aliases,
            }
        ),
        "joint_count": len(joint_records),
        "joints": joint_records,
        "joint_rejection_counts": dict(sorted(rejected_counts.items())),
        "RegisteredJointUniverseID": "joint-universe-v1:"
        + _digest(
            {
                "grammar": GRAMMAR_VERSION,
                "B2SourceID": source_record["B2SourceID"],
                "CandidatePlanIDs": joint_ids,
            }
        ),
        "candidate_generation_count": len(raw),
        "candidate_energy_evaluations": 0,
        "optimizer_starts": 0,
        "FCI_evaluations": 0,
    }
    return _compact_case_storage(value)


def _certified_catalog(
    case_id: str,
) -> tuple[dict[str, Any], Any, AnsatzStructure, tuple[DVGBlock, ...], tuple[CompressionCandidate, ...]]:
    _verify_authority()
    source_record = _verified_source(case_id)
    context = _context(case_id)
    source = _source_structure(source_record)
    blocks = recover_dvg_blocks(
        context.pool,
        source.indices,
        source.coefficients,
        source.cumulative_parameter_counts,
    )
    raw = enumerate_candidates(context.pool, blocks)
    return source_record, context, source, blocks, raw


def build_case(case_id: str) -> dict[str, Any]:
    return _build_case_from_catalog(case_id, *_certified_catalog(case_id))


def generate_case_twice_and_freeze(case_id: str) -> dict[str, Any]:
    destination = case_path(case_id)
    if destination.exists():
        raise A3GrammarError(f"A3 case already frozen: {destination}")
    catalog = _certified_catalog(case_id)
    first = _build_case_from_catalog(case_id, *catalog)
    second = _build_case_from_catalog(case_id, *catalog)
    if canonical_json_bytes(first) != canonical_json_bytes(second):
        raise A3GrammarError("A3 double generation is not byte-identical")
    _write_exclusive(destination, first)
    return {
        "case_id": case_id,
        "raw_candidate_count": first["raw_candidate_count"],
        "canonical_singleton_count": first["canonical_singleton_count"],
        "joint_count": first["joint_count"],
        "CompleteSingletonUniverseID": first["CompleteSingletonUniverseID"],
        "RegisteredJointUniverseID": first["RegisteredJointUniverseID"],
        "case_digest": first["case_digest"],
    }


def compact_v4_case_twice_and_freeze(case_id: str) -> dict[str, Any]:
    destination = case_path(case_id)
    if destination.exists():
        raise A3GrammarError(f"A3 case already frozen: {destination}")
    legacy = legacy_v4_case_path(case_id)
    if not legacy.is_file():
        raise A3GrammarError(f"A3 v4 source is absent: {legacy}")
    value = json.loads(legacy.read_text(encoding="utf-8"))
    digest = value.get("case_digest")
    without_digest = dict(value)
    without_digest.pop("case_digest", None)
    if digest != _digest(without_digest):
        raise A3GrammarError("A3 v4 source digest is invalid")
    first = _compact_case_storage(value)
    second = _compact_case_storage(value)
    if canonical_json_bytes(first) != canonical_json_bytes(second):
        raise A3GrammarError("A3 v4-to-v5 compaction is not byte-identical")
    _write_exclusive(destination, first)
    return {
        "case_id": case_id,
        "raw_candidate_count": first["raw_candidate_count"],
        "canonical_singleton_count": first["canonical_singleton_count"],
        "joint_count": first["joint_count"],
        "CompleteSingletonUniverseID": first["CompleteSingletonUniverseID"],
        "RegisteredJointUniverseID": first["RegisteredJointUniverseID"],
        "case_digest": first["case_digest"],
        "storage_source": "digest-valid-v4-artifact",
    }


def audit() -> dict[str, Any]:
    cases: dict[str, Any] = {}
    all_valid = True
    global_plan_ids: set[str] = set()
    cross_case_collision = False
    for case_id in CASES:
        path = case_path(case_id)
        if not path.is_file():
            cases[case_id] = {"status": "MISSING"}
            all_valid = False
            continue
        value = json.loads(path.read_text(encoding="utf-8"))
        digest = value.pop("case_digest", None)
        valid = digest == _digest(value)
        candidate_ids = [
            item["CandidatePlanID"]
            for key in ("singletons", "joints")
            for item in value[key]
        ]
        structural_ids = [
            item["StructuralTargetID"]
            for key in ("singletons", "joints")
            for item in value[key]
        ]
        singleton_plan_ids = [item["CandidatePlanID"] for item in value["singletons"]]
        joint_plan_ids = [item["CandidatePlanID"] for item in value["joints"]]
        current_ids = set(candidate_ids)
        cross_case_collision |= bool(global_plan_ids & current_ids)
        global_plan_ids.update(current_ids)
        ordinal_count = len(value["singletons"])
        checks = {
            "case_digest_valid": valid,
            "candidate_plan_ids_unique": len(candidate_ids) == len(set(candidate_ids)),
            "structural_target_ids_present": all(structural_ids),
            "stored_counts_exact": (
                len(value["singletons"]) == value["canonical_singleton_count"]
                and len(value["joints"]) == value["joint_count"]
            ),
            "joint_dictionary_references_valid": all(
                len(item.get("singleton_ordinals", ())) == 2
                and len(set(item["singleton_ordinals"])) == 2
                and all(0 <= ordinal < ordinal_count for ordinal in item["singleton_ordinals"])
                and "candidate_ids" not in item
                and "equivalence_class_ids" not in item
                and "source_block_ids" not in item
                for item in value["joints"]
            ),
            "singleton_universe_id_recomputes": value[
                "CompleteSingletonUniverseID"
            ]
            == "singleton-universe-v1:"
            + _digest(
                {
                    "grammar": GRAMMAR_VERSION,
                    "B2SourceID": value["B2SourceID"],
                    "CandidatePlanIDs": singleton_plan_ids,
                    "aliases": value["semantic_alias_groups"],
                }
            ),
            "joint_universe_id_recomputes": value["RegisteredJointUniverseID"]
            == "joint-universe-v1:"
            + _digest(
                {
                    "grammar": GRAMMAR_VERSION,
                    "B2SourceID": value["B2SourceID"],
                    "CandidatePlanIDs": joint_plan_ids,
                }
            ),
            "singleton_universe_nonempty": value["canonical_singleton_count"] > 0,
            "joint_universe_nonempty": value["joint_count"] > 0,
            "no_candidate_energy": value["candidate_energy_evaluations"] == 0,
            "no_optimizer": value["optimizer_starts"] == 0,
            "no_FCI": value["FCI_evaluations"] == 0,
            "git_host_file_limit_respected": path.stat().st_size < 100_000_000,
        }
        all_valid &= all(checks.values())
        cases[case_id] = {
            "status": "VALID" if all(checks.values()) else "INVALID",
            "checks": checks,
            "raw_candidate_count": value["raw_candidate_count"],
            "canonical_singleton_count": value["canonical_singleton_count"],
            "joint_count": value["joint_count"],
        }
    all_valid &= not cross_case_collision
    return {
        "schema": "phase1-frontier.a3-grammar-identity-audit.v1",
        "passed": all_valid,
        "decision": (
            "GO_A4_CPU_STRUCTURAL_CENSUS"
            if all_valid
            else "NO_GO_A3_GRAMMAR_OR_IDENTITY_INVALID"
        ),
        "cases": cases,
        "cross_case_candidate_plan_ids_disjoint": not cross_case_collision,
    }


def freeze_audit() -> dict[str, Any]:
    if A3_AUDIT.exists():
        raise A3GrammarError(f"A3 audit already frozen: {A3_AUDIT}")
    value = audit()
    if not value["passed"]:
        raise A3GrammarError("cannot freeze a failing A3 audit")
    value["artifact_file_sha256"] = {
        str(case_path(case_id).relative_to(ROOT)): hashlib.sha256(
            case_path(case_id).read_bytes()
        ).hexdigest()
        for case_id in CASES
    }
    value["audit_digest"] = _digest(value)
    _write_exclusive(A3_AUDIT, value)
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=CASES)
    parser.add_argument("--compact-v4-case", choices=CASES)
    parser.add_argument("--audit", action="store_true")
    parser.add_argument("--freeze-audit", action="store_true")
    args = parser.parse_args()
    if sum(
        (
            args.case is not None,
            args.compact_v4_case is not None,
            args.audit,
            args.freeze_audit,
        )
    ) != 1:
        parser.error(
            "choose exactly one of --case, --compact-v4-case, --audit, or "
            "--freeze-audit"
        )
    if args.case:
        value = generate_case_twice_and_freeze(args.case)
    elif args.compact_v4_case:
        value = compact_v4_case_twice_and_freeze(args.compact_v4_case)
    elif args.freeze_audit:
        value = freeze_audit()
    else:
        value = audit()
    print(json.dumps(value, indent=2, sort_keys=True))
    if (args.audit or args.freeze_audit) and not value["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

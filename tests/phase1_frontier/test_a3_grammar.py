from __future__ import annotations

import itertools
import json
import subprocess

import pytest

from dvg_obs_ceo.composition import compose_registered_candidates, pairwise_compatibility

from phase1_frontier.a3_grammar import (
    CASES,
    GRAMMAR_VERSION,
    _certified_catalog,
    _dependency_reason,
    _digest,
    _fast_disjoint_pair_record,
    _fast_singleton_record,
    _representatives,
    audit,
    case_path,
    optimization_initialization_id,
    structural_target_id,
)


def test_frozen_A3_records_are_complete_deterministic_and_outcome_free() -> None:
    result = audit()
    assert result["passed"] is True
    assert result["decision"] == "GO_A4_CPU_STRUCTURAL_CENSUS"
    assert result["cross_case_candidate_plan_ids_disjoint"] is True
    for case_id in CASES:
        value = json.loads(case_path(case_id).read_text(encoding="utf-8"))
        assert len(value["singletons"]) == value["canonical_singleton_count"]
        assert len(value["joints"]) == value["joint_count"]
        assert value["candidate_energy_evaluations"] == 0
        assert value["optimizer_starts"] == 0
        assert value["FCI_evaluations"] == 0
        assert value["grammar_contract"]["ranking_or_top_k"] is None
        assert value["grammar_contract"]["historical_or_candidate_energy_input"] is False


@pytest.mark.skipif(
    subprocess.check_output(["git", "branch", "--show-current"], text=True).strip()
    != "feature/phase1-joint-frontier-v1",
    reason="v1 live catalog reconstruction is intentionally branch-bound",
)
def test_fast_atomic_and_direct_sum_materialization_matches_general_composer() -> None:
    source_record, context, source, blocks, raw = _certified_catalog("lih-3.0")
    representatives, _aliases = _representatives(raw)
    by_block = {block.block_id: block for block in blocks}
    for candidate in representatives:
        fast = _fast_singleton_record(
            context.pool,
            source,
            source_record["B2SourceID"],
            by_block[candidate.source_block_id],
            candidate,
        )
        general = compose_registered_candidates(source, blocks, (candidate,))
        assert fast["StructuralTargetID"] == structural_target_id(context.pool, general)
        assert fast["target_parameter_count"] == len(general.target_indices)

    checked = 0
    for left, right in itertools.combinations(
        sorted(representatives, key=lambda value: value.candidate_id), 2
    ):
        left_block = by_block[left.source_block_id]
        right_block = by_block[right.source_block_id]
        if _dependency_reason(left_block, right_block) is None:
            continue
        if not pairwise_compatibility(left, left_block, right, right_block).compatible:
            continue
        fast = _fast_disjoint_pair_record(
            context.pool,
            source,
            source_record["B2SourceID"],
            blocks,
            left,
            right,
        )
        reverse = _fast_disjoint_pair_record(
            context.pool,
            source,
            source_record["B2SourceID"],
            blocks,
            right,
            left,
        )
        general = compose_registered_candidates(source, blocks, (left, right))
        assert fast == reverse
        assert fast["StructuralTargetID"] == structural_target_id(context.pool, general)
        assert fast["target_parameter_count"] == len(general.target_indices)
        checked += 1
    assert checked == 60


def test_identity_layers_separate_structure_plan_and_initialization() -> None:
    value = json.loads(case_path("lih-3.0").read_text(encoding="utf-8"))
    plan = value["singletons"][0]
    warm = optimization_initialization_id(
        plan["CandidatePlanID"], "mapped-warm-start", ["3ff0000000000000"]
    )
    zero = optimization_initialization_id(
        plan["CandidatePlanID"], "zero-target-coordinate", ["0000000000000000"]
    )
    assert warm == optimization_initialization_id(
        plan["CandidatePlanID"], "mapped-warm-start", ["3ff0000000000000"]
    )
    assert warm != zero
    assert plan["StructuralTargetID"] != plan["CandidatePlanID"]
    assert _digest({"grammar": GRAMMAR_VERSION, "resolution": "coarse"}) != _digest(
        {"grammar": GRAMMAR_VERSION, "resolution": "fine"}
    )


def test_semantic_closure_contains_every_raw_alias_once() -> None:
    for case_id in CASES:
        value = json.loads(case_path(case_id).read_text(encoding="utf-8"))
        aliases = value["semantic_alias_groups"]
        flattened = [candidate for group in aliases.values() for candidate in group]
        assert len(flattened) == value["raw_candidate_count"]
        assert len(flattened) == len(set(flattened))
        assert len(aliases) == value["canonical_singleton_count"]

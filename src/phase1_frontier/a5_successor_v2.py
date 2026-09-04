"""Outcome-free Phase-1 v2 successor design and screening-queue freeze."""

from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
import struct
from typing import Any, Mapping

import numpy as np

from dvg_obs_ceo.block_ir import enumerate_candidates, recover_dvg_blocks
from dvg_obs_ceo.composition import compose_registered_candidates
from v5_matched_work.atomic_artifacts import canonical_json_bytes

from .a2_source_lock import CASES, ROOT, _context, source_path
from .a3_grammar import _digest, _representatives, _source_structure, case_path
from .a4_structural_census import AUDIT_PATH as A4_AUDIT_PATH
from .a4_structural_census import census_path
from .a5_e2_capacity_gate import AUDIT_PATH as A5_V1_AUDIT_PATH
from .a5_e2_capacity_gate import CAPACITY_PATH as A5_V1_NOGO_PATH


V2_ROOT = ROOT / "artifacts" / "phase1-v2" / "s0-s2-screen-freeze"
AUTHORITY_PATH = V2_ROOT / "phase1-v2-successor-authority-v1.json"
DESIGN_PATH = V2_ROOT / "phase1-v2-screen-design-v1.json"
QUEUE_PATH = V2_ROOT / "phase1-v2-screen-queue-v1.json"
AUDIT_PATH = V2_ROOT / "phase1-v2-screen-freeze-audit-v1.json"
PROTOCOL_PATHS = (
    ROOT / "docs" / "CEO_PHASE1_SCIENTIFIC_PROTOCOL_V2.md",
    ROOT / "docs" / "CEO_PHASE1_ENGINEERING_PROTOCOL_V2.md",
    ROOT / "docs" / "CEO_PHASE1_AGENT_EXECUTION_PROTOCOL_V2.md",
)
SAMPLE_SEED = "phase1-v2-prospective-stratified-joint-screen-v1"
NON_LIH_JOINTS_PER_STRATUM = 2
STARTS = ("mapped-warm-start", "zero-target-coordinate")
MAX_ITERATIONS_PER_START = 2_000
MAX_ENERGY_EVALUATIONS_PER_START = 2_500
MAX_GRADIENT_VECTORS_PER_START = 2_500


class V2FreezeError(RuntimeError):
    """Raised when the v2 successor cannot be frozen without outcomes."""


def _write_exclusive(path: Path, value: Mapping[str, Any]) -> None:
    payload = canonical_json_bytes(dict(value)) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    try:
        offset = 0
        while offset < len(payload):
            count = os.write(descriptor, payload[offset:])
            if count <= 0:
                raise V2FreezeError("artifact write made no forward progress")
            offset += count
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _decode(value: str) -> float:
    return struct.unpack(">d", bytes.fromhex(value))[0]


def _float_hex(values: Any) -> list[str]:
    return [struct.pack(">d", float(value)).hex() for value in values]


def _read_digest_valid(path: Path, digest_key: str) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    digest = value.pop(digest_key, None)
    if digest != _digest(value):
        raise V2FreezeError(f"invalid digest: {path}")
    value[digest_key] = digest
    return value


def _read_census(path: Path) -> dict[str, Any]:
    """Verify A4 identity while excluding its explicitly observational timing."""

    value = json.loads(path.read_text(encoding="utf-8"))
    digest = value.pop("census_digest", None)
    elapsed = value.pop("elapsed_seconds_observational_not_identity", None)
    if digest != _digest(value):
        raise V2FreezeError(f"invalid A4 census digest: {path}")
    value["elapsed_seconds_observational_not_identity"] = elapsed
    value["census_digest"] = digest
    return value


def freeze_authority() -> dict[str, Any]:
    if AUTHORITY_PATH.exists():
        raise V2FreezeError("v2 authority already exists")
    v1_audit = json.loads(A5_V1_AUDIT_PATH.read_text(encoding="utf-8"))
    v1_no_go = _read_digest_valid(A5_V1_NOGO_PATH, "no_go_digest")
    a4 = json.loads(A4_AUDIT_PATH.read_text(encoding="utf-8"))
    protocol_hashes = {str(path.relative_to(ROOT)): _sha256(path) for path in PROTOCOL_PATHS}
    checks = {
        "v1_A5_audit_passed": v1_audit.get("passed") is True,
        "v1_terminal_decision_preserved": v1_no_go.get("decision")
        == "NO_GO_A5_E2_OR_QUEUE_INVALID",
        "v1_reason_is_capacity": v1_no_go.get("reason_code")
        == "E3_EXHAUSTIVE_CAPACITY_UNPROVEN",
        "v1_candidate_outcomes_zero": v1_no_go.get(
            "E3_candidate_energy_evaluations"
        )
        == 0,
        "A4_outcome_free_census_valid": a4.get("passed") is True,
        "protocol_files_present": len(protocol_hashes) == 3,
    }
    value = {
        "schema": "phase1-frontier.v2-successor-authority.v1",
        "decision": "GO_PHASE1_V2_OUTCOME_FREE_SCREEN_FREEZE"
        if all(checks.values())
        else "NO_GO_PHASE1_V2_AUTHORITY",
        "checks": checks,
        "immutable_v1_parent_commit": "95fc3cf8348cd5f2fb6a59db7edc56d2600d5cdc",
        "v1_A5_audit_sha256": _sha256(A5_V1_AUDIT_PATH),
        "v1_A5_no_go_sha256": _sha256(A5_V1_NOGO_PATH),
        "A4_audit_sha256": _sha256(A4_AUDIT_PATH),
        "protocol_sha256": protocol_hashes,
        "candidate_energy_evaluations": 0,
        "optimizer_starts": 0,
        "FCI_evaluations": 0,
        "scope_change": (
            "v1 exhaustive joint frontier is replaced by a preregistered screening "
            "estimand; absence in the screen is not absence in the full universe"
        ),
    }
    value["authority_digest"] = _digest(value)
    _write_exclusive(AUTHORITY_PATH, value)
    if not all(checks.values()):
        raise V2FreezeError("v2 authority failed")
    return value


def _stratum(singletons: list[dict[str, Any]], joint: Mapping[str, Any], saving: int) -> str:
    left, right = joint["singleton_ordinals"]
    kinds = sorted((singletons[left]["kind"], singletons[right]["kind"]))
    return f"{kinds[0]}+{kinds[1]}|cnot-saving:{saving}"


def _hash_rank(case_id: str, candidate_plan_id: str) -> str:
    return hashlib.sha256(
        f"{SAMPLE_SEED}|{case_id}|{candidate_plan_id}".encode("utf-8")
    ).hexdigest()


def build_design() -> dict[str, Any]:
    authority = _read_digest_valid(AUTHORITY_PATH, "authority_digest")
    if authority["decision"] != "GO_PHASE1_V2_OUTCOME_FREE_SCREEN_FREEZE":
        raise V2FreezeError("v2 authority does not permit design generation")
    cases: dict[str, Any] = {}
    selected_singleton_total = 0
    selected_joint_total = 0
    full_joint_total = 0
    dominance_eligible_total = 0
    for case_id in CASES:
        grammar = _read_digest_valid(case_path(case_id), "case_digest")
        census = _read_census(census_path(case_id, 1))
        resource_by_plan = {row["CandidatePlanID"]: row for row in census["rows"]}
        singletons = grammar["singletons"]
        singleton_delta = [
            resource_by_plan[row["CandidatePlanID"]]["resource_delta_from_B2"]
            for row in singletons
        ]
        selected_singletons = [
            ordinal
            for ordinal, delta in enumerate(singleton_delta)
            if int(delta["cnot_count"]) < 0
        ]
        strata: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for joint in grammar["joints"]:
            left, right = joint["singleton_ordinals"]
            joint_row = resource_by_plan[joint["CandidatePlanID"]]
            joint_delta = int(joint_row["resource_delta_from_B2"]["cnot_count"])
            constituent_best = min(
                int(singleton_delta[left]["cnot_count"]),
                int(singleton_delta[right]["cnot_count"]),
            )
            if joint_delta >= constituent_best:
                continue
            saving = -joint_delta
            key = _stratum(singletons, joint, saving)
            strata[key].append(
                {
                    "CandidatePlanID": joint["CandidatePlanID"],
                    "StructuralTargetID": joint["StructuralTargetID"],
                    "singleton_ordinals": [left, right],
                    "hash_rank": _hash_rank(case_id, joint["CandidatePlanID"]),
                    "cnot_delta": joint_delta,
                }
            )
        selected_joints: list[dict[str, Any]] = []
        stratum_summary: dict[str, Any] = {}
        for key, rows in sorted(strata.items()):
            ordered = sorted(rows, key=lambda row: (row["hash_rank"], row["CandidatePlanID"]))
            take = len(ordered) if case_id == "lih-3.0" else min(
                NON_LIH_JOINTS_PER_STRATUM, len(ordered)
            )
            chosen = ordered[:take]
            for row in chosen:
                row["stratum"] = key
                row["population_count"] = len(ordered)
                row["sample_count"] = take
                row["inclusion_probability"] = take / len(ordered)
            selected_joints.extend(chosen)
            stratum_summary[key] = {
                "population_count": len(ordered),
                "sample_count": take,
                "inclusion_probability": take / len(ordered),
            }
        selected_joints.sort(key=lambda row: row["CandidatePlanID"])
        cases[case_id] = {
            "full_singleton_count": len(singletons),
            "primary_CNOT_eligible_singleton_ordinals": selected_singletons,
            "primary_CNOT_eligible_singleton_count": len(selected_singletons),
            "full_registered_joint_count": len(grammar["joints"]),
            "strict_dominance_eligible_joint_count": sum(
                row["population_count"] for row in stratum_summary.values()
            ),
            "screen_joint_count": len(selected_joints),
            "strata": stratum_summary,
            "screen_joints": selected_joints,
            "A3_case_digest": grammar["case_digest"],
            "A4_census_digest": census["census_digest"],
        }
        selected_singleton_total += len(selected_singletons)
        selected_joint_total += len(selected_joints)
        full_joint_total += len(grammar["joints"])
        dominance_eligible_total += cases[case_id]["strict_dominance_eligible_joint_count"]
    value = {
        "schema": "phase1-frontier.v2-screen-design.v1",
        "stage": "V2-S1",
        "design_type": "prospective-stratified-screen-not-exhaustive-frontier",
        "primary_resource": "paper-era canonical logical CNOT count",
        "exact_dominance_rule": (
            "retain a joint only if its CNOT count is strictly lower than each "
            "constituent singleton; the joint manifold is a subset of each constituent "
            "singleton manifold"
        ),
        "sampling_rule": {
            "LiH_3A": "complete dominance-eligible joint census",
            "other_cases": "two lowest SHA-256 ranks per transformation-kind and exact-CNOT-saving stratum",
            "seed": SAMPLE_SEED,
            "candidate_energy_used": False,
            "historical_winner_used": False,
            "inclusion_probabilities_recorded": True,
        },
        "cases": cases,
        "counts": {
            "full_registered_joints": full_joint_total,
            "strict_dominance_eligible_joints": dominance_eligible_total,
            "complete_primary_CNOT_singletons": selected_singleton_total,
            "screen_joints": selected_joint_total,
            "screen_targets": selected_singleton_total + selected_joint_total,
            "two_start_requests": 2 * (selected_singleton_total + selected_joint_total),
        },
        "interpretation": {
            "positive_screen": "candidate signal requiring held-out confirmation",
            "negative_screen": "no signal in the frozen screen; not proof of no full-universe effect",
            "population_frontier_claim": False,
        },
        "candidate_energy_evaluations": 0,
        "optimizer_starts": 0,
        "FCI_evaluations": 0,
        "authority_digest": authority["authority_digest"],
    }
    value["design_digest"] = _digest(value)
    return value


def freeze_design() -> dict[str, Any]:
    if DESIGN_PATH.exists():
        raise V2FreezeError("v2 design already exists")
    first = build_design()
    second = build_design()
    if canonical_json_bytes(first) != canonical_json_bytes(second):
        raise V2FreezeError("v2 design generation is not byte-identical")
    _write_exclusive(DESIGN_PATH, first)
    return first


def _initialization_id(candidate_plan_id: str, start: str, coordinates: list[str]) -> str:
    return "optimization-initialization-v2:" + _digest(
        {
            "CandidatePlanID": candidate_plan_id,
            "start": start,
            "target_coordinate_float64": coordinates,
        }
    )


def _v2_catalog(case_id: str, source_record: Mapping[str, Any]) -> tuple[Any, Any, Any]:
    """Reconstruct the pinned catalog under v2 authority, not the v1 branch gate."""

    context = _context(case_id)
    source = _source_structure(source_record)
    blocks = recover_dvg_blocks(
        context.pool,
        source.indices,
        source.coefficients,
        source.cumulative_parameter_counts,
    )
    raw = enumerate_candidates(context.pool, blocks)
    return source, blocks, raw


def build_queue() -> dict[str, Any]:
    design = _read_digest_valid(DESIGN_PATH, "design_digest")
    items: list[dict[str, Any]] = []
    for case_id in CASES:
        source_record = _read_digest_valid(source_path(case_id), "source_digest")
        source, blocks, raw = _v2_catalog(case_id, source_record)
        representatives, _aliases = _representatives(raw)
        candidate_by_id = {row.candidate_id: row for row in representatives}
        grammar = _read_digest_valid(case_path(case_id), "case_digest")
        singleton_rows = grammar["singletons"]
        selected: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
        for ordinal in design["cases"][case_id][
            "primary_CNOT_eligible_singleton_ordinals"
        ]:
            row = singleton_rows[ordinal]
            selected.append(("singleton", row, {"singleton_ordinal": ordinal}))
        for row in design["cases"][case_id]["screen_joints"]:
            selected.append(("joint-K2", row, {key: row[key] for key in (
                "stratum", "population_count", "sample_count", "inclusion_probability", "hash_rank"
            )}))
        for target_class, row, selection in selected:
            if target_class == "singleton":
                candidate_ids = row["candidate_ids"]
            else:
                candidate_ids = [
                    singleton_rows[ordinal]["candidate_ids"][0]
                    for ordinal in row["singleton_ordinals"]
                ]
            candidates = tuple(candidate_by_id[value] for value in candidate_ids)
            plan = compose_registered_candidates(source, blocks, candidates)
            transformation = plan.transformation
            jacobian = np.asarray(transformation.jacobian, dtype=np.float64)
            offset = np.asarray(transformation.offset, dtype=np.float64)
            warm, _residuals, rank, _singular = np.linalg.lstsq(
                jacobian,
                np.asarray(source.coefficients, dtype=np.float64) - offset,
                rcond=None,
            )
            if rank != jacobian.shape[1]:
                raise V2FreezeError("exact affine warm-start map is rank deficient")
            mapped_source = offset + jacobian @ warm
            constraint_residual = np.asarray(transformation.constraint_matrix) @ mapped_source - np.asarray(
                transformation.constraint_rhs
            )
            if np.max(np.abs(constraint_residual), initial=0.0) > 1e-10:
                raise V2FreezeError("Euclidean warm start violates exact constraint")
            initializations = {
                "mapped-warm-start": _float_hex(warm),
                "zero-target-coordinate": _float_hex(np.zeros(len(plan.target_indices))),
            }
            for start in STARTS:
                init_id = _initialization_id(
                    row["CandidatePlanID"], start, initializations[start]
                )
                request_payload = {
                    "protocol": "phase1-v2-screen-v1",
                    "case_id": case_id,
                    "B2SourceID": source_record["B2SourceID"],
                    "CandidatePlanID": row["CandidatePlanID"],
                    "StructuralTargetID": row["StructuralTargetID"],
                    "target_class": target_class,
                    "candidate_ids": sorted(candidate_ids),
                    "start": start,
                    "OptimizationInitializationID": init_id,
                }
                items.append(
                    {
                        "RequestID": "phase1-v2-request:" + _digest(request_payload),
                        **request_payload,
                        "initial_coordinates_float64": initializations[start],
                        "target_parameter_count": len(plan.target_indices),
                        "initial_inverse_hessian_policy": "identity-target-dimension-v1",
                        "selection_metadata": selection,
                        "status": "NOT_STARTED",
                    }
                )
    items.sort(key=lambda row: (row["case_id"], row["target_class"], row["CandidatePlanID"], row["start"]))
    caps = {
        "starts_per_target": 2,
        "optimizer_iterations_per_start": MAX_ITERATIONS_PER_START,
        "energy_evaluations_per_start": MAX_ENERGY_EVALUATIONS_PER_START,
        "gradient_vector_evaluations_per_start": MAX_GRADIENT_VECTORS_PER_START,
        "derivation": (
            "fixed before candidate outcomes; 2,000 iterations exceeds twice the "
            "largest 884-iteration B2 source calibration observed in A2"
        ),
    }
    value = {
        "schema": "phase1-frontier.v2-screen-queue.v1",
        "stage": "V2-S2",
        "status": "FROZEN_NOT_STARTED",
        "design_digest": design["design_digest"],
        "optimizer_contract": {
            "family": "pinned-adaptvqe-BFGS",
            "analytic_gradient": True,
            "two_start_policy": list(STARTS),
            "mapped_warm_start": "Euclidean least-squares projection of B2 coordinates into the exact affine target manifold",
            "initial_inverse_hessian_policy": "identity-target-dimension-v1 for both starts",
            "gradient_infinity_tolerance": 1e-8,
            "energy_agreement_tolerance_hartree": 1e-10,
            "accuracy_guard_relative_to_B2_hartree": 1e-4,
            "caps": caps,
        },
        "items": items,
        "counts": {
            "requests": len(items),
            "targets": len(items) // 2,
            "NOT_STARTED": sum(row["status"] == "NOT_STARTED" for row in items),
            "candidate_energy_evaluations": 0,
            "optimizer_starts": 0,
            "FCI_evaluations": 0,
            "maximum_optimizer_iterations": len(items) * MAX_ITERATIONS_PER_START,
        },
    }
    value["queue_digest"] = _digest(value)
    return value


def freeze_queue() -> dict[str, Any]:
    if QUEUE_PATH.exists():
        raise V2FreezeError("v2 queue already exists")
    first = build_queue()
    second = build_queue()
    if canonical_json_bytes(first) != canonical_json_bytes(second):
        raise V2FreezeError("v2 queue generation is not byte-identical")
    _write_exclusive(QUEUE_PATH, first)
    return first


def audit() -> dict[str, Any]:
    authority = _read_digest_valid(AUTHORITY_PATH, "authority_digest")
    design = _read_digest_valid(DESIGN_PATH, "design_digest")
    queue = _read_digest_valid(QUEUE_PATH, "queue_digest")
    request_ids = [row["RequestID"] for row in queue["items"]]
    target_starts: dict[str, set[str]] = defaultdict(set)
    for row in queue["items"]:
        target_starts[row["CandidatePlanID"]].add(row["start"])
    checks = {
        "authority_GO": authority["decision"]
        == "GO_PHASE1_V2_OUTCOME_FREE_SCREEN_FREEZE",
        "design_count_exact": design["counts"] == {
            "full_registered_joints": 87_399,
            "strict_dominance_eligible_joints": 34_245,
            "complete_primary_CNOT_singletons": 485,
            "screen_joints": 148,
            "screen_targets": 633,
            "two_start_requests": 1_266,
        },
        "queue_counts_exact": queue["counts"]["requests"] == 1_266
        and queue["counts"]["targets"] == 633,
        "request_ids_unique": len(request_ids) == len(set(request_ids)),
        "exactly_two_starts_per_target": all(
            starts == set(STARTS) for starts in target_starts.values()
        )
        and len(target_starts) == 633,
        "all_NOT_STARTED": queue["counts"]["NOT_STARTED"] == 1_266
        and all(row["status"] == "NOT_STARTED" for row in queue["items"]),
        "all_outcome_work_zero": all(
            queue["counts"][key] == 0
            for key in (
                "candidate_energy_evaluations",
                "optimizer_starts",
                "FCI_evaluations",
            )
        ),
        "no_population_frontier_claim": design["interpretation"][
            "population_frontier_claim"
        ]
        is False,
    }
    return {
        "schema": "phase1-frontier.v2-screen-freeze-audit.v1",
        "passed": all(checks.values()),
        "decision": "GO_PHASE1_V2_SCREEN_RUNNER_IMPLEMENTATION"
        if all(checks.values())
        else "NO_GO_PHASE1_V2_SCREEN_FREEZE",
        "checks": checks,
        "authority_sha256": _sha256(AUTHORITY_PATH),
        "design_sha256": _sha256(DESIGN_PATH),
        "queue_sha256": _sha256(QUEUE_PATH),
    }


def freeze_audit() -> dict[str, Any]:
    if AUDIT_PATH.exists():
        raise V2FreezeError("v2 audit already exists")
    value = audit()
    if not value["passed"]:
        raise V2FreezeError("v2 freeze audit failed")
    _write_exclusive(AUDIT_PATH, value)
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action",
        choices=("freeze-authority", "freeze-design", "freeze-queue", "audit", "freeze-audit"),
    )
    args = parser.parse_args()
    functions = {
        "freeze-authority": freeze_authority,
        "freeze-design": freeze_design,
        "freeze-queue": freeze_queue,
        "audit": audit,
        "freeze-audit": freeze_audit,
    }
    value = functions[args.action]()
    if args.action == "freeze-design":
        printable = {
            "schema": value["schema"],
            "design_digest": value["design_digest"],
            "counts": value["counts"],
        }
    elif args.action == "freeze-queue":
        printable = {
            "schema": value["schema"],
            "queue_digest": value["queue_digest"],
            "counts": value["counts"],
        }
    else:
        printable = value
    print(json.dumps(printable, indent=2, sort_keys=True))
    if args.action in {"audit", "freeze-audit"} and not value["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

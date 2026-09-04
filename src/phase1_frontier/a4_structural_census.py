"""Outcome-free complete structural census for the frozen Phase-1 language."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import re
import time
from typing import Any, Mapping, Sequence

from dvg_obs_ceo.block_ir import (
    CompressionCandidate,
    DVGBlock,
    recover_dvg_blocks,
)
from dvg_obs_ceo.resources import (
    RESOURCE_EVALUATOR_VERSION,
    AnsatzStructure,
    evaluate_full_circuit_resources,
    paper_era_backend,
)
from dvg_obs_ceo.identity import canonical_json_bytes as resource_canonical_json_bytes
from dvg_obs_ceo.telemetry import ResourceSnapshot
from v5_matched_work.atomic_artifacts import canonical_json_bytes

from .a2_source_lock import CASES, ROOT, _context
from .a3_grammar import (
    IDENTITY_VERSION,
    THREAD_POLICY,
    _certified_catalog,
    _digest,
    _representatives,
    _source_selection_iterations,
    _target_generator_digests,
    case_path,
)


A4_ROOT = ROOT / "artifacts" / "phase1-v1" / "a4-structural-census"
CAP_PATH = A4_ROOT / "a4-structural-safety-cap-v1.json"
AUDIT_PATH = A4_ROOT / "a4-structural-census-audit-v1.json"
FACTORIZED_CERT_PATH = A4_ROOT / "a4-factorized-counter-certification-v2.json"
STRUCTURAL_CAP = 100_000
CALIBRATION_MAX_SECONDS = 0.27120145899243653
CALIBRATION_REPEATS = 10
FACTORIZED_COUNTER_VERSION = "paper-era-factorized-exact-recount-v1"


class A4CensusError(RuntimeError):
    """Raised when a census cannot be proved complete and outcome-free."""


def _write_exclusive(path: Path, value: Mapping[str, Any]) -> None:
    payload = canonical_json_bytes(dict(value)) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    try:
        offset = 0
        while offset < len(payload):
            count = os.write(descriptor, payload[offset:])
            if count <= 0:
                raise A4CensusError("artifact write made no forward progress")
            offset += count
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def census_path(case_id: str, pass_number: int) -> Path:
    return A4_ROOT / f"pass-{pass_number}-v2" / f"{case_id}-census-v2.json"


def freeze_safety_cap() -> dict[str, Any]:
    if CAP_PATH.exists():
        raise A4CensusError(f"safety cap already frozen: {CAP_PATH}")
    counts: dict[str, Any] = {}
    total = 0
    for case_id in CASES:
        value = json.loads(case_path(case_id).read_text(encoding="utf-8"))
        unique = len(
            {
                row["StructuralTargetID"]
                for name in ("singletons", "joints")
                for row in value[name]
            }
        )
        counts[case_id] = {
            "canonical_singletons": value["canonical_singleton_count"],
            "registered_joints": value["joint_count"],
            "unique_StructuralTargetID": unique,
        }
        total += unique
    value = {
        "schema": "phase1-frontier.a4-structural-safety-cap.v1",
        "stage": "A4-pre-census",
        "cap_unique_StructuralTargetID": STRUCTURAL_CAP,
        "cap_basis": {
            "rule": (
                "fixed power-of-ten engineering ceiling; not selected by energy, "
                "optimizer, FCI, historical winner, or candidate ranking"
            ),
            "paper_era_H6_3A_source_recount_repeats": CALIBRATION_REPEATS,
            "observed_max_seconds_per_recount": CALIBRATION_MAX_SECONDS,
            "two_pass_serial_upper_estimate_hours_at_cap": (
                2 * STRUCTURAL_CAP * CALIBRATION_MAX_SECONDS / 3600
            ),
            "scope": "the four pre-registered E3 B2 sources only",
        },
        "observed_frozen_universe_counts_before_recount": counts,
        "total_unique_StructuralTargetID": total,
        "within_cap": total <= STRUCTURAL_CAP,
        "candidate_energy_evaluations": 0,
        "optimizer_starts": 0,
        "FCI_evaluations": 0,
        "disclosure": (
            "The registered structural counts were already known when this numeric "
            "engineering cap was fixed.  The cap admits the complete frozen universe "
            "and therefore censors no Phase-1 target."
        ),
    }
    value["cap_digest"] = _digest(value)
    _write_exclusive(CAP_PATH, value)
    return value


def _materialize(
    pool: Any,
    source: AnsatzStructure,
    blocks: Sequence[DVGBlock],
    candidates: Sequence[CompressionCandidate],
) -> tuple[AnsatzStructure, str]:
    by_id = {block.block_id: block for block in blocks}
    selected = sorted(
        ((by_id[candidate.source_block_id], candidate) for candidate in candidates),
        key=lambda item: item[0].ansatz_positions,
    )
    occupied: set[int] = set()
    for block, _candidate in selected:
        if occupied.intersection(block.ansatz_positions):
            raise A4CensusError("selected candidates overlap")
        occupied.update(block.ansatz_positions)
    replacement = {block.ansatz_positions[0]: (block, candidate) for block, candidate in selected}
    source_iterations = _source_selection_iterations(source)
    indices: list[int] = []
    selection_iterations: list[int] = []
    for position, source_index in enumerate(source.indices):
        if position in occupied and position not in replacement:
            continue
        item = replacement.get(position)
        if item is None:
            indices.append(int(source_index))
            selection_iterations.append(source_iterations[position])
            continue
        block, candidate = item
        if len(set(block.selection_iterations)) != 1:
            raise A4CensusError("source block crosses an ADAPT iteration")
        indices.extend(int(value) for value in candidate.target_pool_indices)
        selection_iterations.extend(
            [block.selection_iterations[0]] * len(candidate.target_pool_indices)
        )
    counts = tuple(
        sum(iteration <= current for iteration in selection_iterations)
        for current in range(1, len(source.cumulative_parameter_counts) + 1)
    )
    target = AnsatzStructure.create(indices, [0.0] * len(indices), counts)
    payload = {
        "version": IDENTITY_VERSION,
        "target_generator_digests": _target_generator_digests(pool, indices),
        "target_iteration_counts": list(counts),
        "target_selection_iterations": selection_iterations,
    }
    return target, "structural-target-v1:" + _digest(payload)


def _snapshot(value: Any) -> dict[str, Any]:
    return asdict(value.snapshot)


def _structural_coefficients(length: int, offset: int = 0) -> tuple[float, ...]:
    return tuple(
        0.2718281828459045 + 0.137035999084 * (offset + index + 1)
        for index in range(length)
    )


def _circuit_groups(pool: Any, indices: Sequence[int]) -> tuple[tuple[int, ...], ...]:
    """Mirror the pinned DVG_CEO grouping rule without building a full circuit."""

    groups: list[tuple[int, ...]] = []
    accumulator: list[int] = []
    for position, raw_index in enumerate(indices):
        index = int(raw_index)
        if index not in pool.parent_range:
            if accumulator:
                raise A4CensusError("unfinished MVP accumulator before OVP")
            groups.append((index,))
            continue
        accumulator.append(index)
        continues = (
            position + 1 < len(indices)
            and int(indices[position + 1]) in pool.parent_range
            and pool.get_qubits(int(indices[position + 1])) == pool.get_qubits(index)
        )
        if not continues:
            groups.append(tuple(accumulator))
            accumulator = []
    if accumulator:
        raise A4CensusError("unfinished MVP accumulator at target end")
    return tuple(groups)


def _fragment_operations(
    pool: Any,
    group: tuple[int, ...],
    cache: dict[tuple[int, ...], tuple[tuple[str, tuple[int, ...]], ...]],
) -> tuple[tuple[str, tuple[int, ...]], ...]:
    cached = cache.get(group)
    if cached is not None:
        return cached
    circuit = pool.get_circuit(list(group), list(_structural_coefficients(len(group))))
    qasm = paper_era_backend().get_qasm(circuit)
    operations: list[tuple[str, tuple[int, ...]]] = []
    for line in qasm.splitlines()[3:]:
        operation = line.split(" ", 1)[0]
        qubits = tuple(int(value) for value in re.findall(r"q\[(\d+)\]", line))
        if qubits:
            operations.append((operation, qubits))
    cache[group] = tuple(operations)
    return cache[group]


def factorized_exact_resources(
    pool: Any,
    structure: AnsatzStructure,
    cache: dict[tuple[int, ...], tuple[tuple[str, tuple[int, ...]], ...]],
) -> ResourceSnapshot:
    """Recount the complete pinned circuit from exact cached circuit fragments.

    This is not a resource estimate.  Each registered DVG_CEO circuit group is
    built by the pinned upstream implementation.  Its QASM operation stream is
    concatenated in target order and scheduled with the same rules as the
    paper-era counters.  Full-circuit parity is required before H6 use.
    """

    structure.validate()
    full_depth = [0] * pool.n
    cnot_depth = [0] * pool.n
    cnot_count = 0
    start = 0
    for stop in structure.cumulative_parameter_counts:
        for group in _circuit_groups(pool, structure.indices[start:stop]):
            for operation, qubits in _fragment_operations(pool, group, cache):
                if operation == "barrier":
                    layer = max(full_depth[index] for index in qubits)
                    for index in qubits:
                        full_depth[index] = layer
                    continue
                layer = max(full_depth[index] for index in qubits) + 1
                for index in qubits:
                    full_depth[index] = layer
                if operation.startswith("cx"):
                    cnot_count += 1
                    cnot_layer = max(cnot_depth[index] for index in qubits) + 1
                    for index in qubits:
                        cnot_depth[index] = cnot_layer
        start = stop
    blocks = recover_dvg_blocks(
        pool,
        structure.indices,
        structure.coefficients,
        structure.cumulative_parameter_counts,
    )
    structural_payload = {
        "evaluator_version": RESOURCE_EVALUATOR_VERSION,
        "backend_version": paper_era_backend().version,
        "indices": list(structure.indices),
        "iteration_counts": list(structure.cumulative_parameter_counts),
        "block_ids": [block.block_id for block in blocks],
        "circuit_implementation_ids": [
            block.circuit_implementation_id for block in blocks
        ],
    }
    structure_digest = hashlib.sha256(
        resource_canonical_json_bytes(structural_payload)
    ).hexdigest()
    return ResourceSnapshot(
        cnot_count,
        max(cnot_depth, default=0),
        max(full_depth, default=0),
        len(structure.indices),
        len(blocks),
        f"{RESOURCE_EVALUATOR_VERSION}:{paper_era_backend().version}",
        structure_digest,
    )


def _case_targets(
    case_id: str,
) -> tuple[Any, AnsatzStructure, Sequence[DVGBlock], list[tuple[dict[str, Any], list[CompressionCandidate]]]]:
    grammar = json.loads(case_path(case_id).read_text(encoding="utf-8"))
    grammar_digest = grammar.pop("case_digest", None)
    if grammar_digest != _digest(grammar):
        raise A4CensusError("A3 grammar digest is invalid")
    _source_record, context, source, blocks, raw = _certified_catalog(case_id)
    representatives, _aliases = _representatives(raw)
    candidate_by_id = {value.candidate_id: value for value in representatives}
    singleton_candidates = [
        candidate_by_id[row["candidate_ids"][0]] for row in grammar["singletons"]
    ]
    targets: list[tuple[dict[str, Any], list[CompressionCandidate]]] = []
    for row in grammar["singletons"]:
        targets.append((row, [candidate_by_id[row["candidate_ids"][0]]]))
    for row in grammar["joints"]:
        targets.append(
            (row, [singleton_candidates[index] for index in row["singleton_ordinals"]])
        )
    return context, source, blocks, targets


def _operations_at_offset(
    pool: Any, group: tuple[int, ...], offset: int
) -> tuple[tuple[str, tuple[int, ...]], ...]:
    circuit = pool.get_circuit(
        list(group), list(_structural_coefficients(len(group), offset))
    )
    qasm = paper_era_backend().get_qasm(circuit)
    return tuple(
        (
            line.split(" ", 1)[0].split("(", 1)[0],
            tuple(int(value) for value in re.findall(r"q\[(\d+)\]", line)),
        )
        for line in qasm.splitlines()[3:]
        if re.findall(r"q\[(\d+)\]", line)
    )


def certify_factorized_counter() -> dict[str, Any]:
    if FACTORIZED_CERT_PATH.exists():
        raise A4CensusError(
            f"factorized counter certification already exists: {FACTORIZED_CERT_PATH}"
        )
    checks: dict[str, Any] = {}
    all_valid = True
    for case_id in CASES:
        context, source, blocks, targets = _case_targets(case_id)
        cache: dict[tuple[int, ...], tuple[tuple[str, tuple[int, ...]], ...]] = {}
        groups: set[tuple[int, ...]] = set()
        source_start = 0
        for source_stop in source.cumulative_parameter_counts:
            groups.update(
                _circuit_groups(context.pool, source.indices[source_start:source_stop])
            )
            source_start = source_stop
        materialized: list[tuple[dict[str, Any], AnsatzStructure]] = []
        for row, candidates in targets:
            target, structural_id = _materialize(context.pool, source, blocks, candidates)
            if structural_id != row["StructuralTargetID"]:
                raise A4CensusError("certification materialization ID mismatch")
            target_start = 0
            for target_stop in target.cumulative_parameter_counts:
                groups.update(
                    _circuit_groups(context.pool, target.indices[target_start:target_stop])
                )
                target_start = target_stop
            materialized.append((row, target))
        topology_invariant = all(
            _operations_at_offset(context.pool, group, 0)
            == _operations_at_offset(context.pool, group, 17)
            == _operations_at_offset(context.pool, group, 173)
            for group in sorted(groups)
        )
        canonical_source = _snapshot(
            evaluate_full_circuit_resources(
                context.pool,
                source,
                paper_era_backend(),
                coefficient_policy="deterministic-structural",
            )
        )
        factorized_source = asdict(
            factorized_exact_resources(context.pool, source, cache)
        )
        source_parity = canonical_source == factorized_source

        canonical_target_parity = True
        parity_target_count = 0
        if case_id in {"lih-3.0", "beh2-3.0"}:
            stored = json.loads(census_path(case_id, 1).read_text(encoding="utf-8"))
            stored_by_id = {
                row["StructuralTargetID"]: row["resources"] for row in stored["rows"]
            }
            for row, target in materialized:
                parity_target_count += 1
                if asdict(factorized_exact_resources(context.pool, target, cache)) != stored_by_id[
                    row["StructuralTargetID"]
                ]:
                    canonical_target_parity = False
                    break
        else:
            # Every atomic replacement is checked with the canonical full-circuit
            # implementation.  Joint targets are direct sums of two such disjoint
            # replacements, while every distinct circuit fragment is covered by
            # the coefficient/topology invariance test above.
            grammar = json.loads(case_path(case_id).read_text(encoding="utf-8"))
            singleton_ids = {
                row["StructuralTargetID"] for row in grammar["singletons"]
            }
            for row, target in materialized:
                if row["StructuralTargetID"] not in singleton_ids:
                    continue
                parity_target_count += 1
                canonical = _snapshot(
                    evaluate_full_circuit_resources(
                        context.pool,
                        target,
                        paper_era_backend(),
                        coefficient_policy="deterministic-structural",
                    )
                )
                if asdict(factorized_exact_resources(context.pool, target, cache)) != canonical:
                    canonical_target_parity = False
                    break
        valid = topology_invariant and source_parity and canonical_target_parity
        all_valid &= valid
        checks[case_id] = {
            "status": "VALID" if valid else "INVALID",
            "distinct_pinned_circuit_fragments": len(groups),
            "fragment_topology_invariant_at_offsets_0_17_173": topology_invariant,
            "source_full_circuit_parity": source_parity,
            "canonical_target_parity": canonical_target_parity,
            "canonical_target_parity_count": parity_target_count,
            "registered_target_count": len(materialized),
        }
    value = {
        "schema": "phase1-frontier.a4-factorized-counter-certification.v2",
        "counter_version": FACTORIZED_COUNTER_VERSION,
        "passed": all_valid,
        "checks": checks,
        "proof_boundary": (
            "Exact pinned fragment QASM plus the paper-era scheduling rules; all "
            "distinct fragments are coefficient-topology checked, all sources and "
            "all singleton targets are full-circuit checked, and all previously "
            "completed LiH/BeH2 targets are checked."
        ),
        "v1_negative_evidence": (
            "a4-factorized-counter-certification-v1.json retained; v1 compared "
            "parameterized gate labels and used the artifact JSON serializer for "
            "the upstream structure digest, so it correctly failed closed"
        ),
        "candidate_energy_evaluations": 0,
        "optimizer_starts": 0,
        "FCI_evaluations": 0,
    }
    value["certification_digest"] = _digest(value)
    _write_exclusive(FACTORIZED_CERT_PATH, value)
    if not all_valid:
        raise A4CensusError("factorized exact counter certification failed")
    return value


def build_case(case_id: str) -> dict[str, Any]:
    cap = json.loads(CAP_PATH.read_text(encoding="utf-8"))
    cap_digest = cap.pop("cap_digest", None)
    if cap_digest != _digest(cap) or not cap["within_cap"]:
        raise A4CensusError("A4 safety cap is absent, invalid, or exceeded")
    certification = json.loads(FACTORIZED_CERT_PATH.read_text(encoding="utf-8"))
    certification_digest = certification.pop("certification_digest", None)
    if certification_digest != _digest(certification) or not certification["passed"]:
        raise A4CensusError("factorized exact counter is not certified")
    grammar = json.loads(case_path(case_id).read_text(encoding="utf-8"))
    grammar_digest = grammar.pop("case_digest", None)
    if grammar_digest != _digest(grammar):
        raise A4CensusError("A3 grammar digest is invalid")

    source_record, context, source, blocks, raw = _certified_catalog(case_id)
    representatives, _aliases = _representatives(raw)
    candidate_by_id = {value.candidate_id: value for value in representatives}
    singleton_candidates = [
        candidate_by_id[row["candidate_ids"][0]] for row in grammar["singletons"]
    ]
    backend = paper_era_backend()
    fragment_cache: dict[
        tuple[int, ...], tuple[tuple[str, tuple[int, ...]], ...]
    ] = {}
    source_resources = _snapshot(
        evaluate_full_circuit_resources(
            context.pool, source, backend, coefficient_policy="deterministic-structural"
        )
    )
    rows: list[dict[str, Any]] = []
    seen_structures: set[str] = set()
    started = time.perf_counter()
    for target_class, records in (
        ("singleton", grammar["singletons"]),
        ("joint-K2", grammar["joints"]),
    ):
        for row in records:
            if target_class == "singleton":
                selected = [candidate_by_id[row["candidate_ids"][0]]]
            else:
                selected = [singleton_candidates[i] for i in row["singleton_ordinals"]]
            target, structural_id = _materialize(
                context.pool, source, blocks, selected
            )
            if structural_id != row["StructuralTargetID"]:
                raise A4CensusError("materialized StructuralTargetID mismatch")
            if structural_id in seen_structures:
                raise A4CensusError("A3 contains duplicate StructuralTargetID")
            seen_structures.add(structural_id)
            resources = asdict(
                factorized_exact_resources(context.pool, target, fragment_cache)
            )
            delta = {
                key: int(resources[key]) - int(source_resources[key])
                for key in (
                    "cnot_count",
                    "cnot_depth",
                    "total_depth",
                    "parameter_count",
                    "logical_block_count",
                )
            }
            rows.append(
                {
                    "StructuralTargetID": structural_id,
                    "CandidatePlanID": row["CandidatePlanID"],
                    "target_class": target_class,
                    "certificate_class": (
                        "globally-unitary-exact-affine-atomic"
                        if target_class == "singleton"
                        else "globally-unitary-exact-affine-direct-sum"
                    ),
                    "resources": resources,
                    "resource_delta_from_B2": delta,
                    "primary_CNOT_resource_positive": delta["cnot_count"] < 0,
                }
            )
    rows.sort(key=lambda value: value["CandidatePlanID"])
    singleton_structures = {
        row["StructuralTargetID"] for row in rows if row["target_class"] == "singleton"
    }
    joint_only_positive = sum(
        row["target_class"] == "joint-K2"
        and row["StructuralTargetID"] not in singleton_structures
        and row["primary_CNOT_resource_positive"]
        for row in rows
    )
    value = {
        "schema": "phase1-frontier.a4-structural-census.v2",
        "stage": "A4",
        "case_id": case_id,
        "B2SourceID": source_record["B2SourceID"],
        "A3_case_digest": grammar_digest,
        "A4_cap_digest": cap_digest,
        "factorized_counter_certification_digest": certification_digest,
        "resource_recount_method": FACTORIZED_COUNTER_VERSION,
        "source_resources": source_resources,
        "unique_structural_target_count": len(rows),
        "singleton_count": grammar["canonical_singleton_count"],
        "joint_count": grammar["joint_count"],
        "joint_only_resource_positive_count": joint_only_positive,
        "rows": rows,
        "elapsed_seconds_observational_not_identity": time.perf_counter() - started,
        "candidate_energy_evaluations": 0,
        "optimizer_starts": 0,
        "FCI_evaluations": 0,
    }
    identity = dict(value)
    identity.pop("elapsed_seconds_observational_not_identity")
    value["census_digest"] = _digest(identity)
    return value


def freeze_case(case_id: str, pass_number: int) -> dict[str, Any]:
    destination = census_path(case_id, pass_number)
    if destination.exists():
        raise A4CensusError(f"census pass already exists: {destination}")
    value = build_case(case_id)
    _write_exclusive(destination, value)
    return {
        "case_id": case_id,
        "pass": pass_number,
        "targets": value["unique_structural_target_count"],
        "joint_only_resource_positive_count": value[
            "joint_only_resource_positive_count"
        ],
        "census_digest": value["census_digest"],
        "elapsed_seconds": value["elapsed_seconds_observational_not_identity"],
    }


def audit() -> dict[str, Any]:
    results: dict[str, Any] = {}
    passed = True
    complete = True
    signal = False
    for case_id in CASES:
        paths = [census_path(case_id, number) for number in (1, 2)]
        if not all(path.is_file() for path in paths):
            results[case_id] = {"status": "MISSING_PASS"}
            passed = False
            complete = False
            continue
        values = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
        identities = []
        valid = True
        for value in values:
            digest = value.pop("census_digest", None)
            value.pop("elapsed_seconds_observational_not_identity", None)
            valid &= digest == _digest(value)
            identities.append(canonical_json_bytes(value))
            valid &= value["candidate_energy_evaluations"] == 0
            valid &= value["optimizer_starts"] == 0
            valid &= value["FCI_evaluations"] == 0
        valid &= identities[0] == identities[1]
        count = values[0]["joint_only_resource_positive_count"]
        signal |= count > 0
        passed &= valid
        results[case_id] = {
            "status": "VALID" if valid else "INVALID",
            "target_count": values[0]["unique_structural_target_count"],
            "joint_only_resource_positive_count": count,
            "byte_identical_identity_payload": identities[0] == identities[1],
        }
    decision = (
        "INCOMPLETE_A4_CENSUS"
        if not complete
        else "NO_GO_A4_CENSUS_INVALID"
        if not passed
        else (
            "GO_A5_E2_CERTIFICATION_AND_QUEUE_FREEZE"
            if signal
            else "STOP_P1_NO_JOINT_RESOURCE_SIGNAL"
        )
    )
    return {
        "schema": "phase1-frontier.a4-structural-census-audit.v1",
        "passed": passed,
        "complete": complete,
        "joint_only_resource_signal_exists": signal,
        "decision": decision,
        "cases": results,
    }


def freeze_audit() -> dict[str, Any]:
    if AUDIT_PATH.exists():
        raise A4CensusError(f"audit already frozen: {AUDIT_PATH}")
    value = audit()
    if not value["passed"]:
        raise A4CensusError("cannot freeze invalid A4 census")
    value["artifact_sha256"] = {
        str(census_path(case_id, number).relative_to(ROOT)): hashlib.sha256(
            census_path(case_id, number).read_bytes()
        ).hexdigest()
        for case_id in CASES
        for number in (1, 2)
    }
    value["audit_digest"] = _digest(value)
    _write_exclusive(AUDIT_PATH, value)
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze-cap", action="store_true")
    parser.add_argument("--certify-factorized-counter", action="store_true")
    parser.add_argument("--case", choices=CASES)
    parser.add_argument("--pass-number", type=int, choices=(1, 2))
    parser.add_argument("--audit", action="store_true")
    parser.add_argument("--freeze-audit", action="store_true")
    args = parser.parse_args()
    actions = sum(
        (
            args.freeze_cap,
            args.certify_factorized_counter,
            args.case is not None,
            args.audit,
            args.freeze_audit,
        )
    )
    if actions != 1 or (args.case is not None) != (args.pass_number is not None):
        parser.error("choose one action; --case requires --pass-number")
    if args.freeze_cap:
        value = freeze_safety_cap()
    elif args.certify_factorized_counter:
        value = certify_factorized_counter()
    elif args.case is not None:
        value = freeze_case(args.case, args.pass_number)
    elif args.freeze_audit:
        value = freeze_audit()
    else:
        value = audit()
    print(json.dumps(value, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

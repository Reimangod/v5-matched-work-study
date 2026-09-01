"""Canonical B2 source reconstruction and same-topology reoptimization.

Each optimizer start is an immutable request so interruption cannot erase or
silently repeat paid work.  This stage never enumerates compression targets and
never evaluates FCI/CCSD.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import struct
from typing import Any, Mapping, Sequence

import numpy as np

from dvg_obs_ceo.block_ir import recover_dvg_blocks
from dvg_obs_ceo.identity import StatePreparationSpec
from dvg_obs_ceo.molecular_identity import generator_definition_digest
from dvg_obs_ceo.resources import AnsatzStructure
from v5_matched_work.atomic_artifacts import canonical_json_bytes

from v5_final.parent_native_development_runtime_factory_v1 import (
    PLAN_PATH,
    build_queue_bound_development_runtime_v1,
)
from v5_final.parent_native_execution_services import ActualOptimizationBoundary

from .a1_vertical_slice import A1KernelBoundary
from .a1_vertical_slice import A1_AUDIT
from .authority import audit_committed_manifest


ROOT = Path(__file__).resolve().parents[2]
A2_ROOT = ROOT / "artifacts" / "phase1-v1" / "a2-b2-source-lock"
A2_AUDIT = A2_ROOT / "a2-source-lock-audit-v1.json"
CASES = ("lih-3.0", "h6-1.5", "h6-3.0", "beh2-3.0")
STARTS = ("mapped-warm-start", "zero-target-coordinate")
THREAD_POLICY = {
    "OMP_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
}


class A2SourceError(RuntimeError):
    """Raised when a B2 source request is invalid or cannot be certified."""


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _float_hex(value: float) -> str:
    return struct.pack(">d", float(value)).hex()


def _write_exclusive(path: Path, value: Mapping[str, Any]) -> None:
    payload = canonical_json_bytes(dict(value)) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    try:
        offset = 0
        while offset < len(payload):
            count = os.write(descriptor, payload[offset:])
            if count <= 0:
                raise A2SourceError("A2 artifact write made no forward progress")
            offset += count
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _verify_authority() -> None:
    if not audit_committed_manifest()["passed"]:
        raise A2SourceError("A0 authority is invalid")
    if not A1_AUDIT.is_file():
        raise A2SourceError("A1 readiness audit is absent")
    a1 = json.loads(A1_AUDIT.read_text(encoding="utf-8"))
    if a1.get("decision") != "GO_A2_SOURCE_LOCK" or not a1.get("passed"):
        raise A2SourceError("A1 does not authorize A2")
    for name, expected in THREAD_POLICY.items():
        if os.environ.get(name) != expected:
            raise A2SourceError(
                f"A2 thread policy mismatch: {name}={os.environ.get(name)!r}"
            )


def _context(case_id: str) -> Any:
    if case_id not in CASES:
        raise A2SourceError(f"unregistered A2 case: {case_id}")
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    matches = [
        item
        for item in plan["items"]
        if item["case_id"] == case_id
        and item["method_id"] == "immutable-ceo-star-source"
        and item["work_envelope"] == "LOW"
    ]
    if len(matches) != 1:
        raise A2SourceError("immutable B0 queue binding is absent or ambiguous")
    return build_queue_bound_development_runtime_v1(matches[0]["queue_item_id"])


def _compact_events(boundary: A1KernelBoundary) -> tuple[list[dict[str, Any]], str]:
    chain = "0" * 64
    events: list[dict[str, Any]] = []
    for sequence, event in enumerate(boundary.events):
        record = {
            "sequence": sequence,
            "operation": event.operation,
            "outcome": event.outcome,
            "units": event.units,
            "evidence_digest": _digest(event.evidence),
        }
        chain = _digest({"previous": chain, "event": record})
        events.append(record)
    return events, chain


def _state_and_energy(
    context: Any,
    boundary: A1KernelBoundary,
    coordinates: np.ndarray,
    indices: Sequence[int],
) -> tuple[np.ndarray, float, str]:
    from qiskit.quantum_info import Statevector

    def build_state() -> np.ndarray:
        circuit = context.pool.get_circuit(list(indices), list(coordinates))
        reference = np.asarray(context._actual_algorithm.ref_state.toarray()).ravel()
        state = np.asarray(Statevector(reference).evolve(circuit).data)
        state /= np.linalg.norm(state)
        return state

    state = np.asarray(
        boundary.invoke(
            "independent-statevector-certification",
            build_state,
            evidence={"route": "qiskit-Statevector-from-reference"},
        ),
        dtype=np.complex128,
    )
    energy = float(
        boundary.invoke(
            "independent-energy-certification",
            lambda: float(
                np.real(np.vdot(state, context._actual_algorithm.hamiltonian @ state))
            ),
            evidence={"route": "direct-Hamiltonian-expectation"},
        )
    )
    state_sha = hashlib.sha256(np.asarray(state, dtype=">c16").tobytes()).hexdigest()
    return state, energy, state_sha


def _state_preparation_id(context: Any, structure: AnsatzStructure) -> str:
    blocks = recover_dvg_blocks(
        context.pool,
        structure.indices,
        structure.coefficients,
        structure.cumulative_parameter_counts,
    )
    spec = StatePreparationSpec.create(
        reference_state=context._actual_algorithm.ref_det,
        generator_definition_digest=generator_definition_digest(context.pool),
        ansatz_block_structure=(
            (block.family, block.pool_indices) for block in blocks
        ),
        ansatz_indices=structure.indices,
        coefficients=structure.coefficients,
        orbital_parameters=(),
        qubit_mapping="openfermion-jordan-wigner-v1",
        qubit_ordering=range(int(context._actual_algorithm.n)),
    )
    return spec.state_preparation_id


def _resource_record(kernels: ActualOptimizationBoundary, structure: AnsatzStructure) -> tuple[dict[str, Any], str]:
    first = kernels.resources(structure)
    second = kernels.resources(structure)
    if (
        first.snapshot != second.snapshot
        or first.circuit_qasm_digest != second.circuit_qasm_digest
    ):
        raise A2SourceError("independent B2 resource recount is not repeatable")
    return asdict(first.snapshot), first.circuit_qasm_digest


def start_path(case_id: str, start: str) -> Path:
    return A2_ROOT / "starts-v2" / case_id / f"{start}.json"


def legacy_start_path(case_id: str, start: str) -> Path:
    return A2_ROOT / "starts" / case_id / f"{start}.json"


def source_path(case_id: str) -> Path:
    return A2_ROOT / "sources" / f"{case_id}-b2.json"


def run_start(case_id: str, start: str) -> dict[str, Any]:
    _verify_authority()
    if start not in STARTS:
        raise A2SourceError(f"unregistered A2 start: {start}")
    destination = start_path(case_id, start)
    if destination.exists():
        raise A2SourceError(f"A2 start already terminal: {destination}")
    context = _context(case_id)
    source = context.runtime.ansatz
    dimension = len(source.indices)
    if start == "mapped-warm-start":
        initial = np.asarray(source.coefficients, dtype=np.float64)
        inverse = np.asarray(context.runtime.inverse_hessian, dtype=np.float64)
        f0 = float(context.runtime.energy_hartree)
        g0 = np.asarray(context.runtime.gradient, dtype=np.float64)
    else:
        initial = np.zeros(dimension, dtype=np.float64)
        inverse = np.eye(dimension, dtype=np.float64)
        f0 = None
        g0 = None
    boundary = A1KernelBoundary()
    kernels = ActualOptimizationBoundary(
        context._actual_algorithm, context.pool, boundary
    )
    result = kernels.optimize(
        initial,
        source.indices,
        inverse,
        f0=f0,
        g0=g0,
    )
    coordinates = np.asarray(result.x, dtype=np.float64)
    structure = AnsatzStructure.create(
        source.indices, coordinates, source.cumulative_parameter_counts
    )
    state, independent_energy, state_sha = _state_and_energy(
        context, boundary, coordinates, source.indices
    )
    independent_gradient = np.asarray(
        boundary.invoke(
            "independent-full-gradient-certification",
            lambda: context._actual_algorithm.estimate_gradients(
                list(coordinates), list(source.indices), method="an"
            ),
            dimension=dimension,
            evidence={"route": "fresh-analytic-gradient-call"},
        ),
        dtype=np.float64,
    )
    resources, qasm_digest = _resource_record(kernels, structure)
    primary_gradient = np.asarray(result.jac, dtype=np.float64)
    gradient_inf = float(np.max(np.abs(independent_gradient), initial=0.0))
    checks = {
        "optimizer_completed": bool(result.success),
        "finite": bool(
            np.isfinite(float(result.fun))
            and np.all(np.isfinite(coordinates))
            and np.all(np.isfinite(independent_gradient))
        ),
        "energy_agreement": abs(float(result.fun) - independent_energy) <= 1e-10,
        "gradient_agreement": bool(
            primary_gradient.shape == independent_gradient.shape
            and np.max(
                np.abs(primary_gradient - independent_gradient), initial=0.0
            )
            <= 1e-8
        ),
        "stationary_at_1e-8": gradient_inf <= 1e-8,
        "topology_unchanged": tuple(structure.indices) == tuple(source.indices)
        and tuple(structure.cumulative_parameter_counts)
        == tuple(source.cumulative_parameter_counts),
        "resources_unchanged": all(
            resources[name] == context.source_resources[name]
            for name in (
                "cnot_count",
                "cnot_depth",
                "total_depth",
                "parameter_count",
                "logical_block_count",
            )
        ),
        "FCI_CCSD_absent": context._actual_algorithm.molecule.fci_energy is None
        and context._actual_algorithm.molecule.ccsd_energy is None,
    }
    events, chain = _compact_events(boundary)
    record: dict[str, Any] = {
        "schema": "phase1-frontier.a2-b2-start.v2",
        "stage": "A2",
        "case_id": case_id,
        "start": start,
        "terminal_status": "COMPLETED_CERTIFIED" if all(checks.values()) else "OPTIMIZER_REJECTED",
        "valid": all(checks.values()),
        "checks": checks,
        "B0": {
            "checkpoint_digest": context.source_checkpoint_digest,
            "state_preparation_id": context.state_preparation_id,
            "energy_hartree": float(context.runtime.energy_hartree),
            "resources": context.source_resources,
        },
        "ProblemID": context.problem_id,
        "Hamiltonian_digest": context.hamiltonian_digest,
        "energy_hartree": float(result.fun),
        "independent_energy_hartree": independent_energy,
        "gradient_infinity_norm": gradient_inf,
        "parameters_float64": [_float_hex(value) for value in coordinates],
        "gradient_float64": [_float_hex(value) for value in independent_gradient],
        "inverse_hessian_float64": [
            [_float_hex(value) for value in row]
            for row in np.asarray(result.hess_inv, dtype=np.float64)
        ],
        "statevector_sha256": state_sha,
        "StatePreparationID": _state_preparation_id(context, structure),
        "resources": resources,
        "qasm_digest": qasm_digest,
        "optimizer": {
            "success": bool(result.success),
            "status": int(result.status),
            "message": str(result.message),
            "iterations": int(result.nit),
            "energy_evaluations": int(result.nfev),
            "gradient_evaluations": int(result.njev),
        },
        "raw_counter_totals": boundary.totals(),
        "raw_events": events,
        "raw_event_chain_digest": chain,
        "candidate_generation_count": 0,
        "FCI_evaluations": 0,
    }
    record["record_digest"] = _digest(record)
    _write_exclusive(destination, record)
    return record


def repair_legacy_start(case_id: str, start: str) -> dict[str, Any]:
    """Correct the v1 resource-vector comparison without rerunning a kernel."""

    _verify_authority()
    legacy = legacy_start_path(case_id, start)
    destination = start_path(case_id, start)
    if not legacy.is_file() or destination.exists():
        raise A2SourceError("legacy repair requires one v1 record and no v2 record")
    value = json.loads(legacy.read_text(encoding="utf-8"))
    old_digest = value.pop("record_digest", None)
    if old_digest != _digest(value):
        raise A2SourceError("legacy A2 start digest is invalid")
    source_resources = value["B0"]["resources"]
    resources = value["resources"]
    corrected = all(
        resources[name] == source_resources[name]
        for name in (
            "cnot_count",
            "cnot_depth",
            "total_depth",
            "parameter_count",
            "logical_block_count",
        )
    )
    if not corrected or value["checks"].get("resources_unchanged") is not False:
        raise A2SourceError("legacy record is not the registered comparison defect")
    value["schema"] = "phase1-frontier.a2-b2-start.v2"
    value["checks"]["resources_unchanged"] = True
    value["valid"] = all(value["checks"].values())
    value["terminal_status"] = (
        "COMPLETED_CERTIFIED" if value["valid"] else "OPTIMIZER_REJECTED"
    )
    value["additive_correction"] = {
        "kind": "RESOURCE_VECTOR_KEY_PROJECTION_ONLY",
        "legacy_path": str(legacy.relative_to(ROOT)),
        "legacy_file_sha256": hashlib.sha256(legacy.read_bytes()).hexdigest(),
        "legacy_record_digest": old_digest,
        "candidate_or_optimizer_rerun": False,
        "scientific_semantics_changed": False,
    }
    value["record_digest"] = _digest(value)
    _write_exclusive(destination, value)
    return value


def _decode(value: str) -> float:
    return struct.unpack(">d", bytes.fromhex(value))[0]


def finalize_case(case_id: str) -> dict[str, Any]:
    _verify_authority()
    destination = source_path(case_id)
    if destination.exists():
        raise A2SourceError(f"B2 source already exists: {destination}")
    records = [
        json.loads(start_path(case_id, start).read_text(encoding="utf-8"))
        for start in STARTS
    ]
    valid = [record for record in records if record.get("valid") is True]
    if not valid:
        status = "SOURCE_INELIGIBLE"
        selected = None
    else:
        status = "B2_ELIGIBLE"
        selected = min(valid, key=lambda value: (value["energy_hartree"], value["start"]))
    context = _context(case_id)
    source: dict[str, Any] = {
        "schema": "phase1-frontier.a2-b2-source.v1",
        "stage": "A2",
        "case_id": case_id,
        "status": status,
        "selected_start": None if selected is None else selected["start"],
        "ProblemID": context.problem_id,
        "Hamiltonian_digest": context.hamiltonian_digest,
        "B0_checkpoint_digest": context.source_checkpoint_digest,
        "B0_state_preparation_id": context.state_preparation_id,
        "ansatz_indices": list(context.runtime.ansatz.indices),
        "iteration_counts": list(
            context.runtime.ansatz.cumulative_parameter_counts
        ),
        "B2": None,
        "start_record_sha256": {
            start: hashlib.sha256(start_path(case_id, start).read_bytes()).hexdigest()
            for start in STARTS
        },
        "candidate_generation_count": 0,
        "FCI_evaluations": 0,
    }
    if selected is not None:
        source["B2"] = {
            "StatePreparationID": selected["StatePreparationID"],
            "energy_hartree": selected["energy_hartree"],
            "parameters_float64": selected["parameters_float64"],
            "parameters": [_decode(value) for value in selected["parameters_float64"]],
            "gradient_float64": selected["gradient_float64"],
            "gradient_infinity_norm": selected["gradient_infinity_norm"],
            "inverse_hessian_float64": selected["inverse_hessian_float64"],
            "statevector_sha256": selected["statevector_sha256"],
            "resources": selected["resources"],
            "qasm_digest": selected["qasm_digest"],
            "raw_counter_totals_by_start": {
                record["start"]: record["raw_counter_totals"] for record in records
            },
        }
        source["B2SourceID"] = "b2-source-v1:" + _digest(
            {
                "case_id": case_id,
                "ProblemID": context.problem_id,
                "Hamiltonian_digest": context.hamiltonian_digest,
                "StatePreparationID": selected["StatePreparationID"],
                "optimizer_contract": "phase1-two-start-bfgs-gtol-1e-8-v1",
            }
        )
    source["source_digest"] = _digest(source)
    _write_exclusive(destination, source)
    return source


def audit() -> dict[str, Any]:
    details: dict[str, Any] = {}
    eligible = 0
    for case_id in CASES:
        source_file = source_path(case_id)
        start_files = [start_path(case_id, start) for start in STARTS]
        starts_exist = all(path.is_file() for path in start_files)
        start_digests_valid = starts_exist
        start_counters_closed = starts_exist
        if starts_exist:
            for path in start_files:
                start_value = json.loads(path.read_text(encoding="utf-8"))
                start_digest = start_value.pop("record_digest", None)
                start_digests_valid &= start_digest == _digest(start_value)
                start_counters_closed &= (
                    start_value.get("candidate_generation_count") == 0
                    and start_value.get("FCI_evaluations") == 0
                )
        source_valid = False
        source_bindings_valid = False
        status = "MISSING"
        if source_file.is_file():
            value = json.loads(source_file.read_text(encoding="utf-8"))
            digest = value.pop("source_digest", None)
            source_valid = digest == _digest(value)
            status = value.get("status", "INVALID")
            source_bindings_valid = starts_exist and value.get(
                "start_record_sha256"
            ) == {
                start: hashlib.sha256(start_path(case_id, start).read_bytes()).hexdigest()
                for start in STARTS
            }
            eligible += int(source_valid and status == "B2_ELIGIBLE")
        details[case_id] = {
            "both_starts_terminal": starts_exist,
            "start_record_digests_valid": start_digests_valid,
            "start_candidate_and_FCI_counts_zero": start_counters_closed,
            "source_digest_valid": source_valid,
            "source_to_start_file_bindings_valid": source_bindings_valid,
            "status": status,
        }
    incident_path = (
        A2_ROOT
        / "incidents"
        / "h6-1.5-zero-target-coordinate-attempt-1.json"
    )
    incident_preserved = False
    if incident_path.is_file():
        incident = json.loads(incident_path.read_text(encoding="utf-8"))
        incident_preserved = (
            incident.get("terminal_status") == "FAILED_ENGINEERING_PRESERVED"
            and incident.get("optimizer_endpoint_recorded") is False
            and incident.get("candidate_generation_count") == 0
            and incident.get("FCI_evaluations") == 0
            and start_path("h6-1.5", "zero-target-coordinate").is_file()
        )
    checks = {
        "all_cases_have_two_terminal_starts": all(
            value["both_starts_terminal"] for value in details.values()
        ),
        "all_source_records_valid": all(
            value["source_digest_valid"] for value in details.values()
        ),
        "all_start_record_digests_valid": all(
            value["start_record_digests_valid"] for value in details.values()
        ),
        "all_start_candidate_and_FCI_counts_zero": all(
            value["start_candidate_and_FCI_counts_zero"]
            for value in details.values()
        ),
        "all_source_to_start_file_bindings_valid": all(
            value["source_to_start_file_bindings_valid"]
            for value in details.values()
        ),
        "engineering_interruption_preserved_and_same_start_retried": incident_preserved,
        "useful_eligible_inventory_exists": eligible > 0,
        "no_candidate_generation": all(
            json.loads(source_path(case_id).read_text(encoding="utf-8"))[
                "candidate_generation_count"
            ]
            == 0
            for case_id in CASES
            if source_path(case_id).is_file()
        ),
        "no_FCI": all(
            json.loads(source_path(case_id).read_text(encoding="utf-8"))[
                "FCI_evaluations"
            ]
            == 0
            for case_id in CASES
            if source_path(case_id).is_file()
        ),
    }
    return {
        "schema": "phase1-frontier.a2-source-lock-audit.v1",
        "passed": all(checks.values()),
        "decision": (
            "GO_A3_GRAMMAR_AND_IDENTITIES"
            if all(checks.values())
            else "A2_INCOMPLETE_OR_NO_ELIGIBLE_SOURCE"
        ),
        "eligible_count": eligible,
        "checks": checks,
        "cases": details,
    }


def freeze_audit() -> dict[str, Any]:
    if A2_AUDIT.exists():
        raise A2SourceError(f"A2 audit already frozen: {A2_AUDIT}")
    value = audit()
    if not value["passed"]:
        raise A2SourceError("cannot freeze a failing A2 audit")
    value["artifact_file_sha256"] = {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(A2_ROOT.rglob("*.json"))
        if path != A2_AUDIT
    }
    value["audit_digest"] = _digest(value)
    _write_exclusive(A2_AUDIT, value)
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=CASES)
    parser.add_argument("--start", choices=STARTS)
    parser.add_argument("--finalize-case", choices=CASES)
    parser.add_argument("--repair-case", choices=CASES)
    parser.add_argument("--repair-start", choices=STARTS)
    parser.add_argument("--audit", action="store_true")
    parser.add_argument("--freeze-audit", action="store_true")
    args = parser.parse_args()
    modes = int(args.case is not None or args.start is not None) + int(
        args.finalize_case is not None
    ) + int(args.repair_case is not None or args.repair_start is not None) + int(
        args.audit
    ) + int(args.freeze_audit)
    if (
        modes != 1
        or (args.case is None) != (args.start is None)
        or (args.repair_case is None) != (args.repair_start is None)
    ):
        parser.error(
            "choose one complete --case/--start pair, --repair-case/--repair-start "
            "pair, --finalize-case, or --audit"
        )
    if args.audit:
        value = audit()
    elif args.freeze_audit:
        value = freeze_audit()
    elif args.finalize_case:
        value = finalize_case(args.finalize_case)
    elif args.repair_case:
        value = repair_legacy_start(args.repair_case, str(args.repair_start))
    else:
        value = run_start(str(args.case), str(args.start))
    if args.audit or args.freeze_audit:
        summary = value
    elif args.finalize_case:
        summary = {
            "case_id": value["case_id"],
            "status": value["status"],
            "selected_start": value.get("selected_start"),
            "B2SourceID": value.get("B2SourceID"),
            "source_digest": value["source_digest"],
        }
    else:
        summary = {
            "case_id": value["case_id"],
            "start": value["start"],
            "terminal_status": value["terminal_status"],
            "valid": value["valid"],
            "energy_hartree": value["energy_hartree"],
            "gradient_infinity_norm": value["gradient_infinity_norm"],
            "optimizer": value["optimizer"],
            "record_digest": value["record_digest"],
        }
    print(json.dumps(summary, indent=2, sort_keys=True))
    if (args.audit or args.freeze_audit) and not value["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

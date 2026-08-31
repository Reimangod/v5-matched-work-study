"""P3 fixed-coordinate CPU/A100 parity runner.

The runner never optimizes a molecular candidate and never evaluates FCI.  It
reconstructs the frozen source ansatz, checks its identity and catalog order,
then compares CPU source data with an explicitly verified Aer GPU statevector.
Gradients use a five-point GPU-statevector finite-difference stencil solely as
an independent validation observable; the production optimizer remains bound
to the pinned analytic CEO* gradient and is not changed here.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import struct
import sys
from types import SimpleNamespace
from typing import Any, Sequence

import numpy as np

from .aer_gpu_backend import (
    RouteCounters,
    build_gpu_backend,
    gpu_statevector,
    hybrid_gpu_state_cpu_sparse_energy,
    phase_aligned_max_error,
)
from .common import (
    ARTIFACT_ROOT,
    A100PilotError,
    digest,
    embedded_digest_valid,
    load_json,
    sha256_file,
)
from .p0_baseline import (
    CALIBRATION_PLAN,
    CASE_SPECS,
    DEVELOPMENT_PLAN,
    PROTOCOL,
    REFERENCE,
    _select_item,
)
from .sparse_hamiltonian_bundle import MANIFEST_V2


TRANSFER_MANIFEST = (
    ARTIFACT_ROOT
    / "p2-source-transfer/outcome-free-molecular-integral-bundle-v1.json"
)


def _from_float_hex(value: str) -> float:
    return float(struct.unpack(">d", bytes.fromhex(value))[0])


def build_context(alias: str) -> Any:
    if alias not in CASE_SPECS:
        raise A100PilotError(f"unknown frozen alias: {alias}")
    spec = CASE_SPECS[alias]
    if spec["plan"] == "calibration":
        import v5_final.parent_native_runtime_factory_v2 as runtime_module

        plan, environment = project_plan_to_aic_runtime(
            load_json(CALIBRATION_PLAN),
            load_json(runtime_module.ENVIRONMENT_PATH),
            required_threads=int(spec["threads"]),
        )
        item = _select_item(plan, str(spec["case_id"]))
        binding = runtime_module.preflight_plan_binding(
            item["queue_item_id"],
            plan_record=plan,
            environment_record=environment,
        )
        return _build_aic_context(alias, binding)
    import v5_final.parent_native_development_runtime_factory_v1 as runtime_module

    plan, environment = project_plan_to_aic_runtime(
        load_json(DEVELOPMENT_PLAN),
        load_json(runtime_module.ENVIRONMENT_PATH),
        required_threads=int(spec["threads"]),
    )
    item = _select_item(plan, str(spec["case_id"]))
    binding = runtime_module.preflight_development_binding_v1(
        item["queue_item_id"],
        plan_record=plan,
        environment_record=environment,
    )
    return _build_aic_context(alias, binding)


def _algorithm_from_transfer(alias: str, case_id: str) -> tuple[Any, Any]:
    """Build the pinned CEO kernel from the exact P0 integral transfer."""

    from openfermion import MolecularData
    from dvg_obs_ceo.baseline import _load_upstream

    manifest = load_json(TRANSFER_MANIFEST)
    if not embedded_digest_valid(manifest, "bundle_digest"):
        raise A100PilotError("P2 integral transfer manifest digest is invalid")
    matches = [case for case in manifest["cases"] if case["alias"] == alias]
    if len(matches) != 1 or matches[0]["case_id"] != case_id:
        raise A100PilotError("P2 integral transfer case binding differs")
    record = matches[0]
    path = (ARTIFACT_ROOT.parent.parent / str(record["path"])).resolve()
    if sha256_file(path) != record["sha256"]:
        raise A100PilotError("P2 integral transfer file SHA-256 differs")
    molecule = MolecularData(filename=str(path.with_suffix("")))
    molecule.load()
    if molecule.fci_energy is not None or molecule.ccsd_energy is not None:
        raise A100PilotError("FCI/CCSD outcome entered transferred molecule")
    LinAlgAdapt, DVG_CEO, _, _ = _load_upstream()
    pool = DVG_CEO(molecule)
    is_calibration = alias == "h2"
    thresholds = {"beh2": 1e-5}
    algorithm = LinAlgAdapt(
        pool=pool,
        molecule=molecule,
        verbose=False,
        max_adapt_iter=12 if is_calibration else 100,
        max_opt_iter=10000,
        full_opt=True,
        threshold=float(thresholds.get(alias, 1e-6)),
        convergence_criterion="total_g_norm",
        tetris=True,
        progressive_opt=False,
        candidates=1,
        sel_criterion="gradient",
        recycle_hessian=True,
        penalize_cnots=False,
        rand_degenerate=False,
        shots=None,
    )
    sparse_manifest = load_json(MANIFEST_V2)
    if not embedded_digest_valid(sparse_manifest, "bundle_digest"):
        raise A100PilotError("P2 sparse Hamiltonian transfer digest is invalid")
    matrix_matches = [
        value for value in sparse_manifest["cases"] if value["alias"] == alias
    ]
    if len(matrix_matches) != 1:
        raise A100PilotError("P2 sparse Hamiltonian transfer case is not unique")
    matrix_record = matrix_matches[0]
    matrix_path = (
        ARTIFACT_ROOT.parent.parent / str(matrix_record["path"])
    ).resolve()
    if sha256_file(matrix_path) != matrix_record["sha256"]:
        raise A100PilotError("P2 sparse Hamiltonian transfer SHA-256 differs")
    from scipy import sparse

    transferred_hamiltonian = sparse.load_npz(matrix_path).tocsc()
    if [int(value) for value in transferred_hamiltonian.shape] != matrix_record["shape"]:
        raise A100PilotError("P2 sparse Hamiltonian transfer shape differs")
    algorithm.hamiltonian = transferred_hamiltonian
    algorithm.energy_meas = algorithm.observable_to_measurement(transferred_hamiltonian)
    return algorithm, pool


def _build_aic_context(alias: str, binding: Any) -> Any:
    """Rebuild an audited same-node CPU reference without weakening production.

    The production factories require a byte-identical macOS sparse-state hash.
    Cross-platform P3 instead applies the pre-frozen numerical state tolerance
    to a same-node Qiskit CPU/Aer-GPU pair while retaining exact Hamiltonian,
    circuit, resource, state-preparation and candidate identities.
    """

    from qiskit.quantum_info import Statevector
    from dvg_obs_ceo.molecular_identity import problem_spec, state_preparation_spec
    from dvg_obs_ceo.resources import (
        AnsatzStructure,
        evaluate_full_circuit_resources,
        paper_era_backend,
    )
    from dvg_obs_ceo.telemetry import WorkCounters
    from dvg_obs_ceo.transaction import CompressionRuntime
    from v5_final.parent_native_runtime_factory import _resource_vector

    item = binding.queue_item
    case = binding.catalog_case
    checkpoint = binding.checkpoint
    algorithm, pool = _algorithm_from_transfer(alias, str(item["case_id"]))
    problem = problem_spec(algorithm=algorithm, case_id=str(item["case_id"]))
    if (
        problem.problem_id != item["ProblemID"]
        or problem.hamiltonian_digest != item["Hamiltonian_digest"]
        or problem.payload() != case["problem_payload"]
    ):
        raise A100PilotError("transferred molecular problem identity differs")
    structure = AnsatzStructure.create(
        checkpoint["ansatz_indices"],
        checkpoint["ansatz_coefficients"],
        checkpoint["iteration_counts"],
    )
    resources = evaluate_full_circuit_resources(pool, structure, paper_era_backend())
    resource_vector = _resource_vector(resources)
    if resource_vector != case["source_resources"]:
        raise A100PilotError("transferred source resources differ")
    registry_source = getattr(binding, "registry_source", None)
    if registry_source is not None and resources.snapshot.structure_digest != registry_source[
        "resources"
    ]["structure_digest"]:
        raise A100PilotError("transferred source structure digest differs")

    circuit = pool.get_circuit(list(structure.indices), list(structure.coefficients))
    reference = np.asarray(algorithm.ref_state.toarray(), dtype=np.complex128).ravel()
    state = np.asarray(Statevector(reference).evolve(circuit).data, dtype=np.complex128)
    state /= np.linalg.norm(state)
    runtime = CompressionRuntime.create(
        ansatz=structure,
        energy_hartree=float(checkpoint["energy_hartree"]),
        gradient=checkpoint["gradient"],
        inverse_hessian=checkpoint["recycled_inverse_hessian"],
        statevector=state,
        work=WorkCounters(),
        adapt_iteration=int(
            checkpoint.get(
                "adapt_iteration", len(structure.cumulative_parameter_counts)
            )
        ),
        metadata={
            "resource_structure_digest": resources.snapshot.structure_digest,
            "budget_reference_energy_hartree": float(checkpoint["energy_hartree"]),
            "queue_item_id": str(item["queue_item_id"]),
            "source_checkpoint_digest": checkpoint["checkpoint_digest"],
            "ProblemID": problem.problem_id,
            "aic_same_node_cpu_reference": True,
        },
    )
    preparation = state_preparation_spec(runtime, algorithm=algorithm, pool=pool)
    if (
        preparation.state_preparation_id != item["StatePreparationID"]
        or preparation.payload() != case["state_preparation_payload"]
    ):
        raise A100PilotError("transferred source preparation differs")
    return SimpleNamespace(
        queue_item_id=str(item["queue_item_id"]),
        case_id=str(item["case_id"]),
        plan_digest=str(binding.plan_digest),
        environment_digest=str(binding.environment_digest),
        source_checkpoint_digest=str(checkpoint["checkpoint_digest"]),
        problem_id=problem.problem_id,
        hamiltonian_digest=problem.hamiltonian_digest,
        state_preparation_id=preparation.state_preparation_id,
        source_resources=resource_vector,
        pool=pool,
        runtime=runtime,
        _actual_algorithm=algorithm,
    )


def project_plan_to_aic_runtime(
    source_plan: dict[str, Any],
    source_environment: dict[str, Any],
    *,
    required_threads: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Create an in-memory, outcome-free OS projection for the A100 pilot.

    Production artifacts remain byte-immutable.  Only platform identity and
    required thread values change; molecular, checkpoint, method and candidate
    fields are retained.  Queue IDs and plan digest are recomputed because they
    are content-addressed to the projected environment.
    """

    environment = deepcopy(source_environment)
    old_environment_digest = str(environment.pop("environment_digest"))
    environment["runtime"] = {
        "byte_order": sys.byteorder,
        "machine": platform.machine().lower(),
        "python_implementation": platform.python_implementation().lower(),
        "python_version": platform.python_version(),
        "system": platform.system().lower(),
    }
    environment["required_threads"] = {
        key: str(required_threads)
        for key in ("MKL_NUM_THREADS", "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS")
    }
    environment["aic_pilot_projection"] = {
        "source_environment_digest": old_environment_digest,
        "allowed_changes": ["runtime", "required_threads"],
        "production_artifact_changed": False,
        "scientific_source_changed": False,
    }
    environment["environment_digest"] = digest(environment)

    plan = deepcopy(source_plan)
    schema = str(plan["schema"])
    if schema.endswith("mb6-h2-h4-calibration-plan.v4"):
        prefix = "mb6-calibration-item-v4:"
    elif schema == "v5-final.s11-development-plan.v4":
        prefix = "development-queue-item-v4:"
    else:
        raise A100PilotError(f"unregistered plan projection schema: {schema}")
    plan.pop("plan_digest", None)
    plan["environment_digest"] = environment["environment_digest"]
    plan["aic_pilot_projection"] = {
        "source_plan_digest": source_plan["plan_digest"],
        "source_environment_digest": old_environment_digest,
        "production_artifact_changed": False,
    }
    for item in plan["items"]:
        item["environment_digest"] = environment["environment_digest"]
        item.pop("queue_item_id", None)
        item["queue_item_id"] = prefix + digest(item)
    plan["plan_digest"] = digest(plan)
    return plan, environment


def _reference_case(alias: str) -> dict[str, Any]:
    bundle = load_json(REFERENCE)
    matches = [case for case in bundle["cases"] if case["alias"] == alias]
    if len(matches) != 1:
        raise A100PilotError(f"frozen CPU reference not unique: {alias}")
    return matches[0]


def _gpu_energy(
    coefficients: Sequence[float],
    indices: Sequence[int],
    *,
    context: Any,
    reference: np.ndarray,
    backend: Any,
    counters: RouteCounters,
) -> float:
    circuit = context.pool.get_circuit(list(indices), list(coefficients))
    value, _, _ = hybrid_gpu_state_cpu_sparse_energy(
        reference,
        circuit,
        context._actual_algorithm.hamiltonian,
        backend=backend,
        counters=counters,
    )
    return value


def validation_gradient_five_point(
    coefficients: Sequence[float],
    indices: Sequence[int],
    *,
    context: Any,
    reference: np.ndarray,
    backend: Any,
    counters: RouteCounters,
    step: float = 1e-4,
) -> np.ndarray:
    """Independent derivative check; never supplied to the optimizer."""

    origin = np.asarray(coefficients, dtype=np.float64)
    values: list[float] = []
    for position in range(origin.size):
        energies: dict[int, float] = {}
        for multiple in (-2, -1, 1, 2):
            point = origin.copy()
            point[position] += multiple * step
            energies[multiple] = _gpu_energy(
                point,
                indices,
                context=context,
                reference=reference,
                backend=backend,
                counters=counters,
            )
        derivative = (
            energies[-2]
            - 8.0 * energies[-1]
            + 8.0 * energies[1]
            - energies[2]
        ) / (12.0 * step)
        counters.record_gpu_gradient_component()
        values.append(float(derivative))
    return np.asarray(values, dtype=np.float64)


def run_case(alias: str) -> dict[str, Any]:
    from v5_final.parent_native_candidate_adapter import build_typed_catalog

    protocol = load_json(PROTOCOL)
    expected = _reference_case(alias)
    context = build_context(alias)
    algorithm = context._actual_algorithm
    indices = [int(value) for value in context.runtime.ansatz.indices]
    coefficients = [float(value) for value in context.runtime.ansatz.coefficients]
    if indices != expected["ansatz_indices"]:
        raise A100PilotError("ansatz indices differ from frozen CPU reference")
    coefficient_hex = [struct.pack(">d", value).hex() for value in coefficients]
    if coefficient_hex != expected["coefficients_float64_hex"]:
        raise A100PilotError("ansatz coefficients differ from frozen CPU reference")

    cpu_state = np.asarray(context.runtime.statevector, dtype=np.complex128).ravel()
    cpu_sha = hashlib.sha256(np.asarray(cpu_state, dtype=">c16").tobytes()).hexdigest()
    reference = np.asarray(algorithm.ref_state.toarray(), dtype=np.complex128).ravel()
    circuit = context.pool.get_circuit(indices, coefficients)
    if hashlib.sha256(circuit.qasm().encode("utf-8")).hexdigest() != expected["source_qasm_sha256"]:
        raise A100PilotError("source circuit digest differs")
    catalog = build_typed_catalog(context.pool, context.runtime.ansatz)
    rebuilt_candidate_ids = [
        str(candidate.candidate_id) for candidate in catalog.candidates
    ]
    rebuilt_candidate_order_digest = digest(rebuilt_candidate_ids)
    # The GPU backend is a statevector backend, not a candidate-generation
    # backend.  Cross-platform catalog rebuilding is diagnostic only; the
    # operational pilot consumes the exact P0-frozen CPU catalog order.
    candidate_ids = [str(value) for value in expected["candidate_ids"]]
    candidate_order_digest = digest(candidate_ids)
    if candidate_order_digest != expected["candidate_order_digest"]:
        raise A100PilotError("P0-frozen candidate semantic order digest is invalid")
    if {key: int(value) for key, value in context.source_resources.items()} != expected["resources"]:
        raise A100PilotError("physical resource vector differs")

    counters = RouteCounters()
    counters.N_cpu_statevector += 1
    backend = build_gpu_backend()
    gpu_state, metadata = gpu_statevector(
        reference, circuit, backend=backend, counters=counters
    )
    state_error = phase_aligned_max_error(cpu_state, gpu_state)
    gpu_energy = float(
        np.real(np.vdot(gpu_state, algorithm.hamiltonian @ gpu_state))
    )
    counters.record_hybrid_energy()
    cpu_energy = _from_float_hex(expected["energy_hartree_float64_hex"])
    energy_error = abs(gpu_energy - cpu_energy)

    gpu_validation_gradient = validation_gradient_five_point(
        coefficients,
        indices,
        context=context,
        reference=reference,
        backend=backend,
        counters=counters,
    )
    cpu_gradient = np.asarray(
        [_from_float_hex(value) for value in expected["gradient_float64_hex"]],
        dtype=np.float64,
    )
    if gpu_validation_gradient.shape != cpu_gradient.shape:
        raise A100PilotError("gradient dimensions differ")
    gradient_error = float(
        np.max(np.abs(gpu_validation_gradient - cpu_gradient), initial=0.0)
    )
    tolerances = protocol["tolerances"]
    checks = {
        "state": state_error <= float(tolerances["phase_aligned_state_error_max"]),
        "energy": energy_error <= float(tolerances["absolute_energy_hartree_max"]),
        "gradient": gradient_error <= float(tolerances["max_gradient_component_max"]),
        "resources": True,
        "candidate_semantic_order": True,
        "explicit_gpu_metadata": str(metadata.get("device", "")).upper() == "GPU",
        "no_cpu_fallback": counters.N_cpu_fallback == 0,
    }
    return {
        "schema": "aic-a100-pilot.p3-case-parity.v1",
        "alias": alias,
        "case_id": expected["case_id"],
        "qubit_count": expected["qubit_count"],
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "errors": {
            "phase_aligned_state_max_abs": state_error,
            "absolute_energy_hartree": energy_error,
            "max_gradient_component": gradient_error,
        },
        "values": {
            "cpu_energy_hartree": cpu_energy,
            "gpu_energy_hartree": gpu_energy,
            "cpu_gradient": cpu_gradient.tolist(),
            "gpu_validation_gradient": gpu_validation_gradient.tolist(),
        },
        "gradient_validation": {
            "method": "five-point-central-finite-difference-of-GPU-statevector-energy",
            "step": 1e-4,
            "optimizer_binding": "VALIDATION_ONLY_NOT_USED_BY_OPTIMIZER",
            "production_optimizer_gradient": "PINNED_CEO_ANALYTIC_GRADIENT_UNCHANGED",
        },
        "identity": {
            "StatePreparationID": expected["StatePreparationID"],
            "ProblemID": expected["ProblemID"],
            "Hamiltonian_digest": expected["Hamiltonian_digest"],
            "statevector_sha256_cpu": cpu_sha,
            "statevector_sha256_frozen_mac_cpu": expected["statevector_sha256"],
            "frozen_mac_state_digest_reproduced_on_aic_cpu": (
                cpu_sha == expected["statevector_sha256"]
            ),
            "candidate_order_digest": candidate_order_digest,
            "aic_rebuilt_candidate_order_digest": rebuilt_candidate_order_digest,
            "aic_rebuilt_candidate_order_matches_frozen": (
                rebuilt_candidate_order_digest == candidate_order_digest
            ),
            "aic_projected_environment_digest": context.environment_digest,
            "aic_projected_plan_digest": context.plan_digest,
        },
        "resources": expected["resources"],
        "route_counters": counters.as_dict(),
        "candidate_molecular_energy_evaluations": 0,
        "optimizer_runs": 0,
        "FCI_evaluations": 0,
        "performance_claim_authorized": False,
        "reference_scope": {
            "state": "same-AIC-node Qiskit CPU versus Aer GPU under frozen numerical tolerance",
            "energy_and_gradient": "frozen P0 macOS CPU values",
            "exact_identities": [
                "Hamiltonian_digest",
                "ProblemID",
                "StatePreparationID",
                "source_qasm_sha256",
                "candidate_order_digest",
                "physical_resources",
            ],
        },
        "candidate_catalog_policy": {
            "operational_source": "P0_FROZEN_CPU_CATALOG_ORDER",
            "AIC_dynamic_rebuild_consumed": False,
            "AIC_dynamic_rebuild_is_diagnostic_only": True,
            "candidate_count": len(candidate_ids),
            "aic_rebuilt_candidate_count": len(rebuilt_candidate_ids),
            "reason": (
                "Candidate generation remains a pinned CPU responsibility; the "
                "A100 pilot changes only statevector execution."
            ),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=list(CASE_SPECS), required=True)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    output = arguments.output
    if output is None:
        raw_output = os.environ.get("A100_PARITY_OUTPUT")
        if not raw_output:
            raise RuntimeError("set --output or A100_PARITY_OUTPUT")
        output = Path(raw_output)
    result = run_case(arguments.case)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, sort_keys=True))
    if result["status"] != "PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    main()

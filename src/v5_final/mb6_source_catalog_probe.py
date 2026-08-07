"""Outcome-free H2/H4 source identity and structural-candidate probe.

Run this module with the pinned parent virtual environment.  It deliberately
guards every molecular state/energy/gradient/optimizer entrypoint while it
reconstructs immutable source identities and circuit-only candidate metadata.
"""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import tempfile
from typing import Any, Iterator

from dvg_obs_ceo.block_ir import candidate_to_dict, enumerate_candidates, recover_dvg_blocks
from dvg_obs_ceo.identity import StatePreparationSpec, canonical_json_bytes
from dvg_obs_ceo.molecular_identity import generator_definition_digest, problem_spec
from dvg_obs_ceo.resources import (
    AnsatzStructure,
    apply_candidate_structure,
    evaluate_full_circuit_resources,
    paper_era_backend,
)
from dvg_obs_ceo.baseline import _load_upstream

from .s0_successor import ROOT


CASES = {
    "h2-1.5-iteration-1": ROOT
    / "provenance/dvg-obs-ceo/artifacts/s8/calibration-bundle/checkpoint-h2-1.5-iteration-1.json",
    "h4-1.5-first-chemical-accuracy": ROOT
    / "provenance/dvg-obs-ceo/artifacts/s8/calibration-bundle/checkpoint-h4-1.5-first-chemical-accuracy.json",
}
FORBIDDEN_OUTPUT_KEYS = {
    "energy_hartree",
    "fci_energy_hartree",
    "absolute_error_hartree",
    "trajectory",
    "exact_hessian",
    "predictors",
}


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@contextmanager
def _molecular_kernel_guard() -> Iterator[dict[str, int]]:
    from adaptvqe.algorithms.adapt_vqe import AdaptVQE

    names = (
        "initialize",
        "run_iteration",
        "get_state",
        "compute_state",
        "evaluate_energy",
        "estimate_gradients",
        "optimize",
    )
    originals = {name: getattr(AdaptVQE, name) for name in names}
    calls = {name: 0 for name in names}

    def blocked(name: str):
        def stop(*_: Any, **__: Any) -> Any:
            calls[name] += 1
            raise RuntimeError(f"MB6 outcome-free guard blocked molecular kernel: {name}")

        return stop

    try:
        for name in names:
            setattr(AdaptVQE, name, blocked(name))
        yield calls
    finally:
        for name, value in originals.items():
            setattr(AdaptVQE, name, value)


def _checkpoint(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    # Strict allowlist: historical outcomes are not admitted to MB6 selection.
    return {
        "case_id": raw["case_id"],
        "ansatz_indices": raw["ansatz_indices"],
        "ansatz_coefficients": raw["ansatz_coefficients"],
        "iteration_counts": raw["iteration_counts"],
        "gradient_infinity": raw["gradient_infinity"],
        "checkpoint_digest": raw["checkpoint_digest"],
    }


def _algorithm_outcome_free(case_id: str) -> tuple[Any, Any]:
    """Build integrals/Hamiltonian without FCI, CCSD, state, or energy kernels."""

    from openfermion import MolecularData
    from openfermionpyscf import run_pyscf

    LinAlgAdapt, DVG_CEO, _, _ = _load_upstream()
    atom_count = 2 if case_id == "h2-1.5-iteration-1" else 4
    geometry = [("H", (0.0, 0.0, 1.5 * index)) for index in range(atom_count)]
    molecule = MolecularData(
        geometry,
        "sto-3g",
        1,
        0,
        description="H2" if atom_count == 2 else "H4",
        filename=str(Path(tempfile.gettempdir()) / f"v5-mb6-{case_id}"),
    )
    molecule = run_pyscf(
        molecule,
        run_scf=True,
        run_mp2=False,
        run_cisd=False,
        run_ccsd=False,
        run_fci=False,
    )
    if molecule.fci_energy is not None or molecule.ccsd_energy is not None:
        raise RuntimeError("MB6 FCI/CCSD firewall failed")
    pool = DVG_CEO(molecule)
    algorithm = LinAlgAdapt(
        pool=pool,
        molecule=molecule,
        verbose=False,
        max_adapt_iter=12,
        max_opt_iter=10000,
        full_opt=True,
        threshold=1e-6,
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
    return algorithm, pool


def _resource_vector(value: Any) -> dict[str, int]:
    snapshot = value.snapshot
    return {
        "cnot_count": snapshot.cnot_count,
        "cnot_depth": snapshot.cnot_depth,
        "total_depth": snapshot.total_depth,
        "parameter_count": snapshot.parameter_count,
        "logical_block_count": snapshot.logical_block_count,
    }


def _pareto_compression(before: dict[str, int], after: dict[str, int]) -> bool:
    return all(after[key] <= before[key] for key in before) and any(
        after[key] < before[key] for key in before
    )


def _delete_coordinate(structure: AnsatzStructure, position: int) -> AnsatzStructure:
    iteration = next(
        index for index, stop in enumerate(structure.cumulative_parameter_counts) if position < stop
    )
    counts = tuple(
        count if index < iteration else count - 1
        for index, count in enumerate(structure.cumulative_parameter_counts)
    )
    return AnsatzStructure.create(
        structure.indices[:position] + structure.indices[position + 1 :],
        structure.coefficients[:position] + structure.coefficients[position + 1 :],
        counts,
    )


def _case_record(case_id: str, path: Path) -> dict[str, Any]:
    checkpoint = _checkpoint(path)
    structure = AnsatzStructure.create(
        checkpoint["ansatz_indices"],
        checkpoint["ansatz_coefficients"],
        checkpoint["iteration_counts"],
    )
    algorithm, pool = _algorithm_outcome_free(case_id)
    blocks = recover_dvg_blocks(
        pool,
        structure.indices,
        structure.coefficients,
        structure.cumulative_parameter_counts,
    )
    state = StatePreparationSpec.create(
        reference_state=algorithm.ref_det,
        generator_definition_digest=generator_definition_digest(pool),
        ansatz_block_structure=((block.family, block.pool_indices) for block in blocks),
        ansatz_indices=structure.indices,
        coefficients=structure.coefficients,
        qubit_mapping="openfermion-jordan-wigner-v1",
        qubit_ordering=range(int(algorithm.n)),
    )
    problem = problem_spec(algorithm=algorithm, case_id=case_id)
    backend = paper_era_backend()
    source_resources = _resource_vector(
        evaluate_full_circuit_resources(
            pool, structure, backend, coefficient_policy="deterministic-structural"
        )
    )

    catalog = []
    for candidate in enumerate_candidates(pool, blocks):
        target = apply_candidate_structure(
            pool,
            structure,
            candidate,
            [0.0] * len(candidate.target_pool_indices),
        )
        target_resources = _resource_vector(
            evaluate_full_circuit_resources(
                pool, target, backend, coefficient_policy="deterministic-structural"
            )
        )
        record = candidate_to_dict(candidate)
        record.update(
            {
                "candidate_structural_id": candidate.candidate_id,
                "canonical_order_key": [candidate.equivalence_class_id, candidate.candidate_id],
                "structurally_eligible": _pareto_compression(
                    source_resources, target_resources
                ),
                "target_structure_digest": _digest(
                    {
                        "indices": list(target.indices),
                        "iteration_counts": list(target.cumulative_parameter_counts),
                    }
                ),
                "deterministic_structural_resources": target_resources,
            }
        )
        catalog.append(record)
    catalog.sort(key=lambda item: (item["equivalence_class_id"], item["candidate_id"]))

    magnitude = []
    for position, (pool_index, coefficient) in enumerate(
        zip(structure.indices, structure.coefficients)
    ):
        target = _delete_coordinate(structure, position)
        target_resources = _resource_vector(
            evaluate_full_circuit_resources(
                pool, target, backend, coefficient_policy="deterministic-structural"
            )
        )
        payload = {
            "source_state_preparation_id": state.state_preparation_id,
            "position": position,
            "pool_index": pool_index,
            "constraint": "theta_i->0",
            "physical_generator_deletion": True,
        }
        magnitude.append(
            {
                "candidate_structural_id": "magnitude-delete-v1:" + _digest(payload),
                "equivalence_class_id": "single-coordinate-position:" + str(position),
                "canonical_order": position,
                "ansatz_position": position,
                "pool_index": pool_index,
                "magnitude_score_float64_hex": __import__("struct").pack(
                    ">d", abs(float(coefficient)) ** 2
                ).hex(),
                "constraint": "theta_i->0",
                "constraint_valid": True,
                "physical_generator_deleted": True,
                "coefficient_zeroing_only": False,
                "full_circuit_rebuild_and_recount": True,
                "resources_after": target_resources,
                "resource_reduction_success": _pareto_compression(
                    source_resources, target_resources
                ),
                "zero_reduction_is_success": False,
            }
        )
    magnitude.sort(
        key=lambda item: (item["magnitude_score_float64_hex"], item["candidate_structural_id"])
    )

    return {
        "case_id": case_id,
        "source_checkpoint_path": str(path.relative_to(ROOT)),
        "source_checkpoint_sha256": _sha(path),
        "source_checkpoint_digest": checkpoint["checkpoint_digest"],
        "stationary_source_audit": {
            "parameter_gradient_infinity": checkpoint["gradient_infinity"],
            "threshold": 1e-8,
            "passed": float(checkpoint["gradient_infinity"]) <= 1e-8,
            "pool_gradient_convergence_not_claimed": True,
        },
        "StatePreparationID": state.state_preparation_id,
        "state_preparation_payload": state.payload(),
        "ProblemID": problem.problem_id,
        "problem_payload": problem.payload(),
        "Hamiltonian_digest": problem.hamiltonian_digest,
        "source_resources": source_resources,
        "source_structural_catalog": catalog,
        "magnitude_candidates": magnitude,
    }


def build() -> dict[str, Any]:
    with _molecular_kernel_guard() as calls:
        cases = [_case_record(case_id, path) for case_id, path in CASES.items()]
    result = {
        "schema": "v5-final.mb6-outcome-free-source-catalog-probe.v1",
        "cases": cases,
        "molecular_kernel_guard_calls": calls,
        "candidate_energy_evaluations": 0,
        "selection_inputs": "structural identities and deterministic circuit recounts only",
        "forbidden_inputs": sorted(FORBIDDEN_OUTPUT_KEYS),
    }
    result["probe_digest"] = _digest(result)
    return result


def main() -> None:
    print(json.dumps(build(), sort_keys=True, separators=(",", ":"), allow_nan=False))


if __name__ == "__main__":
    main()

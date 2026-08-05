"""Quantum reconstruction probe executed with the pinned historical environment."""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from dvg_obs_ceo.molecular_identity import measurement_context, problem_spec, state_preparation_spec
from dvg_obs_ceo.multisystem_checkpoint import _algorithm as multisystem_algorithm
from dvg_obs_ceo.resources import AnsatzStructure, evaluate_full_circuit_resources, paper_era_backend
from dvg_obs_ceo.s10_lih import _algorithm as lih_algorithm
from dvg_obs_ceo.s8_probe import _state_vector
from dvg_obs_ceo.telemetry import WorkCounters
from dvg_obs_ceo.transaction import CompressionRuntime
from dvg_obs_ceo.v4_lih import _energy, _gradient

from .s0_common import PARENT


CASES = {
    "lih-3.0": PARENT / "artifacts/s10/lih-3a-first-accuracy-primary-v1-2/checkpoint.json",
    "h6-1.5": PARENT / "artifacts/full-figures/ceo-star/h6-1.5/checkpoint.json",
    "h6-3.0": PARENT / "artifacts/full-figures/ceo-star/h6-3.0/checkpoint.json",
    "beh2-3.0": PARENT / "artifacts/full-figures/ceo-star/beh2-3.0/checkpoint.json",
}


def _factory(case_id: str, checkpoint: dict[str, Any]):
    if case_id == "lih-3.0":
        algorithm, pool, _ = lih_algorithm()
        return algorithm, pool
    if case_id == "h4-1.5-known-development":
        from dvg_obs_ceo.s8_probe import _algorithm as h2_h4_algorithm

        return h2_h4_algorithm("h4-1.5-first-chemical-accuracy")
    return multisystem_algorithm(checkpoint["case"])


def run_probe(
    cases: Mapping[str, Path] = CASES,
    *,
    probe_version: str = "s2-stationary-source-quantum-probe-v1",
) -> dict[str, Any]:
    results = []
    for case_id, path in cases.items():
        checkpoint = json.loads(path.read_text(encoding="utf-8"))
        algorithm, pool = _factory(case_id, checkpoint)
        algorithm.initialize()
        coordinates = np.asarray(checkpoint["ansatz_coefficients"], dtype=np.float64)
        indices = tuple(int(value) for value in checkpoint["ansatz_indices"])
        structure = AnsatzStructure.create(indices, coordinates, checkpoint["iteration_counts"])
        energy = _energy(algorithm, coordinates, indices)
        gradient = _gradient(algorithm, coordinates, indices)
        state = _state_vector(algorithm, coordinates, indices)
        resources = evaluate_full_circuit_resources(pool, structure, paper_era_backend()).snapshot
        runtime = CompressionRuntime.create(
            ansatz=structure,
            energy_hartree=energy,
            gradient=gradient,
            inverse_hessian=np.eye(len(coordinates)),
            statevector=state,
            work=WorkCounters(),
            adapt_iteration=len(checkpoint["iteration_counts"]),
            metadata={
                "resource_structure_digest": resources.structure_digest,
                "budget_reference_energy_hartree": energy,
            },
        )
        state_spec = state_preparation_spec(runtime, algorithm=algorithm, pool=pool)
        problem = problem_spec(algorithm=algorithm, case_id=case_id)
        measurement = measurement_context(
            state_preparation_id=state_spec.state_preparation_id,
            problem_id=problem.problem_id,
        )
        positions = sorted({0, len(coordinates) // 4, len(coordinates) // 2, 3 * len(coordinates) // 4, len(coordinates) - 1})
        step = 1e-5
        finite_difference = []
        for position in positions:
            plus = coordinates.copy()
            minus = coordinates.copy()
            plus[position] += step
            minus[position] -= step
            observed = (_energy(algorithm, plus, indices) - _energy(algorithm, minus, indices)) / (2 * step)
            finite_difference.append(
                {
                    "position": position,
                    "analytic": float(gradient[position]),
                    "central_difference": float(observed),
                    "absolute_difference": abs(float(gradient[position]) - float(observed)),
                }
            )
        results.append(
            {
                "case_id": case_id,
                "checkpoint_path": str(path.relative_to(PARENT)),
                "checkpoint_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "energy_hartree": energy,
                "checkpoint_energy_difference_hartree": abs(energy - checkpoint["energy_hartree"]),
                "parameter_gradient_infinity": float(np.max(np.abs(gradient))),
                "finite_difference_step": step,
                "finite_difference": finite_difference,
                "finite_difference_max_absolute_difference": max(item["absolute_difference"] for item in finite_difference),
                "statevector_sha256": hashlib.sha256(np.asarray(state, dtype=">c16").tobytes()).hexdigest(),
                "resources": asdict(resources),
                "identities": {
                    "StatePreparationID": state_spec.state_preparation_id,
                    "ProblemID": problem.problem_id,
                    "MeasurementContextID": measurement.measurement_context_id,
                    "state_preparation_payload": state_spec.payload(),
                    "problem_payload": problem.payload(),
                    "measurement_context_payload": measurement.payload(),
                },
                "pool_gradient_stopping": {
                    "satisfied": None,
                    "reason": "historical first-accuracy checkpoint captured before ADAPT finished; not used as parameter-stationarity evidence",
                    "historical_selection_threshold": (checkpoint.get("case") or {}).get("gradient_threshold", 1e-6),
                },
            }
        )
    return {"probe_version": probe_version, "cases": results}


def main() -> None:
    print(json.dumps(run_probe(), allow_nan=False, sort_keys=True))


if __name__ == "__main__":
    main()

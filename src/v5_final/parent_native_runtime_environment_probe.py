"""Probe frozen molecular identities under one explicit thread environment."""

from __future__ import annotations

import json
import os
from typing import Any

from dvg_obs_ceo.molecular_identity import problem_spec

from .mb6_source_catalog_probe import (
    CASES,
    _algorithm_outcome_free,
    _molecular_kernel_guard,
)
from .parent_native_runtime_factory import CATALOG_PATH, build_s3_corrected_environment


def build() -> dict[str, Any]:
    catalog = json.loads(CATALOG_PATH.read_text())
    expected = {case["case_id"]: case for case in catalog["cases"]}
    cases = []
    with _molecular_kernel_guard() as calls:
        for case_id in CASES:
            algorithm, _ = _algorithm_outcome_free(case_id)
            problem = problem_spec(algorithm=algorithm, case_id=case_id)
            cases.append(
                {
                    "case_id": case_id,
                    "actual_ProblemID": problem.problem_id,
                    "expected_ProblemID": expected[case_id]["ProblemID"],
                    "actual_Hamiltonian_digest": problem.hamiltonian_digest,
                    "expected_Hamiltonian_digest": expected[case_id][
                        "Hamiltonian_digest"
                    ],
                    "exact_match": (
                        problem.problem_id == expected[case_id]["ProblemID"]
                        and problem.hamiltonian_digest
                        == expected[case_id]["Hamiltonian_digest"]
                    ),
                    "FCI_used": algorithm.molecule.fci_energy is not None,
                    "CCSD_used": algorithm.molecule.ccsd_energy is not None,
                }
            )
    return {
        "schema": "v5-final.s3-runtime-environment-identity-probe.v1",
        "threads": {
            name: os.environ.get(name)
            for name in ("MKL_NUM_THREADS", "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS")
        },
        "cases": cases,
        "molecular_kernel_guard_calls": calls,
        "candidate_energy_evaluations": 0,
        "corrected_environment": build_s3_corrected_environment(),
    }


def main() -> None:
    print(json.dumps(build(), sort_keys=True, separators=(",", ":"), allow_nan=False))


if __name__ == "__main__":
    main()

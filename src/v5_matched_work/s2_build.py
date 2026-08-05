"""Build the stationary-source protocol from known development checkpoints."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from typing import Any

from .atomic_artifacts import canonical_json_bytes, write_json_exclusive
from .s0_common import PARENT, ROOT, git


def _digest_without(value: dict[str, Any], field: str) -> str:
    content = dict(value)
    content.pop(field, None)
    return hashlib.sha256(canonical_json_bytes(content)).hexdigest()


def quantum_probe() -> dict[str, Any]:
    python = PARENT / ".venv/bin/python"
    environment = dict(os.environ)
    environment.update(
        {
            "PYTHONPATH": f"{ROOT / 'src'}:{PARENT / 'src'}",
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
        }
    )
    completed = subprocess.run(
        [str(python), "-m", "v5_matched_work.s2_probe"],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError("S2 quantum probe failed: " + completed.stderr[-4000:])
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError("S2 quantum probe produced no machine-readable output")
    return json.loads(lines[-1])


def build() -> dict[str, Any]:
    probe = quantum_probe()
    cases = probe["cases"]
    checks = {
        "four_development_sources": len(cases) == 4,
        "parameter_stationarity": all(case["parameter_gradient_infinity"] <= 1e-8 for case in cases),
        "finite_difference_agreement": all(case["finite_difference_max_absolute_difference"] <= 1e-6 for case in cases),
        "energy_reconstruction": all(case["checkpoint_energy_difference_hartree"] <= 1e-10 for case in cases),
        "state_reconstruction": all(len(case["statevector_sha256"]) == 64 for case in cases),
        "resource_recount": all(case["resources"]["parameter_count"] > 0 for case in cases),
        "three_layer_identity": all(
            set(case["identities"]) >= {
                "StatePreparationID", "ProblemID", "MeasurementContextID",
                "state_preparation_payload", "problem_payload", "measurement_context_payload",
            }
            for case in cases
        ),
        "pool_gradient_separate": all("pool_gradient_stopping" in case for case in cases),
    }
    failures = [name for name, passed in checks.items() if not passed]
    result: dict[str, Any] = {
        "schema": "v5-matched-work.s2-stationary-source-protocol.v1",
        "stage": "S2",
        "status": "COMPLETE" if not failures else "FAILED",
        "source_role": "stationarity-normalized-historical-development-checkpoint",
        "parameter_stationarity_threshold_infinity": 1e-8,
        "finite_difference": {"scheme": "central", "step": 1e-5, "agreement_tolerance": 1e-6, "positions_per_source": 5},
        "source_generation_contract": {
            "molecule_geometry_basis_active_space_mapping_ordering": "bound by ProblemID payload",
            "ceo_pool_tetris_selection": "pinned upstream CEO* DVG pool; TETRIS; gradient selection; deterministic",
            "parameter_optimizer": "pinned historical full optimization with recycled Hessian; source must independently pass 1e-8 parameter stationarity",
            "pool_gradient_stopping_stored_separately": True,
            "historical_checkpoint_pool_stop_may_be_null": True,
            "fci_or_exact_reference_online": False,
            "resource_counter": "paper-era-full-circuit logical native counter at a3f89d0",
            "primary_backend": "exact-noiseless-statevector",
        },
        "quantum_probe": probe,
        "checks": checks,
        "failed_checks": failures,
        "decision": "GO_S3" if not failures else "NO_GO_S2",
        "next_stage_authorized": "S3" if not failures else "NONE",
        "paper_measurement_cost": None,
        "claim_boundary": "Known development checkpoint identity/stationarity protocol only; no compression performance result.",
    }
    result["protocol_digest"] = _digest_without(result, "protocol_digest")
    if failures:
        raise RuntimeError("S2 gate failed: " + ", ".join(failures))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-only", action="store_true")
    arguments = parser.parse_args()
    output = ROOT / "artifacts/s2/stationary-source-protocol-v1.json"
    result = build()
    if arguments.verify_only:
        if output.read_bytes() != canonical_json_bytes(result):
            raise RuntimeError("committed S2 protocol differs from quantum reconstruction")
    else:
        write_json_exclusive(output, result)
    print(json.dumps({"decision": result["decision"], "cases": len(result["quantum_probe"]["cases"])}, sort_keys=True))


if __name__ == "__main__":
    main()

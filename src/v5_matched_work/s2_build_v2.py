"""Build S2-v2 without changing the frozen S2-v1 artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from typing import Any

from .atomic_artifacts import canonical_json_bytes, write_json_exclusive
from .s0_common import PARENT, ROOT


def _digest(value: dict[str, Any]) -> str:
    content = dict(value); content.pop("protocol_digest", None)
    return hashlib.sha256(canonical_json_bytes(content)).hexdigest()


def quantum_probe() -> dict[str, Any]:
    environment = dict(os.environ)
    environment.update({
        "PYTHONPATH": f"{ROOT / 'src'}:{PARENT / 'src'}",
        "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1",
    })
    completed = subprocess.run(
        [str(PARENT / ".venv/bin/python"), "-m", "v5_matched_work.s2_probe_v2"],
        cwd=ROOT, env=environment, text=True, capture_output=True, check=False,
    )
    if completed.returncode:
        raise RuntimeError("S2-v2 quantum probe failed: " + completed.stderr[-4000:])
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError("S2-v2 quantum probe produced no JSON")
    return json.loads(lines[-1])


def build() -> dict[str, Any]:
    probe = quantum_probe()
    cases = probe["cases"]
    checks = {
        "five_scheduled_development_sources": len(cases) == 5,
        "h4_source_present": any(case["case_id"] == "h4-1.5-known-development" for case in cases),
        "parameter_stationarity": all(case["parameter_gradient_infinity"] <= 1e-8 for case in cases),
        "finite_difference_agreement": all(case["finite_difference_max_absolute_difference"] <= 1e-6 for case in cases),
        "energy_reconstruction": all(case["checkpoint_energy_difference_hartree"] <= 1e-10 for case in cases),
        "state_reconstruction": all(len(case["statevector_sha256"]) == 64 for case in cases),
        "resource_recount": all(case["resources"]["parameter_count"] > 0 for case in cases),
        "three_layer_identity": all(set(case["identities"]) >= {
            "StatePreparationID", "ProblemID", "MeasurementContextID",
        } for case in cases),
    }
    failures = [name for name, passed in checks.items() if not passed]
    result = {
        "schema": "v5-matched-work.s2-stationary-source-protocol.v2",
        "stage": "S2", "version": 2,
        "status": "COMPLETE" if not failures else "FAILED",
        "supersedes_for_future_execution": "artifacts/s2/stationary-source-protocol-v1.json",
        "source_role": "stationarity-normalized-historical-development-checkpoint",
        "parameter_stationarity_threshold_infinity": 1e-8,
        "finite_difference": {"scheme": "central", "step": 1e-5, "agreement_tolerance": 1e-6},
        "verification_scope": (
            "Checkpoint reconstruction with the pinned implementation. This is independent re-execution, "
            "not verification by a different engine. State hashes are recomputation identities, not cross-engine fidelity."
        ),
        "quantum_probe": probe,
        "checks": checks, "failed_checks": failures,
        "decision": "GO_S3_V2" if not failures else "NO_GO_S2_V2",
        "next_stage_authorized": "S3_V2" if not failures else "NONE",
        "paper_measurement_cost": None,
        "claim_boundary": "Known development checkpoint identity/stationarity reconstruction only; no compression performance result.",
    }
    result["protocol_digest"] = _digest(result)
    if failures:
        raise RuntimeError("S2-v2 gate failed: " + ", ".join(failures))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args(); output = ROOT / "artifacts/s2/stationary-source-protocol-v2.json"
    result = build()
    if args.verify_only:
        if output.read_bytes() != canonical_json_bytes(result):
            raise RuntimeError("S2-v2 protocol drift")
    else:
        write_json_exclusive(output, result)
    print(json.dumps({"decision": result["decision"], "cases": len(result["quantum_probe"]["cases"])}, sort_keys=True))


if __name__ == "__main__":
    main()

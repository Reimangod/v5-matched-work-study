"""Exercise the actual pinned binding on a synthetic circuit, never a molecule."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile

from qiskit import QuantumCircuit

from .mb5_1_production_backend_audit import fixture
from .production_backends.common import digest
from .production_backends_v2.common import PersistentBoundaryRecorderV2, validate_request_v2
from .production_kernel_bindings_v2 import PinnedCEOProductionKernelBindings


class BlockingAlgorithm:
    def __getattr__(self, name: str):
        raise AssertionError(f"molecular algorithm access is forbidden in probe: {name}")


class SyntheticCircuitPool:
    def get_circuit(self, coefficients, indices):
        circuit = QuantumCircuit(2)
        circuit.cx(0, 1)
        return circuit


def main() -> None:
    request = fixture("immutable-ceo-star-source")
    request["schema"] = "v5-final.mb5-2-production-backend-request.v1"
    request["request_digest"] = digest(
        {key: value for key, value in request.items() if key != "request_digest"}
    )
    bound = validate_request_v2(request, "immutable-ceo-star-source")
    with tempfile.TemporaryDirectory() as directory:
        recorder = PersistentBoundaryRecorderV2(
            bound, __name__, Path(directory) / "probe.jsonl"
        )
        binding = PinnedCEOProductionKernelBindings(
            algorithm=BlockingAlgorithm(), pool=SyntheticCircuitPool(), recorder=recorder
        )
        resources = dict(binding.resource_recount([0.1], [0], 2))
        result = {
            "binding_kind": binding.binding_kind,
            "trace": binding.trace,
            "resources": resources,
            "raw_work_total": recorder.total,
            "events": recorder.events,
            "molecular_algorithm_accessed": False,
            "candidate_energy_evaluations": 0,
        }
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()

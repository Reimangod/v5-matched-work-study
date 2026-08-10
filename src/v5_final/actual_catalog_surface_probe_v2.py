"""Probe the actual pinned catalog return surface without evaluating energy."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile

from dvg_obs_ceo.resources import AnsatzStructure

from .mb5_1_production_backend_audit import fixture
from .mb6_source_catalog_probe import CASES, _algorithm_outcome_free, _checkpoint
from .production_backends.common import digest
from .production_backends_v2.common import PersistentBoundaryRecorderV2, validate_request_v2
from .production_kernel_bindings_v2 import PinnedCEOProductionKernelBindings


def main() -> None:
    checkpoint = _checkpoint(CASES["h2-1.5-iteration-1"])
    structure = AnsatzStructure.create(
        checkpoint["ansatz_indices"],
        checkpoint["ansatz_coefficients"],
        checkpoint["iteration_counts"],
    )
    algorithm, pool = _algorithm_outcome_free("h2-1.5-iteration-1")
    request = fixture("v5-sequential-with-rebuilding")
    request["schema"] = "v5-final.mb5-2-production-backend-request.v1"
    request["request_digest"] = digest(
        {key: value for key, value in request.items() if key != "request_digest"}
    )
    bound = validate_request_v2(request, "v5-sequential-with-rebuilding")
    with tempfile.TemporaryDirectory() as directory:
        recorder = PersistentBoundaryRecorderV2(
            bound, __name__, Path(directory) / "catalog.jsonl"
        )
        binding = PinnedCEOProductionKernelBindings(
            algorithm=algorithm, pool=pool, recorder=recorder
        )
        _, candidates = binding.catalog(
            structure.indices,
            structure.coefficients,
            structure.cumulative_parameter_counts,
            parent_digest="f" * 64,
        )
        first = candidates[0]
        result = {
            "candidate_count": len(candidates),
            "return_type": type(first).__name__,
            "is_mapping": isinstance(first, dict),
            "has_candidate_id": hasattr(first, "candidate_id"),
            "has_rank_numerator": hasattr(first, "rank_numerator"),
            "has_proposed_physical_state_id": hasattr(
                first, "proposed_physical_state_id"
            ),
            "candidate_energy_evaluations": recorder.total["energy_evaluations"],
            "catalog_calls": recorder.total["candidate_generations"],
        }
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()

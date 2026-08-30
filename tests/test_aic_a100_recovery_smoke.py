from __future__ import annotations

from types import SimpleNamespace

import pytest

from aic_a100_pilot.aer_gpu_backend import RouteCounters, require_gpu_metadata
from aic_a100_pilot.common import A100PilotError
from aic_a100_pilot.environment import preflight_recovery_body
from aic_a100_pilot.gpu_smoke import smoke_body


def _result(metadata):
    return SimpleNamespace(results=[SimpleNamespace(metadata=metadata)])


def test_additive_recovery_binds_original_no_go_and_authorizes_only_p2():
    value = preflight_recovery_body()
    assert value["status"] == "GO_P2_PINNED_GPU_ENVIRONMENT"
    assert value["supersedes_without_mutation"]["historical_no_go_remains_valid_for_original_window"] is True
    assert value["allocated_device"]["slurm_alloc_tres_gpu"] == 1
    assert value["allocated_device"]["cuda_driver_device_count"] == 1
    assert value["successor_authorization"]["P2_GPU_ENVIRONMENT_AND_SMOKE"] == "AUTHORIZED"
    assert value["successor_authorization"]["P3_SCIENTIFIC_PARITY"].startswith("NOT_AUTHORIZED")


def test_smoke_proves_gpu_route_but_makes_no_scientific_claim():
    value = smoke_body()
    assert value["status"] == "GO_P3_SCIENTIFIC_PARITY"
    assert value["smoke"]["four_qubit_GHZ_experiment_metadata_device"] == "GPU"
    assert value["route_counters"]["N_gpu_statevector"] == 2
    assert value["route_counters"]["N_cpu_fallback"] == 0
    assert value["scientific_boundaries"]["molecular_case_executed"] is False
    assert value["scientific_boundaries"]["performance_claim_authorized"] is False


def test_gpu_metadata_is_fail_closed_on_cpu_fallback():
    counters = RouteCounters()
    with pytest.raises(A100PilotError, match="CPU fallback"):
        require_gpu_metadata(_result({"device": "CPU", "method": "statevector"}), counters)
    assert counters.N_cpu_fallback == 1


def test_gpu_metadata_accepts_explicit_gpu_statevector_only():
    counters = RouteCounters()
    metadata = require_gpu_metadata(
        _result({"device": "GPU", "method": "statevector"}), counters
    )
    assert metadata["device"] == "GPU"
    assert counters.N_cpu_fallback == 0

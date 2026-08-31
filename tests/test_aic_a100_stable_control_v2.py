from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import ModuleType
from typing import Any, Sequence

import numpy as np
import pytest

from aic_a100_pilot.common import (
    A100PilotError,
    embedded_digest_valid,
    load_json,
    sha256_file,
)
from aic_a100_pilot.objective_parity import PilotBoundary
from aic_a100_pilot.stable_control_runtime_incident import (
    INCIDENT,
    incident_body,
)
from aic_a100_pilot.stable_control_v2_contract import (
    CONTRACT,
    SOURCE_PATHS,
    VALIDATION_PATHS,
    contract_body,
)
from aic_a100_pilot.stable_control_v2_route import (
    OPTIMIZER_EVENT_CROSSWALK,
    StableControlV2DeviceBoundary,
    _publish_failure_incident,
)
from aic_a100_pilot.unified_route import UnifiedCounters


EXPECTED_V1_CONTRACT_SHA256 = (
    "20d7210fcabc450ed4fd3c411bdc782bb05b4323f6903db74bf1a0e3cc78a934"
)
EXPECTED_V1_H2_SHA256 = (
    "baa0beb34c7a288e2a407454ecd9cd6955ba20a53d19e6536be31e217e479b23"
)
EXPECTED_V1_INCIDENT_LOG_SHA256 = (
    "c9546abcca86a7f7013f344d0b561eb1f0e8411f0199ecc58674d8b5bf11fcec"
)


@pytest.fixture
def pinned_minimize_module(monkeypatch: pytest.MonkeyPatch) -> None:
    """Load only the pinned minimizer without importing adaptvqe.__init__."""

    root = CONTRACT.parents[3]
    package_path = (
        root
        / "provenance/dvg-obs-ceo/vendor/ceo-adapt-vqe/adaptvqe"
    )
    package = ModuleType("adaptvqe")
    package.__path__ = [str(package_path)]  # type: ignore[attr-defined]
    specification = importlib.util.spec_from_file_location(
        "adaptvqe.minimize", package_path / "minimize.py"
    )
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    monkeypatch.setitem(sys.modules, "adaptvqe", package)
    monkeypatch.setitem(sys.modules, "adaptvqe.minimize", module)


class SyntheticStableBoundary(StableControlV2DeviceBoundary):
    """One-dimensional deterministic fixture exercising the pinned BFGS path."""

    target = np.float64(0.125)

    def __init__(self) -> None:
        self.boundary = PilotBoundary()
        self.device = "CPU"
        self.counters = UnifiedCounters(device="CPU")
        self.control_trace: list[dict[str, Any]] = []
        self.quantization_audit: list[dict[str, Any]] = []
        self.raw_gradient_series: list[list[float]] = []
        self.optimizer_accounting_audit: list[dict[str, Any]] = []
        self.operation_trace: list[dict[str, Any]] = []
        self.trajectory: list[dict[str, Any]] = []
        self.metadata: list[dict[str, str]] = []
        self._latest_states: dict[bytes, np.ndarray] = {}

    @staticmethod
    def _key(coordinates: Sequence[float]) -> bytes:
        return np.asarray(coordinates, dtype=">f8").reshape(-1).tobytes()

    def _energy_at(
        self,
        coordinates: Sequence[float],
        indices: Sequence[int],
        *,
        purpose: str,
        parameter_position: int | None = None,
        stencil_multiple: int | None = None,
    ) -> tuple[float, np.ndarray]:
        del indices
        values = np.asarray(coordinates, dtype=np.float64).reshape(-1)
        state = np.asarray([1.0 + 0.0j], dtype=np.complex128)

        def call() -> tuple[float, np.ndarray]:
            energy = float(np.sum((values - self.target) ** 2))
            return energy, state.copy()

        energy, observed_state = self.boundary.invoke(
            purpose,
            call,
            evidence={
                "parameter_position": parameter_position,
                "stencil_multiple": stencil_multiple,
            },
        )
        self._latest_states[self._key(values)] = observed_state.copy()
        self.counters.N_device_statevector += 1
        self.counters.N_deterministic_energy += 1
        self.operation_trace.append(
            {
                "purpose": purpose,
                "parameter_position": parameter_position,
                "stencil_multiple": stencil_multiple,
            }
        )
        return float(energy), observed_state

    def _state_at(
        self,
        coordinates: Sequence[float],
        indices: Sequence[int],
        *,
        purpose: str,
        parameter_position: int | None = None,
        stencil_multiple: int | None = None,
    ) -> tuple[np.ndarray, dict[str, str]]:
        del coordinates, indices, parameter_position, stencil_multiple
        state = np.asarray([1.0 + 0.0j], dtype=np.complex128)
        observed = self.boundary.invoke(purpose, lambda: state.copy())
        return observed, {"device": "CPU", "method": "synthetic-statevector"}


class OldEventNameSyntheticBoundary(SyntheticStableBoundary):
    def energy(self, coordinates: Sequence[float], indices: Sequence[int]) -> float:
        raw, _ = self._energy_at(
            coordinates, indices, purpose="optimizer-objective-raw-energy"
        )
        return raw


def test_v1_runtime_incident_is_precise_and_preserves_scientific_boundary():
    value = incident_body()
    assert value["status"] == (
        "NO_GO_A100_STABLE_CONTROL_V1_RUNTIME_ACCOUNTING_MISMATCH"
    )
    assert value["contract_binding"]["sha256"] == EXPECTED_V1_CONTRACT_SHA256
    assert value["prior_h2_result"]["sha256"] == EXPECTED_V1_H2_SHA256
    assert value["slurm"]["failed_h4_job"]["remote_log_sha256"] == (
        EXPECTED_V1_INCIDENT_LOG_SHA256
    )
    assert value["outcome_boundary"]["H4_CPU_optimizer_computation_reached"]
    assert not value["outcome_boundary"]["H4_GPU_optimizer_computation_reached"]
    assert value["outcome_boundary"]["LiH_H6_BeH2_candidate_outcomes"] == 0
    assert value["outcome_boundary"]["FCI_evaluations"] == 0
    published = load_json(INCIDENT)
    assert embedded_digest_valid(published, "incident_digest")


def test_v2_contract_is_additive_and_changes_no_scientific_numerics():
    value = contract_body()
    assert value["status"] == (
        "GO_BOUNDED_STABLE_CONTROL_V2_TRAJECTORY_CALIBRATION"
    )
    assert value["frozen_before_new_stable_control_v2_candidate_outcomes"]
    assert value["immutable_predecessor"]["preserved_without_mutation"]
    assert value["candidate_binding"] == {
        "selection_changed": False,
        "ansatz_changed": False,
        "rewrite_changed": False,
        "molecular_source_changed": False,
        "optimizer_changed": False,
        "tolerance_changed": False,
        "control_numerics_changed": False,
        "only_accounting_and_failure_durability_changed": True,
    }
    assert value["route_contract"]["optimizer_event_crosswalk"] == (
        OPTIMIZER_EVENT_CROSSWALK
    )
    assert value["sequential_gate"]["case_order"] == [
        "h2",
        "h4",
        "lih",
        "h6",
        "beh2",
    ]
    assert value["scientific_boundary"]["FCI_evaluations"] == 0
    assert value["scientific_boundary"]["existing_90_item_execution"] == (
        "UNCHANGED"
    )
    assert value["validation_binding"] == {
        path.relative_to(CONTRACT.parents[3]).as_posix(): sha256_file(path)
        for path in VALIDATION_PATHS
    }


def test_nonzero_dimensional_optimizer_accounting_matches_pinned_bfgs(
    pinned_minimize_module: None,
):
    del pinned_minimize_module
    kernel = SyntheticStableBoundary()
    result = kernel.optimize([0.8], [0], np.eye(1, dtype=np.float64))
    assert int(result.nfev) > 0
    assert int(result.njev) > 0
    assert kernel.optimizer_accounting_audit
    audit = kernel.optimizer_accounting_audit[-1]
    assert audit["dimension"] == 1
    assert all(audit["checks"].values())
    assert audit["observed"]["optimizer-objective-energy"] == int(result.nfev)
    assert audit["observed"]["full-gradient-evaluation"] == int(result.njev)


def test_zero_dimensional_optimizer_is_not_an_accounting_bypass(
    pinned_minimize_module: None,
):
    del pinned_minimize_module
    kernel = SyntheticStableBoundary()
    result = kernel.optimize([], [], np.empty((0, 0), dtype=np.float64))
    assert int(result.nfev) == 1
    assert kernel.optimizer_accounting_audit[-1]["dimension"] == 0
    assert all(kernel.optimizer_accounting_audit[-1]["checks"].values())


def test_regression_fixture_proves_the_v1_event_name_is_rejected(
    pinned_minimize_module: None,
):
    del pinned_minimize_module
    kernel = OldEventNameSyntheticBoundary()
    with pytest.raises(A100PilotError, match="optimizer accounting differs"):
        kernel.optimize([0.8], [0], np.eye(1, dtype=np.float64))


def test_failure_incident_is_exclusive_and_captures_partial_counters(tmp_path: Path):
    path = tmp_path / "incident.json"
    kernel = SyntheticStableBoundary()
    kernel.energy([0.5], [0])
    contract = {"contract_digest": "frozen-contract-digest"}
    start = {"start_digest": "frozen-start-digest"}
    value = _publish_failure_incident(
        path=path,
        alias="h4",
        contract=contract,
        start_record=start,
        stage="cpu-candidate-attempt",
        error=A100PilotError("synthetic failure without outcome values"),
        capture={"cpu_kernel": kernel, "gpu_kernel": None},
    )
    assert embedded_digest_valid(value, "incident_digest")
    assert value["partial_execution"]["cpu"]["constructed"]
    assert value["partial_execution"]["cpu"]["route_counters"][
        "N_deterministic_energy"
    ] == 1
    assert not value["partial_execution"]["gpu"]["constructed"]
    assert value["scientific_boundary"][
        "partial_values_eligible_for_parity_or_performance_claim"
    ] is False
    with pytest.raises(FileExistsError):
        _publish_failure_incident(
            path=path,
            alias="h4",
            contract=contract,
            start_record=start,
            stage="retry",
            error=A100PilotError("must not overwrite"),
            capture={},
        )


def test_v2_batch_uses_new_namespace_and_durable_evidence_paths():
    batch_path = next(
        path
        for path in SOURCE_PATHS
        if path.name == "a100_stable_control_v2_trajectory.sbatch"
    )
    batch = batch_path.read_text(encoding="utf-8")
    assert 'namespace="${root}/p8-unified-stable-v2"' in batch
    assert "stable_control_v2_prepare" in batch
    assert "stable_control_v2_route" in batch
    assert '--start-record "${start_record}"' in batch
    assert '--incident "${incident}"' in batch
    assert "p7-unified-stable-v1/results" not in batch


def test_published_v2_contract_is_content_addressed_and_source_bound():
    if not CONTRACT.is_file():
        return
    value = load_json(CONTRACT)
    assert embedded_digest_valid(value, "contract_digest")
    assert value["source_binding"] == {
        path.relative_to(CONTRACT.parents[3]).as_posix(): sha256_file(path)
        for path in SOURCE_PATHS
    }

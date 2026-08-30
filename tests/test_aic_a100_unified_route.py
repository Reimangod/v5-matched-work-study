from __future__ import annotations

import json
from pathlib import Path
import struct

import numpy as np
import pytest
from scipy.sparse import csr_matrix

from aic_a100_pilot.common import (
    A100PilotError,
    digest,
    embedded_digest_valid,
    git,
    load_json,
    sha256_file,
)
from aic_a100_pilot.unified_route import (
    DeterministicHamiltonian,
    _require_predecessors,
    _runtime_binding,
    deterministic_normalize,
    fixed_pairwise_complex_sum,
)
from aic_a100_pilot.unified_route_contract import (
    CONTRACT,
    CONTRACT_V1,
    CONTRACT_V2,
    CONTRACT_V3,
    HYBRID_REPORT,
    SOURCE_PATHS,
    TERMINAL_NO_GO,
    V3_PREOUTCOME_INCIDENT,
    contract_body,
)


EXPECTED_HYBRID_REPORT_SHA256 = (
    "ec9244d6edad05fbe5fa8a6b641a4fcd8a2c7951f242bb4669a5cc81cfed4a5f"
)
EXPECTED_TERMINAL_NO_GO_SHA256 = (
    "f53dc4ad3293a426a8a707498d2d7db600a71a595d59559b71fbfdaf8f66835a"
)
EXPECTED_UNIFIED_V1_SHA256 = (
    "0a3fc81eb48fc0cc8af2792f211e2c06cd73bccc2059072e66c340f0a0aa8e36"
)
EXPECTED_UNIFIED_V2_SHA256 = (
    "7fd8a8e160e59d6c6eb6b40007b2b4b9f370249ab8e4cc7287d4a48bef6e6037"
)
EXPECTED_UNIFIED_V3_SHA256 = (
    "9bd572614af0f9415894fb0a642963803c90d0bb5365fcec2736875a8322b8d6"
)


def _float_hex(value: float) -> str:
    return struct.pack(">d", float(value)).hex()


def test_unified_contract_preserves_no_go_and_freezes_one_route():
    value = contract_body()
    assert value["schema"].endswith(".v4")
    assert value["status"] == "GO_BOUNDED_UNIFIED_ROUTE_TRAJECTORY_PARITY"
    assert value["frozen_before_new_unified_route_candidate_outcomes"] is True
    assert sha256_file(HYBRID_REPORT) == EXPECTED_HYBRID_REPORT_SHA256
    assert sha256_file(TERMINAL_NO_GO) == EXPECTED_TERMINAL_NO_GO_SHA256
    predecessor = value["immutable_predecessor_no_go"]
    assert predecessor["preserved_without_mutation"] is True
    assert predecessor["hybrid_report"]["sha256"] == EXPECTED_HYBRID_REPORT_SHA256
    assert predecessor["terminal_decision"]["sha256"] == (
        EXPECTED_TERMINAL_NO_GO_SHA256
    )
    correction = value["pre_outcome_correction"]
    assert sha256_file(CONTRACT_V1) == EXPECTED_UNIFIED_V1_SHA256
    assert sha256_file(CONTRACT_V2) == EXPECTED_UNIFIED_V2_SHA256
    assert sha256_file(CONTRACT_V3) == EXPECTED_UNIFIED_V3_SHA256
    assert correction["superseded_contract"]["sha256"] == EXPECTED_UNIFIED_V3_SHA256
    assert correction["new_unified_route_candidate_outcomes_before_v4_freeze"] == 0
    assert correction["v1_v2_v3_remain_immutable"] is True
    incident = load_json(V3_PREOUTCOME_INCIDENT)
    assert embedded_digest_valid(incident, "incident_digest")
    assert incident["status"] == (
        "PRE_OUTCOME_ENGINEERING_INCIDENT_H2_SOURCE_THREAD_CONTRACT"
    )
    assert incident["outcome_boundary"]["candidate_energy_evaluations"] == 0
    route = value["route_contract"]
    assert route["CPU_analytic_gradient_used"] is False
    assert route["finite_difference_step_float64_hex"] == _float_hex(1e-4)
    assert route["stencil_order"] == [-2, -1, 1, 2]
    assert route["aer_fusion_enable"] is False
    assert route["aer_max_parallel_threads"] == 1
    assert route["source_reconstruction_thread_environment"] == {
        "h2": 2,
        "h4": 1,
        "lih": 1,
        "h6": 1,
        "beh2": 1,
    }
    assert route["source_and_numerical_processes_are_separate"] is True
    assert route["numerical_process_thread_environment"] == 1
    assert route["runtime_source_hash_validation"] == (
        "REQUIRED_BEFORE_CASE_PREPARATION"
    )
    assert value["sequential_gate"]["case_order"] == [
        "h2",
        "h4",
        "lih",
        "h6",
        "beh2",
    ]
    assert value["sequential_gate"]["H6_BeH2_before_LiH_pass"] == (
        "NOT_AUTHORIZED"
    )
    assert value["sequential_gate"][
        "complete_item_timing_before_all_parity_pass"
    ] == "NOT_AUTHORIZED"
    assert value["sequential_gate"]["candidate_attempt_timing_during_parity"] == (
        "NOT_RECORDED"
    )
    assert value["scientific_boundary"]["FCI_evaluations"] == 0
    assert value["scientific_boundary"]["existing_90_item_execution"] == (
        "UNCHANGED"
    )


def test_published_unified_contract_is_content_addressed_and_source_bound():
    value = load_json(CONTRACT)
    assert embedded_digest_valid(value, "contract_digest")
    expected = contract_body()
    assert value["contract_digest"] == digest(expected)
    assert {
        path.relative_to(CONTRACT.parents[3]).as_posix(): sha256_file(path)
        for path in SOURCE_PATHS
    } == value["source_binding"]

    source = next(
        path for path in SOURCE_PATHS if path.name == "unified_route.py"
    ).read_text(encoding="utf-8")
    batch = next(
        path for path in SOURCE_PATHS if path.name == "a100_unified_trajectory.sbatch"
    ).read_text(encoding="utf-8")
    assert "super().gradient" not in source
    assert '"wall_time_seconds"' not in source
    for variable in (
        "OMP_NUM_THREADS",
        "MKL_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
    ):
        assert f'{variable}="${{source_threads}}"' in batch
        assert f"{variable}=1" in batch
    assert "A100_NUMERICAL_THREADS=1" in batch


def test_runtime_binding_records_exact_commit_submodules_and_versions(monkeypatch):
    contract = load_json(CONTRACT)
    head = git("rev-parse", "HEAD")
    monkeypatch.setenv("A100_EXPECTED_HEAD", head)
    for variable in (
        "OMP_NUM_THREADS",
        "MKL_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
    ):
        monkeypatch.setenv(variable, "1")
    monkeypatch.setenv("A100_NUMERICAL_THREADS", "1")
    value = _runtime_binding(contract, "h4")
    assert value["git_head"] == value["expected_git_head"] == head
    assert value["contract_digest"] == contract["contract_digest"]
    assert value["source_sha256"] == contract["source_binding"]
    assert set(value["distributions"]) == {
        "numpy",
        "scipy",
        "qiskit",
        "qiskit_aer",
    }
    assert all(
        set(record) == {"module", "version", "source"}
        for record in value["distributions"].values()
    )
    assert len(value["parent_submodule_head"]) == 40
    assert len(value["CEO_submodule_head"]) == 40
    assert set(value["numerical_process_thread_environment"].values()) == {"1"}


def test_runtime_binding_fails_closed_on_wrong_commit(monkeypatch):
    monkeypatch.setenv("A100_EXPECTED_HEAD", "0" * 40)
    with pytest.raises(A100PilotError, match="runtime Git HEAD differs"):
        _runtime_binding(load_json(CONTRACT), "h4")


def test_pairwise_complex_reduction_and_normalization_are_repeatable():
    values = np.asarray(
        [1.0 + 2.0j, -3.0 + 0.5j, 4.0 - 5.0j, 0.25 + 0.75j, 2.0j],
        dtype=np.complex128,
    )
    first = fixed_pairwise_complex_sum(values)
    second = fixed_pairwise_complex_sum(values)
    assert np.asarray(first, dtype=">c16").tobytes() == np.asarray(
        second, dtype=">c16"
    ).tobytes()
    assert first == ((values[0] + values[1]) + (values[2] + values[3])) + values[4]
    assert fixed_pairwise_complex_sum([]) == np.complex128(0.0)

    raw = np.asarray([1.0 + 2.0j, -0.5j, 3.0 - 1.0j], dtype=np.complex128)
    normalized_first = deterministic_normalize(raw)
    normalized_second = deterministic_normalize(raw)
    assert normalized_first.dtype == np.dtype(np.complex128)
    assert np.array_equal(normalized_first, normalized_second)
    assert abs(float(np.vdot(normalized_first, normalized_first).real) - 1.0) < 1e-15


def test_deterministic_hamiltonian_uses_registered_sparse_order():
    matrix = csr_matrix(
        np.asarray(
            [[1.0, 2.0 + 1.0j], [2.0 - 1.0j, -0.5]],
            dtype=np.complex128,
        )
    )
    state = deterministic_normalize([1.0 + 0.5j, -0.25 + 0.75j])
    hamiltonian = DeterministicHamiltonian(matrix)
    first = hamiltonian.energy(state)
    second = hamiltonian.energy(state)
    expected = float(np.real(np.vdot(state, matrix @ state)))
    assert _float_hex(first) == _float_hex(second)
    assert abs(first - expected) < 1e-15
    assert len(hamiltonian.operation_order_digest) == 64


def test_predecessor_gate_is_additive_and_fail_closed(tmp_path: Path):
    contract = load_json(CONTRACT)
    assert _require_predecessors("h2", tmp_path) == []
    with pytest.raises(A100PilotError, match="missing predecessor"):
        _require_predecessors("h4", tmp_path)

    record = {
        "schema": "test-only-unified-predecessor",
        "status": "PASS",
        "contract_digest": contract["contract_digest"],
    }
    record["record_digest"] = digest(record)
    (tmp_path / "h2.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    predecessor = _require_predecessors("h4", tmp_path)
    assert [value["alias"] for value in predecessor] == ["h2"]

    failed = dict(record)
    failed.pop("record_digest")
    failed["status"] = "FAIL"
    failed["record_digest"] = digest(failed)
    (tmp_path / "h2.json").write_text(
        json.dumps(failed, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    with pytest.raises(A100PilotError, match="did not pass"):
        _require_predecessors("h4", tmp_path)

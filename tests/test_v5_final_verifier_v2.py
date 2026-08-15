from __future__ import annotations

import inspect

import numpy as np
import pytest
from scipy import sparse
from scipy.linalg import expm
from scipy.sparse.linalg import expm_multiply

from v5_matched_work.atomic_artifacts import canonical_json_bytes
from v5_final import parent_native_verifier_v2 as parent_adapter
from v5_final import verifier_v2 as subject


def _fixture(tmp_path, *, top_k: int = 2):
    z_left = 1j * sparse.diags([1.0, 1.0, -1.0, -1.0], format="csr")
    z_right = 1j * sparse.diags([1.0, -1.0, 1.0, -1.0], format="csr")
    z_sum = z_left + z_right
    matrices = {"z-left": z_left, "z-right": z_right, "z-sum": z_sum}
    loads: list[str] = []
    recounts: list[str] = []

    def loader(digest: str):
        loads.append(digest)
        return matrices[digest]

    def resources(label: str, values: tuple[int, ...]):
        def recount():
            recounts.append(label)
            return values

        return recount

    def circuit_state(coordinates: np.ndarray, probe: np.ndarray) -> np.ndarray:
        return expm_multiply(float(coordinates[0]) * z_sum, probe)

    candidates = (
        subject.CandidateV2(
            "candidate-a",
            "semantic-a",
            "state-a",
            ("z-left", "z-right"),
            ("z-sum",),
            ((1.0,), (1.0,)),
            0.2,
            4,
            2,
            resources("a", (4, 3, 2)),
            circuit_state,
        ),
        subject.CandidateV2(
            "candidate-a-alias",
            "semantic-a",
            "state-a-alias",
            ("z-left", "z-right"),
            ("z-sum",),
            ((1.0,), (1.0,)),
            0.3,
            4,
            2,
            resources("semantic-alias", (99, 99, 99)),
            circuit_state,
        ),
        subject.CandidateV2(
            "candidate-physical-alias",
            "semantic-physical-alias",
            "state-a",
            ("z-left", "z-right"),
            ("z-sum",),
            ((1.0,), (1.0,)),
            0.4,
            4,
            2,
            resources("physical-alias", (98, 98, 98)),
            circuit_state,
        ),
        subject.CandidateV2(
            "candidate-deletion",
            "semantic-deletion",
            "state-deletion",
            ("z-left",),
            (),
            ((),),
            0.1,
            4,
            2,
            resources("deletion", (2, 2, 1)),
            deletion_shortcut=True,
        ),
    )
    verifier = subject.VerifierV2(
        policy=subject.VerifierV2Policy(top_k=top_k, probe_count=3, seed=17),
        generator_loader=loader,
        checkpoint_dir=tmp_path,
        source_binding={"case_id": "toy", "source_digest": "source-v1"},
    )
    return verifier, candidates, loads, recounts, matrices


def test_pipeline_deduplicates_before_heavy_work_and_freezes_top_k(tmp_path):
    verifier, candidates, loads, recounts, _ = _fixture(tmp_path)
    result = verifier.run(candidates)
    core = result["core"]
    counters = core["deterministic_work_counters"]
    assert core["status"] == "VERIFIED_READY_AWAITING_OUTCOME_AUTHORIZATION"
    assert core["top_k_freeze"]["selected_candidate_ids"] == [
        "candidate-deletion",
        "candidate-a",
    ]
    assert counters["candidate_generations"] == 4
    assert counters["unique_semantic_candidates"] == 3
    assert counters["unique_physical_states"] == 2
    assert recounts == ["a", "deletion"]
    assert "semantic-alias" not in recounts and "physical-alias" not in recounts
    assert sorted(loads) == ["z-left", "z-right", "z-sum"]
    assert counters["N_dense_expm"] == 0
    assert counters["optimizer_iterations"] == 0
    assert counters["energy_evaluations"] == 0
    assert (tmp_path / "top-k-freeze-v2.json").exists()
    assert all(value.startswith("NOT_AUTHORIZED") for value in core["authorization"].values())


def test_sparse_probe_matches_registered_relation_and_native_circuit(tmp_path):
    verifier, candidates, _, _, _ = _fixture(tmp_path)
    core = verifier.run(candidates)["core"]
    sparse_record = next(
        value
        for value in core["numeric_verifications"]
        if value["candidate_id"] == "candidate-a"
    )
    assert sparse_record["status"] == "VERIFIED_SPARSE_STATE_PROBES"
    assert sparse_record["primitive_delta"]["N_sparse_expm_multiply"] == 9
    assert sparse_record["primitive_delta"]["N_state_probe_vectors"] == 3
    assert sparse_record["primitive_delta"]["N_circuit_operator_builds"] == 3


def test_deletion_shortcut_has_dense_parity_without_production_exponential(tmp_path):
    verifier, candidates, _, _, matrices = _fixture(tmp_path)
    core = verifier.run(candidates)["core"]
    deletion = next(
        value
        for value in core["numeric_verifications"]
        if value["candidate_id"] == "candidate-deletion"
    )
    probe = np.asarray([1.0, 2.0j, -1.0, 0.5], dtype=np.complex128)
    dense_reference = expm(0.0 * matrices["z-left"].toarray()) @ probe
    assert np.allclose(dense_reference, probe)
    assert deletion["status"] == "VERIFIED_ANALYTIC_DELETION_EXP_0G_IDENTITY"
    assert deletion["primitive_delta"]["N_sparse_expm_multiply"] == 0
    assert deletion["primitive_delta"]["N_dense_expm"] == 0


def test_checkpoint_resume_equals_uninterrupted_core_without_recomputation(tmp_path):
    resume_dir = tmp_path / "resume"
    first, candidates, first_loads, _, _ = _fixture(resume_dir)
    partial = first.run(candidates, max_new_numeric_verifications=1)
    assert partial["core"]["status"] == "CHECKPOINTED_INCOMPLETE_OUTCOME_FREE"
    assert partial["operational_telemetry"]["new_numeric_verifications"] == 1

    resumed, candidates_again, resumed_loads, _, _ = _fixture(resume_dir)
    resumed_result = resumed.run(candidates_again)
    assert resumed_result["operational_telemetry"]["resumed_numeric_verifications"] == 1

    clean, clean_candidates, clean_loads, _, _ = _fixture(tmp_path / "clean")
    clean_result = clean.run(clean_candidates)
    assert canonical_json_bytes(resumed_result["core"]) == canonical_json_bytes(
        clean_result["core"]
    )
    assert first_loads == []  # deletion is rank 0 and requires no generator
    assert sorted(resumed_loads) == ["z-left", "z-right", "z-sum"]
    assert sorted(clean_loads) == ["z-left", "z-right", "z-sum"]


def test_policy_and_session_drift_fail_closed(tmp_path):
    verifier, candidates, _, _, _ = _fixture(tmp_path)
    verifier.run(candidates, max_new_numeric_verifications=0)
    changed, changed_candidates, _, _, _ = _fixture(tmp_path, top_k=1)
    with pytest.raises(subject.VerifierV2Error, match="session binding differs"):
        changed.run(changed_candidates)


def test_semantic_id_cannot_alias_incompatible_certificate(tmp_path):
    verifier, candidates, _, _, _ = _fixture(tmp_path)
    bad = subject.CandidateV2(
        "candidate-bad",
        "semantic-a",
        "state-bad",
        ("z-left",),
        ("z-sum",),
        ((1.0,),),
        0.5,
        4,
        2,
        lambda: (1, 1, 1),
    )
    with pytest.raises(subject.VerifierV2Error, match="incompatible certificates"):
        verifier.run((*candidates, bad))


def test_production_module_contains_no_dense_expm_or_sparse_toarray():
    source = inspect.getsource(subject) + inspect.getsource(parent_adapter)
    assert "scipy.linalg.expm" not in source
    assert ".toarray(" not in source
    assert set(subject.ALL_COUNTER_FIELDS) == {
        "N_symbolic_checks",
        "N_sparse_expm_multiply",
        "N_state_probe_vectors",
        "N_dense_expm",
        "N_circuit_operator_builds",
        "N_generator_materializations",
        "matrix_dimension",
        "qubit_count",
        "candidate_generations",
        "unique_semantic_candidates",
        "unique_physical_states",
        "rewrite_verifications",
        "resource_recounts",
        "optimizer_iterations",
        "energy_evaluations",
        "CPU_time_seconds",
        "wall_time_seconds",
        "peak_RSS_raw",
    }


def test_initial_source_work_is_bound_and_counted(tmp_path):
    verifier, candidates, _, _, _ = _fixture(tmp_path)
    verifier = subject.VerifierV2(
        policy=verifier.policy,
        generator_loader=verifier.generator_loader,
        checkpoint_dir=tmp_path / "with-source-work",
        source_binding={"case_id": "toy", "source_digest": "source-v1"},
        initial_counts={
            "resource_recounts": 1,
            "N_circuit_operator_builds": 2,
            "matrix_dimension": 4,
            "qubit_count": 2,
        },
    )
    result = verifier.run(candidates)
    counters = result["core"]["deterministic_work_counters"]
    assert counters["resource_recounts"] == 3
    assert counters["N_circuit_operator_builds"] == 5
    assert result["core"]["session_binding"][
        "initial_deterministic_work_counters"
    ]["resource_recounts"] == 1


@pytest.mark.parametrize(
    "forbidden",
    [
        {"N_dense_expm": 1},
        {"optimizer_iterations": 1},
        {"energy_evaluations": 1},
    ],
)
def test_initial_boundary_crossing_fails_closed(tmp_path, forbidden):
    verifier, _, _, _, _ = _fixture(tmp_path)
    with pytest.raises(subject.VerifierV2Error, match="crosses the outcome-free boundary"):
        subject.VerifierV2(
            policy=verifier.policy,
            generator_loader=verifier.generator_loader,
            checkpoint_dir=tmp_path / "forbidden",
            source_binding={"case_id": "toy"},
            initial_counts=forbidden,
        )

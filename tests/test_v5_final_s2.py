from __future__ import annotations

from dataclasses import replace

import pytest

from v5_final.identities import (
    CandidateIntent,
    ExecutionRequest,
    GeneratorSemantic,
    HamiltonianTerm,
    IdentityError,
    IntentAlias,
    NativeGateSemantic,
    PhysicalStateEvaluationIndex,
    ProblemSpec,
    ProposedPhysicalState,
)


DIGEST_A = "a" * 64
DIGEST_B = "b" * 64
COEFF_A = "000000000000f03f"
COEFF_B = "010000000000f03f"


def _problem(*, second_coefficient: str = COEFF_B, reversed_terms: bool = False) -> ProblemSpec:
    terms = (
        HamiltonianTerm("ZI", COEFF_A),
        HamiltonianTerm("IZ", second_coefficient),
    )
    return ProblemSpec(
        system_label="H2",
        geometry_decimal=("0", "0", "0", "0", "0", "0.74"),
        basis="sto-3g",
        charge=0,
        multiplicity=1,
        mapping="jordan-wigner",
        qubit_count=2,
        hamiltonian_terms=tuple(reversed(terms)) if reversed_terms else terms,
    )


def _state(problem_id: str) -> ProposedPhysicalState:
    return ProposedPhysicalState(
        problem_id=problem_id,
        reference_state=(1, 0),
        generator_semantics=(
            GeneratorSemantic((0, 1), "fermionic-single", 1, COEFF_A),
            GeneratorSemantic((1,), "number", -1, COEFF_B),
        ),
        block_order=("block-a", "block-b"),
        mapping="jordan-wigner",
        qubit_order=(0, 1),
        canonical_coefficient_bytes=(COEFF_A, COEFF_B),
        target_structure={"blocks": ["block-a", "block-b"], "version": 1},
        native_circuit_semantics=(
            NativeGateSemantic("rx", (0,), (COEFF_A,)),
            NativeGateSemantic("cx", (0, 1)),
        ),
    )


def _request(state_id: str) -> ExecutionRequest:
    return ExecutionRequest(
        proposed_physical_state_id=state_id,
        source_checkpoint_digest=DIGEST_A,
        optimizer={"name": "lbfgs", "max_iterations": 100},
        initialization={"kind": "mapped-source", "seed": 7},
        work_profile={"name": "small", "N_E": 100},
        energy_budget_hartree="0.0001",
        stationarity_threshold="0.000001",
        protocol_digest=DIGEST_A,
        environment_digest=DIGEST_B,
    )


def _intent(path: str) -> CandidateIntent:
    return CandidateIntent(
        source_block="source-block-7",
        transformation_family="exact-rewrite",
        target_family="two-block",
        candidate_provenance={"rule": "merge", "parents": ["a", "b"]},
        generation_path=("catalog", path),
    )


def test_hamiltonian_enumeration_order_is_identity_invariant() -> None:
    assert _problem().problem_id == _problem(reversed_terms=True).problem_id


def test_same_circuit_under_different_hamiltonian_has_different_state_id() -> None:
    first = _state(_problem().problem_id)
    second = _state(_problem(second_coefficient=COEFF_A).problem_id)
    assert first.proposed_physical_state_id != second.proposed_physical_state_id


def test_qubit_order_generator_sign_and_coefficient_bytes_change_state_id() -> None:
    base = _state(_problem().problem_id)
    assert replace(base, qubit_order=(1, 0)).proposed_physical_state_id != base.proposed_physical_state_id
    flipped = replace(
        base,
        generator_semantics=(
            replace(base.generator_semantics[0], sign=-1),
            base.generator_semantics[1],
        ),
    )
    assert flipped.proposed_physical_state_id != base.proposed_physical_state_id
    changed = replace(base, canonical_coefficient_bytes=(COEFF_B, COEFF_B))
    assert changed.proposed_physical_state_id != base.proposed_physical_state_id


def test_generator_enumeration_order_is_identity_invariant() -> None:
    base = _state(_problem().problem_id)
    reordered = replace(base, generator_semantics=tuple(reversed(base.generator_semantics)))
    assert reordered.proposed_physical_state_id == base.proposed_physical_state_id


def test_optimizer_or_budget_changes_execution_request_id() -> None:
    request = _request(_state(_problem().problem_id).proposed_physical_state_id)
    optimizer_changed = replace(request, optimizer={"name": "adam", "max_iterations": 100})
    budget_changed = replace(request, energy_budget_hartree="0.0002")
    assert optimizer_changed.execution_request_id != request.execution_request_id
    assert budget_changed.execution_request_id != request.execution_request_id


def test_different_intents_same_state_share_one_evaluation_and_keep_aliases() -> None:
    state_id = _state(_problem().problem_id).proposed_physical_state_id
    first = _intent("path-a")
    second = _intent("path-b")
    index = PhysicalStateEvaluationIndex()
    for intent in (first, second):
        index.add_alias(
            IntentAlias(
                candidate_intent_id=intent.candidate_intent_id,
                proposed_physical_state_id=state_id,
                candidate_provenance=intent.candidate_provenance,
                generation_path=intent.generation_path,
                generation_work_digest=DIGEST_A,
            )
        )
    assert index.bind_evaluation(state_id, DIGEST_B) is True
    assert index.bind_evaluation(state_id, DIGEST_B) is False
    assert index.quantum_evaluation_count == 1
    assert len(index.aliases_for(state_id)) == 2
    assert index.document()["intent_alias_count"] == 2


def test_second_different_evaluation_for_same_state_is_rejected() -> None:
    state_id = _state(_problem().problem_id).proposed_physical_state_id
    intent = _intent("path-a")
    index = PhysicalStateEvaluationIndex()
    index.add_alias(
        IntentAlias(
            intent.candidate_intent_id,
            state_id,
            intent.candidate_provenance,
            intent.generation_path,
            DIGEST_A,
        )
    )
    index.bind_evaluation(state_id, DIGEST_A)
    with pytest.raises(IdentityError, match="different quantum evaluation"):
        index.bind_evaluation(state_id, DIGEST_B)


def test_binary_float_in_identity_payload_is_rejected() -> None:
    with pytest.raises(IdentityError, match="exact bytes or decimal text"):
        CandidateIntent("source", "rewrite", "target", {"score": 0.1}, ("path",))


@pytest.mark.parametrize(
    ("field", "value"),
    [("energy_budget_hartree", "NaN"), ("stationarity_threshold", "-0.1")],
)
def test_execution_request_rejects_nonfinite_or_negative_thresholds(
    field: str, value: str
) -> None:
    request = _request(_state(_problem().problem_id).proposed_physical_state_id)
    with pytest.raises(IdentityError, match="decimal text"):
        replace(request, **{field: value})


def test_problem_rejects_hamiltonian_dimension_mismatch() -> None:
    with pytest.raises(IdentityError, match="qubit count"):
        replace(_problem(), qubit_count=3)

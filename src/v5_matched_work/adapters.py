"""Six executable comparator adapters sharing one immutable-source/counter API.

The module is infrastructure.  Molecular performance execution is deliberately
absent; S6 must supply a frozen backend only after the S5-v2 tag exists.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Protocol, Sequence

from .atomic_artifacts import canonical_json_bytes
from .comparators import ImmutableSource, PRIMARY_METHODS
from .work_ledger import WorkLedger, WorkVector


class AdapterError(RuntimeError):
    pass


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    proposed_state_id: str
    magnitude_rank: int


@dataclass(frozen=True)
class Evaluation:
    accepted: bool
    final_state_id: str | None
    outcome: str


@dataclass(frozen=True)
class AdapterResult:
    method_id: str
    case_id: str
    accepted_state_ids: tuple[str, ...]
    stop_reason: str
    source_digest_before: str
    source_digest_after: str
    event_digest: str


class AdapterBackend(Protocol):
    def catalog(self, parent_state_id: str) -> Sequence[Candidate]: ...
    def evaluate(self, candidate: Candidate, parent_state_id: str) -> Evaluation: ...


def _source_digest(source: ImmutableSource) -> str:
    return hashlib.sha256(canonical_json_bytes({
        "state_preparation_id": source.state_preparation_id,
        "problem_id": source.problem_id,
        "coefficients": source.coefficients,
        "ansatz_indices": source.ansatz_indices,
        "structure_digest": source.structure_digest,
    })).hexdigest()


def _event_digest(ledger: WorkLedger) -> str:
    return hashlib.sha256(canonical_json_bytes([
        {"event_id": event.event_id, "sequence": event.sequence}
        for event in ledger.events
    ])).hexdigest()


def _charge(
    ledger: WorkLedger,
    *,
    method_id: str,
    case_id: str,
    candidate_id: str | None,
    path_id: str,
    operation: str,
    outcome: str = "completed",
    units: int = 1,
) -> None:
    ledger.charge(
        operation,
        method_id=method_id,
        case_id=case_id,
        candidate_id=candidate_id,
        path_id=path_id,
        outcome=outcome,
        units=units,
    )


def _catalog(
    backend: AdapterBackend,
    ledger: WorkLedger,
    *,
    method_id: str,
    case_id: str,
    parent_state_id: str,
    count_duplicate_states: bool,
) -> tuple[Candidate, ...]:
    values = tuple(backend.catalog(parent_state_id))
    unique: list[Candidate] = []
    seen: set[str] = set()
    for candidate in values:
        outcome = "duplicate" if candidate.candidate_id in seen else "completed"
        _charge(
            ledger,
            method_id=method_id,
            case_id=case_id,
            candidate_id=candidate.candidate_id,
            path_id=parent_state_id,
            operation="exact-algebraic-rewrite",
            outcome=outcome,
        )
        if outcome == "duplicate" and not count_duplicate_states:
            ledger.record_evidence(
                "duplicate-detection",
                method_id=method_id,
                case_id=case_id,
                candidate_id=candidate.candidate_id,
                path_id=parent_state_id,
                outcome="duplicate",
            )
            continue
        _charge(
            ledger,
            method_id=method_id,
            case_id=case_id,
            candidate_id=candidate.candidate_id,
            path_id=parent_state_id,
            operation="unique-search-state-expansion",
            outcome=outcome,
        )
        if candidate.candidate_id not in seen:
            seen.add(candidate.candidate_id)
            unique.append(candidate)
    return tuple(unique)


def _evaluate(
    backend: AdapterBackend,
    ledger: WorkLedger,
    *,
    method_id: str,
    case_id: str,
    parent_state_id: str,
    candidate: Candidate,
) -> Evaluation:
    common = dict(
        method_id=method_id,
        case_id=case_id,
        candidate_id=candidate.candidate_id,
        path_id=parent_state_id,
    )
    _charge(ledger, **common, operation="exact-candidate-attempt")
    _charge(ledger, **common, operation="candidate-energy-evaluation")
    result = backend.evaluate(candidate, parent_state_id)
    _charge(ledger, **common, operation="full-physical-resource-recount", outcome=result.outcome)
    if not result.accepted:
        _charge(ledger, **common, operation="exact-algebraic-rewrite", outcome="rollback")
    return result


def run_comparator(
    method_id: str,
    *,
    case_id: str,
    source: ImmutableSource,
    backend: AdapterBackend,
    cap: WorkVector,
    maximum_rounds: int = 2,
    counter_semantics: str = "v2",
) -> tuple[AdapterResult, WorkLedger]:
    if method_id not in PRIMARY_METHODS:
        raise AdapterError("unregistered comparator")
    if counter_semantics not in {"v2", "v3-unique-states"}:
        raise AdapterError("unregistered counter semantics")
    count_duplicate_states = counter_semantics == "v2"
    before = _source_digest(source)
    ledger = WorkLedger(cap)
    accepted: list[str] = []
    source_state = source.state_preparation_id

    if method_id == "immutable-ceo-star-source":
        _charge(ledger, method_id=method_id, case_id=case_id, candidate_id=None,
                path_id=source_state, operation="full-physical-resource-recount")
        stop = "source-only"
    elif method_id == "same-structure-reoptimization":
        candidate = Candidate("same-structure", source_state, 0)
        outcome = _evaluate(backend, ledger, method_id=method_id, case_id=case_id,
                            parent_state_id=source_state, candidate=candidate)
        if outcome.accepted and outcome.final_state_id:
            accepted.append(outcome.final_state_id)
        stop = "same-structure-complete"
    elif method_id == "structural-magnitude-pruning":
        catalog = sorted(_catalog(backend, ledger, method_id=method_id, case_id=case_id,
                                  parent_state_id=source_state,
                                  count_duplicate_states=count_duplicate_states), key=lambda item: (item.magnitude_rank, item.candidate_id))
        if catalog:
            outcome = _evaluate(backend, ledger, method_id=method_id, case_id=case_id,
                                parent_state_id=source_state, candidate=catalog[0])
            if outcome.accepted and outcome.final_state_id:
                accepted.append(outcome.final_state_id)
        stop = "one-structural-attempt"
    elif method_id == "v4.1-one-shot-joint-compression":
        _charge(ledger, method_id=method_id, case_id=case_id, candidate_id=None,
                path_id=source_state, operation="sequential-round-attempt")
        for candidate in _catalog(backend, ledger, method_id=method_id, case_id=case_id,
                                  parent_state_id=source_state,
                                  count_duplicate_states=count_duplicate_states):
            outcome = _evaluate(backend, ledger, method_id=method_id, case_id=case_id,
                                parent_state_id=source_state, candidate=candidate)
            if outcome.accepted and outcome.final_state_id:
                accepted.append(outcome.final_state_id)
        stop = "one-shot-complete"
    else:
        rebuild = method_id == "v5-sequential-with-rebuilding"
        parent_state = source_state
        original = _catalog(backend, ledger, method_id=method_id, case_id=case_id,
                            parent_state_id=source_state,
                            count_duplicate_states=count_duplicate_states)
        stop = "maximum-rounds"
        attempted: set[str] = set()
        for _ in range(maximum_rounds):
            _charge(ledger, method_id=method_id, case_id=case_id, candidate_id=None,
                    path_id=parent_state, operation="sequential-round-attempt")
            catalog = (_catalog(backend, ledger, method_id=method_id, case_id=case_id,
                                parent_state_id=parent_state,
                                count_duplicate_states=count_duplicate_states) if rebuild else original)
            candidate = next((item for item in catalog if item.candidate_id not in attempted), None)
            if candidate is None:
                stop = "no-new-candidate"
                break
            attempted.add(candidate.candidate_id)
            outcome = _evaluate(backend, ledger, method_id=method_id, case_id=case_id,
                                parent_state_id=parent_state, candidate=candidate)
            if not outcome.accepted or not outcome.final_state_id:
                stop = "rejected-with-rollback"
                break
            accepted.append(outcome.final_state_id)
            parent_state = outcome.final_state_id

    after = _source_digest(source)
    if before != after:
        raise AdapterError("immutable source changed")
    return AdapterResult(method_id, case_id, tuple(accepted), stop, before, after, _event_digest(ledger)), ledger


def run_immutable_source(**kwargs): return run_comparator(PRIMARY_METHODS[0], **kwargs)
def run_same_structure_reoptimization(**kwargs): return run_comparator(PRIMARY_METHODS[1], **kwargs)
def run_structural_magnitude_pruning(**kwargs): return run_comparator(PRIMARY_METHODS[2], **kwargs)
def run_v41_one_shot(**kwargs): return run_comparator(PRIMARY_METHODS[3], **kwargs)
def run_v5_without_rebuilding(**kwargs): return run_comparator(PRIMARY_METHODS[4], **kwargs)
def run_v5_with_rebuilding(**kwargs): return run_comparator(PRIMARY_METHODS[5], **kwargs)


ENTRYPOINTS = {
    PRIMARY_METHODS[0]: "v5_matched_work.adapters:run_immutable_source",
    PRIMARY_METHODS[1]: "v5_matched_work.adapters:run_same_structure_reoptimization",
    PRIMARY_METHODS[2]: "v5_matched_work.adapters:run_structural_magnitude_pruning",
    PRIMARY_METHODS[3]: "v5_matched_work.adapters:run_v41_one_shot",
    PRIMARY_METHODS[4]: "v5_matched_work.adapters:run_v5_without_rebuilding",
    PRIMARY_METHODS[5]: "v5_matched_work.adapters:run_v5_with_rebuilding",
}

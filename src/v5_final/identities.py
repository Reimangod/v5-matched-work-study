"""Content-addressed scientific identities and lossless deduplication aliases."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import re
from typing import Any, Mapping, Sequence

from v5_matched_work.atomic_artifacts import canonical_json_bytes


class IdentityError(ValueError):
    pass


SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
HEX_BYTES_PATTERN = re.compile(r"^(?:[0-9a-f]{2})+$")


def _validate_digest(value: str, label: str) -> None:
    if not SHA256_PATTERN.fullmatch(value):
        raise IdentityError(f"{label} must be a lowercase SHA-256 digest")


def _validate_id(value: str, prefix: str) -> None:
    if not re.fullmatch(re.escape(prefix) + r":[0-9a-f]{64}", value):
        raise IdentityError(f"identity must use {prefix}:<sha256>")


def _validate_exact_bytes(value: str, label: str) -> None:
    if not HEX_BYTES_PATTERN.fullmatch(value):
        raise IdentityError(f"{label} must be nonempty lowercase hexadecimal bytes")


def _validate_decimal_text(value: str, label: str, *, nonnegative: bool = False) -> None:
    try:
        parsed = Decimal(value)
    except (InvalidOperation, TypeError) as error:
        raise IdentityError(f"{label} must be finite decimal text") from error
    if not parsed.is_finite() or (nonnegative and parsed < 0):
        qualifier = "nonnegative finite" if nonnegative else "finite"
        raise IdentityError(f"{label} must be {qualifier} decimal text")


def _validate_canonical_data(value: Any, path: str = "value") -> None:
    """Reject ambiguous/nonportable payload types before hashing."""

    if value is None or isinstance(value, (bool, int, str)):
        return
    if isinstance(value, float):
        raise IdentityError(f"{path} must encode numeric data as exact bytes or decimal text")
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                raise IdentityError(f"{path} mapping keys must be strings")
            _validate_canonical_data(child, f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _validate_canonical_data(child, f"{path}[{index}]")
        return
    raise IdentityError(f"{path} contains a noncanonical type: {type(value).__name__}")


def _content_id(prefix: str, payload: Mapping[str, Any]) -> str:
    _validate_canonical_data(payload)
    return f"{prefix}:" + hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


@dataclass(frozen=True)
class HamiltonianTerm:
    pauli_word: str
    coefficient_bytes: str

    def __post_init__(self) -> None:
        if not self.pauli_word:
            raise IdentityError("Hamiltonian Pauli word is required")
        _validate_exact_bytes(self.coefficient_bytes, "Hamiltonian coefficient")


@dataclass(frozen=True)
class ProblemSpec:
    system_label: str
    geometry_decimal: tuple[str, ...]
    basis: str
    charge: int
    multiplicity: int
    mapping: str
    qubit_count: int
    hamiltonian_terms: tuple[HamiltonianTerm, ...]

    def __post_init__(self) -> None:
        if not self.system_label or not self.basis or not self.mapping:
            raise IdentityError("problem system, basis, and mapping are required")
        if isinstance(self.charge, bool) or not isinstance(self.charge, int):
            raise IdentityError("charge must be an integer")
        if (
            isinstance(self.multiplicity, bool)
            or not isinstance(self.multiplicity, int)
            or self.multiplicity < 1
        ):
            raise IdentityError("multiplicity must be a positive integer")
        if (
            isinstance(self.qubit_count, bool)
            or not isinstance(self.qubit_count, int)
            or self.qubit_count < 1
        ):
            raise IdentityError("qubit count must be a positive integer")
        if not self.hamiltonian_terms:
            raise IdentityError("problem Hamiltonian cannot be empty")
        if not self.geometry_decimal:
            raise IdentityError("problem geometry cannot be empty")
        if len({term.pauli_word for term in self.hamiltonian_terms}) != len(
            self.hamiltonian_terms
        ):
            raise IdentityError("Hamiltonian Pauli words must be unique after collection")
        if any(
            len(term.pauli_word) != self.qubit_count
            or any(symbol not in "IXYZ" for symbol in term.pauli_word)
            for term in self.hamiltonian_terms
        ):
            raise IdentityError("Hamiltonian Pauli words must match the problem qubit count")
        for coordinate in self.geometry_decimal:
            _validate_decimal_text(coordinate, "geometry coordinate")

    def payload(self) -> dict[str, Any]:
        terms = sorted(
            (asdict(term) for term in self.hamiltonian_terms),
            key=canonical_json_bytes,
        )
        return {
            "schema": "v5-final.problem.v1",
            "system_label": self.system_label,
            "geometry_decimal": list(self.geometry_decimal),
            "basis": self.basis,
            "charge": self.charge,
            "multiplicity": self.multiplicity,
            "mapping": self.mapping,
            "qubit_count": self.qubit_count,
            "hamiltonian_terms": terms,
        }

    @property
    def problem_id(self) -> str:
        return _content_id("problem-v1", self.payload())


@dataclass(frozen=True)
class CandidateIntent:
    source_block: str
    transformation_family: str
    target_family: str
    candidate_provenance: Mapping[str, Any]
    generation_path: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.source_block or not self.transformation_family or not self.target_family:
            raise IdentityError("candidate intent families and source block are required")
        if not self.generation_path or any(not step for step in self.generation_path):
            raise IdentityError("candidate generation path must be nonempty")
        _validate_canonical_data(self.candidate_provenance, "candidate_provenance")

    def payload(self) -> dict[str, Any]:
        return {
            "schema": "v5-final.candidate-intent.v1",
            "source_block": self.source_block,
            "transformation_family": self.transformation_family,
            "target_family": self.target_family,
            "candidate_provenance": dict(self.candidate_provenance),
            "generation_path": list(self.generation_path),
        }

    @property
    def candidate_intent_id(self) -> str:
        return _content_id("candidate-intent-v1", self.payload())


@dataclass(frozen=True)
class GeneratorSemantic:
    support: tuple[int, ...]
    operator_family: str
    sign: int
    coefficient_bytes: str

    def __post_init__(self) -> None:
        if not self.support or len(set(self.support)) != len(self.support):
            raise IdentityError("generator support must be a nonempty unique sequence")
        if any(isinstance(index, bool) or not isinstance(index, int) or index < 0 for index in self.support):
            raise IdentityError("generator support indices must be nonnegative integers")
        if not self.operator_family or self.sign not in {-1, 1}:
            raise IdentityError("generator family and a +/-1 sign are required")
        _validate_exact_bytes(self.coefficient_bytes, "generator coefficient")


@dataclass(frozen=True)
class NativeGateSemantic:
    gate: str
    qubits: tuple[int, ...]
    parameter_bytes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.gate or not self.qubits:
            raise IdentityError("native gate name and qubits are required")
        if len(set(self.qubits)) != len(self.qubits):
            raise IdentityError("native gate qubits must be unique")
        if any(isinstance(index, bool) or not isinstance(index, int) or index < 0 for index in self.qubits):
            raise IdentityError("native gate qubits must be nonnegative integers")
        for parameter in self.parameter_bytes:
            _validate_exact_bytes(parameter, "native gate parameter")


@dataclass(frozen=True)
class ProposedPhysicalState:
    problem_id: str
    reference_state: tuple[int, ...]
    generator_semantics: tuple[GeneratorSemantic, ...]
    block_order: tuple[str, ...]
    mapping: str
    qubit_order: tuple[int, ...]
    canonical_coefficient_bytes: tuple[str, ...]
    target_structure: Mapping[str, Any]
    native_circuit_semantics: tuple[NativeGateSemantic, ...]

    def __post_init__(self) -> None:
        _validate_id(self.problem_id, "problem-v1")
        if not self.reference_state or any(
            isinstance(bit, bool) or bit not in {0, 1} for bit in self.reference_state
        ):
            raise IdentityError("reference state must be a nonempty bit sequence")
        if not self.generator_semantics or not self.block_order or not self.mapping:
            raise IdentityError("generator semantics, block order, and mapping are required")
        if len(set(self.block_order)) != len(self.block_order):
            raise IdentityError("block order entries must be unique")
        if sorted(self.qubit_order) != list(range(len(self.qubit_order))):
            raise IdentityError("qubit order must be a permutation of its indices")
        if len(self.reference_state) != len(self.qubit_order):
            raise IdentityError("reference state and qubit order dimensions must match")
        if any(
            index >= len(self.qubit_order)
            for generator in self.generator_semantics
            for index in generator.support
        ):
            raise IdentityError("generator support exceeds the state qubit dimension")
        if len(self.canonical_coefficient_bytes) != len(self.block_order):
            raise IdentityError("one canonical coefficient byte string is required per block")
        for coefficient in self.canonical_coefficient_bytes:
            _validate_exact_bytes(coefficient, "canonical coefficient")
        _validate_canonical_data(self.target_structure, "target_structure")
        if not self.native_circuit_semantics:
            raise IdentityError("native circuit semantics are required")
        if any(
            index >= len(self.qubit_order)
            for gate in self.native_circuit_semantics
            for index in gate.qubits
        ):
            raise IdentityError("native circuit qubit exceeds the state dimension")

    def payload(self) -> dict[str, Any]:
        generators = sorted(
            (asdict(generator) for generator in self.generator_semantics),
            key=canonical_json_bytes,
        )
        return {
            "schema": "v5-final.proposed-physical-state.v1",
            "ProblemID": self.problem_id,
            "reference_state": list(self.reference_state),
            "generator_semantics": generators,
            "block_order": list(self.block_order),
            "mapping": self.mapping,
            "qubit_order": list(self.qubit_order),
            "canonical_coefficient_bytes": list(self.canonical_coefficient_bytes),
            "target_structure": dict(self.target_structure),
            "native_circuit_semantics": [
                asdict(gate) for gate in self.native_circuit_semantics
            ],
        }

    @property
    def proposed_physical_state_id(self) -> str:
        return _content_id("physical-state-v1", self.payload())


@dataclass(frozen=True)
class ExecutionRequest:
    proposed_physical_state_id: str
    source_checkpoint_digest: str
    optimizer: Mapping[str, Any]
    initialization: Mapping[str, Any]
    work_profile: Mapping[str, Any]
    energy_budget_hartree: str
    stationarity_threshold: str
    protocol_digest: str
    environment_digest: str

    def __post_init__(self) -> None:
        _validate_id(self.proposed_physical_state_id, "physical-state-v1")
        for label, digest in (
            ("source checkpoint", self.source_checkpoint_digest),
            ("protocol", self.protocol_digest),
            ("environment", self.environment_digest),
        ):
            _validate_digest(digest, label)
        for label, value in (
            ("optimizer", self.optimizer),
            ("initialization", self.initialization),
            ("work_profile", self.work_profile),
        ):
            if not value:
                raise IdentityError(f"{label} cannot be empty")
            _validate_canonical_data(value, label)
        _validate_decimal_text(
            self.energy_budget_hartree, "energy budget", nonnegative=True
        )
        _validate_decimal_text(
            self.stationarity_threshold, "stationarity threshold", nonnegative=True
        )

    def payload(self) -> dict[str, Any]:
        return {
            "schema": "v5-final.execution-request.v1",
            "ProposedPhysicalStateID": self.proposed_physical_state_id,
            "source_checkpoint_digest": self.source_checkpoint_digest,
            "optimizer": dict(self.optimizer),
            "initialization": dict(self.initialization),
            "work_profile": dict(self.work_profile),
            "energy_budget_hartree": self.energy_budget_hartree,
            "stationarity_threshold": self.stationarity_threshold,
            "protocol_digest": self.protocol_digest,
            "environment_digest": self.environment_digest,
        }

    @property
    def execution_request_id(self) -> str:
        return _content_id("execution-request-v1", self.payload())


@dataclass(frozen=True)
class IntentAlias:
    candidate_intent_id: str
    proposed_physical_state_id: str
    candidate_provenance: Mapping[str, Any]
    generation_path: tuple[str, ...]
    generation_work_digest: str
    rejection_history: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _validate_id(self.candidate_intent_id, "candidate-intent-v1")
        _validate_id(self.proposed_physical_state_id, "physical-state-v1")
        _validate_digest(self.generation_work_digest, "generation work")
        _validate_canonical_data(self.candidate_provenance, "candidate_provenance")
        if not self.generation_path:
            raise IdentityError("alias generation path is required")
        if any(not item for item in self.generation_path + self.rejection_history):
            raise IdentityError("alias path and rejection history entries must be nonempty")

    def payload(self) -> dict[str, Any]:
        return {
            "candidate_intent_id": self.candidate_intent_id,
            "proposed_physical_state_id": self.proposed_physical_state_id,
            "candidate_provenance": dict(self.candidate_provenance),
            "generation_path": list(self.generation_path),
            "generation_work_digest": self.generation_work_digest,
            "rejection_history": list(self.rejection_history),
        }

    @property
    def alias_digest(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.payload())).hexdigest()


class PhysicalStateEvaluationIndex:
    """One quantum evaluation per physical state, with every intent retained."""

    def __init__(self) -> None:
        self._aliases: dict[str, list[IntentAlias]] = {}
        self._intent_ids: set[str] = set()
        self._evaluation_segments: dict[str, str] = {}

    def add_alias(self, alias: IntentAlias) -> None:
        if alias.candidate_intent_id in self._intent_ids:
            raise IdentityError("CandidateIntentID may appear in only one alias record")
        self._intent_ids.add(alias.candidate_intent_id)
        self._aliases.setdefault(alias.proposed_physical_state_id, []).append(alias)

    def bind_evaluation(self, proposed_physical_state_id: str, segment_digest: str) -> bool:
        _validate_id(proposed_physical_state_id, "physical-state-v1")
        _validate_digest(segment_digest, "evaluation segment")
        if proposed_physical_state_id not in self._aliases:
            raise IdentityError("cannot evaluate a physical state without an intent alias")
        existing = self._evaluation_segments.get(proposed_physical_state_id)
        if existing is None:
            self._evaluation_segments[proposed_physical_state_id] = segment_digest
            return True
        if existing != segment_digest:
            raise IdentityError("physical state already has a different quantum evaluation segment")
        return False

    def aliases_for(self, proposed_physical_state_id: str) -> tuple[IntentAlias, ...]:
        return tuple(self._aliases.get(proposed_physical_state_id, ()))

    @property
    def quantum_evaluation_count(self) -> int:
        return len(self._evaluation_segments)

    def document(self) -> dict[str, Any]:
        states = []
        for state_id in sorted(self._aliases):
            aliases = sorted(
                self._aliases[state_id], key=lambda alias: alias.candidate_intent_id
            )
            states.append(
                {
                    "proposed_physical_state_id": state_id,
                    "aliases": [alias.payload() | {"alias_digest": alias.alias_digest} for alias in aliases],
                    "evaluation_segment_digest": self._evaluation_segments.get(state_id),
                }
            )
        return {
            "schema": "v5-final.physical-state-evaluation-index.v1",
            "states": states,
            "quantum_evaluation_count": self.quantum_evaluation_count,
            "intent_alias_count": len(self._intent_ids),
        }

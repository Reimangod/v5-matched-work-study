"""Bounded, outcome-free candidate verifier for the future S11-v2 study.

The verifier deliberately has no optimizer or energy callback.  It performs
symbolic validation, semantic and physical deduplication, outcome-blind
ranking, a digest-bound top-K freeze, and sparse state-probe certification.
Operational timings are returned separately from the byte-reproducible core.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import resource
import time
from typing import Any, Callable, Mapping, Sequence

import numpy as np
from scipy import sparse
from scipy.sparse.linalg import expm_multiply, norm as sparse_norm

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive


class VerifierV2Error(RuntimeError):
    """Fail-closed verifier contract violation."""


DETERMINISTIC_COUNTER_FIELDS = (
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
)
OPERATIONAL_COUNTER_FIELDS = (
    "CPU_time_seconds",
    "wall_time_seconds",
    "peak_RSS_raw",
)
ALL_COUNTER_FIELDS = DETERMINISTIC_COUNTER_FIELDS + OPERATIONAL_COUNTER_FIELDS


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _float_hex(value: float) -> str:
    number = float(value)
    if number == 0.0:
        number = 0.0
    return number.hex()


def _matrix_hex(value: Sequence[Sequence[float]]) -> list[list[str]]:
    return [[_float_hex(item) for item in row] for row in value]


@dataclass(frozen=True)
class VerifierV2Policy:
    top_k: int = 4
    tie_break: tuple[str, ...] = (
        "OBS_predicted_loss_float64",
        "resource_vector_lexicographic",
        "candidate_id",
    )
    probe_count: int = 3
    seed: int = 20260815
    tolerance: float = 1e-10

    def __post_init__(self) -> None:
        if self.top_k <= 0 or self.probe_count <= 0 or self.tolerance <= 0.0:
            raise VerifierV2Error("invalid frozen verifier policy")
        if self.tie_break != (
            "OBS_predicted_loss_float64",
            "resource_vector_lexicographic",
            "candidate_id",
        ):
            raise VerifierV2Error("unregistered ranking tie-break")

    def to_dict(self) -> dict[str, Any]:
        body = {
            "schema": "v5-final.verifier-v2-policy.v1",
            "top_k": self.top_k,
            "tie_break": list(self.tie_break),
            "probe_count": self.probe_count,
            "seed": self.seed,
            "tolerance_float64_hex": _float_hex(self.tolerance),
            "candidate_outcomes_used_to_choose_policy": False,
        }
        body["policy_digest"] = _digest(body)
        return body


@dataclass(frozen=True)
class CandidateV2:
    candidate_id: str
    semantic_id: str
    proposed_state_preparation_id: str
    source_generator_digests: tuple[str, ...]
    target_generator_digests: tuple[str, ...]
    jacobian: tuple[tuple[float, ...], ...]
    obs_predicted_loss: float
    matrix_dimension: int
    qubit_count: int
    resource_recount: Callable[[], Sequence[int] | Mapping[str, Any]] = field(
        repr=False, compare=False
    )
    circuit_state_factory: Callable[[np.ndarray, np.ndarray], np.ndarray] | None = field(
        default=None, repr=False, compare=False
    )
    deletion_shortcut: bool = False

    def deterministic_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "semantic_id": self.semantic_id,
            "proposed_state_preparation_id": self.proposed_state_preparation_id,
            "source_generator_digests": list(self.source_generator_digests),
            "target_generator_digests": list(self.target_generator_digests),
            "jacobian_float64_hex": _matrix_hex(self.jacobian),
            "OBS_predicted_loss_float64_hex": _float_hex(self.obs_predicted_loss),
            "matrix_dimension": self.matrix_dimension,
            "qubit_count": self.qubit_count,
            "deletion_shortcut": self.deletion_shortcut,
        }


def _empty_counts() -> dict[str, int]:
    return {field: 0 for field in DETERMINISTIC_COUNTER_FIELDS}


def _merge_counts(target: dict[str, int], delta: Mapping[str, int]) -> None:
    unknown = set(delta) - set(DETERMINISTIC_COUNTER_FIELDS)
    if unknown:
        raise VerifierV2Error(f"unknown primitive counters: {sorted(unknown)}")
    for key, value in delta.items():
        if int(value) < 0:
            raise VerifierV2Error("primitive counter cannot be negative")
        if key in {"matrix_dimension", "qubit_count"}:
            target[key] = max(target[key], int(value))
        else:
            target[key] += int(value)


class VerifierV2:
    def __init__(
        self,
        *,
        policy: VerifierV2Policy,
        generator_loader: Callable[[str], Any],
        checkpoint_dir: Path,
        source_binding: Mapping[str, Any],
        initial_counts: Mapping[str, int] | None = None,
    ) -> None:
        self.policy = policy
        self.generator_loader = generator_loader
        self.checkpoint_dir = checkpoint_dir
        self.source_binding = dict(source_binding)
        self.initial_counts = dict(initial_counts or {})
        initial_validation = _empty_counts()
        _merge_counts(initial_validation, self.initial_counts)
        if (
            initial_validation["N_dense_expm"]
            or initial_validation["optimizer_iterations"]
            or initial_validation["energy_evaluations"]
        ):
            raise VerifierV2Error("initial work crosses the outcome-free boundary")
        self._generator_cache: dict[str, sparse.csr_matrix] = {}
        self._semantic_cache: dict[str, dict[str, Any]] = {}

    def _binding(self, candidates: Sequence[CandidateV2]) -> dict[str, Any]:
        body = {
            "schema": "v5-final.verifier-v2-session-binding.v1",
            "source_binding": self.source_binding,
            "initial_deterministic_work_counters": self.initial_counts,
            "policy": self.policy.to_dict(),
            "candidate_descriptors": [
                candidate.deterministic_dict() for candidate in candidates
            ],
        }
        body["session_digest"] = _digest(body)
        return body

    def _ensure_binding(self, binding: Mapping[str, Any]) -> None:
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        path = self.checkpoint_dir / "session-binding-v2.json"
        if path.exists():
            if json.loads(path.read_text()) != binding:
                raise VerifierV2Error("checkpoint session binding differs")
        else:
            write_json_exclusive(path, dict(binding))

    @staticmethod
    def _ensure_exact_record(path: Path, record: Mapping[str, Any]) -> None:
        if path.exists():
            if json.loads(path.read_text()) != record:
                raise VerifierV2Error(f"durable record differs: {path.name}")
        else:
            write_json_exclusive(path, dict(record))

    def _cache_semantic_certificate(self, certificate: Mapping[str, Any]) -> None:
        suffix = hashlib.sha256(str(certificate["semantic_id"]).encode()).hexdigest()
        self._ensure_exact_record(
            self.checkpoint_dir / f"semantic-{suffix}.json", certificate
        )

    @staticmethod
    def _sparse_content_digest(matrix: sparse.csr_matrix) -> str:
        payload = {
            "shape": list(matrix.shape),
            "indptr": matrix.indptr.astype(np.int64, copy=False).tobytes().hex(),
            "indices": matrix.indices.astype(np.int64, copy=False).tobytes().hex(),
            "data": matrix.data.astype(np.complex128, copy=False).tobytes().hex(),
        }
        return _digest(payload)

    def _structural_certificate(self, candidate: CandidateV2) -> dict[str, Any]:
        if not all(
            (
                candidate.candidate_id,
                candidate.semantic_id,
                candidate.proposed_state_preparation_id,
            )
        ):
            raise VerifierV2Error("candidate identity is incomplete")
        if candidate.matrix_dimension != 2 ** candidate.qubit_count:
            raise VerifierV2Error("matrix dimension and qubit count differ")
        rows = len(candidate.source_generator_digests)
        columns = len(candidate.target_generator_digests)
        if candidate.deletion_shortcut:
            if columns != 0 or candidate.circuit_state_factory is not None:
                raise VerifierV2Error("deletion shortcut must target exp(0G)=I")
        elif rows == 0 or columns == 0:
            raise VerifierV2Error("non-deletion candidate lacks generators")
        if len(candidate.jacobian) != rows or any(
            len(row) != columns for row in candidate.jacobian
        ):
            raise VerifierV2Error("jacobian and generator slots differ")
        body = {
            "schema": "v5-final.verifier-v2-semantic-certificate.v1",
            "semantic_id": candidate.semantic_id,
            "source_generator_digests": list(candidate.source_generator_digests),
            "target_generator_digests": list(candidate.target_generator_digests),
            "jacobian_float64_hex": _matrix_hex(candidate.jacobian),
            "deletion_shortcut": candidate.deletion_shortcut,
            "symbolic_relation_registered": True,
        }
        body["certificate_digest"] = _digest(body)
        return body

    def _load_generator(
        self, digest: str, counts: dict[str, int], dimension: int
    ) -> sparse.csr_matrix:
        matrix = self._generator_cache.get(digest)
        if matrix is None:
            suffix = hashlib.sha256(digest.encode()).hexdigest()
            cache_dir = self.checkpoint_dir / "generator-cache-v2"
            cache_dir.mkdir(parents=True, exist_ok=True)
            matrix_path = cache_dir / f"{suffix}.npz"
            metadata_path = cache_dir / f"{suffix}.json"
            if matrix_path.exists() or metadata_path.exists():
                if not (matrix_path.exists() and metadata_path.exists()):
                    raise VerifierV2Error("partial durable generator cache")
                metadata = json.loads(metadata_path.read_text())
                metadata_body = dict(metadata)
                observed_metadata_digest = metadata_body.pop("cache_digest", None)
                matrix = sparse.load_npz(matrix_path).tocsr().astype(np.complex128)
                if (
                    observed_metadata_digest != _digest(metadata_body)
                    or metadata.get("matrix_shape") != list(matrix.shape)
                    or metadata.get("generator_digest") != digest
                    or metadata.get("sparse_content_digest")
                    != self._sparse_content_digest(matrix)
                ):
                    raise VerifierV2Error("durable generator cache digest mismatch")
            else:
                raw = self.generator_loader(digest)
                if not sparse.issparse(raw):
                    raise VerifierV2Error("generator loader must return a sparse matrix")
                matrix = raw.tocsr().astype(np.complex128)
                temporary = cache_dir / f".{suffix}.{time.time_ns()}.npz"
                sparse.save_npz(temporary, matrix)
                temporary.replace(matrix_path)
                metadata = {
                    "schema": "v5-final.verifier-v2-generator-cache.v1",
                    "generator_digest": digest,
                    "sparse_content_digest": self._sparse_content_digest(matrix),
                    "matrix_shape": list(matrix.shape),
                }
                metadata["cache_digest"] = _digest(metadata)
                write_json_exclusive(metadata_path, metadata)
                counts["N_generator_materializations"] += 1
            if matrix.shape != (dimension, dimension):
                raise VerifierV2Error("generator has the wrong sparse dimension")
            self._generator_cache[digest] = matrix
        return matrix

    @staticmethod
    def _aligned_error(expected: np.ndarray, observed: np.ndarray) -> float:
        overlap = np.vdot(expected, observed)
        if abs(overlap) <= np.finfo(np.float64).tiny:
            return float("inf")
        phase = overlap / abs(overlap)
        return float(np.linalg.norm(observed - phase * expected))

    def _numeric_verify(self, candidate: CandidateV2) -> dict[str, Any]:
        counts = _empty_counts()
        counts["matrix_dimension"] = candidate.matrix_dimension
        counts["qubit_count"] = candidate.qubit_count
        counts["rewrite_verifications"] = 1
        if candidate.deletion_shortcut:
            record = {
                "candidate_id": candidate.candidate_id,
                "semantic_id": candidate.semantic_id,
                "proposed_state_preparation_id": candidate.proposed_state_preparation_id,
                "status": "VERIFIED_ANALYTIC_DELETION_EXP_0G_IDENTITY",
                "maximum_probe_error_float64_hex": _float_hex(0.0),
                "primitive_delta": counts,
                "candidate_energy_evaluations": 0,
                "optimizer_iterations": 0,
            }
            record["verification_digest"] = _digest(record)
            return record

        source = tuple(
            self._load_generator(value, counts, candidate.matrix_dimension)
            for value in candidate.source_generator_digests
        )
        target = tuple(
            self._load_generator(value, counts, candidate.matrix_dimension)
            for value in candidate.target_generator_digests
        )
        tolerance = self.policy.tolerance
        for matrix in (*source, *target):
            counts["N_symbolic_checks"] += 1
            if float(sparse_norm(matrix + matrix.getH())) > tolerance:
                raise VerifierV2Error("generator is not anti-Hermitian")
        for left_index, left in enumerate(source):
            for right in source[left_index + 1 :]:
                counts["N_symbolic_checks"] += 1
                if float(sparse_norm(left @ right - right @ left)) > tolerance:
                    raise VerifierV2Error("source generators do not commute")
        jacobian = np.asarray(candidate.jacobian, dtype=np.float64)
        for target_slot, target_matrix in enumerate(target):
            reconstructed = sparse.csr_matrix(target_matrix.shape, dtype=np.complex128)
            for source_slot, source_matrix in enumerate(source):
                reconstructed = reconstructed + (
                    jacobian[source_slot, target_slot] * source_matrix
                )
            counts["N_symbolic_checks"] += 1
            if float(sparse_norm(reconstructed - target_matrix)) > tolerance:
                raise VerifierV2Error("registered sparse generator relation failed")

        seed_material = f"{self.policy.seed}:{candidate.semantic_id}".encode()
        seed = int.from_bytes(hashlib.sha256(seed_material).digest()[:8], "big")
        rng = np.random.default_rng(seed)
        maximum_error = 0.0
        for _ in range(self.policy.probe_count):
            coordinates = rng.uniform(-0.7, 0.7, size=len(target))
            source_coordinates = jacobian @ coordinates
            probe = rng.normal(size=candidate.matrix_dimension) + 1j * rng.normal(
                size=candidate.matrix_dimension
            )
            probe = np.asarray(probe / np.linalg.norm(probe), dtype=np.complex128)
            counts["N_state_probe_vectors"] += 1
            source_state = probe
            for coordinate, generator in zip(source_coordinates, source):
                source_state = expm_multiply(float(coordinate) * generator, source_state)
                counts["N_sparse_expm_multiply"] += 1
            target_state = probe
            for coordinate, generator in zip(coordinates, target):
                target_state = expm_multiply(float(coordinate) * generator, target_state)
                counts["N_sparse_expm_multiply"] += 1
            error = float(np.linalg.norm(source_state - target_state))
            maximum_error = max(maximum_error, error)
            if error > tolerance:
                raise VerifierV2Error("sparse source and target probes differ")
            if candidate.circuit_state_factory is not None:
                observed = np.asarray(
                    candidate.circuit_state_factory(coordinates, probe),
                    dtype=np.complex128,
                ).ravel()
                counts["N_circuit_operator_builds"] += 1
                circuit_error = self._aligned_error(target_state, observed)
                maximum_error = max(maximum_error, circuit_error)
                if circuit_error > tolerance:
                    raise VerifierV2Error("native circuit state probe differs")
        if counts["N_dense_expm"] != 0:
            raise VerifierV2Error("production dense exponential count is nonzero")
        record = {
            "candidate_id": candidate.candidate_id,
            "semantic_id": candidate.semantic_id,
            "proposed_state_preparation_id": candidate.proposed_state_preparation_id,
            "status": "VERIFIED_SPARSE_STATE_PROBES",
            "maximum_probe_error_float64_hex": _float_hex(maximum_error),
            "primitive_delta": counts,
            "candidate_energy_evaluations": 0,
            "optimizer_iterations": 0,
        }
        record["verification_digest"] = _digest(record)
        return record

    def _checkpoint_path(self, rank: int, candidate: CandidateV2) -> Path:
        suffix = hashlib.sha256(candidate.candidate_id.encode()).hexdigest()[:16]
        return self.checkpoint_dir / f"numeric-{rank:04d}-{suffix}.json"

    def preview_selected_candidate_ids(
        self, candidates: Sequence[CandidateV2]
    ) -> tuple[str, ...]:
        """Reproduce top-K selection without numeric verification or checkpoints.

        This preflight intentionally performs only structural validation,
        semantic/physical deduplication, and deterministic resource ranking.
        It never loads a generator or invokes a circuit-state factory.
        """

        ordered = tuple(sorted(candidates, key=lambda value: value.candidate_id))
        if len({candidate.candidate_id for candidate in ordered}) != len(ordered):
            raise VerifierV2Error("candidate IDs are duplicated")
        semantic_representatives: dict[str, CandidateV2] = {}
        semantic_certificates: dict[str, dict[str, Any]] = {}
        for candidate in ordered:
            certificate = self._structural_certificate(candidate)
            cached = semantic_certificates.get(candidate.semantic_id)
            if cached is not None and cached != certificate:
                raise VerifierV2Error("semantic ID aliases incompatible certificates")
            semantic_certificates[candidate.semantic_id] = certificate
            semantic_representatives.setdefault(candidate.semantic_id, candidate)
        physical_representatives: dict[str, CandidateV2] = {}
        for candidate in semantic_representatives.values():
            physical_representatives.setdefault(
                candidate.proposed_state_preparation_id, candidate
            )
        ranked: list[tuple[tuple[Any, ...], CandidateV2]] = []
        for candidate in physical_representatives.values():
            recount = candidate.resource_recount()
            if isinstance(recount, Mapping):
                resources = tuple(int(value) for value in recount["resource_vector"])
            else:
                resources = tuple(int(value) for value in recount)
            if not resources or any(value < 0 for value in resources):
                raise VerifierV2Error("resource recount is incomplete")
            ranked.append(
                (
                    (candidate.obs_predicted_loss, resources, candidate.candidate_id),
                    candidate,
                )
            )
        ranked.sort(key=lambda value: value[0])
        return tuple(
            candidate.candidate_id
            for _, candidate in ranked[: min(self.policy.top_k, len(ranked))]
        )

    @staticmethod
    def _read_verified_checkpoint(path: Path, candidate: CandidateV2) -> dict[str, Any]:
        record = json.loads(path.read_text())
        body = dict(record)
        observed = body.pop("verification_digest", None)
        if observed != _digest(body) or record.get("candidate_id") != candidate.candidate_id:
            raise VerifierV2Error("numeric checkpoint is invalid or misbound")
        if record.get("candidate_energy_evaluations") != 0:
            raise VerifierV2Error("checkpoint contains forbidden candidate energy")
        return record

    def run(
        self,
        candidates: Sequence[CandidateV2],
        *,
        max_new_numeric_verifications: int | None = None,
    ) -> dict[str, Any]:
        started_wall = time.perf_counter()
        started_cpu = time.process_time()
        ordered_input = tuple(sorted(candidates, key=lambda value: value.candidate_id))
        binding = self._binding(ordered_input)
        self._ensure_binding(binding)
        counts = _empty_counts()
        _merge_counts(counts, self.initial_counts)
        counts["candidate_generations"] = len(ordered_input)

        semantic_representatives: dict[str, CandidateV2] = {}
        semantic_aliases: dict[str, list[str]] = {}
        for candidate in ordered_input:
            certificate = self._structural_certificate(candidate)
            counts["N_symbolic_checks"] += 1
            cached = self._semantic_cache.get(candidate.semantic_id)
            if cached is not None and cached != certificate:
                raise VerifierV2Error("semantic ID aliases incompatible certificates")
            self._semantic_cache[candidate.semantic_id] = certificate
            self._cache_semantic_certificate(certificate)
            semantic_aliases.setdefault(candidate.semantic_id, []).append(
                candidate.candidate_id
            )
            semantic_representatives.setdefault(candidate.semantic_id, candidate)
        counts["unique_semantic_candidates"] = len(semantic_representatives)

        physical_representatives: dict[str, CandidateV2] = {}
        physical_aliases: dict[str, list[str]] = {}
        for candidate in semantic_representatives.values():
            physical_aliases.setdefault(
                candidate.proposed_state_preparation_id, []
            ).append(candidate.candidate_id)
            physical_representatives.setdefault(
                candidate.proposed_state_preparation_id, candidate
            )
        counts["unique_physical_states"] = len(physical_representatives)

        ranked: list[tuple[tuple[Any, ...], CandidateV2, tuple[int, ...]]] = []
        for candidate in physical_representatives.values():
            recount = candidate.resource_recount()
            if isinstance(recount, Mapping):
                resources = tuple(int(value) for value in recount["resource_vector"])
                _merge_counts(
                    counts,
                    {
                        "resource_recounts": int(recount.get("resource_recounts", 1)),
                        "N_circuit_operator_builds": int(
                            recount.get("N_circuit_operator_builds", 0)
                        ),
                    },
                )
            else:
                resources = tuple(int(value) for value in recount)
                counts["resource_recounts"] += 1
            if not resources or any(value < 0 for value in resources):
                raise VerifierV2Error("resource recount is incomplete")
            ranked.append(
                (
                    (candidate.obs_predicted_loss, resources, candidate.candidate_id),
                    candidate,
                    resources,
                )
            )
        ranked.sort(key=lambda value: value[0])
        selected = ranked[: min(self.policy.top_k, len(ranked))]
        selection_body = {
            "schema": "v5-final.verifier-v2-top-k-freeze.v1",
            "policy_digest": self.policy.to_dict()["policy_digest"],
            "session_digest": binding["session_digest"],
            "ranked_candidates": [
                {
                    "rank": index,
                    "candidate_id": candidate.candidate_id,
                    "semantic_id": candidate.semantic_id,
                    "proposed_state_preparation_id": candidate.proposed_state_preparation_id,
                    "OBS_predicted_loss_float64_hex": _float_hex(
                        candidate.obs_predicted_loss
                    ),
                    "resource_vector": list(resources),
                }
                for index, (_, candidate, resources) in enumerate(ranked)
            ],
            "selected_candidate_ids": [
                candidate.candidate_id for _, candidate, _ in selected
            ],
            "candidate_outcomes_observed_before_freeze": False,
        }
        selection_body["selection_digest"] = _digest(selection_body)
        self._ensure_exact_record(
            self.checkpoint_dir / "top-k-freeze-v2.json", selection_body
        )

        verifications: list[dict[str, Any]] = []
        new_count = 0
        incomplete = False
        for rank, (_, candidate, _) in enumerate(selected):
            path = self._checkpoint_path(rank, candidate)
            if path.exists():
                record = self._read_verified_checkpoint(path, candidate)
            else:
                if (
                    max_new_numeric_verifications is not None
                    and new_count >= max_new_numeric_verifications
                ):
                    incomplete = True
                    break
                record = self._numeric_verify(candidate)
                write_json_exclusive(path, record)
                new_count += 1
            _merge_counts(counts, record["primitive_delta"])
            verifications.append(record)
        if counts["N_dense_expm"] != 0:
            raise VerifierV2Error("dense exponential production gate failed")
        if counts["optimizer_iterations"] or counts["energy_evaluations"]:
            raise VerifierV2Error("outcome-free verifier crossed execution boundary")

        core = {
            "schema": "v5-final.verifier-v2-core.v1",
            "status": (
                "CHECKPOINTED_INCOMPLETE_OUTCOME_FREE"
                if incomplete
                else "VERIFIED_READY_AWAITING_OUTCOME_AUTHORIZATION"
            ),
            "session_binding": binding,
            "semantic_aliases": {
                key: sorted(value) for key, value in sorted(semantic_aliases.items())
            },
            "physical_aliases": {
                key: sorted(value) for key, value in sorted(physical_aliases.items())
            },
            "top_k_freeze": selection_body,
            "numeric_verifications": verifications,
            "deterministic_work_counters": counts,
            "counter_schema": {
                "deterministic": list(DETERMINISTIC_COUNTER_FIELDS),
                "operational_sidecar": list(OPERATIONAL_COUNTER_FIELDS),
            },
            "authorization": {
                "optimizer": "NOT_AUTHORIZED",
                "candidate_energy": "NOT_AUTHORIZED",
                "FCI_reporting": "NOT_AUTHORIZED",
                "performance_claim": "NOT_AUTHORIZED",
            },
        }
        core["core_digest"] = _digest(core)
        telemetry = {
            "schema": "v5-final.verifier-v2-operational-telemetry.v1",
            "core_digest": core["core_digest"],
            "CPU_time_seconds": time.process_time() - started_cpu,
            "wall_time_seconds": time.perf_counter() - started_wall,
            "peak_RSS_raw": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
            "peak_RSS_unit": "platform_ru_maxrss",
            "new_numeric_verifications": new_count,
            "resumed_numeric_verifications": len(verifications) - new_count,
        }
        return {"core": core, "operational_telemetry": telemetry}


def write_verifier_v2_artifacts(
    output_dir: Path, result: Mapping[str, Any]
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    core_path = output_dir / "verification-core-v2.json"
    telemetry_path = output_dir / "operational-telemetry-v2.json"
    write_json_exclusive(core_path, dict(result["core"]))
    write_json_exclusive(telemetry_path, dict(result["operational_telemetry"]))
    return core_path, telemetry_path

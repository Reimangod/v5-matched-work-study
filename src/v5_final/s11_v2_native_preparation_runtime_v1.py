"""Outcome-free, cumulative Verifier V2 preparation for S11 queue v2.

This module realizes the verifier policy already frozen in queue v2.  It has
no optimizer or molecular-energy entrypoint.  Every verifier session is
durable, its deterministic counters are reconstructed cumulatively, and the
frozen componentwise verifier cap is checked before a new session starts.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from dvg_obs_ceo.block_ir import recover_dvg_blocks
from dvg_obs_ceo.identity import StatePreparationSpec
from dvg_obs_ceo.molecular_identity import (
    generator_definition_digest,
    state_preparation_spec,
)
from dvg_obs_ceo.resources import (
    AnsatzStructure,
    evaluate_full_circuit_resources,
    paper_era_backend,
)
from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .parent_native_executors import PreparedMagnitudeDeletion
from .parent_native_physical_identity import canonical_proposed_physical_state_id
from .verifier_v2 import (
    CandidateV2,
    DETERMINISTIC_COUNTER_FIELDS,
    VerifierV2,
    VerifierV2Policy,
)


MAXIMUM_FIELDS = {"matrix_dimension", "qubit_count"}


class S11V2NativePreparationError(RuntimeError):
    pass


class VerifierComponentwiseCapRejected(S11V2NativePreparationError):
    """A verifier session was rejected before any of its work was run."""


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _float_hex(value: float) -> str:
    return float(value).hex()


def _empty_counts() -> dict[str, int]:
    return {field: 0 for field in DETERMINISTIC_COUNTER_FIELDS}


def _merge_counts(
    left: Mapping[str, int], right: Mapping[str, int]
) -> dict[str, int]:
    if set(left) != set(DETERMINISTIC_COUNTER_FIELDS) or set(right) != set(
        DETERMINISTIC_COUNTER_FIELDS
    ):
        raise S11V2NativePreparationError("verifier counter schema differs")
    merged = {}
    for field in DETERMINISTIC_COUNTER_FIELDS:
        first = int(left[field])
        second = int(right[field])
        if first < 0 or second < 0:
            raise S11V2NativePreparationError("verifier counter is negative")
        merged[field] = (
            max(first, second) if field in MAXIMUM_FIELDS else first + second
        )
    return merged


def _fits(value: Mapping[str, int], cap: Mapping[str, int]) -> bool:
    return set(value) == set(cap) == set(DETERMINISTIC_COUNTER_FIELDS) and all(
        int(value[field]) <= int(cap[field])
        for field in DETERMINISTIC_COUNTER_FIELDS
    )


def policy_from_queue_item(item: Mapping[str, Any]) -> VerifierV2Policy:
    record = dict(item["verifier_policy"])
    policy = VerifierV2Policy(
        top_k=int(record["top_k"]),
        tie_break=tuple(record["tie_break"]),
        probe_count=int(record["probe_count"]),
        seed=int(record["seed"]),
        tolerance=float.fromhex(str(record["tolerance_float64_hex"])),
    )
    if policy.to_dict() != record:
        raise S11V2NativePreparationError("frozen verifier policy differs")
    return policy


def conservative_session_upper_bound(
    *,
    candidate_count: int,
    selected_count: int,
    source_block_count: int,
    maximum_relation_terms: int,
    matrix_dimension: int,
    qubit_count: int,
    probe_count: int,
) -> dict[str, int]:
    """Reproduce the frozen queue-v1 per-session cap formula exactly."""

    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 0
        for value in (
            candidate_count,
            selected_count,
            source_block_count,
            maximum_relation_terms,
            matrix_dimension,
            qubit_count,
            probe_count,
        )
    ):
        raise S11V2NativePreparationError("session cap input is invalid")
    if selected_count > candidate_count:
        raise S11V2NativePreparationError("selected count exceeds candidates")
    has_candidates = candidate_count > 0
    return {
        "N_symbolic_checks": candidate_count + 5 * selected_count,
        "N_sparse_expm_multiply": 3 * probe_count * selected_count,
        "N_state_probe_vectors": probe_count * selected_count,
        "N_dense_expm": 0,
        "N_circuit_operator_builds": (
            source_block_count
            + 2 * candidate_count * source_block_count
            + probe_count * selected_count
            if has_candidates
            else 0
        ),
        "N_generator_materializations": maximum_relation_terms * selected_count,
        "matrix_dimension": matrix_dimension,
        "qubit_count": qubit_count,
        "candidate_generations": candidate_count,
        "unique_semantic_candidates": candidate_count,
        "unique_physical_states": candidate_count,
        "rewrite_verifications": selected_count,
        "resource_recounts": 1 + 2 * candidate_count if has_candidates else 0,
        "optimizer_iterations": 0,
        "energy_evaluations": 0,
    }


@dataclass(frozen=True)
class VerifierRoundReceipt:
    round_index: int
    phase: str
    source_state_preparation_id: str
    verifier_core_digest: str
    selected_candidate_ids: tuple[str, ...]
    deterministic_work_counters: dict[str, int]
    cumulative_work_counters: dict[str, int]
    session_upper_bound: dict[str, int]
    result_core_sha256: str

    def to_dict(self) -> dict[str, Any]:
        body = {
            "schema": "v5-final.s11-v2-verifier-round-receipt.v1",
            "round_index": self.round_index,
            "phase": self.phase,
            "source_state_preparation_id": self.source_state_preparation_id,
            "verifier_core_digest": self.verifier_core_digest,
            "selected_candidate_ids": list(self.selected_candidate_ids),
            "deterministic_work_counters": self.deterministic_work_counters,
            "cumulative_work_counters": self.cumulative_work_counters,
            "session_upper_bound": self.session_upper_bound,
            "result_core_sha256": self.result_core_sha256,
            "candidate_energy_evaluations": 0,
            "optimizer_iterations": 0,
            "FCI_evaluations": 0,
        }
        body["receipt_digest"] = _digest(body)
        return body


class CumulativeVerifierLedger:
    """Append-only verifier-round receipts with strict cumulative replay."""

    def __init__(self, root: Path, *, cap: Mapping[str, int]) -> None:
        self.root = root
        frozen_fields = set(DETERMINISTIC_COUNTER_FIELDS) - {
            "optimizer_iterations",
            "energy_evaluations",
        }
        if set(cap) != frozen_fields:
            raise S11V2NativePreparationError("frozen verifier cap schema differs")
        self.cap = {
            field: int(cap.get(field, 0)) for field in DETERMINISTIC_COUNTER_FIELDS
        }

    def _receipt_paths(self) -> list[Path]:
        if not self.root.exists():
            return []
        if not self.root.is_dir() or self.root.is_symlink():
            raise S11V2NativePreparationError("verifier ledger root is unsafe")
        paths = sorted(self.root.glob("round-*-receipt.json"))
        # Session contents are owned and validated by Verifier V2.  At the
        # ledger root only round receipt files and round session directories
        # are allowed.
        for child in self.root.iterdir():
            if child in paths:
                continue
            if child.is_dir() and child.name.startswith("round-") and child.name.endswith(
                "-session"
            ):
                continue
            raise S11V2NativePreparationError(
                f"unregistered verifier ledger entry: {child.name}"
            )
        return paths

    def replay(self) -> tuple[VerifierRoundReceipt, ...]:
        receipts: list[VerifierRoundReceipt] = []
        cumulative = _empty_counts()
        for expected_index, path in enumerate(self._receipt_paths(), start=1):
            raw = path.read_bytes()
            try:
                record = json.loads(raw)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise S11V2NativePreparationError("verifier receipt JSON invalid") from error
            if raw != canonical_json_bytes(record):
                raise S11V2NativePreparationError("verifier receipt is noncanonical")
            body = dict(record)
            observed = body.pop("receipt_digest", None)
            if (
                observed != _digest(body)
                or record.get("schema")
                != "v5-final.s11-v2-verifier-round-receipt.v1"
                or record.get("round_index") != expected_index
                or path.name != f"round-{expected_index:04d}-receipt.json"
                or record.get("candidate_energy_evaluations") != 0
                or record.get("optimizer_iterations") != 0
                or record.get("FCI_evaluations") != 0
            ):
                raise S11V2NativePreparationError("verifier receipt binding invalid")
            delta = {
                field: int(record["deterministic_work_counters"][field])
                for field in DETERMINISTIC_COUNTER_FIELDS
            }
            core_path = (
                self.root
                / f"round-{expected_index:04d}-session"
                / "verification-core-v2.json"
            )
            if not core_path.is_file() or core_path.is_symlink():
                raise S11V2NativePreparationError("verifier core artifact is absent")
            core_raw = core_path.read_bytes()
            try:
                core = json.loads(core_raw)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise S11V2NativePreparationError("verifier core JSON invalid") from error
            core_body = dict(core)
            core_digest = core_body.pop("core_digest", None)
            if (
                core_raw != canonical_json_bytes(core)
                or hashlib.sha256(core_raw).hexdigest()
                != record["result_core_sha256"]
                or core_digest != _digest(core_body)
                or core_digest != record["verifier_core_digest"]
                or core.get("deterministic_work_counters") != delta
                or core.get("top_k_freeze", {}).get("selected_candidate_ids")
                != record["selected_candidate_ids"]
            ):
                raise S11V2NativePreparationError("verifier core binding invalid")
            cumulative = _merge_counts(cumulative, delta)
            if cumulative != record["cumulative_work_counters"] or not _fits(
                cumulative, self.cap
            ):
                raise S11V2NativePreparationError("verifier cumulative counter differs")
            receipts.append(
                VerifierRoundReceipt(
                    expected_index,
                    str(record["phase"]),
                    str(record["source_state_preparation_id"]),
                    str(record["verifier_core_digest"]),
                    tuple(record["selected_candidate_ids"]),
                    delta,
                    dict(cumulative),
                    dict(record["session_upper_bound"]),
                    str(record["result_core_sha256"]),
                )
            )
        return tuple(receipts)

    @property
    def total(self) -> dict[str, int]:
        receipts = self.replay()
        return _empty_counts() if not receipts else dict(receipts[-1].cumulative_work_counters)

    def precheck(self, upper_bound: Mapping[str, int]) -> None:
        projected = _merge_counts(self.total, upper_bound)
        if not _fits(projected, self.cap):
            exceeded = [
                field
                for field in DETERMINISTIC_COUNTER_FIELDS
                if int(projected[field]) > int(self.cap[field])
            ]
            raise VerifierComponentwiseCapRejected(
                "verifier cap rejected before session: " + ", ".join(exceeded)
            )

    def commit(
        self,
        *,
        phase: str,
        source_state_preparation_id: str,
        result: Mapping[str, Any],
        session_upper_bound: Mapping[str, int],
    ) -> VerifierRoundReceipt:
        core = dict(result["core"])
        if core.get("status") != "VERIFIED_READY_AWAITING_OUTCOME_AUTHORIZATION":
            raise S11V2NativePreparationError("verifier session is incomplete")
        core_body = dict(core)
        observed_core_digest = core_body.pop("core_digest", None)
        if observed_core_digest != _digest(core_body):
            raise S11V2NativePreparationError("verifier core digest is invalid")
        counters = {
            field: int(core["deterministic_work_counters"][field])
            for field in DETERMINISTIC_COUNTER_FIELDS
        }
        if not _fits(counters, session_upper_bound):
            raise S11V2NativePreparationError("session exceeded prechecked upper bound")
        before = self.total
        cumulative = _merge_counts(before, counters)
        if not _fits(cumulative, self.cap):
            raise S11V2NativePreparationError("completed session exceeded frozen cap")
        index = len(self.replay()) + 1
        self.root.mkdir(parents=True, exist_ok=True)
        session_dir = self.root / f"round-{index:04d}-session"
        session_dir.mkdir(parents=True, exist_ok=True)
        core_path = session_dir / "verification-core-v2.json"
        telemetry_path = session_dir / "operational-telemetry-v2.json"
        expected_core = canonical_json_bytes(core)
        if core_path.exists():
            if core_path.is_symlink() or core_path.read_bytes() != expected_core:
                raise S11V2NativePreparationError(
                    "existing verifier core differs during recovery"
                )
        else:
            write_json_exclusive(core_path, core)
        telemetry = dict(result["operational_telemetry"])
        if telemetry.get("core_digest") != core["core_digest"]:
            raise S11V2NativePreparationError("verifier telemetry is misbound")
        if telemetry_path.exists():
            if telemetry_path.is_symlink():
                raise S11V2NativePreparationError("verifier telemetry path is unsafe")
            existing_telemetry = json.loads(telemetry_path.read_text(encoding="utf-8"))
            if existing_telemetry.get("core_digest") != core["core_digest"]:
                raise S11V2NativePreparationError(
                    "existing verifier telemetry is misbound"
                )
        else:
            write_json_exclusive(telemetry_path, telemetry)
        receipt = VerifierRoundReceipt(
            index,
            phase,
            source_state_preparation_id,
            str(core["core_digest"]),
            tuple(core["top_k_freeze"]["selected_candidate_ids"]),
            counters,
            cumulative,
            {field: int(session_upper_bound[field]) for field in DETERMINISTIC_COUNTER_FIELDS},
            hashlib.sha256(core_path.read_bytes()).hexdigest(),
        )
        write_json_exclusive(
            self.root / f"round-{index:04d}-receipt.json", receipt.to_dict()
        )
        self.replay()
        return receipt


@dataclass
class MagnitudeVerifierBundleV1:
    verifier: VerifierV2
    candidates: tuple[CandidateV2, ...]
    deletions: dict[str, PreparedMagnitudeDeletion]
    resource_cache: dict[str, Any]
    source_state_preparation_id: str

    def selected_deletion(
        self, result: Mapping[str, Any]
    ) -> PreparedMagnitudeDeletion:
        core = result["core"]
        if core.get("status") != "VERIFIED_READY_AWAITING_OUTCOME_AUTHORIZATION":
            raise S11V2NativePreparationError("magnitude verifier is incomplete")
        selected = list(core["top_k_freeze"]["selected_candidate_ids"])
        if not selected or selected[0] not in self.deletions:
            raise S11V2NativePreparationError("magnitude selection is invalid")
        candidate_id = str(selected[0])
        after = self.resource_cache.get(candidate_id)
        if after is None:
            raise S11V2NativePreparationError("magnitude selected recount is absent")
        return replace(
            self.deletions[candidate_id],
            after_resources={
                key: value
                for key, value in zip(
                    (
                        "cnot_count",
                        "cnot_depth",
                        "total_depth",
                        "parameter_count",
                        "logical_block_count",
                    ),
                    _resource_vector(after),
                )
            },
        )


def _resource_vector(value: Any) -> list[int]:
    snapshot = value.snapshot
    return [
        int(snapshot.cnot_count),
        int(snapshot.cnot_depth),
        int(snapshot.total_depth),
        int(snapshot.parameter_count),
        int(snapshot.logical_block_count),
    ]


def build_magnitude_verifier_v2(
    *,
    context: Any,
    policy: VerifierV2Policy,
    checkpoint_dir: Path,
) -> MagnitudeVerifierBundleV1:
    """Build actual single-coordinate deletion candidates without outcomes."""

    source = context.runtime.ansatz
    if not source.indices:
        raise S11V2NativePreparationError("magnitude source has no coordinate")
    current_state = state_preparation_spec(
        context.runtime,
        algorithm=context._actual_algorithm,
        pool=context.pool,
    )
    backend = paper_era_backend()
    before = evaluate_full_circuit_resources(context.pool, source, backend)
    candidates: list[CandidateV2] = []
    deletions: dict[str, PreparedMagnitudeDeletion] = {}
    resource_cache: dict[str, Any] = {}
    for position, (pool_index, coefficient) in enumerate(
        zip(source.indices, source.coefficients)
    ):
        payload = {
            "source_state_preparation_id": current_state.state_preparation_id,
            "position": position,
            "pool_index": int(pool_index),
            "constraint": "theta_i->0",
            "physical_generator_deletion": True,
        }
        candidate_id = "magnitude-delete-v1:" + _digest(payload)
        iteration = next(
            index
            for index, stop in enumerate(source.cumulative_parameter_counts)
            if position < stop
        )
        counts = tuple(
            count if index < iteration else count - 1
            for index, count in enumerate(source.cumulative_parameter_counts)
        )
        target = AnsatzStructure.create(
            source.indices[:position] + source.indices[position + 1 :],
            source.coefficients[:position] + source.coefficients[position + 1 :],
            counts,
        )
        blocks = recover_dvg_blocks(
            context.pool,
            target.indices,
            target.coefficients,
            target.cumulative_parameter_counts,
        )
        preparation = StatePreparationSpec.create(
            reference_state=context._actual_algorithm.ref_det,
            generator_definition_digest=generator_definition_digest(context.pool),
            ansatz_block_structure=(
                (block.family, block.pool_indices) for block in blocks
            ),
            ansatz_indices=target.indices,
            coefficients=target.coefficients,
            orbital_parameters=(),
            qubit_mapping="openfermion-jordan-wigner-v1",
            qubit_ordering=range(int(context._actual_algorithm.n)),
        )
        physical_id = canonical_proposed_physical_state_id(
            problem_id=context.problem_id,
            state_preparation_spec=preparation,
        )
        cache: dict[str, Any] = {}

        def recount(
            *,
            target: Any = target,
            cache: dict[str, Any] = cache,
            candidate_id: str = candidate_id,
        ) -> Mapping[str, Any]:
            if "after" not in cache:
                after = evaluate_full_circuit_resources(context.pool, target, backend)
                structural = evaluate_full_circuit_resources(
                    context.pool,
                    target,
                    backend,
                    coefficient_policy="deterministic-structural",
                )
                if after.snapshot != structural.snapshot:
                    raise S11V2NativePreparationError(
                        "magnitude physical/structural recount differs"
                    )
                cache["after"] = after
                resource_cache[candidate_id] = after
            return {
                "resource_vector": _resource_vector(cache["after"]),
                "resource_recounts": 2,
                "N_circuit_operator_builds": 2
                * len(target.cumulative_parameter_counts),
            }

        operator_id = hashlib.sha256(
            canonical_json_bytes(
                {
                    "pool_index": int(pool_index),
                    "generator_definition_digest": generator_definition_digest(
                        context.pool
                    ),
                }
            )
        ).hexdigest()
        candidates.append(
            CandidateV2(
                candidate_id=candidate_id,
                semantic_id=candidate_id,
                proposed_state_preparation_id=preparation.state_preparation_id,
                source_generator_digests=(operator_id,),
                target_generator_digests=(),
                jacobian=((),),
                obs_predicted_loss=abs(float(coefficient)) ** 2,
                matrix_dimension=1 << int(context.pool.n),
                qubit_count=int(context.pool.n),
                resource_recount=recount,
                deletion_shortcut=True,
            )
        )
        deletions[candidate_id] = PreparedMagnitudeDeletion(
            candidate_id,
            position,
            int(pool_index),
            target,
            preparation.state_preparation_id,
            {
                key: value
                for key, value in zip(
                    (
                        "cnot_count",
                        "cnot_depth",
                        "total_depth",
                        "parameter_count",
                        "logical_block_count",
                    ),
                    _resource_vector(before),
                )
            },
            {},
        )
        # Physical identity is calculated here even though CandidateV2 binds
        # the StatePreparationID; it proves the same canonical state namespace
        # used by the live ledger can be reconstructed without an outcome.
        if not physical_id.startswith("physical-state-v3:"):
            raise S11V2NativePreparationError("magnitude physical identity differs")

    verifier = VerifierV2(
        policy=policy,
        generator_loader=lambda _: (_ for _ in ()).throw(
            S11V2NativePreparationError(
                "analytic magnitude deletion must not materialize a generator"
            )
        ),
        checkpoint_dir=checkpoint_dir,
        source_binding={
            "schema": "v5-final.s11-v2-magnitude-verifier-source-binding.v1",
            "case_id": context.case_id,
            "ProblemID": context.problem_id,
            "StatePreparationID": current_state.state_preparation_id,
            "Hamiltonian_digest": context.hamiltonian_digest,
            "frozen_source_checkpoint_digest": context.source_checkpoint_digest,
            "current_runtime_snapshot_digest": context.runtime.snapshot().snapshot_digest,
            "candidate_energy_evaluations": 0,
            "optimizer_iterations": 0,
        },
        initial_counts={
            "resource_recounts": 1,
            "N_circuit_operator_builds": len(
                source.cumulative_parameter_counts
            ),
            "matrix_dimension": 1 << int(context.pool.n),
            "qubit_count": int(context.pool.n),
        },
    )
    return MagnitudeVerifierBundleV1(
        verifier,
        tuple(candidates),
        deletions,
        resource_cache,
        current_state.state_preparation_id,
    )


def magnitude_session_upper_bound(
    *, bundle: MagnitudeVerifierBundleV1, policy: VerifierV2Policy, context: Any
) -> dict[str, int]:
    return conservative_session_upper_bound(
        candidate_count=len(bundle.candidates),
        selected_count=min(policy.top_k, len(bundle.candidates)),
        source_block_count=len(context.runtime.ansatz.cumulative_parameter_counts),
        maximum_relation_terms=1,
        matrix_dimension=1 << int(context.pool.n),
        qubit_count=int(context.pool.n),
        probe_count=policy.probe_count,
    )

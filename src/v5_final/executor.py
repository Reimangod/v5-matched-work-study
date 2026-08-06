"""Production-path S4 executor bound to the pinned CEO* H2 kernel."""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import selectors
import subprocess
import time
from typing import Any, Callable, Mapping

from v5_matched_work.atomic_artifacts import canonical_json_bytes

from .architecture_state import ArchitectureState, RESOURCE_FIELDS
from .candidate_catalog import CandidateCatalog, CatalogCandidate
from .certifier import certify_candidate
from .frozen_queue import QueueItem, freeze_queue, verify_frozen_queue
from .identities import (
    CandidateIntent,
    ExecutionRequest,
    GeneratorSemantic,
    NativeGateSemantic,
    ProposedPhysicalState,
)
from .pareto_selector import select_prediction
from .predictor import predict_structural
from .s0_successor import ROOT
from .s3_smoke_authorization_v3 import audit as audit_smoke_authorization
from .scientific_values import TaggedScientificValue
from .semantic_contract import ScientificValueDelta, StateDelta
from .semantic_contract_v2 import ResourceDelta, SemanticDelta, WorkDelta, WORK_COMPONENTS
from .semantic_events import SemanticEventType
from .transaction import ArchitectureTransaction
from .work_ledger import IntegratedWorkLedger, reconcile, release_summary


class ProductionExecutorError(RuntimeError):
    pass


PARENT = ROOT / "provenance" / "dvg-obs-ceo"
WORKER_PYTHON = PARENT / ".venv" / "bin" / "python"
SOURCE_ARTIFACT = PARENT / "artifacts" / "s1" / "h2-1.5-smoke.json"
REQUIRED_THREADS = {
    "OMP_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _add_work(left: WorkDelta, right: WorkDelta) -> WorkDelta:
    return WorkDelta(
        **{
            field: getattr(left, field) + getattr(right, field)
            for field in WORK_COMPONENTS
        }
    )


def _zero_scientific(quantity: str = "executor_evidence") -> TaggedScientificValue:
    return TaggedScientificValue.not_evaluated(
        quantity=quantity, unit="dimensionless", reason="no_scientific_value_transition"
    )


def _semantic_delta(
    *,
    source_digest: str,
    work: WorkDelta | None = None,
    scientific: Mapping[str, str] | None = None,
    resource: ResourceDelta | None = None,
    state: StateDelta | None = None,
) -> SemanticDelta:
    if scientific is None:
        before = _zero_scientific()
        after = before
    else:
        quantity = scientific["quantity"]
        unit = "hartree" if "energy" in quantity else "hartree_per_radian"
        before = TaggedScientificValue.not_evaluated(
            quantity=quantity, unit=unit, reason="not_yet_evaluated_in_this_event"
        )
        after = TaggedScientificValue.available(
            quantity=quantity, unit=unit, value=scientific["value"]
        )
    return SemanticDelta(
        state_delta=state or StateDelta(source_digest, source_digest),
        resource_delta=resource or ResourceDelta(),
        scientific_value_delta=ScientificValueDelta(before, after),
        work_delta=work or WorkDelta(),
    )


class KernelBridge:
    def __init__(self, *, timeout_seconds: float = 30.0) -> None:
        self.timeout_seconds = timeout_seconds

    def run(
        self,
        request: Mapping[str, Any],
        on_raw_operation: Callable[[Mapping[str, Any]], None],
    ) -> dict[str, Any]:
        if not WORKER_PYTHON.is_file():
            raise ProductionExecutorError("pinned parent virtual environment is unavailable")
        environment = dict(os.environ)
        environment.update(REQUIRED_THREADS)
        python_path = os.pathsep.join(
            (
                str(ROOT / "src"),
                str(PARENT / "src"),
                str(PARENT / "vendor" / "ceo-adapt-vqe"),
            )
        )
        environment["PYTHONPATH"] = python_path
        process = subprocess.Popen(
            [str(WORKER_PYTHON), "-m", "v5_final.kernel_bridge_worker"],
            cwd=ROOT,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        assert process.stdin is not None and process.stdout is not None
        process.stdin.write(json.dumps(dict(request), sort_keys=True, allow_nan=False))
        process.stdin.close()
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        deadline = time.monotonic() + self.timeout_seconds
        result: dict[str, Any] | None = None
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("pinned CEO* kernel bridge timed out")
                ready = selector.select(timeout=min(remaining, 0.25))
                if ready:
                    line = process.stdout.readline()
                    if line:
                        try:
                            message = json.loads(line)
                        except json.JSONDecodeError as error:
                            raise ProductionExecutorError("kernel bridge emitted malformed JSON") from error
                        if message.get("kind") == "raw-operation":
                            on_raw_operation(message)
                        elif message.get("kind") == "result":
                            if result is not None:
                                raise ProductionExecutorError("kernel bridge emitted duplicate results")
                            result = message
                        else:
                            raise ProductionExecutorError("kernel bridge emitted an unknown message")
                if process.poll() is not None:
                    for line in process.stdout:
                        if line.strip():
                            message = json.loads(line)
                            if message.get("kind") == "raw-operation":
                                on_raw_operation(message)
                            elif message.get("kind") == "result" and result is None:
                                result = message
                            else:
                                raise ProductionExecutorError("invalid trailing kernel message")
                    break
        except BaseException:
            process.kill()
            process.wait()
            raise
        finally:
            selector.close()
        stderr = process.stderr.read() if process.stderr is not None else ""
        if process.returncode != 0:
            raise ProductionExecutorError(
                f"kernel bridge failed with exit {process.returncode}: {stderr[-500:]}"
            )
        if result is None:
            raise ProductionExecutorError("kernel bridge completed without a result")
        return result


def _physical_state(inspect: Mapping[str, Any], structure: Mapping[str, Any]) -> ProposedPhysicalState:
    return ProposedPhysicalState(
        problem_id=inspect["problem_id"],
        reference_state=tuple(inspect["reference_state"]),
        generator_semantics=tuple(
            GeneratorSemantic(
                tuple(value["support"]),
                value["operator_family"],
                value["sign"],
                value["coefficient_bytes"],
            )
            for value in structure["generator_semantics"]
        ),
        block_order=tuple(structure["block_order"]),
        mapping=inspect["mapping"],
        qubit_order=tuple(inspect["qubit_order"]),
        canonical_coefficient_bytes=tuple(structure["coefficient_bytes"]),
        target_structure=dict(structure["target_structure"]),
        native_circuit_semantics=tuple(
            NativeGateSemantic(
                value["gate"], tuple(value["qubits"]), tuple(value["parameter_bytes"])
            )
            for value in structure["native_circuit_semantics"]
        ),
    )


def _resource_values(value: Mapping[str, Any]) -> dict[str, int]:
    return {field: int(value[field]) for field in RESOURCE_FIELDS}


class ProductionExecutor:
    def __init__(self, *, bridge: KernelBridge | None = None) -> None:
        self.bridge = bridge or KernelBridge()

    def run_registered_h2_smoke(self) -> dict[str, Any]:
        if not all(audit_smoke_authorization().values()):
            raise ProductionExecutorError("S3-v2 did not authorize the S4 smoke")
        if any(os.environ.get(name) != value for name, value in REQUIRED_THREADS.items()):
            raise ProductionExecutorError("single-thread deterministic environment is not active")
        authorization = json.loads(
            (ROOT / "artifacts/v5-final/s3/s4-smoke-authorization-v3.json").read_text()
        )
        cap = WorkDelta(**authorization["work_cap"])
        ledger = IntegratedWorkLedger(
            cap=cap,
            root_digest=authorization["authorization_digest"],
            producer="v5_final.executor.ProductionExecutor",
        )
        independent_raw = WorkDelta()
        current_source_digest = "0" * 64

        def record_host(
            event_type: SemanticEventType,
            queue_item_id: str,
            *,
            work: WorkDelta | None = None,
            evidence: Mapping[str, Any],
            execution_request_id: str | None = None,
            candidate_intent_id: str | None = None,
            state_id: str | None = None,
            delta: SemanticDelta | None = None,
        ) -> None:
            nonlocal independent_raw
            charged = work or WorkDelta()
            if not charged.is_zero():
                independent_raw = _add_work(independent_raw, charged)
            ledger.record_operation(
                event_type=event_type,
                queue_item_id=queue_item_id,
                delta=delta
                or _semantic_delta(source_digest=current_source_digest, work=charged),
                evidence=dict(evidence),
                execution_request_id=execution_request_id,
                candidate_intent_id=candidate_intent_id,
                proposed_physical_state_id=state_id,
            )

        def bridge_callback(queue_item_id: str) -> Callable[[Mapping[str, Any]], None]:
            bridge_raw = WorkDelta()

            def callback(message: Mapping[str, Any]) -> None:
                nonlocal independent_raw, bridge_raw
                work = WorkDelta(**dict(message["work_delta"]))
                bridge_raw = _add_work(bridge_raw, work)
                independent_raw = _add_work(independent_raw, work)
                ledger.record_operation(
                    event_type=SemanticEventType(message["event_type"]),
                    queue_item_id=queue_item_id,
                    delta=_semantic_delta(
                        source_digest=current_source_digest,
                        work=work,
                        scientific=message.get("scientific_value"),
                    ),
                    evidence={
                        "raw_counter_source": "pinned-upstream-kernel-live-jsonl",
                        "raw_counter_after": dict(message["raw_counter_after"]),
                    },
                )

            callback.bridge_total = lambda: bridge_raw  # type: ignore[attr-defined]
            return callback

        source_record = json.loads(SOURCE_ARTIFACT.read_text())
        source_artifact_sha = _sha256(SOURCE_ARTIFACT)
        record_host(
            SemanticEventType.SOURCE_LOADED,
            "s4-h2-source-prequeue",
            evidence={
                "source_artifact": str(SOURCE_ARTIFACT.relative_to(ROOT)),
                "source_artifact_sha256": source_artifact_sha,
            },
        )
        inspect_callback = bridge_callback("s4-h2-source-prequeue")
        inspect = self.bridge.run(
            {
                "action": "inspect",
                "candidate_coefficient_delta": "0.01",
                "source": {
                    "ansatz_indices": source_record["ansatz_indices"],
                    "ansatz_coefficients": source_record["ansatz_coefficients"],
                    "cumulative_parameter_counts": [len(source_record["ansatz_indices"])],
                },
            },
            inspect_callback,
        )
        if asdict(inspect_callback.bridge_total()) != inspect["raw_counter"]:  # type: ignore[attr-defined]
            raise ProductionExecutorError("inspect bridge raw stream and final counter differ")
        source_physical = _physical_state(inspect, inspect["source"])
        source = ArchitectureState(
            problem_id=inspect["problem_id"],
            physical_state=source_physical,
            ansatz_indices=tuple(inspect["source"]["ansatz_indices"]),
            coefficient_bytes=tuple(inspect["source"]["coefficient_bytes"]),
            cumulative_parameter_counts=tuple(inspect["source"]["cumulative_parameter_counts"]),
            energy_hartree=inspect["source_energy_hartree"],
            gradient_infinity=inspect["source_gradient_infinity"],
            resources=_resource_values(inspect["source"]["resources"]),
            statevector_digest=inspect["source_statevector_digest"],
            circuit_digest=inspect["source"]["circuit_digest"],
        )
        current_source_digest = source.source_digest
        candidate_physical = _physical_state(inspect, inspect["candidate"])
        intent = CandidateIntent(
            source_block=inspect["source"]["block_order"][0],
            transformation_family="same-structure-coefficient-smoke",
            target_family="pinned-upstream-CEO-circuit",
            candidate_provenance={
                "source_artifact_sha256": source_artifact_sha,
                "coefficient_delta_decimal": "0.01",
                "purpose": "S4-production-path-smoke",
            },
            generation_path=("source-load", "actual-circuit-inspection", "bounded-smoke-catalog"),
        )
        candidate = CatalogCandidate(
            intent,
            candidate_physical,
            tuple(inspect["candidate"]["coefficient_bytes"]),
            inspect["candidate"]["circuit_digest"],
            _resource_values(inspect["candidate"]["resources"]),
        )
        record_host(
            SemanticEventType.CANDIDATE_GENERATED,
            "s4-h2-source-prequeue",
            work=WorkDelta(candidate_generations=1),
            evidence={"raw_counter_source": "candidate_catalog.build", "actual_circuit": True},
            candidate_intent_id=candidate.candidate_intent_id,
            state_id=candidate.proposed_physical_state_id,
        )
        record_host(
            SemanticEventType.SEARCH_STATE_EXPANDED,
            "s4-h2-source-prequeue",
            work=WorkDelta(search_states=1),
            evidence={"raw_counter_source": "CandidateCatalog.unique_physical_state_count"},
            candidate_intent_id=candidate.candidate_intent_id,
            state_id=candidate.proposed_physical_state_id,
        )
        record_host(
            SemanticEventType.REWRITE_VERIFIED,
            "s4-h2-source-prequeue",
            work=WorkDelta(rewrite_verifications=1),
            evidence={"raw_counter_source": "actual-circuit-identity-verification"},
            candidate_intent_id=candidate.candidate_intent_id,
            state_id=candidate.proposed_physical_state_id,
        )
        catalog = CandidateCatalog.build(source.source_digest, (candidate,))
        record_host(
            SemanticEventType.CATALOG_BUILT,
            "s4-h2-source-prequeue",
            evidence={
                "catalog_digest": catalog.catalog_digest,
                "unique_physical_state_count": catalog.unique_physical_state_count,
            },
        )
        prediction = predict_structural(source, candidate)
        selected = select_prediction((prediction,))
        record_host(
            SemanticEventType.PREDICTOR_EVALUATED,
            "s4-h2-source-prequeue",
            evidence={"outcome_blind": True, "selected_intent": selected.candidate_intent_id},
        )
        environment_digest = hashlib.sha256(
            canonical_json_bytes(inspect["environment"])
        ).hexdigest()
        request = ExecutionRequest(
            proposed_physical_state_id=candidate.proposed_physical_state_id,
            source_checkpoint_digest=source_artifact_sha,
            optimizer={"name": "L-BFGS-B", "maximum_iterations": 2},
            initialization={"kind": "source-coefficient-plus-delta", "delta": "0.01"},
            work_profile=authorization["work_cap"],
            energy_budget_hartree="0.0001",
            stationarity_threshold="0.000001",
            protocol_digest=authorization["authorization_digest"],
            environment_digest=environment_digest,
        )
        queue_item = QueueItem(
            request.execution_request_id,
            candidate.candidate_intent_id,
            candidate.proposed_physical_state_id,
            source.source_digest,
            catalog.catalog_digest,
        )
        frozen = freeze_queue((queue_item,), protocol_digest=authorization["authorization_digest"])
        verify_frozen_queue(frozen)
        record_host(
            SemanticEventType.QUEUE_FROZEN,
            queue_item.queue_item_id,
            evidence={"queue_digest": frozen["queue_digest"], "expected_queue_count": 1},
            execution_request_id=request.execution_request_id,
            candidate_intent_id=candidate.candidate_intent_id,
            state_id=candidate.proposed_physical_state_id,
        )
        transaction = ArchitectureTransaction(source)
        execute_callback = bridge_callback(queue_item.queue_item_id)
        execute = self.bridge.run(
            {
                "action": "execute",
                "ansatz_indices": list(inspect["candidate"]["ansatz_indices"]),
                "coefficient_bytes": list(candidate.initial_coefficient_bytes),
                "cumulative_parameter_counts": list(
                    inspect["candidate"]["cumulative_parameter_counts"]
                ),
                "maximum_optimizer_iterations": 2,
            },
            execute_callback,
        )
        if asdict(execute_callback.bridge_total()) != execute["raw_counter"]:  # type: ignore[attr-defined]
            raise ProductionExecutorError("execute bridge raw stream and final counter differ")
        final_physical = _physical_state(inspect, execute["final"])
        final_state = ArchitectureState(
            problem_id=inspect["problem_id"],
            physical_state=final_physical,
            ansatz_indices=tuple(execute["final"]["ansatz_indices"]),
            coefficient_bytes=tuple(execute["final"]["coefficient_bytes"]),
            cumulative_parameter_counts=tuple(execute["final"]["cumulative_parameter_counts"]),
            energy_hartree=execute["energy_hartree"],
            gradient_infinity=execute["gradient_infinity"],
            resources=_resource_values(execute["final"]["resources"]),
            statevector_digest=execute["statevector_digest"],
            circuit_digest=execute["final"]["circuit_digest"],
            generation=1,
        )
        transaction.stage(final_state)
        certification = certify_candidate(
            source,
            energy_hartree=final_state.energy_hartree,
            gradient_infinity=final_state.gradient_infinity,
            resources=final_state.resources,
            energy_budget_hartree=request.energy_budget_hartree,
            stationarity_threshold=request.stationarity_threshold,
        )
        final_value = TaggedScientificValue.available(
            quantity="candidate_energy", unit="hartree", value=final_state.energy_hartree
        )
        stable_science = ScientificValueDelta(final_value, final_value)
        record_host(
            SemanticEventType.CANDIDATE_CERTIFIED
            if certification.accepted
            else SemanticEventType.CANDIDATE_REJECTED,
            queue_item.queue_item_id,
            evidence={"reason": certification.reason, "FCI_used": False},
            execution_request_id=request.execution_request_id,
            candidate_intent_id=candidate.candidate_intent_id,
            state_id=final_state.proposed_physical_state_id,
            delta=SemanticDelta(
                StateDelta(source.source_digest, source.source_digest),
                ResourceDelta(),
                stable_science,
                WorkDelta(),
            ),
        )
        if certification.accepted:
            committed = transaction.commit()
            resource_change = ResourceDelta(
                **{
                    field: committed.resources[field] - source.resources[field]
                    for field in RESOURCE_FIELDS
                }
            )
            record_host(
                SemanticEventType.STATE_COMMITTED,
                queue_item.queue_item_id,
                evidence={"certification": certification.reason},
                execution_request_id=request.execution_request_id,
                candidate_intent_id=candidate.candidate_intent_id,
                state_id=committed.proposed_physical_state_id,
                delta=SemanticDelta(
                    StateDelta(
                        source.source_digest,
                        committed.source_digest,
                        created_physical_state_ids=(committed.proposed_physical_state_id,),
                        committed=True,
                    ),
                    resource_change,
                    stable_science,
                    WorkDelta(),
                ),
            )
            terminal = "EXECUTED"
            terminal_state = committed
        else:
            rollback = transaction.rollback(certification.reason)
            record_host(
                SemanticEventType.STATE_ROLLED_BACK,
                queue_item.queue_item_id,
                evidence={"reason": rollback.reason, "exact": rollback.exact},
                execution_request_id=request.execution_request_id,
                candidate_intent_id=candidate.candidate_intent_id,
                state_id=source.proposed_physical_state_id,
                delta=SemanticDelta(
                    StateDelta(source.source_digest, source.source_digest),
                    ResourceDelta(),
                    stable_science,
                    WorkDelta(),
                ),
            )
            terminal = "STRUCTURALLY_REJECTED"
            terminal_state = source
        rebuilt_catalog = CandidateCatalog.build(
            terminal_state.source_digest,
            (
                CatalogCandidate(
                    CandidateIntent(
                        source_block=terminal_state.physical_state.block_order[0],
                        transformation_family="same-structure-coefficient-smoke",
                        target_family="pinned-upstream-CEO-circuit",
                        candidate_provenance={"rebuild_generation": terminal_state.generation},
                        generation_path=("post-commit", "catalog-rebuilt"),
                    ),
                    terminal_state.physical_state,
                    terminal_state.coefficient_bytes,
                    terminal_state.circuit_digest,
                    terminal_state.resources,
                ),
            ),
        )
        record_host(
            SemanticEventType.CANDIDATE_GENERATED,
            queue_item.queue_item_id,
            work=WorkDelta(candidate_generations=1),
            evidence={"raw_counter_source": "post-commit CandidateCatalog.build"},
            execution_request_id=request.execution_request_id,
        )
        record_host(
            SemanticEventType.SEARCH_STATE_EXPANDED,
            queue_item.queue_item_id,
            work=WorkDelta(search_states=1),
            evidence={"raw_counter_source": "post-commit unique physical state"},
            execution_request_id=request.execution_request_id,
        )
        record_host(
            SemanticEventType.REWRITE_VERIFIED,
            queue_item.queue_item_id,
            work=WorkDelta(rewrite_verifications=1),
            evidence={"raw_counter_source": "post-commit circuit identity verification"},
            execution_request_id=request.execution_request_id,
        )
        record_host(
            SemanticEventType.CATALOG_REBUILT,
            queue_item.queue_item_id,
            evidence={
                "parent_source_digest": terminal_state.source_digest,
                "rebuilt_catalog_digest": rebuilt_catalog.catalog_digest,
            },
            execution_request_id=request.execution_request_id,
        )
        record_host(
            SemanticEventType.TERMINAL_REACHED,
            queue_item.queue_item_id,
            evidence={"terminal_status": terminal, "evidence_complete": True},
            execution_request_id=request.execution_request_id,
            candidate_intent_id=candidate.candidate_intent_id,
            state_id=terminal_state.proposed_physical_state_id,
        )
        document = ledger.close()
        summary = release_summary(document)
        reconciliation = reconcile(
            independent_raw_counter=independent_raw,
            ledger_document=document,
            summary=summary,
        )
        if not all(reconciliation.values()):
            raise ProductionExecutorError("S4 raw/ledger/release reconciliation failed")
        transaction_failure_probes = {}
        for failure_mode in (
            "crash",
            "timeout",
            "interrupt",
            "nan",
            "malformed_json",
            "partial_write",
            "wrong_digest",
            "counter_mismatch",
            "queue_substitution",
            "missing_segment",
        ):
            probe = ArchitectureTransaction(source)
            probe.stage(final_state)
            rollback = probe.rollback(failure_mode)
            transaction_failure_probes[failure_mode] = {
                "source_digest_before": rollback.source_digest_before,
                "source_digest_after": rollback.source_digest_after,
                "exact": rollback.exact,
            }
        result: dict[str, Any] = {
            "schema": "v5-final.s4-h2-production-smoke.v1",
            "classification": "bounded infrastructure smoke; not performance evidence",
            "source_artifact": {
                "path": str(SOURCE_ARTIFACT.relative_to(ROOT)),
                "sha256": source_artifact_sha,
            },
            "upstream": inspect["upstream"],
            "problem_id": inspect["problem_id"],
            "source": source.payload() | {"source_digest": source.source_digest},
            "catalog": {
                "candidate_count": len(catalog.candidates),
                "unique_physical_state_count": catalog.unique_physical_state_count,
                "catalog_digest": catalog.catalog_digest,
                "candidate_intent_id": candidate.candidate_intent_id,
                "proposed_physical_state_id": candidate.proposed_physical_state_id,
            },
            "frozen_queue": frozen,
            "execution_request_id": request.execution_request_id,
            "optimizer": execute["optimizer"],
            "certification": asdict(certification),
            "terminal_status": terminal,
            "terminal_source_digest": terminal_state.source_digest,
            "catalog_rebuilt_digest": rebuilt_catalog.catalog_digest,
            "independent_raw_counter": asdict(independent_raw),
            "integrated_ledger": document,
            "release_summary": summary,
            "reconciliation": reconciliation,
            "transaction_failure_probes": transaction_failure_probes,
            "claim_boundary": (
                "One registered H2 production-path smoke. Energy values verify "
                "executor semantics only and cannot support method-performance claims."
            ),
        }
        result["smoke_digest"] = hashlib.sha256(canonical_json_bytes(result)).hexdigest()
        return result

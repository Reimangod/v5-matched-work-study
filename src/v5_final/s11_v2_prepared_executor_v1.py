"""Prepare all six frozen S11-v2 methods exclusively through Verifier V2."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Mapping

from dvg_obs_ceo.molecular_identity import state_preparation_spec
from dvg_obs_ceo.resources import AnsatzStructure

from .parent_native_candidate_adapter import (
    build_typed_catalog,
    compose_parent_native_plan,
)
from .parent_native_candidate_work_bindings import (
    candidate_structural_whitelist_key,
)
from .parent_native_executors import (
    PreparedMagnitudeDeletion,
    PreparedMethodNativeExecutor,
    _compatible_v4_sentinels,
    prepare_method_executor,
)
from .parent_native_verifier_v2 import build_parent_verifier_v2
from .s11_v2_native_preparation_runtime_v1 import (
    CumulativeVerifierLedger,
    build_magnitude_verifier_v2,
    conservative_session_upper_bound,
    magnitude_session_upper_bound,
    policy_from_queue_item,
)
from .s11_v2_queue_native_adapter import (
    CONTROL_METHODS,
    PreparedQueueV2NativeRequest,
    QueueV2NativeAdapter,
    QueueV2NativeRequest,
)


class S11V2PreparedExecutorError(RuntimeError):
    pass


@dataclass(frozen=True)
class PreparedJointRewriteV1:
    target: Any
    target_inverse_hessian: Any
    verified_candidate_ids: tuple[str, ...]
    verifier_core_digest: str

    def to_audit_dict(self) -> dict[str, Any]:
        return {
            "schema": "v5-final.s11-v2-prepared-joint-rewrite.v1",
            "target_indices": list(self.target.indices),
            "target_iteration_counts": list(
                self.target.cumulative_parameter_counts
            ),
            "verified_candidate_ids": list(self.verified_candidate_ids),
            "verifier_core_digest": self.verifier_core_digest,
            "candidate_energy_evaluations": 0,
            "optimizer_iterations": 0,
        }


@dataclass(frozen=True)
class PreparedSessionV1:
    result: dict[str, Any]
    selected_candidate_ids: tuple[str, ...]
    plans: tuple[Any, ...]
    rewrites: tuple[Any, ...]
    generated_candidate_count: int
    unique_physical_state_count: int
    verifier_core_digest: str


class _CurrentRuntimeVerifierContext:
    def __init__(self, context: Any) -> None:
        self._context = context
        current = state_preparation_spec(
            context.runtime,
            algorithm=context._actual_algorithm,
            pool=context.pool,
        )
        self.state_preparation_id = current.state_preparation_id
        self.source_checkpoint_digest = context.runtime.snapshot().snapshot_digest

    def __getattr__(self, name: str) -> Any:
        return getattr(self._context, name)


def _maximum_relation_terms(catalog: Any) -> int:
    return max(
        (
            len(candidate.source_pool_indices)
            + len(candidate.target_pool_indices)
            for candidate in catalog.candidates
        ),
        default=0,
    )


def typed_session_upper_bound(
    *, context: Any, catalog: Any, admitted_count: int, policy: Any
) -> dict[str, int]:
    return conservative_session_upper_bound(
        candidate_count=admitted_count,
        selected_count=min(policy.top_k, admitted_count),
        source_block_count=len(context.runtime.ansatz.cumulative_parameter_counts),
        maximum_relation_terms=_maximum_relation_terms(catalog),
        matrix_dimension=1 << int(context.pool.n),
        qubit_count=int(context.pool.n),
        probe_count=policy.probe_count,
    )


def run_typed_verifier_session(
    *,
    context: Any,
    catalog: Any,
    admitted_candidate_ids: tuple[str, ...],
    policy: Any,
    ledger: CumulativeVerifierLedger,
    phase: str,
    bind_current_runtime: bool = False,
) -> PreparedSessionV1:
    admitted = tuple(dict.fromkeys(str(value) for value in admitted_candidate_ids))
    if not admitted:
        raise S11V2PreparedExecutorError("typed verifier candidate set is empty")
    upper = typed_session_upper_bound(
        context=context,
        catalog=catalog,
        admitted_count=len(admitted),
        policy=policy,
    )
    ledger.precheck(upper)
    round_index = len(ledger.replay()) + 1
    checkpoint_dir = ledger.root / f"round-{round_index:04d}-session/checkpoints"
    verifier_context = (
        _CurrentRuntimeVerifierContext(context) if bind_current_runtime else context
    )
    bundle = build_parent_verifier_v2(
        context=verifier_context,
        catalog=catalog,
        admitted_candidate_ids=admitted,
        policy=policy,
        checkpoint_dir=checkpoint_dir,
    )
    result = bundle.run()
    receipt = ledger.commit(
        phase=phase,
        source_state_preparation_id=str(verifier_context.state_preparation_id),
        result=result,
        session_upper_bound=upper,
    )
    rewrites = bundle.prepared_rewrites(result)
    selected = tuple(receipt.selected_candidate_ids)
    if tuple(value.candidate_id for value in rewrites) != selected:
        raise S11V2PreparedExecutorError("prepared rewrite order differs from top-K")
    plans = tuple(bundle.plans[value] for value in selected)
    counters = result["core"]["deterministic_work_counters"]
    return PreparedSessionV1(
        dict(result),
        selected,
        plans,
        tuple(rewrites),
        int(counters["candidate_generations"]),
        int(counters["unique_physical_states"]),
        str(result["core"]["core_digest"]),
    )


def _directives(method: str) -> dict[str, Any]:
    base = {
        "optimizer_entrypoint": "adaptvqe.minimize:minimize_bfgs",
        "acceptance_entrypoint": "dvg_obs_ceo.transaction:evaluate_acceptance",
        "transaction_entrypoint": (
            "dvg_obs_ceo.v5_nested_transaction:NestedRoundTransaction"
        ),
        "preparation_engine": "VerifierV2",
        "candidate_outcomes_used": False,
        "rollback_scope": [
            "ansatz",
            "parameters",
            "optimizer_inverse_hessian",
            "resources",
            "ledger_transaction",
        ],
    }
    if method == "structural-magnitude-pruning":
        base.update(
            selection="minimum theta_i^2; canonical structural-ID tie break",
            sequential_commits=True,
            post_commit_score_rebuild=True,
            physical_generator_deletion=True,
        )
    elif method == "v4.1-one-shot-joint-compression":
        base.update(
            selection="frozen sentinels followed by pairwise compatibility",
            one_shot=True,
            post_commit_catalog_rebuild=False,
        )
    elif method in {
        "v5-fixed-source-whitelist-no-replenishment",
        "v5-sequential-with-rebuilding",
    }:
        base.update(
            selection="frozen Verifier V2 OBS/resource/candidate-ID top-K",
            sequential_commits=True,
            post_commit_catalog_rebuild=True,
            replenishment_allowed=method == "v5-sequential-with-rebuilding",
            source_whitelist_only=(
                method == "v5-fixed-source-whitelist-no-replenishment"
            ),
        )
    return base


def prepare_initial_executor_v1(
    *,
    adapter: QueueV2NativeAdapter,
    request: QueueV2NativeRequest,
    context: Any,
    verifier_ledger: CumulativeVerifierLedger,
) -> tuple[PreparedMethodNativeExecutor, PreparedQueueV2NativeRequest]:
    """Prepare one exact queue-v2 item while all outcomes remain blocked."""

    method = request.method_id
    old_item = request.execution_item_v4
    if method in CONTROL_METHODS:
        prepared_request = adapter.consume_verifier_v2(request, None)
        executor = replace(
            prepare_method_executor(context, old_item),
            queue_item_id=str(request.item["queue_item_id"]),
        )
        return executor, prepared_request

    policy = policy_from_queue_item(request.item)
    if method == "structural-magnitude-pruning":
        upper_count = len(context.runtime.ansatz.indices)
        upper = conservative_session_upper_bound(
            candidate_count=upper_count,
            selected_count=min(policy.top_k, upper_count),
            source_block_count=len(
                context.runtime.ansatz.cumulative_parameter_counts
            ),
            maximum_relation_terms=1,
            matrix_dimension=1 << int(context.pool.n),
            qubit_count=int(context.pool.n),
            probe_count=policy.probe_count,
        )
        verifier_ledger.precheck(upper)
        round_index = len(verifier_ledger.replay()) + 1
        bundle = build_magnitude_verifier_v2(
            context=context,
            policy=policy,
            checkpoint_dir=(
                verifier_ledger.root
                / f"round-{round_index:04d}-session/checkpoints"
            ),
        )
        exact_upper = magnitude_session_upper_bound(
            bundle=bundle, policy=policy, context=context
        )
        if exact_upper != upper:
            raise S11V2PreparedExecutorError(
                "magnitude pre-build and exact upper bounds differ"
            )
        result = bundle.verifier.run(bundle.candidates)
        receipt = verifier_ledger.commit(
            phase="initial-magnitude",
            source_state_preparation_id=bundle.source_state_preparation_id,
            result=result,
            session_upper_bound=upper,
        )
        prepared_request = adapter.consume_verifier_v2(request, result)
        deletion = bundle.selected_deletion(result)
        if deletion.candidate_id != prepared_request.selected_candidate_ids[0]:
            raise S11V2PreparedExecutorError(
                "magnitude executor selection differs from Verifier V2"
            )
        executor = PreparedMethodNativeExecutor(
            method,
            context.case_id,
            str(request.item["queue_item_id"]),
            context,
            None,
            request.admitted_candidate_ids,
            (deletion.candidate_id,),
            (),
            (),
            deletion,
            int(result["core"]["deterministic_work_counters"]["candidate_generations"]),
            int(result["core"]["deterministic_work_counters"]["unique_physical_states"]),
            _directives(method)
            | {"verifier_core_digest": receipt.verifier_core_digest},
            (),
        )
        return executor, prepared_request

    catalog = build_typed_catalog(context.pool, context.runtime.ansatz)
    session = run_typed_verifier_session(
        context=context,
        catalog=catalog,
        admitted_candidate_ids=request.admitted_candidate_ids,
        policy=policy,
        ledger=verifier_ledger,
        phase="initial-" + method,
    )
    prepared_request = adapter.consume_verifier_v2(request, session.result)
    incompatible: tuple[str, ...] = ()
    plans = session.plans
    rewrites = session.rewrites
    selected = session.selected_candidate_ids
    unique_states = session.unique_physical_state_count
    if method == "v4.1-one-shot-joint-compression":
        verified = set(session.selected_candidate_ids)
        if verified != set(request.admitted_candidate_ids):
            raise S11V2PreparedExecutorError(
                "V4.1 did not verify every frozen sentinel"
            )
        compatible, incompatible = _compatible_v4_sentinels(
            catalog, request.admitted_candidate_ids
        )
        joint = compose_parent_native_plan(
            pool=context.pool,
            source=context.runtime.ansatz,
            catalog=catalog,
            candidates=compatible,
            gradient=context.runtime.gradient,
            inverse_hessian=context.runtime.inverse_hessian,
            problem_id=context.problem_id,
            reference_state=context._actual_algorithm.ref_det,
        )
        target = AnsatzStructure.create(
            joint.joint_plan.target_indices,
            joint.target_initial_coordinates,
            joint.joint_plan.target_iteration_counts,
        )
        plans = (joint,)
        rewrites = (
            PreparedJointRewriteV1(
                target,
                joint.target_inverse_hessian,
                tuple(value.candidate_id for value in compatible),
                session.verifier_core_digest,
            ),
        )
        selected = tuple(value.candidate_id for value in compatible)
        unique_states = 1
    executor = PreparedMethodNativeExecutor(
        method,
        context.case_id,
        str(request.item["queue_item_id"]),
        context,
        catalog,
        request.admitted_candidate_ids,
        selected,
        tuple(plans),
        tuple(rewrites),
        None,
        session.generated_candidate_count,
        unique_states,
        _directives(method)
        | {"verifier_core_digest": session.verifier_core_digest},
        incompatible,
    )
    return executor, prepared_request


def prepare_dynamic_v5_v1(
    *,
    executor: PreparedMethodNativeExecutor,
    queue_item: Mapping[str, Any],
    verifier_ledger: CumulativeVerifierLedger,
) -> PreparedSessionV1:
    """Rebuild one child catalog under the unchanged frozen queue-v2 policy."""

    catalog = build_typed_catalog(
        executor.context.pool, executor.context.runtime.ansatz
    )
    binding = dict(executor.context.runtime.metadata["candidate_work_binding"])
    upper = int(binding["dynamic_catalog_generation_upper_bound"])
    if catalog.generated_candidate_intent_count > upper:
        raise S11V2PreparedExecutorError(
            "child catalog exceeded frozen source upper bound"
        )
    if executor.method_id == "v5-fixed-source-whitelist-no-replenishment":
        whitelist = set(binding["source_whitelist_keys"])
        if not whitelist:
            raise S11V2PreparedExecutorError("fixed source whitelist is absent")
        admitted = tuple(
            candidate.candidate_id
            for candidate in catalog.candidates
            if candidate_structural_whitelist_key(candidate) in whitelist
        )
    elif executor.method_id == "v5-sequential-with-rebuilding":
        admitted = tuple(candidate.candidate_id for candidate in catalog.candidates)
    else:
        raise S11V2PreparedExecutorError("dynamic V5 called for another method")
    if not admitted:
        return PreparedSessionV1({}, (), (), (), 0, 0, "0" * 64)
    return run_typed_verifier_session(
        context=executor.context,
        catalog=catalog,
        admitted_candidate_ids=admitted,
        policy=policy_from_queue_item(queue_item),
        ledger=verifier_ledger,
        phase="post-commit-" + executor.method_id,
        bind_current_runtime=True,
    )


def prepare_dynamic_magnitude_v1(
    *,
    executor: PreparedMethodNativeExecutor,
    queue_item: Mapping[str, Any],
    verifier_ledger: CumulativeVerifierLedger,
) -> PreparedMagnitudeDeletion | None:
    if not executor.context.runtime.ansatz.indices:
        return None
    policy = policy_from_queue_item(queue_item)
    count = len(executor.context.runtime.ansatz.indices)
    upper = conservative_session_upper_bound(
        candidate_count=count,
        selected_count=min(policy.top_k, count),
        source_block_count=len(
            executor.context.runtime.ansatz.cumulative_parameter_counts
        ),
        maximum_relation_terms=1,
        matrix_dimension=1 << int(executor.context.pool.n),
        qubit_count=int(executor.context.pool.n),
        probe_count=policy.probe_count,
    )
    verifier_ledger.precheck(upper)
    round_index = len(verifier_ledger.replay()) + 1
    bundle = build_magnitude_verifier_v2(
        context=executor.context,
        policy=policy,
        checkpoint_dir=(
            verifier_ledger.root / f"round-{round_index:04d}-session/checkpoints"
        ),
    )
    result = bundle.verifier.run(bundle.candidates)
    verifier_ledger.commit(
        phase="post-commit-magnitude",
        source_state_preparation_id=bundle.source_state_preparation_id,
        result=result,
        session_upper_bound=upper,
    )
    return bundle.selected_deletion(result)

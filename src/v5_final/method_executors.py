"""Outcome-blind method-native planning controllers for the six S5 methods."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from typing import Any, Mapping

from v5_matched_work.atomic_artifacts import canonical_json_bytes


class MethodExecutorError(ValueError):
    pass


class CandidateExecutionNotAuthorized(RuntimeError):
    pass


@dataclass(frozen=True)
class MethodExecutionPlan:
    method_id: str
    queue_item_id: str
    case_id: str
    source_checkpoint_sha256: str
    problem_id: str
    state_preparation_id: str
    work_envelope: str
    semantic_work_cap: Mapping[str, int]
    maximum_rounds: int
    optimizer: Mapping[str, Any]
    acceptance: Mapping[str, Any]
    policy_digest: str
    queue_digest: str
    catalog_policy: str
    sequential_commits: bool
    post_commit_catalog_rebuild: bool

    def payload(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def plan_id(self) -> str:
        return "method-plan-v1:" + hashlib.sha256(
            canonical_json_bytes(self.payload())
        ).hexdigest()


class MethodController:
    method_id = ""
    catalog_policy = ""
    sequential_commits = False
    post_commit_catalog_rebuild = False

    def build_plan(
        self,
        *,
        queue_item: Mapping[str, Any],
        queue_digest: str,
        source: Mapping[str, Any],
        policy: Mapping[str, Any],
    ) -> MethodExecutionPlan:
        if queue_item["method_id"] != self.method_id:
            raise MethodExecutorError("queue item was routed to the wrong method controller")
        if queue_item["case_id"] != source["case_id"]:
            raise MethodExecutorError("queue item and source case differ")
        if queue_item["source_checkpoint_sha256"] != source["checkpoint_sha256"]:
            raise MethodExecutorError("queue item and source checkpoint differ")
        if queue_item["policy_digest"] != policy["policy_digest"]:
            raise MethodExecutorError("queue item and policy digest differ")
        profile = policy["work_profiles"][queue_item["work_envelope"]]
        contract = policy["method_contracts"][self.method_id]
        if contract["catalog_policy"] != self.catalog_policy:
            raise MethodExecutorError("controller and frozen catalog policy differ")
        return MethodExecutionPlan(
            method_id=self.method_id,
            queue_item_id=queue_item["queue_item_id"],
            case_id=queue_item["case_id"],
            source_checkpoint_sha256=source["checkpoint_sha256"],
            problem_id=source["ProblemID"],
            state_preparation_id=source["StatePreparationID"],
            work_envelope=queue_item["work_envelope"],
            semantic_work_cap=dict(profile["semantic_work_cap"]),
            maximum_rounds=profile["maximum_rounds"],
            optimizer=dict(policy["optimizer"]),
            acceptance=dict(policy["acceptance"]),
            policy_digest=policy["policy_digest"],
            queue_digest=queue_digest,
            catalog_policy=self.catalog_policy,
            sequential_commits=self.sequential_commits,
            post_commit_catalog_rebuild=self.post_commit_catalog_rebuild,
        )

    def catalog_parent_trace(
        self, source_digest: str, accepted_child_digests: tuple[str, ...]
    ) -> tuple[str, ...]:
        if not self.sequential_commits:
            return (source_digest,)
        if self.post_commit_catalog_rebuild:
            return (source_digest, *accepted_child_digests)
        return (source_digest,) * (len(accepted_child_digests) + 1)

    def execute_candidate(self, *_: object, **__: object) -> None:
        raise CandidateExecutionNotAuthorized(
            "S6 method controllers are planning-only until production backend parity passes"
        )


class ImmutableSourceController(MethodController):
    method_id = "immutable-ceo-star-source"
    catalog_policy = "none"


class SameStructureReoptimizationController(MethodController):
    method_id = "same-structure-reoptimization"
    catalog_policy = "source structure only"


class StructuralMagnitudePruningController(MethodController):
    method_id = "structural-magnitude-pruning"
    catalog_policy = "frozen magnitude order"


class V41OneShotController(MethodController):
    method_id = "v4.1-one-shot-joint-compression"
    catalog_policy = "one source catalog; no post-commit rebuild"


class V5SequentialNoRebuildController(MethodController):
    method_id = "v5-sequential-without-rebuilding"
    catalog_policy = "one source catalog reused after commit"
    sequential_commits = True
    post_commit_catalog_rebuild = False


class V5SequentialRebuildController(MethodController):
    method_id = "v5-sequential-with-rebuilding"
    catalog_policy = "full catalog rebuilt from every committed state"
    sequential_commits = True
    post_commit_catalog_rebuild = True


CONTROLLERS = (
    ImmutableSourceController,
    SameStructureReoptimizationController,
    StructuralMagnitudePruningController,
    V41OneShotController,
    V5SequentialNoRebuildController,
    V5SequentialRebuildController,
)


def controller_registry() -> dict[str, MethodController]:
    result = {controller.method_id: controller() for controller in CONTROLLERS}
    if len(result) != len(CONTROLLERS):
        raise RuntimeError("method controller IDs are not unique")
    return result


def causal_ablation_parity(
    no_rebuild: MethodExecutionPlan, rebuild: MethodExecutionPlan
) -> dict[str, bool]:
    left = no_rebuild.payload()
    right = rebuild.payload()
    allowed_differences = {
        "method_id",
        "queue_item_id",
        "catalog_policy",
        "post_commit_catalog_rebuild",
    }
    common_fields_equal = all(
        left[key] == right[key] for key in left if key not in allowed_differences
    )
    observed_differences = {
        key for key in left if left[key] != right[key]
    }
    return {
        "all_non_ablation_fields_equal": common_fields_equal,
        "difference_set_exact": observed_differences == allowed_differences,
        "both_are_sequential": no_rebuild.sequential_commits
        and rebuild.sequential_commits,
        "rebuild_flag_is_only_behavioral_switch": (
            no_rebuild.post_commit_catalog_rebuild is False
            and rebuild.post_commit_catalog_rebuild is True
        ),
    }

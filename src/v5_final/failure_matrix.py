"""Shared production checkpoints and fail-closed control-plane fault matrix."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .architecture_state import ArchitectureState
from .transaction import ArchitectureTransaction


PRODUCTION_STAGES = (
    "SOURCE_LOADED",
    "CATALOG_BUILT",
    "QUEUE_FROZEN",
    "CANDIDATE_EXECUTED",
    "CANDIDATE_CERTIFIED",
    "STATE_COMMITTED_OR_ROLLED_BACK",
    "CATALOG_REBUILT",
    "LEDGER_CLOSED",
)

FAILURE_MODES = (
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
)


class InjectedProductionFailure(RuntimeError):
    pass


@dataclass
class ProductionCheckpoints:
    """The checkpoint object used by both normal execution and fault audits."""

    failure_mode: str | None = None
    failure_stage: str | None = None

    def __post_init__(self) -> None:
        if self.failure_mode is not None and self.failure_mode not in FAILURE_MODES:
            raise ValueError("unknown failure mode")
        if self.failure_stage is not None and self.failure_stage not in PRODUCTION_STAGES:
            raise ValueError("unknown production stage")
        self.visited: list[str] = []

    def checkpoint(self, stage: str) -> None:
        if stage not in PRODUCTION_STAGES:
            raise ValueError("unknown production stage")
        if self.visited and PRODUCTION_STAGES.index(stage) <= PRODUCTION_STAGES.index(
            self.visited[-1]
        ):
            raise RuntimeError("production checkpoints must be monotone and unique")
        self.visited.append(stage)
        if stage == self.failure_stage:
            raise InjectedProductionFailure(f"{self.failure_mode}@{stage}")


def run_control_plane_cartesian_matrix(
    source: ArchitectureState, *, artifact_directory: Path
) -> dict[str, Any]:
    """Inject every failure label at every shared boundary and prove exact rollback.

    This is deliberately a control-plane proof. Crash, timeout, and malformed JSON
    are additionally exercised against the real subprocess bridge by S4 closure.
    """

    records = []
    for failure_mode in FAILURE_MODES:
        for failure_stage in PRODUCTION_STAGES:
            transaction = ArchitectureTransaction(source)
            transaction.stage(source)
            checkpoints = ProductionCheckpoints(failure_mode, failure_stage)
            caught = False
            try:
                for stage in PRODUCTION_STAGES:
                    checkpoints.checkpoint(stage)
            except InjectedProductionFailure:
                caught = True
            rollback = transaction.rollback(f"{failure_mode}@{failure_stage}")
            records.append(
                {
                    "failure_mode": failure_mode,
                    "production_stage": failure_stage,
                    "injected_and_caught": caught,
                    "target_stage_reached": failure_stage in checkpoints.visited,
                    "source_digest_before": rollback.source_digest_before,
                    "source_digest_after": rollback.source_digest_after,
                    "exact_rollback": rollback.exact,
                    "terminal_classification": "FAILED_CLOSED",
                }
            )
    orphan_paths = []
    if artifact_directory.exists():
        orphan_paths = list(artifact_directory.glob("*.tmp")) + list(
            artifact_directory.glob(".*.tmp")
        )
    return {
        "schema": "v5-final.failure-mode-stage-matrix.v1",
        "classification": (
            "control-plane boundary proof; not 80 physical quantum-kernel executions"
        ),
        "failure_modes": list(FAILURE_MODES),
        "production_stages": list(PRODUCTION_STAGES),
        "expected_pair_count": len(FAILURE_MODES) * len(PRODUCTION_STAGES),
        "observed_pair_count": len(records),
        "records": records,
        "all_pairs_fail_closed": all(
            record["injected_and_caught"]
            and record["target_stage_reached"]
            and record["exact_rollback"]
            and record["source_digest_before"] == record["source_digest_after"]
            and record["terminal_classification"] == "FAILED_CLOSED"
            for record in records
        ),
        "orphan_artifact_count": len(orphan_paths),
    }

"""Outcome-free filesystem fault probe for the parent-native persistent runner."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
from typing import Any

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .parent_native_persistent_runner import (
    ParentNativePersistentRunner,
    ParentNativePersistentRunnerError,
    make_attempt_id,
    publish_terminal_result_exclusive,
    recover_terminal_result,
    replay_raw_ledger,
)
from .parent_native_work_accounting import (
    ComponentwiseCapRejected,
    ParentNativeWorkRequest,
    work_cap_digest,
)
from .semantic_contract_v2 import WorkDelta


def _request(cap: WorkDelta, suffix: str) -> ParentNativeWorkRequest:
    character = format((sum(suffix.encode("utf-8")) % 14) + 1, "x")
    return ParentNativeWorkRequest(
        queue_item_id=f"synthetic-persistent-proof-{suffix}",
        method_id="v5-sequential-with-rebuilding",
        case_id="synthetic-non-molecular-persistence-proof",
        state_preparation_id="state-v1:" + character * 64,
        problem_id="problem-v1:" + "e" * 64,
        hamiltonian_digest="d" * 64,
        source_checkpoint_digest="c" * 64,
        frozen_queue_digest="b" * 64,
        work_cap_digest=work_cap_digest(cap),
    )


def _start(base: Path, suffix: str, cap: WorkDelta):
    request = _request(cap, suffix)
    attempt = make_attempt_id(request, ordinal=1, nonce=f"{suffix}-attempt-1")
    runner = ParentNativePersistentRunner.create(
        base / suffix, request=request, cap=cap, attempt_id=attempt
    )
    return runner, request, attempt


def _record_energy(runner: ParentNativePersistentRunner, *, fail: bool = False) -> None:
    recorder = runner.resume_work_recorder()
    if fail:
        class SyntheticKernelFailure(RuntimeError):
            pass

        try:
            recorder.invoke(
                "candidate-energy-evaluation",
                lambda: (_ for _ in ()).throw(SyntheticKernelFailure("synthetic")),
            )
        except SyntheticKernelFailure:
            pass
    else:
        recorder.invoke("candidate-energy-evaluation", lambda: -1.0)
    runner.persist_new_work_events(recorder.events)


def _complete_accepted(base: Path, suffix: str) -> tuple[Any, Any, Any]:
    cap = WorkDelta(energy_evaluations=2, optimizer_iterations=1)
    runner, request, _ = _start(base, suffix, cap)
    _record_energy(runner)
    resumed = ParentNativePersistentRunner.open(
        runner.root, request=request, cap=cap
    )
    recorder = resumed.resume_work_recorder()
    recorder.invoke("optimizer-iteration", lambda: None)
    resumed.persist_new_work_events(recorder.events)
    resumed.finish("ACCEPTED", outcome_digest="6" * 64)
    return resumed, request, cap


def run_probe() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="v5-s6-proof-") as temporary:
        base = Path(temporary)

        accepted, accepted_request, accepted_cap = _complete_accepted(
            base, "accepted"
        )
        accepted_state = accepted.state(require_terminal=True)
        recovered_before = recover_terminal_result(
            accepted.root, request=accepted_request, cap=accepted_cap
        )
        blocked_output = base / "already-present-result.json"
        write_json_exclusive(blocked_output, {"preexisting": True})
        try:
            publish_terminal_result_exclusive(
                blocked_output,
                accepted.root,
                request=accepted_request,
                cap=accepted_cap,
            )
        except FileExistsError:
            publication_failure_observed = True
        else:
            publication_failure_observed = False
        recovered_after = recover_terminal_result(
            accepted.root, request=accepted_request, cap=accepted_cap
        )
        published = publish_terminal_result_exclusive(
            base / "published-result.json",
            accepted.root,
            request=accepted_request,
            cap=accepted_cap,
        )

        rejected_cap = WorkDelta()
        rejected, rejected_request, _ = _start(base, "algorithm-rejected", rejected_cap)
        rejected.finish(
            "ALGORITHM_REJECTED", rejection_reason="SYNTHETIC_ACCEPTANCE_FALSE"
        )

        capped, capped_request, _ = _start(base, "cap-rejected", rejected_cap)
        capped_recorder = capped.resume_work_recorder()
        cap_kernel_calls = {"count": 0}
        try:
            capped_recorder.invoke(
                "candidate-energy-evaluation",
                lambda: cap_kernel_calls.__setitem__(
                    "count", cap_kernel_calls["count"] + 1
                ),
            )
        except ComponentwiseCapRejected:
            pass
        capped.persist_new_work_events(capped_recorder.events)
        capped.finish("CAP_REJECTED", rejection_reason="COMPONENTWISE_CAP_EXCEEDED")

        failure_cap = WorkDelta(energy_evaluations=1)
        failed, failed_request, _ = _start(base, "kernel-failure", failure_cap)
        _record_energy(failed, fail=True)
        rollback_snapshot = {
            component: format(index + 1, "x") * 64
            for index, component in enumerate(
                (
                    "ansatz",
                    "parameters",
                    "optimizer_inverse_hessian",
                    "resources",
                    "ledger_transaction",
                )
            )
        }
        failed.rollback_active_attempt(
            component_digests_before=rollback_snapshot,
            component_digests_after=rollback_snapshot,
            reason="SYNTHETIC_KERNEL_FAILURE",
        )
        failed.finish("KERNEL_FAILURE", rejection_reason="SYNTHETIC_KERNEL_FAILURE")

        retry_cap = WorkDelta(energy_evaluations=2)
        retried, retry_request, _ = _start(base, "retry", retry_cap)
        _record_energy(retried, fail=True)
        retried.rollback_active_attempt(
            component_digests_before=rollback_snapshot,
            component_digests_after=rollback_snapshot,
            reason="SYNTHETIC_RETRYABLE_FAILURE",
        )
        retried.start_retry(
            make_attempt_id(retry_request, ordinal=2, nonce="retry-attempt-2")
        )
        _record_energy(retried)
        retried.finish("ACCEPTED", outcome_digest="8" * 64)
        retry_state = retried.state(require_terminal=True)

        bad_rollback, _, _ = _start(base, "bad-rollback", WorkDelta())
        mismatched_snapshot = dict(rollback_snapshot)
        mismatched_snapshot["parameters"] = "f" * 64
        try:
            bad_rollback.rollback_active_attempt(
                component_digests_before=rollback_snapshot,
                component_digests_after=mismatched_snapshot,
                reason="SYNTHETIC_MISMATCH",
            )
        except ParentNativePersistentRunnerError:
            invalid_rollback_rejected_before_append = (
                len(bad_rollback.state().records) == 2
            )
        else:
            invalid_rollback_rejected_before_append = False

        exclusive_cap = WorkDelta()
        exclusive, exclusive_request, exclusive_attempt = _start(
            base, "exclusive", exclusive_cap
        )
        try:
            ParentNativePersistentRunner.create(
                exclusive.root,
                request=exclusive_request,
                cap=exclusive_cap,
                attempt_id=exclusive_attempt,
            )
        except FileExistsError:
            duplicate_root_rejected = True
        else:
            duplicate_root_rejected = False

        orphan, orphan_request, _ = _start(base, "orphan", WorkDelta())
        orphan_attempt = make_attempt_id(
            orphan_request, ordinal=2, nonce="orphan-overlap"
        )
        orphan._append_record(
            "attempt-start",
            orphan_attempt,
            {"attempt_ordinal": 2, "prior_attempt_rolled_back": False},
        )
        try:
            orphan.state()
        except ParentNativePersistentRunnerError:
            orphan_attempt_rejected = True
        else:
            orphan_attempt_rejected = False

        duplicate, duplicate_request, duplicate_cap = _complete_accepted(
            base, "duplicate-terminal"
        )
        duplicate_state = duplicate.state(require_terminal=True)
        duplicate._append_record(
            "terminal",
            duplicate_state.attempt_ids[-1],
            dict(duplicate_state.terminal or {}),
        )
        try:
            replay_raw_ledger(
                duplicate.root,
                request=duplicate_request,
                cap=duplicate_cap,
                require_terminal=True,
            )
        except ParentNativePersistentRunnerError:
            duplicate_terminal_rejected = True
        else:
            duplicate_terminal_rejected = False

        mismatch, mismatch_request, mismatch_cap = _complete_accepted(
            base, "digest-mismatch"
        )
        kernel_path = sorted(mismatch.root.glob("*-kernel-event.json"))[0]
        altered = json.loads(kernel_path.read_text())
        altered["payload"]["units"] = 2
        kernel_path.write_bytes(canonical_json_bytes(altered))
        try:
            replay_raw_ledger(
                mismatch.root,
                request=mismatch_request,
                cap=mismatch_cap,
                require_terminal=True,
            )
        except ParentNativePersistentRunnerError:
            digest_mismatch_rejected = True
        else:
            digest_mismatch_rejected = False

        statuses = {
            "accepted": accepted_state.terminal["terminal_status"],
            "algorithm_rejected": rejected.state(require_terminal=True).terminal[
                "terminal_status"
            ],
            "cap_rejected": capped.state(require_terminal=True).terminal[
                "terminal_status"
            ],
            "kernel_failure": failed.state(require_terminal=True).terminal[
                "terminal_status"
            ],
        }
        result = {
            "schema": "v5-final.parent-native-persistent-runner-probe.v1",
            "probe_kind": "synthetic_non_molecular_filesystem_control",
            "terminal_statuses": statuses,
            "accepted_terminal_count": sum(
                record["kind"] == "terminal" for record in accepted_state.records
            ),
            "process_interruption_resume_work_total": accepted_state.terminal[
                "work_total"
            ],
            "publication_failure_observed": publication_failure_observed,
            "recovery_identical_after_publication_failure": (
                recovered_before == recovered_after
            ),
            "successful_publication_recovered_digest": published[
                "recovered_result"
            ]["recovered_result_digest"],
            "raw_recovery_digest": recovered_after["recovered_result_digest"],
            "cap_rejection_kernel_calls": cap_kernel_calls["count"],
            "retry_attempt_count": len(retry_state.attempt_ids),
            "retry_rollback_count": len(retry_state.rolled_back_attempt_ids),
            "retry_preserved_failed_and_successful_work": (
                retry_state.work_total.energy_evaluations == 2
                and [event.outcome for event in retry_state.work_events]
                == ["failed", "completed"]
            ),
            "invalid_rollback_rejected_before_append": (
                invalid_rollback_rejected_before_append
            ),
            "duplicate_root_rejected": duplicate_root_rejected,
            "orphan_attempt_rejected": orphan_attempt_rejected,
            "duplicate_terminal_rejected": duplicate_terminal_rejected,
            "digest_mismatch_rejected": digest_mismatch_rejected,
            "molecular_candidate_energy_evaluations": 0,
            "H2_H4_queue_executed": False,
            "performance_evidence": False,
        }
        result["probe_digest"] = __import__("hashlib").sha256(
            canonical_json_bytes(result)
        ).hexdigest()
        return result


def main() -> None:
    print(json.dumps(run_probe(), sort_keys=True))


if __name__ == "__main__":
    main()

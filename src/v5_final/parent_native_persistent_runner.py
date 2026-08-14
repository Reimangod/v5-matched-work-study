"""Crash-auditable, exclusive raw ledger for one parent-native queue item.

Every raw record is an immutable, atomically published JSON file.  The record
chain is separate from (and binds) the kernel-event chain, so publication can
be retried without re-running scientific work.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from v5_matched_work.atomic_artifacts import (
    canonical_json_bytes,
    write_json_exclusive,
)

from .parent_native_work_accounting import (
    ParentNativeWorkError,
    ParentNativeWorkEvent,
    ParentNativeWorkRecorder,
    ParentNativeWorkRequest,
    event_from_dict_strict,
    reconstruct,
    release_summary,
    work_cap_digest,
)
from .semantic_contract_v2 import WORK_COMPONENTS, WorkDelta


RECORD_RE = re.compile(
    r"^(?P<sequence>[0-9]{8})-(?P<kind>request-start|attempt-start|kernel-event|"
    r"attempt-rollback|terminal)\.json$"
)
ATTEMPT_RE = re.compile(r"^parent-native-attempt-v1:[0-9a-f]{64}$")
TERMINAL_STATUSES = {
    "CAP_REJECTED",
    "ALGORITHM_REJECTED",
    "ACCEPTED",
    "KERNEL_FAILURE",
}
ROLLBACK_COMPONENTS = {
    "ansatz",
    "parameters",
    "optimizer_inverse_hessian",
    "resources",
    "ledger_transaction",
}


class ParentNativePersistentRunnerError(RuntimeError):
    pass


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _digest_without(value: Mapping[str, Any], field: str) -> str:
    body = dict(value)
    body.pop(field, None)
    return _digest(body)


def _is_digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _add(left: WorkDelta, right: WorkDelta) -> WorkDelta:
    return WorkDelta(
        **{
            component: getattr(left, component) + getattr(right, component)
            for component in WORK_COMPONENTS
        }
    )


def _fits(value: WorkDelta, cap: WorkDelta) -> bool:
    return all(
        getattr(value, component) <= getattr(cap, component)
        for component in WORK_COMPONENTS
    )


def make_attempt_id(
    request: ParentNativeWorkRequest, *, ordinal: int, nonce: str
) -> str:
    if isinstance(ordinal, bool) or not isinstance(ordinal, int) or ordinal < 1:
        raise ParentNativePersistentRunnerError("attempt ordinal must be positive")
    if not nonce:
        raise ParentNativePersistentRunnerError("attempt nonce must be nonempty")
    return "parent-native-attempt-v1:" + _digest(
        {"request_id": request.request_id, "ordinal": ordinal, "nonce": nonce}
    )


def _validate_attempt_id(value: str) -> None:
    if not ATTEMPT_RE.fullmatch(value):
        raise ParentNativePersistentRunnerError("attempt ID is invalid")


def _validate_rollback_snapshots(
    before: object, after: object
) -> None:
    if not isinstance(before, dict) or not isinstance(after, dict):
        raise ParentNativePersistentRunnerError("rollback snapshots are absent")
    if set(before) != ROLLBACK_COMPONENTS or set(after) != ROLLBACK_COMPONENTS:
        raise ParentNativePersistentRunnerError("rollback scope is incomplete")
    if before != after or not all(_is_digest(value) for value in before.values()):
        raise ParentNativePersistentRunnerError(
            "rollback did not restore every exact component"
        )


def _build_record(
    *,
    sequence: int,
    previous_record_digest: str,
    kind: str,
    request_id: str,
    attempt_id: str | None,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    if kind not in {"request-start", "attempt-start", "kernel-event", "attempt-rollback", "terminal"}:
        raise ParentNativePersistentRunnerError("raw ledger record kind is invalid")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
        raise ParentNativePersistentRunnerError("raw ledger sequence is invalid")
    if not _is_digest(previous_record_digest):
        raise ParentNativePersistentRunnerError("raw ledger previous digest is invalid")
    if attempt_id is not None:
        _validate_attempt_id(attempt_id)
    record = {
        "schema": "v5-final.parent-native-raw-record.v1",
        "sequence": sequence,
        "previous_record_digest": previous_record_digest,
        "kind": kind,
        "request_id": request_id,
        "attempt_id": attempt_id,
        "payload": dict(payload),
    }
    record["record_digest"] = _digest(record)
    return record


def _record_path(root: Path, sequence: int, kind: str) -> Path:
    return root / f"{sequence:08d}-{kind}.json"


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _ledger_from_events(
    request: ParentNativeWorkRequest,
    cap: WorkDelta,
    events: Sequence[ParentNativeWorkEvent],
) -> dict[str, Any]:
    recorder = ParentNativeWorkRecorder.resume(request=request, cap=cap, events=events)
    return recorder.close()


@dataclass(frozen=True)
class ReplayedRawLedger:
    root: Path
    ledger_id: str
    request: ParentNativeWorkRequest
    cap: WorkDelta
    records: tuple[Mapping[str, Any], ...]
    attempt_ids: tuple[str, ...]
    active_attempt_id: str | None
    rolled_back_attempt_ids: tuple[str, ...]
    work_events: tuple[ParentNativeWorkEvent, ...]
    work_attempt_ids: tuple[str, ...]
    work_total: WorkDelta
    terminal: Mapping[str, Any] | None

    @property
    def last_record_digest(self) -> str:
        return str(self.records[-1]["record_digest"])

    @property
    def next_record_sequence(self) -> int:
        return len(self.records)


def _read_records(root: Path) -> list[dict[str, Any]]:
    if not root.is_dir() or root.is_symlink():
        raise ParentNativePersistentRunnerError("raw ledger root is absent or unsafe")
    paths = sorted(root.iterdir())
    if not paths:
        raise ParentNativePersistentRunnerError("raw ledger is empty")
    records: list[dict[str, Any]] = []
    for path in paths:
        match = RECORD_RE.fullmatch(path.name)
        if match is None or not path.is_file() or path.is_symlink():
            raise ParentNativePersistentRunnerError(
                f"orphan or unregistered raw-ledger entry: {path.name}"
            )
        raw = path.read_bytes()
        try:
            record = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ParentNativePersistentRunnerError("raw ledger JSON is invalid") from error
        if raw != canonical_json_bytes(record):
            raise ParentNativePersistentRunnerError("raw ledger record is not canonical JSON")
        if int(match.group("sequence")) != record.get("sequence"):
            raise ParentNativePersistentRunnerError("raw ledger filename sequence mismatch")
        if match.group("kind") != record.get("kind"):
            raise ParentNativePersistentRunnerError("raw ledger filename kind mismatch")
        records.append(record)
    return records


def replay_raw_ledger(
    root: Path,
    *,
    request: ParentNativeWorkRequest,
    cap: WorkDelta,
    require_terminal: bool = False,
) -> ReplayedRawLedger:
    """Rebuild all state from immutable raw records and reject any ambiguity."""

    records = _read_records(root)
    expected_previous = "0" * 64
    attempt_ids: list[str] = []
    rolled_back: list[str] = []
    work_events: list[ParentNativeWorkEvent] = []
    work_attempts: list[str] = []
    active_attempt: str | None = None
    terminal: Mapping[str, Any] | None = None
    ledger_id = ""
    total = WorkDelta()
    for expected_sequence, record in enumerate(records):
        if record.get("schema") != "v5-final.parent-native-raw-record.v1":
            raise ParentNativePersistentRunnerError("raw ledger record schema mismatch")
        if record.get("sequence") != expected_sequence:
            raise ParentNativePersistentRunnerError("raw ledger sequence is missing or duplicated")
        if record.get("previous_record_digest") != expected_previous:
            raise ParentNativePersistentRunnerError("raw ledger hash chain is broken")
        if record.get("record_digest") != _digest_without(record, "record_digest"):
            raise ParentNativePersistentRunnerError("raw ledger record digest mismatch")
        if record.get("request_id") != request.request_id:
            raise ParentNativePersistentRunnerError("raw ledger request binding mismatch")
        if terminal is not None:
            raise ParentNativePersistentRunnerError("record exists after the item terminal")
        expected_previous = str(record["record_digest"])
        kind = str(record["kind"])
        payload = record.get("payload")
        if not isinstance(payload, dict):
            raise ParentNativePersistentRunnerError("raw ledger payload is invalid")

        if expected_sequence == 0:
            expected_start = {
                "schema": "v5-final.parent-native-raw-ledger-start.v1",
                "request": request.payload() | {"request_id": request.request_id},
                "cap": asdict(cap),
                "work_cap_digest": work_cap_digest(cap),
            }
            expected_start["ledger_id"] = (
                "parent-native-raw-ledger-v1:" + _digest(expected_start)
            )
            if kind != "request-start" or record.get("attempt_id") is not None:
                raise ParentNativePersistentRunnerError("request-start must be first")
            if payload != expected_start:
                raise ParentNativePersistentRunnerError("request-start binding mismatch")
            ledger_id = str(payload["ledger_id"])
            continue
        if kind == "request-start":
            raise ParentNativePersistentRunnerError("duplicate request-start record")
        attempt_id = record.get("attempt_id")
        if not isinstance(attempt_id, str):
            raise ParentNativePersistentRunnerError("attempt-bound record lacks attempt ID")
        _validate_attempt_id(attempt_id)

        if kind == "attempt-start":
            if active_attempt is not None:
                raise ParentNativePersistentRunnerError(
                    "orphan or overlapping attempt without exact rollback"
                )
            if attempt_id in attempt_ids:
                raise ParentNativePersistentRunnerError("attempt ID was reused")
            if payload != {
                "attempt_ordinal": len(attempt_ids) + 1,
                "prior_attempt_rolled_back": bool(attempt_ids),
            }:
                raise ParentNativePersistentRunnerError("attempt-start semantics mismatch")
            if attempt_ids and attempt_ids[-1] not in rolled_back:
                raise ParentNativePersistentRunnerError("retry lacks prior exact rollback")
            attempt_ids.append(attempt_id)
            active_attempt = attempt_id
            continue
        if kind == "kernel-event":
            if active_attempt != attempt_id:
                raise ParentNativePersistentRunnerError("kernel event is orphaned from its attempt")
            try:
                event = event_from_dict_strict(payload, request)
            except (KeyError, TypeError, ParentNativeWorkError) as error:
                raise ParentNativePersistentRunnerError("kernel event is invalid") from error
            expected_work_sequence = len(work_events)
            expected_work_previous = (
                "0" * 64 if not work_events else work_events[-1].event_digest
            )
            if (
                event.sequence != expected_work_sequence
                or event.previous_event_digest != expected_work_previous
            ):
                raise ParentNativePersistentRunnerError("kernel event chain is discontinuous")
            projected = _add(total, event.delta)
            if not _fits(projected, cap):
                raise ParentNativePersistentRunnerError("persisted work exceeds componentwise cap")
            work_events.append(event)
            work_attempts.append(attempt_id)
            total = projected
            continue
        if kind == "attempt-rollback":
            if active_attempt != attempt_id:
                raise ParentNativePersistentRunnerError("rollback is orphaned from its attempt")
            before = payload.get("component_digests_before")
            after = payload.get("component_digests_after")
            _validate_rollback_snapshots(before, after)
            if not payload.get("reason"):
                raise ParentNativePersistentRunnerError("rollback reason is empty")
            rolled_back.append(attempt_id)
            active_attempt = None
            continue
        if kind != "terminal":
            raise ParentNativePersistentRunnerError("unregistered raw ledger record")
        status = payload.get("terminal_status")
        if status not in TERMINAL_STATUSES:
            raise ParentNativePersistentRunnerError("terminal status is invalid")
        if status == "KERNEL_FAILURE":
            if active_attempt is not None or not rolled_back or rolled_back[-1] != attempt_id:
                raise ParentNativePersistentRunnerError(
                    "kernel failure terminal requires exact rollback"
                )
            if not any(
                owner == attempt_id and event.outcome == "failed"
                for owner, event in zip(work_attempts, work_events)
            ):
                raise ParentNativePersistentRunnerError(
                    "kernel failure terminal lacks failed kernel work"
                )
        elif active_attempt != attempt_id:
            raise ParentNativePersistentRunnerError("terminal is orphaned from active attempt")
        if status == "CAP_REJECTED" and not any(
            owner == attempt_id and event.operation == "cap-rejection"
            for owner, event in zip(work_attempts, work_events)
        ):
            raise ParentNativePersistentRunnerError("cap terminal lacks pre-kernel rejection")
        if status == "ACCEPTED" and not _is_digest(payload.get("outcome_digest")):
            raise ParentNativePersistentRunnerError("accepted terminal lacks outcome digest")
        if status == "ALGORITHM_REJECTED" and not payload.get("rejection_reason"):
            raise ParentNativePersistentRunnerError("algorithm rejection reason is empty")
        if status != "ACCEPTED" and payload.get("outcome_digest") is not None:
            raise ParentNativePersistentRunnerError("non-accepted terminal has an outcome digest")
        if status == "ACCEPTED" and payload.get("rejection_reason") is not None:
            raise ParentNativePersistentRunnerError("accepted terminal has a rejection reason")
        if status in {"CAP_REJECTED", "KERNEL_FAILURE"} and not payload.get(
            "rejection_reason"
        ):
            raise ParentNativePersistentRunnerError("failure terminal reason is empty")
        if payload.get("work_event_count") != len(work_events):
            raise ParentNativePersistentRunnerError("terminal work event count mismatch")
        if payload.get("work_total") != asdict(total):
            raise ParentNativePersistentRunnerError("terminal work total mismatch")
        if payload.get("final_work_event_digest") != (
            "0" * 64 if not work_events else work_events[-1].event_digest
        ):
            raise ParentNativePersistentRunnerError("terminal work digest mismatch")
        try:
            reconstructed = reconstruct(work_events, request)
        except ParentNativeWorkError as error:
            raise ParentNativePersistentRunnerError(
                "terminal kernel-event reconstruction failed"
            ) from error
        if reconstructed != total:
            raise ParentNativePersistentRunnerError("terminal reconstructed work differs")
        terminal = dict(payload)
        active_attempt = None

    if not ledger_id:
        raise ParentNativePersistentRunnerError("raw ledger lacks request-start")
    if require_terminal and terminal is None:
        raise ParentNativePersistentRunnerError("raw ledger has no item terminal")
    return ReplayedRawLedger(
        root=root,
        ledger_id=ledger_id,
        request=request,
        cap=cap,
        records=tuple(records),
        attempt_ids=tuple(attempt_ids),
        active_attempt_id=active_attempt,
        rolled_back_attempt_ids=tuple(rolled_back),
        work_events=tuple(work_events),
        work_attempt_ids=tuple(work_attempts),
        work_total=total,
        terminal=terminal,
    )


class ParentNativePersistentRunner:
    def __init__(
        self, root: Path, request: ParentNativeWorkRequest, cap: WorkDelta
    ) -> None:
        self.root = root
        self.request = request
        self.cap = cap

    @classmethod
    def create(
        cls,
        root: Path,
        *,
        request: ParentNativeWorkRequest,
        cap: WorkDelta,
        attempt_id: str,
    ) -> "ParentNativePersistentRunner":
        _validate_attempt_id(attempt_id)
        if work_cap_digest(cap) != request.work_cap_digest:
            raise ParentNativePersistentRunnerError("request and cap digest differ")
        root.parent.mkdir(parents=True, exist_ok=True)
        root.mkdir(exist_ok=False)
        _fsync_directory(root.parent)
        runner = cls(root, request, cap)
        start = {
            "schema": "v5-final.parent-native-raw-ledger-start.v1",
            "request": request.payload() | {"request_id": request.request_id},
            "cap": asdict(cap),
            "work_cap_digest": work_cap_digest(cap),
        }
        start["ledger_id"] = "parent-native-raw-ledger-v1:" + _digest(start)
        runner._append_record("request-start", None, start)
        runner._append_record(
            "attempt-start",
            attempt_id,
            {"attempt_ordinal": 1, "prior_attempt_rolled_back": False},
        )
        replay_raw_ledger(root, request=request, cap=cap)
        return runner

    @classmethod
    def open(
        cls,
        root: Path,
        *,
        request: ParentNativeWorkRequest,
        cap: WorkDelta,
    ) -> "ParentNativePersistentRunner":
        state = replay_raw_ledger(root, request=request, cap=cap)
        if state.terminal is not None:
            raise ParentNativePersistentRunnerError("terminal ledger cannot resume execution")
        return cls(root, request, cap)

    def state(self, *, require_terminal: bool = False) -> ReplayedRawLedger:
        return replay_raw_ledger(
            self.root,
            request=self.request,
            cap=self.cap,
            require_terminal=require_terminal,
        )

    def _append_record(
        self,
        kind: str,
        attempt_id: str | None,
        payload: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        if not self.root.is_dir():
            raise ParentNativePersistentRunnerError("raw ledger root is absent")
        paths = sorted(self.root.iterdir())
        previous = "0" * 64
        if paths:
            records = _read_records(self.root)
            previous = str(records[-1]["record_digest"])
            sequence = len(records)
        else:
            sequence = 0
        record = _build_record(
            sequence=sequence,
            previous_record_digest=previous,
            kind=kind,
            request_id=self.request.request_id,
            attempt_id=attempt_id,
            payload=payload,
        )
        write_json_exclusive(_record_path(self.root, sequence, kind), record)
        return record

    def resume_work_recorder(self) -> ParentNativeWorkRecorder:
        state = self.state()
        if state.active_attempt_id is None:
            raise ParentNativePersistentRunnerError("no active attempt can execute work")
        return ParentNativeWorkRecorder.resume(
            request=self.request, cap=self.cap, events=state.work_events
        )

    def persist_new_work_events(
        self, events: Sequence[ParentNativeWorkEvent]
    ) -> None:
        state = self.state()
        if state.active_attempt_id is None:
            raise ParentNativePersistentRunnerError("no active attempt can persist work")
        existing = len(state.work_events)
        if len(events) < existing or tuple(events[:existing]) != state.work_events:
            raise ParentNativePersistentRunnerError(
                "work recorder history differs from persistent ledger"
            )
        for event in events[existing:]:
            self._append_record(
                "kernel-event", state.active_attempt_id, event.to_dict()
            )
        self.state()

    def rollback_active_attempt(
        self,
        *,
        component_digests_before: Mapping[str, str],
        component_digests_after: Mapping[str, str],
        reason: str,
    ) -> None:
        state = self.state()
        if state.active_attempt_id is None:
            raise ParentNativePersistentRunnerError("no active attempt can roll back")
        _validate_rollback_snapshots(
            dict(component_digests_before), dict(component_digests_after)
        )
        if not reason:
            raise ParentNativePersistentRunnerError("rollback reason is empty")
        self._append_record(
            "attempt-rollback",
            state.active_attempt_id,
            {
                "component_digests_before": dict(component_digests_before),
                "component_digests_after": dict(component_digests_after),
                "reason": reason,
            },
        )
        self.state()

    def start_retry(self, attempt_id: str) -> None:
        _validate_attempt_id(attempt_id)
        state = self.state()
        if state.active_attempt_id is not None or not state.rolled_back_attempt_ids:
            raise ParentNativePersistentRunnerError(
                "retry requires a completed exact rollback"
            )
        self._append_record(
            "attempt-start",
            attempt_id,
            {
                "attempt_ordinal": len(state.attempt_ids) + 1,
                "prior_attempt_rolled_back": True,
            },
        )
        self.state()

    def finish(
        self,
        status: str,
        *,
        outcome_digest: str | None = None,
        rejection_reason: str | None = None,
    ) -> Mapping[str, Any]:
        if status not in TERMINAL_STATUSES:
            raise ParentNativePersistentRunnerError("terminal status is invalid")
        state = self.state()
        if state.terminal is not None:
            raise ParentNativePersistentRunnerError("duplicate terminal is forbidden")
        if status == "KERNEL_FAILURE":
            if not state.rolled_back_attempt_ids or state.active_attempt_id is not None:
                raise ParentNativePersistentRunnerError(
                    "kernel failure requires rollback before terminal"
                )
            attempt_id = state.rolled_back_attempt_ids[-1]
        else:
            if state.active_attempt_id is None:
                raise ParentNativePersistentRunnerError("terminal lacks active attempt")
            attempt_id = state.active_attempt_id
        if status == "ACCEPTED":
            if not _is_digest(outcome_digest) or rejection_reason is not None:
                raise ParentNativePersistentRunnerError(
                    "accepted terminal requires only a valid outcome digest"
                )
        else:
            if outcome_digest is not None:
                raise ParentNativePersistentRunnerError(
                    "non-accepted terminal cannot contain an outcome digest"
                )
            if not rejection_reason:
                raise ParentNativePersistentRunnerError(
                    "non-accepted terminal requires a reason"
                )
        if status == "CAP_REJECTED" and not any(
            owner == attempt_id and event.operation == "cap-rejection"
            for owner, event in zip(state.work_attempt_ids, state.work_events)
        ):
            raise ParentNativePersistentRunnerError(
                "cap terminal requires a persistent cap rejection"
            )
        if status == "KERNEL_FAILURE" and not any(
            owner == attempt_id and event.outcome == "failed"
            for owner, event in zip(state.work_attempt_ids, state.work_events)
        ):
            raise ParentNativePersistentRunnerError(
                "kernel failure requires persistent failed work"
            )
        payload = {
            "terminal_status": status,
            "work_event_count": len(state.work_events),
            "work_total": asdict(state.work_total),
            "final_work_event_digest": (
                "0" * 64
                if not state.work_events
                else state.work_events[-1].event_digest
            ),
            "outcome_digest": outcome_digest,
            "rejection_reason": rejection_reason,
        }
        record = self._append_record("terminal", attempt_id, payload)
        self.state(require_terminal=True)
        return record


def recover_terminal_result(
    root: Path,
    *,
    request: ParentNativeWorkRequest,
    cap: WorkDelta,
) -> dict[str, Any]:
    state = replay_raw_ledger(
        root, request=request, cap=cap, require_terminal=True
    )
    ledger = _ledger_from_events(request, cap, state.work_events)
    summary = release_summary(ledger, request)
    result = {
        "schema": "v5-final.parent-native-recovered-result.v1",
        "ledger_id": state.ledger_id,
        "request_id": request.request_id,
        "terminal": dict(state.terminal or {}),
        "raw_record_count": len(state.records),
        "raw_record_digests": [record["record_digest"] for record in state.records],
        "work_ledger_digest": ledger["ledger_digest"],
        "work_release_summary": summary,
    }
    result["recovered_result_digest"] = _digest(result)
    return result


def publish_terminal_result_exclusive(
    output: Path,
    root: Path,
    *,
    request: ParentNativeWorkRequest,
    cap: WorkDelta,
) -> dict[str, Any]:
    result = recover_terminal_result(root, request=request, cap=cap)
    artifact = {
        "schema": "v5-final.parent-native-published-result.v1",
        "recovered_result": result,
    }
    artifact["artifact_digest"] = _digest(artifact)
    write_json_exclusive(output, artifact)
    return artifact

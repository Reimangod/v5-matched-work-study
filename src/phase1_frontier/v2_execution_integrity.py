"""Content-addressed integrity records for the Phase-1 v2 terminal prefix.

The frozen scientific protocol is deliberately outside this module.  These
helpers only prove that already-terminal queue items still bind to their raw
ledger, cap, request, and immutable published result.
"""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from v5_final.parent_native_persistent_runner import replay_raw_ledger
from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive


class V2ExecutionIntegrityError(RuntimeError):
    """Raised before new kernel work when the terminal prefix is ambiguous."""


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def content_digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(dict(value))).hexdigest()


def read_canonical_digest_artifact(path: Path, digest_key: str) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (FileNotFoundError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise V2ExecutionIntegrityError(f"missing or invalid artifact: {path}") from error
    if raw != canonical_json_bytes(value):
        raise V2ExecutionIntegrityError(f"artifact is not canonical JSON: {path}")
    body = dict(value)
    observed = body.pop(digest_key, None)
    if observed != content_digest(body):
        raise V2ExecutionIntegrityError(f"artifact digest mismatch: {path}")
    return value


def _item_root(base_root: Path, index: int, request_id: str) -> Path:
    return base_root / f"{index:04d}-{request_id.rsplit(':', 1)[-1]}"


def _attestation_path(attestation_root: Path, index: int) -> Path:
    return attestation_root / f"item-{index:04d}-terminal-attestation-v1.json"


def _prefix_path(attestation_root: Path, terminal_count: int) -> Path:
    return attestation_root / f"prefix-{terminal_count:04d}-manifest-v1.json"


def build_terminal_attestation(
    *,
    index: int,
    row: Mapping[str, Any],
    item_root: Path,
    request: Any,
    cap: Any,
) -> dict[str, Any]:
    terminal_path = item_root / "terminal-result.json"
    terminal = read_canonical_digest_artifact(terminal_path, "artifact_digest")
    replay = replay_raw_ledger(
        item_root / "ledger", request=request, cap=cap, require_terminal=True
    )
    recovered = terminal.get("recovered_result", {})
    if recovered.get("request_id") != request.request_id:
        raise V2ExecutionIntegrityError("terminal result request binding mismatch")
    if recovered.get("raw_record_count") != len(replay.records):
        raise V2ExecutionIntegrityError("terminal result raw-record count mismatch")
    terminal_payload = replay.terminal or {}
    if recovered.get("terminal") != terminal_payload:
        raise V2ExecutionIntegrityError("terminal result differs from replayed terminal")
    value: dict[str, Any] = {
        "schema": "phase1-frontier.v2-terminal-attestation.v1",
        "queue_index": index,
        "RequestID": row["RequestID"],
        "work_request_id": request.request_id,
        "terminal_status": terminal_payload.get("terminal_status"),
        "terminal_result_sha256": sha256_file(terminal_path),
        "terminal_artifact_digest": terminal["artifact_digest"],
        "raw_record_count": len(replay.records),
        "raw_ledger_last_record_digest": replay.last_record_digest,
        "work_total": asdict(replay.work_total),
        "cap": asdict(cap),
    }
    value["attestation_digest"] = content_digest(value)
    return value


def publish_terminal_attestation(
    *,
    index: int,
    row: Mapping[str, Any],
    base_root: Path,
    attestation_root: Path,
    request: Any,
    cap: Any,
) -> dict[str, Any]:
    value = build_terminal_attestation(
        index=index,
        row=row,
        item_root=_item_root(base_root, index, str(row["RequestID"])),
        request=request,
        cap=cap,
    )
    path = _attestation_path(attestation_root, index)
    if path.exists():
        existing = read_canonical_digest_artifact(path, "attestation_digest")
        if existing != value:
            raise V2ExecutionIntegrityError("existing terminal attestation changed")
        return existing
    write_json_exclusive(path, value)
    return value


def _verify_attestation_reference(
    entry: Mapping[str, Any], *, attestation_root: Path, expected_index: int
) -> dict[str, Any]:
    path = _attestation_path(attestation_root, expected_index)
    value = read_canonical_digest_artifact(path, "attestation_digest")
    if entry != {
        "queue_index": expected_index,
        "RequestID": value["RequestID"],
        "attestation_sha256": sha256_file(path),
        "attestation_digest": value["attestation_digest"],
    }:
        raise V2ExecutionIntegrityError("prefix attestation reference mismatch")
    return value


def publish_prefix_manifest(
    *,
    queue: Mapping[str, Any],
    terminal_count: int,
    attestation_root: Path,
) -> dict[str, Any]:
    if terminal_count < 1 or terminal_count > len(queue["items"]):
        raise V2ExecutionIntegrityError("invalid terminal prefix length")
    entries = []
    for index, row in enumerate(queue["items"][:terminal_count]):
        path = _attestation_path(attestation_root, index)
        attestation = read_canonical_digest_artifact(path, "attestation_digest")
        if (
            attestation.get("queue_index") != index
            or attestation.get("RequestID") != row["RequestID"]
        ):
            raise V2ExecutionIntegrityError("attestation is not the frozen queue prefix")
        entries.append(
            {
                "queue_index": index,
                "RequestID": row["RequestID"],
                "attestation_sha256": sha256_file(path),
                "attestation_digest": attestation["attestation_digest"],
            }
        )
    previous_digest = None
    if terminal_count > 1:
        previous = read_canonical_digest_artifact(
            _prefix_path(attestation_root, terminal_count - 1), "prefix_digest"
        )
        if previous.get("entries") != entries[:-1]:
            raise V2ExecutionIntegrityError("previous prefix is not an exact predecessor")
        previous_digest = previous["prefix_digest"]
    value: dict[str, Any] = {
        "schema": "phase1-frontier.v2-terminal-prefix-manifest.v1",
        "queue_canonical_sha256": hashlib.sha256(
            canonical_json_bytes(queue)
        ).hexdigest(),
        "queue_digest": queue["queue_digest"],
        "terminal_count": terminal_count,
        "previous_prefix_digest": previous_digest,
        "entries": entries,
    }
    value["prefix_digest"] = content_digest(value)
    path = _prefix_path(attestation_root, terminal_count)
    if path.exists():
        existing = read_canonical_digest_artifact(path, "prefix_digest")
        if existing != value:
            raise V2ExecutionIntegrityError("existing prefix manifest changed")
        return existing
    write_json_exclusive(path, value)
    return value


def validate_prefix_manifest(
    *,
    queue: Mapping[str, Any],
    expected_count: int,
    attestation_root: Path,
) -> dict[str, Any] | None:
    if expected_count == 0:
        return None
    manifest = read_canonical_digest_artifact(
        _prefix_path(attestation_root, expected_count), "prefix_digest"
    )
    if manifest.get("terminal_count") != expected_count:
        raise V2ExecutionIntegrityError("terminal prefix length mismatch")
    if manifest.get("queue_digest") != queue["queue_digest"]:
        raise V2ExecutionIntegrityError("terminal prefix queue digest mismatch")
    entries: Sequence[Mapping[str, Any]] = manifest.get("entries", ())
    if len(entries) != expected_count:
        raise V2ExecutionIntegrityError("terminal prefix entry count mismatch")
    for index, (entry, row) in enumerate(zip(entries, queue["items"])):
        attestation = _verify_attestation_reference(
            entry, attestation_root=attestation_root, expected_index=index
        )
        if attestation.get("RequestID") != row["RequestID"]:
            raise V2ExecutionIntegrityError("terminal prefix is not in frozen order")
    if expected_count > 1:
        previous = read_canonical_digest_artifact(
            _prefix_path(attestation_root, expected_count - 1), "prefix_digest"
        )
        if (
            manifest.get("previous_prefix_digest") != previous["prefix_digest"]
            or previous.get("entries") != list(entries[:-1])
        ):
            raise V2ExecutionIntegrityError("terminal prefix digest chain mismatch")
    return manifest


def audit_attestation_payload(
    *,
    index: int,
    row: Mapping[str, Any],
    base_root: Path,
    attestation_root: Path,
    request: Any,
    cap: Any,
) -> bool:
    expected = build_terminal_attestation(
        index=index,
        row=row,
        item_root=_item_root(base_root, index, str(row["RequestID"])),
        request=request,
        cap=cap,
    )
    observed = read_canonical_digest_artifact(
        _attestation_path(attestation_root, index), "attestation_digest"
    )
    return expected == observed

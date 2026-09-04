from __future__ import annotations

import json
from pathlib import Path

import pytest

from phase1_frontier.v2_execution_integrity import (
    V2ExecutionIntegrityError,
    content_digest,
    publish_prefix_manifest,
    read_canonical_digest_artifact,
    validate_prefix_manifest,
)
from v5_matched_work.atomic_artifacts import canonical_json_bytes


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(value))


def _attestation(root: Path, index: int, request_id: str) -> None:
    value = {
        "schema": "phase1-frontier.v2-terminal-attestation.v1",
        "queue_index": index,
        "RequestID": request_id,
        "terminal_status": "ALGORITHM_REJECTED",
    }
    value["attestation_digest"] = content_digest(value)
    _write(root / f"item-{index:04d}-terminal-attestation-v1.json", value)


def test_prefix_manifest_is_content_addressed_and_chained(tmp_path) -> None:
    queue = {
        "queue_digest": "queue-v1:test",
        "items": [{"RequestID": "request:a"}, {"RequestID": "request:b"}],
    }
    _attestation(tmp_path, 0, "request:a")
    first = publish_prefix_manifest(
        queue=queue, terminal_count=1, attestation_root=tmp_path
    )
    _attestation(tmp_path, 1, "request:b")
    second = publish_prefix_manifest(
        queue=queue, terminal_count=2, attestation_root=tmp_path
    )
    assert second["previous_prefix_digest"] == first["prefix_digest"]
    assert validate_prefix_manifest(
        queue=queue, expected_count=2, attestation_root=tmp_path
    ) == second


def test_prefix_manifest_rejects_attestation_mutation(tmp_path) -> None:
    queue = {"queue_digest": "queue-v1:test", "items": [{"RequestID": "request:a"}]}
    _attestation(tmp_path, 0, "request:a")
    publish_prefix_manifest(queue=queue, terminal_count=1, attestation_root=tmp_path)
    path = tmp_path / "item-0000-terminal-attestation-v1.json"
    value = json.loads(path.read_text())
    value["terminal_status"] = "ACCEPTED"
    _write(path, value)
    with pytest.raises(V2ExecutionIntegrityError):
        validate_prefix_manifest(
            queue=queue, expected_count=1, attestation_root=tmp_path
        )


def test_noncanonical_artifact_is_rejected(tmp_path) -> None:
    path = tmp_path / "artifact.json"
    value = {"value": 1}
    value["digest"] = content_digest(value)
    path.write_text(json.dumps(value, indent=2))
    with pytest.raises(V2ExecutionIntegrityError, match="not canonical"):
        read_canonical_digest_artifact(path, "digest")

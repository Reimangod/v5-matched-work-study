from __future__ import annotations

import hashlib
from pathlib import Path

from aic_a100_pilot.common import digest
from aic_a100_pilot.dual_optimizer_execution import (
    CASES,
    STATUS_GO,
    STATUS_NO_GO,
    intervals_overlap,
    merge_shards,
)
from v5_matched_work.atomic_artifacts import canonical_json_bytes


def test_registered_case_order_is_small_and_fixed():
    assert CASES == ("h2", "h6", "beh2")


def test_interval_overlap_uses_strict_positive_intersection():
    first = {"started_unix_ns": 10, "ended_unix_ns": 30}
    overlapping = {"started_unix_ns": 20, "ended_unix_ns": 40}
    touching = {"started_unix_ns": 30, "ended_unix_ns": 50}
    assert intervals_overlap(first, overlapping)
    assert not intervals_overlap(first, touching)


def test_record_digest_rejects_post_publication_mutation():
    value = {"schema": "test", "status": "PASS"}
    value["record_digest"] = digest(value)
    assert value["record_digest"] == digest(
        {key: item for key, item in value.items() if key != "record_digest"}
    )
    value["status"] = "FAIL"
    assert value["record_digest"] != digest(
        {key: item for key, item in value.items() if key != "record_digest"}
    )


def test_gpu_identity_is_privacy_preserving():
    raw_uuid = "GPU-example-secret"
    public = hashlib.sha256(raw_uuid.encode("utf-8")).hexdigest()
    assert raw_uuid not in public
    assert len(public) == 64


def _publish(path: Path, value: dict) -> dict:
    body = dict(value)
    body["record_digest"] = digest(body)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(body))
    return body


def _fake_shards(root: Path, *, overlap: bool) -> None:
    intervals = ((0, 20), (10 if overlap else 20, 30), (30, 40))
    for task_id, (alias, (started, ended)) in enumerate(zip(CASES, intervals)):
        shard = root / "shards" / f"{task_id:04d}-{alias}"
        scientific = _publish(
            shard / "scientific-result.json",
            {
                "schema": "test-scientific",
                "status": "PASS",
                "alias": alias,
                "checks": {
                    "GPU_objective_was_invoked": True,
                    "cpu_gpu_terminal_decision": True,
                    "resources_exact": True,
                },
                "route_counters": {"gpu": {"N_cpu_fallback": 0}},
            },
        )
        scientific_path = shard / "scientific-result.json"
        _publish(
            shard / "terminal.json",
            {
                "schema": "test-terminal",
                "status": "PASS",
                "alias": alias,
                "task_id": task_id,
                "started_unix_ns": started,
                "ended_unix_ns": ended,
                "speed_used_for_decision": False,
                "gpu": {
                    "gpu_uuid_sha256": f"gpu-{task_id}",
                    "CUDA_VISIBLE_DEVICES_count": 1,
                    "SLURM_JOB_GPUS_count": 1,
                },
                "scientific_result_sha256": hashlib.sha256(
                    scientific_path.read_bytes()
                ).hexdigest(),
            },
        )


def test_merger_requires_concurrent_distinct_gpu_execution(tmp_path: Path):
    passing = tmp_path / "passing"
    _fake_shards(passing, overlap=True)
    result = merge_shards(passing)
    assert result["status"] == STATUS_GO
    assert result["checks"]["speed_excluded_from_decision"]

    sequential = tmp_path / "sequential"
    _fake_shards(sequential, overlap=False)
    result = merge_shards(sequential)
    assert result["status"] == STATUS_NO_GO
    assert not result["checks"]["at_least_two_tasks_overlapped_on_distinct_gpus"]

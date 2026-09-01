from __future__ import annotations

import hashlib
from pathlib import Path

from aic_a100_pilot.beh2_successor_execution import (
    STATUS_GO,
    merge,
)
from aic_a100_pilot.common import digest
from v5_matched_work.atomic_artifacts import canonical_json_bytes


def _publish(path: Path, value: dict) -> dict:
    result = dict(value)
    result["record_digest"] = digest(result)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(result))
    return result


def _pair(
    shard: Path,
    *,
    alias: str,
    contract_digest: str,
    started: int,
    ended: int,
    gpu: str,
    scheduler: dict | None = None,
) -> None:
    scientific_path = shard / "scientific-result.json"
    scientific = _publish(
        scientific_path,
        {
            "schema": "test-scientific",
            "status": "PASS",
            "alias": alias,
            "checks": {
                "GPU_objective_was_invoked": True,
                "no_CPU_fallback": True,
                "no_full_cpu_optimization": True,
            },
            "route_counters": {"gpu": {"N_cpu_fallback": 0}},
        },
    )
    terminal = {
        "schema": "test-terminal",
        "status": "PASS",
        "alias": alias,
        "started_unix_ns": started,
        "ended_unix_ns": ended,
        "speed_used_for_decision": False,
        "gpu": {
            "gpu_uuid_sha256": gpu,
            "CUDA_VISIBLE_DEVICES_count": 1,
            "SLURM_JOB_GPUS_count": 1,
        },
        "contract_digest": contract_digest,
        "scientific_result_sha256": hashlib.sha256(
            scientific_path.read_bytes()
        ).hexdigest(),
    }
    if scheduler is not None:
        terminal["scheduler"] = scheduler
    _publish(shard / "terminal.json", terminal)


def test_successor_merge_accepts_only_complete_cross_contract_evidence(
    tmp_path: Path, monkeypatch
):
    from aic_a100_pilot import beh2_successor_execution as module

    successor_contract = module._load_contract()
    v4_contract = module.load_json(module.V4_CONTRACT)
    predecessor = tmp_path / "predecessor"
    successor = tmp_path / "successor"
    _pair(
        predecessor / "shards/0000-h2",
        alias="h2",
        contract_digest=v4_contract["contract_digest"],
        started=0,
        ended=20,
        gpu="gpu-a",
    )
    _pair(
        predecessor / "shards/0001-h6",
        alias="h6",
        contract_digest=v4_contract["contract_digest"],
        started=10,
        ended=30,
        gpu="gpu-b",
    )
    _pair(
        successor / "beh2",
        alias="beh2",
        contract_digest=successor_contract["contract_digest"],
        started=40,
        ended=50,
        gpu="gpu-a",
        scheduler=successor_contract["scheduler"],
    )
    result = merge(predecessor, successor)
    assert result["status"] == STATUS_GO
    assert all(result["checks"].values())
    assert result["scientific_boundary"]["performance_claim"] == "NOT_AUTHORIZED"

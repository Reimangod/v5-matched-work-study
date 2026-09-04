"""Bounded, frozen-order Phase-1 v2 execution with in-process case caching."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
from typing import Any

from .a5_successor_v2 import _read_digest_valid
from .v2_execution_integrity import sha256_file, validate_prefix_manifest
from .v2_runner_adapter import (
    S4_2_READINESS_PATH,
    S5_ATTESTATION_ROOT,
    S5_EXECUTION_ROOT,
    execute_bound_request,
    load_frozen_queue,
)


MINIMUM_FREE_BYTES = 40 * 1024**3


class V2BatchRunnerError(RuntimeError):
    pass


def current_terminal_count(queue: dict[str, Any]) -> int:
    root = S5_ATTESTATION_ROOT
    counts = []
    if root.is_dir():
        for path in root.glob("prefix-*-manifest-v1.json"):
            try:
                counts.append(int(path.name.split("-")[1]))
            except (IndexError, ValueError):
                raise V2BatchRunnerError(f"unregistered prefix artifact: {path.name}")
    if not counts:
        return 0
    count = max(counts)
    validate_prefix_manifest(queue=queue, expected_count=count, attestation_root=root)
    if sorted(counts) != list(range(1, count + 1)):
        raise V2BatchRunnerError("prefix manifests are not contiguous")
    return count


def run_batch(max_items: int) -> list[dict[str, Any]]:
    if max_items < 1 or max_items > 32:
        raise V2BatchRunnerError("max_items must be between 1 and 32")
    try:
        authority = _read_digest_valid(S4_2_READINESS_PATH, "readiness_digest")
    except (FileNotFoundError, KeyError, ValueError) as error:
        raise V2BatchRunnerError("valid S4.2 authority is absent") from error
    if (
        authority.get("decision") != "GO_PHASE1_V2_S4_2_EXECUTION"
        or authority.get("batch_runner_sha256") != sha256_file(Path(__file__).resolve())
    ):
        raise V2BatchRunnerError("S4.2 does not authorize this batch runner")
    queue = load_frozen_queue()
    start = current_terminal_count(queue)
    stop = min(start + max_items, len(queue["items"]))
    results = []
    for index in range(start, stop):
        if shutil.disk_usage(Path.cwd()).free < MINIMUM_FREE_BYTES:
            raise V2BatchRunnerError("free space fell below the frozen 40 GiB floor")
        row = queue["items"][index]
        request_id = str(row["RequestID"])
        item_root = S5_EXECUTION_ROOT / f"{index:04d}-{request_id.rsplit(':', 1)[-1]}"
        result = execute_bound_request(request_id, item_root)
        results.append(
            {
                "queue_index": index,
                "RequestID": request_id,
                "terminal_status": result["recovered_result"]["terminal"][
                    "terminal_status"
                ],
                "artifact_digest": result["artifact_digest"],
            }
        )
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-items", type=int, required=True)
    arguments = parser.parse_args()
    print(json.dumps(run_batch(arguments.max_items), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

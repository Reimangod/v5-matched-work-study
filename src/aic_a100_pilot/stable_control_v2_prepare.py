"""Outcome-free source preparation for stable-control v2."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import pickle
from typing import Any

from .common import (
    A100PilotError,
    ROOT,
    embedded_digest_valid,
    git,
    load_json,
    publish,
    sha256_file,
)
from .objective_parity import _contract_case, _prepare
from .stable_control_v2_contract import CONTRACT, SOURCE_PATHS


THREAD_KEYS = (
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
)


def prepare_bundle(
    alias: str, *, bundle_path: Path, manifest_path: Path
) -> dict[str, Any]:
    if bundle_path.exists() or manifest_path.exists():
        raise A100PilotError("refusing to overwrite stable-control v2 preparation")
    contract = load_json(CONTRACT)
    if not embedded_digest_valid(contract, "contract_digest"):
        raise A100PilotError("stable-control v2 contract digest is invalid")
    expected_head = os.environ.get("A100_EXPECTED_HEAD")
    if not expected_head or git("rev-parse", "HEAD") != expected_head:
        raise A100PilotError("stable-control v2 source preparation Git HEAD differs")
    observed_sources = {
        path.relative_to(ROOT).as_posix(): sha256_file(path)
        for path in SOURCE_PATHS
    }
    if observed_sources != contract["source_binding"]:
        raise A100PilotError("stable-control v2 source differs from frozen contract")
    expected_threads = int(
        contract["route_contract"]["source_reconstruction_thread_environment"][
            alias
        ]
    )
    environment = {key: os.environ.get(key) for key in THREAD_KEYS}
    if any(value != str(expected_threads) for value in environment.values()):
        raise A100PilotError("historical source thread environment differs")

    _, specification = _contract_case(alias)
    prepared = _prepare(alias, specification)
    _, _, rewrite = prepared
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    with bundle_path.open("xb") as stream:
        pickle.dump(prepared, stream, protocol=5)
        stream.flush()
        os.fsync(stream.fileno())
    manifest = {
        "schema": "aic-a100-pilot.stable-control-prepared-source.v2",
        "alias": alias,
        "contract_digest": contract["contract_digest"],
        "git_head": expected_head,
        "source_sha256": observed_sources,
        "source_thread_environment": environment,
        "bundle_relative_name": bundle_path.name,
        "bundle_sha256": sha256_file(bundle_path),
        "bundle_size_bytes": bundle_path.stat().st_size,
        "verified_candidate_ids": list(rewrite.verified_candidate_ids),
        "counter_scope": "SOURCE_PREPARATION_PROCESS_ONLY",
        "counter_scope_excludes_later_numerical_process": True,
        "candidate_outcomes": 0,
        "candidate_state_preparations": 0,
        "candidate_energy_evaluations": 0,
        "candidate_gradient_evaluations": 0,
        "optimizer_runs": 0,
        "FCI_evaluations": 0,
    }
    return publish(manifest_path, manifest, "manifest_digest")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--case", choices=("h2", "h4", "lih", "h6", "beh2"), required=True
    )
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    arguments = parser.parse_args()
    value = prepare_bundle(
        arguments.case,
        bundle_path=arguments.bundle,
        manifest_path=arguments.manifest,
    )
    print(json.dumps(value, sort_keys=True))


if __name__ == "__main__":
    main()

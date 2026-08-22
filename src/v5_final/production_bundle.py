"""Content-address the exact production code interpreted by an ExecutionRequest."""

from __future__ import annotations

import hashlib
from typing import Any

from v5_matched_work.atomic_artifacts import canonical_json_bytes

from .s0_successor import ROOT


PRODUCTION_MODULES = (
    "architecture_state.py",
    "candidate_catalog.py",
    "certifier.py",
    "executor.py",
    "failure_matrix.py",
    "frozen_queue.py",
    "identities.py",
    "kernel_bridge_worker.py",
    "pareto_selector.py",
    "predictor.py",
    "production_bundle.py",
    "release_audit.py",
    "scientific_values.py",
    "semantic_contract.py",
    "semantic_contract_v2.py",
    "semantic_events.py",
    "transaction.py",
    "work_ledger.py",
)


def build_production_bundle() -> dict[str, Any]:
    modules = []
    for name in PRODUCTION_MODULES:
        path = ROOT / "src" / "v5_final" / name
        if not path.is_file():
            raise RuntimeError(f"production module is missing: {name}")
        modules.append(
            {
                "path": f"src/v5_final/{name}",
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    payload: dict[str, Any] = {
        "schema": "v5-final.production-code-bundle.v1",
        "hash_algorithm": "sha256",
        "modules": modules,
    }
    payload["bundle_digest"] = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    return payload


def verify_production_bundle(value: dict[str, Any]) -> bool:
    return value == build_production_bundle()

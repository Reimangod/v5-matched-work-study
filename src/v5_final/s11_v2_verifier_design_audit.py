"""Freeze and audit the outcome-blind S11-v2 Verifier V2 design."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .historical_artifact_audit import (
    artifact_is_immutable_git_blob,
    manifest_file_matches_artifact_commit,
)
from .s0_successor import ROOT
from .verifier_v2 import ALL_COUNTER_FIELDS, VerifierV2Policy


OUTPUT_DIR = ROOT / "artifacts/v5-final/parent-native/s11-v2-verifier-remediation"
OUTPUT_PATH = OUTPUT_DIR / "verifier-v2-design-v1.json"
MANIFEST_PATH = OUTPUT_DIR / "MANIFEST.sha256"
CODE_PATHS = (
    ROOT / "src/v5_final/verifier_v2.py",
    ROOT / "src/v5_final/parent_native_verifier_v2.py",
)


class VerifierV2DesignAuditError(RuntimeError):
    pass


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def build_record() -> dict[str, Any]:
    policy = VerifierV2Policy().to_dict()
    source = "\n".join(path.read_text() for path in CODE_PATHS)
    checks = {
        "production_dense_scipy_expm_absent": "scipy.linalg.expm" not in source,
        "production_sparse_toarray_absent": ".toarray(" not in source,
        "sparse_expm_multiply_present": "expm_multiply" in source,
        "semantic_cache_present": "_semantic_cache" in source
        and "semantic-" in source,
        "generator_digest_cache_present": "generator-cache-v2" in source,
        "durable_numeric_checkpoint_present": "numeric-" in source,
        "top_k_frozen_before_numeric_loop": source.index("top-k-freeze-v2.json")
        < source.index("for rank, (_, candidate, _) in enumerate(selected)"),
        "optimizer_entrypoint_absent": "minimize_bfgs" not in source,
        "energy_kernel_entrypoint_absent": "compute_energy" not in source,
        "counter_schema_complete": set(ALL_COUNTER_FIELDS)
        == {
            "N_symbolic_checks",
            "N_sparse_expm_multiply",
            "N_state_probe_vectors",
            "N_dense_expm",
            "N_circuit_operator_builds",
            "N_generator_materializations",
            "matrix_dimension",
            "qubit_count",
            "candidate_generations",
            "unique_semantic_candidates",
            "unique_physical_states",
            "rewrite_verifications",
            "resource_recounts",
            "optimizer_iterations",
            "energy_evaluations",
            "CPU_time_seconds",
            "wall_time_seconds",
            "peak_RSS_raw",
        },
        "policy_selected_without_candidate_outcomes": policy[
            "candidate_outcomes_used_to_choose_policy"
        ]
        is False,
    }
    if not all(checks.values()):
        raise VerifierV2DesignAuditError(
            "Verifier V2 design failed: "
            + ", ".join(key for key, value in checks.items() if not value)
        )
    record = {
        "schema": "v5-final.s11-v2-verifier-design-freeze.v1",
        "status": "PASS_OUTCOME_FREE_VERIFIER_V2_DESIGN",
        "processing_order": [
            "structural-symbolic-validation",
            "semantic-candidate-deduplication",
            "proposed-StatePreparationID-physical-deduplication",
            "outcome-blind-OBS-resource-ranking",
            "digest-bound-frozen-top-K-numeric-verification",
            "optimizer-and-candidate-energy-only-after-separate-authorization",
        ],
        "policy": policy,
        "counter_schema": {
            "fields": list(ALL_COUNTER_FIELDS),
            "production_invariant": "N_dense_expm == 0",
            "timing_separation": (
                "CPU/wall/peak-RSS are operational sidecar fields; deterministic "
                "primitive counters remain in the byte-reproducible scientific core."
            ),
            "componentwise_cap_required": True,
            "wall_time_only_cap_forbidden": True,
        },
        "checkpoint_contract": {
            "unit": "one selected candidate",
            "session_binding": "source+candidate descriptors+policy digest",
            "semantic_certificate_cache": "durable by semantic ID",
            "generator_cache": "durable sparse CSR by generator digest",
            "resume_completed_numeric_candidate": "LOAD_AND_VERIFY_NO_RECOMPUTE",
        },
        "code_sha256": {
            str(path.relative_to(ROOT)): _sha(path) for path in CODE_PATHS
        },
        "checks": checks,
        "authorization": {
            "outcome_free_calibration": "AUTHORIZED",
            "molecular_candidate_energy": "NOT_AUTHORIZED",
            "optimizer": "NOT_AUTHORIZED",
            "FCI_reporting": "NOT_AUTHORIZED",
            "S11_v2_execution": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "scientific_boundary": {
            "established": (
                "The versioned verifier design is bounded, sparse, deduplicated, "
                "checkpointable, and outcome-free."
            ),
            "not_established": (
                "No molecular candidate performance, comparative advantage, or "
                "production S11-v2 result is established."
            ),
        },
    }
    record["design_freeze_digest"] = _digest(record)
    return record


def write_record() -> dict[str, Any]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    record = build_record()
    write_json_exclusive(OUTPUT_PATH, record)
    paths = (*CODE_PATHS, OUTPUT_PATH)
    lines = [f"{_sha(path)}  {path.relative_to(ROOT)}" for path in paths]
    if MANIFEST_PATH.exists():
        raise VerifierV2DesignAuditError("design manifest already exists")
    MANIFEST_PATH.write_text("\n".join(lines) + "\n")
    return record


def audit() -> dict[str, bool]:
    raw = OUTPUT_PATH.read_bytes()
    committed = json.loads(raw)
    body = dict(committed)
    observed_digest = body.pop("design_freeze_digest", None)
    checks = {
        "byte_reconstructible": raw == canonical_json_bytes(committed)
        and artifact_is_immutable_git_blob(OUTPUT_PATH),
        "design_digest_valid": observed_digest == _digest(body),
        "manifest_exact": manifest_file_matches_artifact_commit(
            OUTPUT_PATH, MANIFEST_PATH
        ),
        "all_design_checks_pass": all(committed.get("checks", {}).values()),
        "candidate_outcomes_blocked": all(
            value == "NOT_AUTHORIZED"
            for key, value in committed["authorization"].items()
            if key != "outcome_free_calibration"
        ),
    }
    if not all(checks.values()):
        raise VerifierV2DesignAuditError("committed design freeze audit failed")
    return checks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--audit", action="store_true")
    args = parser.parse_args()
    if args.write == args.audit:
        raise VerifierV2DesignAuditError("select exactly one operation")
    result = write_record() if args.write else audit()
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

"""S1 outcome-free audit of the actual parent-native typed adapter."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
from typing import Any

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .s0_successor import CEO_COMMIT, PARENT_COMMIT, ROOT


OUTPUT = ROOT / "artifacts/v5-final/parent-native/s1-typed-candidate-adapter-v1.json"
PARENT_PYTHON = ROOT / "provenance/dvg-obs-ceo/.venv/bin/python"
PRIMARY_SOURCES = (
    ROOT / "provenance/dvg-obs-ceo/src/dvg_obs_ceo/block_ir.py",
    ROOT / "provenance/dvg-obs-ceo/src/dvg_obs_ceo/composition.py",
    ROOT / "provenance/dvg-obs-ceo/src/dvg_obs_ceo/v5_s8_h4_width1.py",
    ROOT / "provenance/dvg-obs-ceo/src/dvg_obs_ceo/v5_sequential.py",
)
IMPLEMENTATION = (
    ROOT / "src/v5_final/parent_native_candidate_adapter.py",
    ROOT / "src/v5_final/parent_native_candidate_probe.py",
)


class S1ParentNativeAdapterError(RuntimeError):
    pass


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _probe() -> dict[str, Any]:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        (
            str(ROOT / "src"),
            str(ROOT / "provenance/dvg-obs-ceo/src"),
            str(ROOT / "provenance/dvg-obs-ceo/vendor/ceo-adapt-vqe"),
        )
    )
    completed = subprocess.run(
        [str(PARENT_PYTHON), "-m", "v5_final.parent_native_candidate_probe"],
        cwd=ROOT,
        env=environment,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return json.loads(completed.stdout)


def build() -> dict[str, Any]:
    probe = _probe()
    checks = {
        "actual_DVGBlock": probe["block_type"] == "DVGBlock",
        "actual_CompressionCandidate": probe["candidate_type"]
        == "CompressionCandidate"
        and probe["candidate_is_mapping"] is False,
        "candidate_fields_preserved": probe["candidate_id"].startswith(
            "candidate-v1:"
        )
        and probe["equivalence_class_id"].startswith("transform-v1:"),
        "actual_joint_constraint_plan": probe["constraint_semantic_id"].startswith(
            "constraint-semantic-v1:"
        )
        and probe["constraint_numerical_id"].startswith(
            "constraint-numerical-v1:"
        )
        and bool(probe["target_indices"]),
        "actual_OBS_warm_start": probe["warm_start_dimension"]
        == len(probe["target_indices"])
        == probe["inverse_hessian_dimension"],
        "three_identity_layers_separate": len(
            {
                probe["candidate_intent_id"],
                probe["proposed_physical_state_id"],
                probe["proposed_state_preparation_id"],
            }
        )
        == 3,
        "candidate_energy_zero": probe["candidate_energy_evaluations"] == 0,
    }
    if not all(checks.values()):
        raise S1ParentNativeAdapterError("actual typed adapter probe failed")
    artifact: dict[str, Any] = {
        "schema": "v5-final.s1-parent-native-adapter-audit.v1",
        "stage": "S1_PARENT_NATIVE_TYPED_CANDIDATE_ADAPTER",
        "status": "PASS_OUTCOME_FREE_ACTUAL_PARENT_TYPES",
        "decision": "GO_S2_REWRITE_MATRIX_RESOURCE_PARITY_ONLY",
        "pinned_commits": {"parent": PARENT_COMMIT, "CEO": CEO_COMMIT},
        "primary_source_manifest": [
            {"path": str(path.relative_to(ROOT)), "sha256": _sha(path)}
            for path in PRIMARY_SOURCES
        ],
        "implementation_manifest": [
            {"path": str(path.relative_to(ROOT)), "sha256": _sha(path)}
            for path in IMPLEMENTATION
        ],
        "probe": probe,
        "checks": checks,
        "authorization": {
            "S2_outcome_free_rewrite_matrix_resource_parity": "AUTHORIZED",
            "molecular_candidate_energy": "NOT_AUTHORIZED",
            "H2_H4_execution": "NOT_AUTHORIZED",
            "development_queue_execution": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "academic_boundary": (
            "Actual type, composition, warm-start, and identity evidence only. "
            "No optimizer, molecular candidate energy, or performance result exists."
        ),
    }
    artifact["audit_digest"] = _digest(artifact)
    return artifact


def verify(record: dict[str, Any]) -> dict[str, bool]:
    body = dict(record)
    observed = body.pop("audit_digest", None)
    return {
        "audit_digest_valid": observed == _digest(body),
        "primary_sources_unchanged": all(
            _sha(ROOT / item["path"]) == item["sha256"]
            for item in record["primary_source_manifest"]
        ),
        "implementation_unchanged": all(
            _sha(ROOT / item["path"]) == item["sha256"]
            for item in record["implementation_manifest"]
        ),
        "all_checks_passed": all(record["checks"].values()),
        "decision_scoped": record["decision"]
        == "GO_S2_REWRITE_MATRIX_RESOURCE_PARITY_ONLY",
        "candidate_energy_zero": record["probe"]["candidate_energy_evaluations"]
        == 0,
        "execution_blocked": record["authorization"]["H2_H4_execution"]
        == "NOT_AUTHORIZED",
    }


def audit() -> dict[str, bool]:
    record = json.loads(OUTPUT.read_text())
    checks = verify(record)
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S1ParentNativeAdapterError("S1 audit failed: " + ", ".join(failures))
    return checks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.output is None:
        print(json.dumps(audit(), sort_keys=True))
    else:
        write_json_exclusive(args.output, build())
        print(args.output)


if __name__ == "__main__":
    main()

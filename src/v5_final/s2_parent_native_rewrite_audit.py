"""S2 outcome-free audit of parent-native rewrites and resource parity."""

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


OUTPUT = ROOT / "artifacts/v5-final/parent-native/s2-rewrite-matrix-resource-parity-v1.json"
PARENT_PYTHON = ROOT / "provenance/dvg-obs-ceo/.venv/bin/python"
PRIMARY_SOURCES = (
    ROOT / "provenance/dvg-obs-ceo/src/dvg_obs_ceo/block_ir.py",
    ROOT / "provenance/dvg-obs-ceo/src/dvg_obs_ceo/composition.py",
    ROOT / "provenance/dvg-obs-ceo/src/dvg_obs_ceo/resources.py",
)
IMPLEMENTATION = (
    ROOT / "src/v5_final/parent_native_rewrite.py",
    ROOT / "src/v5_final/parent_native_rewrite_probe.py",
)


class S2ParentNativeRewriteError(RuntimeError):
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
        [str(PARENT_PYTHON), "-m", "v5_final.parent_native_rewrite_probe"],
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
    rewrite = probe["rewrite"]
    h2 = probe["known_h2_parent_parity"]
    checks = {
        "actual_source_and_target_matrices_verified": (
            rewrite["actual_matrix_counts"]["source"] > 0
            and rewrite["actual_matrix_counts"]["target"] > 0
        ),
        "actual_target_native_circuit_verified": (
            rewrite["target_native_circuits_verified"] > 0
        ),
        "rewrite_precedes_optimizer_arguments": (
            probe["rewrite_applied_before_optimizer_arguments"] is True
            and probe["optimizer_called"] is False
            and rewrite["optimizer_arguments"]["indices"]
            == rewrite["target_indices"]
            and rewrite["target_indices"] != rewrite["source_indices"]
        ),
        "parent_resource_recounts_agree": (
            rewrite["parent_physical_structural_snapshot_equal"] is True
        ),
        "physical_circuit_and_structure_changed": (
            rewrite["physical_circuit_changed"] is True
        ),
        "circuit_metric_reduced": rewrite["circuit_metric_reduced"] is True,
        "no_parameter_only_reduction_claim": (
            rewrite["parameter_only_reduction_claimed"] is False
        ),
        "known_H2_parent_parity_reproduced_twice": (
            h2["exact_match"] is True
            and h2["first"] == h2["second"]
            and h2["first"]["cnot_count"] == 9
            and h2["first"]["cnot_depth"] == 7
        ),
        "candidate_energy_zero": probe["candidate_energy_evaluations"] == 0,
    }
    if not all(checks.values()):
        raise S2ParentNativeRewriteError(
            "parent-native rewrite or resource-parity probe failed"
        )
    artifact: dict[str, Any] = {
        "schema": "v5-final.s2-parent-native-rewrite-audit.v1",
        "stage": "S2_REWRITE_MATRIX_AND_RESOURCE_PARITY",
        "status": "PASS_OUTCOME_FREE_ACTUAL_PARENT_REWRITE",
        "decision": "GO_S3_QUEUE_BOUND_FACTORY_ONLY",
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
            "S3_outcome_free_queue_bound_factory": "AUTHORIZED",
            "optimizer_execution": "NOT_AUTHORIZED",
            "molecular_candidate_energy": "NOT_AUTHORIZED",
            "H2_H4_execution": "NOT_AUTHORIZED",
            "development_queue_execution": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "academic_boundary": (
            "Actual algebraic and native-circuit semantics plus parent resource "
            "counter parity only. No molecular optimizer, candidate energy, or "
            "performance result exists."
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
        == "GO_S3_QUEUE_BOUND_FACTORY_ONLY",
        "candidate_energy_zero": record["probe"]["candidate_energy_evaluations"]
        == 0,
        "optimizer_blocked": record["authorization"]["optimizer_execution"]
        == "NOT_AUTHORIZED",
        "molecular_execution_blocked": record["authorization"]["H2_H4_execution"]
        == "NOT_AUTHORIZED",
    }


def audit() -> dict[str, bool]:
    record = json.loads(OUTPUT.read_text())
    checks = verify(record)
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S2ParentNativeRewriteError("S2 audit failed: " + ", ".join(failures))
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

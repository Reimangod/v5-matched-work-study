"""MB1 code-level registry of the method-native parent semantics."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .mb0_baseline import audit as audit_mb0
from .s0_successor import ROOT


OUTPUT = ROOT / "artifacts/v5-final/method-native/mb1-parent-semantics-v1.json"

EVIDENCE_HASHES = {
    "provenance/dvg-obs-ceo/src/dvg_obs_ceo/v4_1_multisystem.py": "243e8dfb666e334b8f2e1b9acd28d8e72094c5c8a335251a4e7301f02b66254e",
    "provenance/dvg-obs-ceo/src/dvg_obs_ceo/v4_1_exact_multisystem.py": "824483540562d6c33f10569e69e5d5b2aa604476cd84500ede4106157a3bc9bc",
    "provenance/dvg-obs-ceo/src/dvg_obs_ceo/v5_sequential.py": "b50388f844727d127cecb4d5fe0dd90ff25b23d0519098d7aab4379f679d6996",
    "provenance/dvg-obs-ceo/src/dvg_obs_ceo/v5_s8_h4_width1.py": "a87f437cb9c3d2e377721540c0ef0d4a7cf7a70be79cef90422af393dd98203c",
    "provenance/dvg-obs-ceo/src/dvg_obs_ceo/calibration.py": "734e3b53add3861b4c6303687473ee64c0ee2deff138419b5a527c6eafc99840",
    "provenance/dvg-obs-ceo/src/dvg_obs_ceo/composition.py": "35c2627638e72ed32c16d5c9aa1d5b2438677ac4eb5643a47ab519207094319c",
    "provenance/dvg-obs-ceo/src/dvg_obs_ceo/block_ir.py": "e245018b9915b371875ef3e717fd45099cd6999659076fa110a0688b0f682391",
    "provenance/dvg-obs-ceo/src/dvg_obs_ceo/resources.py": "4220cc44fde4a264f793e1190ef61e5ef8c93497d3614d13cd96763f9db98efd",
    "provenance/dvg-obs-ceo/src/dvg_obs_ceo/v5_nested_transaction.py": "5f3acbaf8874fdbb4f8c5d009301a0862bfa470f5b9b701db7ddfcb4f0a149e3",
    "provenance/dvg-obs-ceo/src/dvg_obs_ceo/transaction.py": "6e6aabbdef895cb024ec820e8ffc49ca606e1159031a9c1e56f1e7b690aa6d68",
    "provenance/dvg-obs-ceo/src/dvg_obs_ceo/v6_rank_adaptive/ns10_h6_optimizer_ablation.py": "5c8b56fdb130adbb4f1558004929ffd158814df8dc54d5d3834ee624fee544ed",
    "docs/S4_COMPARATORS.md": "3a24187cb0e83438bb5ffd5363546ff8c330e6f322ca526e36ba236f21c4e4fd",
    "artifacts/v5-final/s5/development-protocol-freeze-v3.json": "0143e8eebe6f68aff2fbba23b917f2d34d042c205f32489b38f3a4a315677f4a",
}

ANCHORS = {
    "v4_joint_screen": (
        "provenance/dvg-obs-ceo/src/dvg_obs_ceo/v4_1_multisystem.py",
        "def screen_case(case_id: str",
    ),
    "v4_joint_execution": (
        "provenance/dvg-obs-ceo/src/dvg_obs_ceo/v4_1_exact_multisystem.py",
        "def execute_case(case_id: str",
    ),
    "v5_sequential": (
        "provenance/dvg-obs-ceo/src/dvg_obs_ceo/v5_sequential.py",
        "post_catalog = catalog_builder(runtime)",
    ),
    "v5_native_adapter": (
        "provenance/dvg-obs-ceo/src/dvg_obs_ceo/v5_s8_h4_width1.py",
        "MolecularWidthOneAdapter = H4WidthOneAdapter",
    ),
    "warm_start": (
        "provenance/dvg-obs-ceo/src/dvg_obs_ceo/calibration.py",
        "def obs_warm_start(",
    ),
    "magnitude_definition": (
        "provenance/dvg-obs-ceo/src/dvg_obs_ceo/calibration.py",
        "magnitude = float(residual @ residual)",
    ),
    "canonical_composition": (
        "provenance/dvg-obs-ceo/src/dvg_obs_ceo/composition.py",
        "def compose_registered_candidates(",
    ),
    "physical_recount": (
        "provenance/dvg-obs-ceo/src/dvg_obs_ceo/resources.py",
        "def evaluate_full_circuit_resources(",
    ),
    "rollback": (
        "provenance/dvg-obs-ceo/src/dvg_obs_ceo/v5_nested_transaction.py",
        "self.runtime.restore(self.parent_snapshot)",
    ),
    "same_structure_control": (
        "provenance/dvg-obs-ceo/src/dvg_obs_ceo/v6_rank_adaptive/ns10_h6_optimizer_ablation.py",
        "def evaluate_control(item: Mapping[str, Any])",
    ),
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _queue_state() -> dict[str, Any]:
    queue = json.loads(
        (ROOT / "artifacts/v5-final/s5/development-queue-v3.json").read_text()
    )
    ledger = json.loads(
        (ROOT / "artifacts/v5-final/s5/development-ledger-root-v3.json").read_text()
    )
    return {
        "expected_count": queue["expected_queue_count"],
        "not_started_count": sum(
            item["terminal_status"] == "NOT_STARTED" for item in queue["items"]
        ),
        "completed_count": len(ledger["completed_queue_item_ids"]),
        "segment_count": len(ledger["segments"]),
        "candidate_energy_evaluations": ledger[
            "development_candidate_energy_evaluations"
        ],
        "complete": ledger["completeness"]["complete"],
    }


def _methods() -> list[dict[str, Any]]:
    return [
        {
            "method_id": "immutable-ceo-star-source",
            "classification": "PARENT_PRIMITIVE_COMPOSITION",
            "entrypoints": [
                "dvg_obs_ceo.v4_1_exact_multisystem:execute_case[source reconstruction]",
                "dvg_obs_ceo.resources:evaluate_full_circuit_resources",
            ],
            "native_semantics": "load and independently reconstruct the frozen source; invoke no compression or optimizer",
            "implementation_requirement": "a dedicated wrapper must reject any candidate, rewrite, or optimization call",
        },
        {
            "method_id": "same-structure-reoptimization",
            "classification": "PARENT_NATIVE_CONTROL",
            "entrypoints": [
                "dvg_obs_ceo.v6_rank_adaptive.ns10_h6_optimizer_ablation:evaluate_control"
            ],
            "native_semantics": "optimize source coefficients while retaining the exact source index sequence",
            "implementation_requirement": "assert identical canonical structure before and after optimization, then independently recount",
        },
        {
            "method_id": "structural-magnitude-pruning",
            "classification": "PARENT_PRIMITIVE_COMPOSITION",
            "entrypoints": [
                "dvg_obs_ceo.calibration:predictor_values[magnitude]",
                "dvg_obs_ceo.resources:evaluate_full_circuit_resources",
            ],
            "native_semantics": "rank single-coordinate structural deletions by squared constraint residual, physically delete generators, reoptimize, and recount the full circuit",
            "implementation_requirement": "freeze tie-breaking and stopping before outcomes; no named parent executor or paper-defined pruning protocol exists",
        },
        {
            "method_id": "v4.1-one-shot-joint-compression",
            "classification": "NATIVE_PARENT_ENTRYPOINT",
            "entrypoints": [
                "dvg_obs_ceo.v4_1_multisystem:screen_case",
                "dvg_obs_ceo.v4_1_exact_multisystem:execute_case",
            ],
            "native_semantics": "compose a compatible set of atomic registered rewrites against one immutable source, freeze sentinels, and execute each independently from that same source",
            "implementation_requirement": "bind the shared recorder inside screening, optimization, recount, and transaction kernels without changing selection",
        },
        {
            "method_id": "v5-sequential-with-rebuilding",
            "classification": "NATIVE_PARENT_ENTRYPOINT",
            "entrypoints": [
                "dvg_obs_ceo.v5_sequential:run_width_one",
                "dvg_obs_ceo.v5_s8_h4_width1:MolecularWidthOneAdapter",
            ],
            "native_semantics": "after an accepted child, rebuild blocks, candidates, warm-start coordinates, curvature coordinates, and resources from the committed runtime",
            "implementation_requirement": "preserve parent catalog_builder(runtime) before every round and after acceptance",
        },
        {
            "method_id": "v5-sequential-without-rebuilding",
            "classification": "NEW_CAUSAL_ABLATION_REQUIRED",
            "entrypoints": [
                "dvg_obs_ceo.v5_sequential:run_width_one[kernel basis]",
                "dvg_obs_ceo.v5_s8_h4_width1:MolecularWidthOneAdapter[kernel basis]",
            ],
            "native_semantics": "use the same V5 candidate and transaction kernels but retain the original source catalog after accepted children",
            "implementation_requirement": "implement a separately named policy; prove by trace that catalog reuse is the only intended difference from full V5",
        },
    ]


def build() -> dict[str, Any]:
    files = [
        {"path": path, "sha256": _sha(ROOT / path)}
        for path in sorted(EVIDENCE_HASHES)
    ]
    result: dict[str, Any] = {
        "schema": "v5-final.method-native.mb1-parent-semantics.v1",
        "stage": "MB1",
        "status": "COMPLETE_CODE_RESEARCH_ONLY",
        "parent_repository_commit": "4783b9ff9f9b6f2061a1ef8c02613f4c6cef38db",
        "ceo_adapt_vqe_commit": "a3f89d03e6a03c89767d3cf8ee7657a57653dda0",
        "evidence_files": files,
        "methods": _methods(),
        "shared_parent_semantics": {
            "canonical_structure": "recover_dvg_blocks + enumerate_candidates + compose_registered_candidates",
            "warm_start": "obs_warm_start maps source coefficients, gradient, and recycled inverse Hessian into target-native coordinates",
            "curvature_inheritance": "accepted V5 runtime stores the selected final inverse Hessian; rollback restores the entire parent snapshot",
            "resource_counter": "paper_era_backend plus full composed circuit recount; no barrier-free compiler",
            "resource_axes": [
                "cnot_count",
                "cnot_depth",
                "total_depth",
                "parameter_count",
                "logical_block_count",
            ],
            "fci_firewall": "V4.1 execute_case explicitly sets chemical_margin=None and excludes exact/FCI energy from runtime",
        },
        "negative_findings": {
            "standalone_parent_no_rebuild_executor": False,
            "standalone_parent_magnitude_pruning_executor": False,
            "paper_defines_post_ansatz_magnitude_pruning": False,
            "proxy_substitution_authorized": False,
        },
        "preimplementation_freeze_requirements": [
            "magnitude-pruning deterministic tie break and stopping rule",
            "no-rebuild catalog identity and stale-candidate validity checks",
            "shared recorder placement must not alter method control flow",
        ],
        "development_queue": _queue_state(),
        "test_summary": {
            "targeted": "2 passed in MB0+MB1 audit",
            "full": "87 passed, 3 xfailed",
        },
        "authorization": {
            "MB2_recording_interface": "AUTHORIZED",
            "candidate_molecular_energy": "NOT_AUTHORIZED",
            "H2_H4_calibration": "NOT_AUTHORIZED",
            "development_queue_execution": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "academic_boundary": "This registry distinguishes existing parent algorithms from controls and a newly required causal ablation; it contains no outcome evidence.",
        "systems_boundary": "Every source anchor and hash is fail-closed; later wrappers must retain exact executor identity.",
        "decision": "GO_MB2_RECORDING_INTERFACE_ONLY",
    }
    result["research_digest"] = _digest(result)
    return result


def audit() -> dict[str, bool]:
    committed = json.loads(OUTPUT.read_text())
    payload = dict(committed)
    observed_digest = payload.pop("research_digest")
    queue = committed["development_queue"]
    methods = {item["method_id"]: item for item in committed["methods"]}
    checks = {
        "mb0_still_passes": all(audit_mb0().values()),
        "research_digest": observed_digest == _digest(payload),
        "evidence_hashes": all(
            _sha(ROOT / path) == expected for path, expected in EVIDENCE_HASHES.items()
        ),
        "source_anchors": all(
            anchor in (ROOT / path).read_text(encoding="utf-8")
            for path, anchor in ANCHORS.values()
        ),
        "six_methods": len(methods) == 6,
        "native_v4_v5_bound": methods["v4.1-one-shot-joint-compression"]["classification"]
        == "NATIVE_PARENT_ENTRYPOINT"
        and methods["v5-sequential-with-rebuilding"]["classification"]
        == "NATIVE_PARENT_ENTRYPOINT",
        "ablation_not_misrepresented": methods[
            "v5-sequential-without-rebuilding"
        ]["classification"]
        == "NEW_CAUSAL_ABLATION_REQUIRED",
        "queue_untouched": queue
        == {
            "expected_count": 90,
            "not_started_count": 90,
            "completed_count": 0,
            "segment_count": 0,
            "candidate_energy_evaluations": 0,
            "complete": False,
        },
        "experiments_closed": all(
            value == "NOT_AUTHORIZED"
            for key, value in committed["authorization"].items()
            if key != "MB2_recording_interface"
        ),
    }
    if not all(checks.values()):
        raise RuntimeError("MB1 parent-semantics audit failed")
    return checks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("build", "verify"))
    args = parser.parse_args()
    if args.action == "build":
        write_json_exclusive(OUTPUT, build())
    else:
        audit()
    print(json.dumps({"action": args.action, "passed": True}, sort_keys=True))


if __name__ == "__main__":
    main()

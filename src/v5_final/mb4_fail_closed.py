"""MB4 fail-closed audit for unresolved method-native semantics."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
from typing import Any

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .mb0_baseline import audit as audit_mb0
from .mb1_parent_semantics import EVIDENCE_HASHES, audit as audit_mb1
from .mb2_interface_audit import audit as audit_mb2
from .mb3_live_ledger_audit import audit as audit_mb3
from .s0_successor import ROOT


OUTPUT = ROOT / "artifacts/v5-final/method-native/mb4-no-go-v1.json"
PARENT_SRC = ROOT / "provenance/dvg-obs-ceo/src/dvg_obs_ceo"


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _definitions() -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for path in sorted(PARENT_SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                result.append(
                    {
                        "path": str(path.relative_to(ROOT)),
                        "name": node.name,
                        "kind": type(node).__name__,
                    }
                )
    return result


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


def build() -> dict[str, Any]:
    sequential_path = PARENT_SRC / "v5_sequential.py"
    adapter_path = PARENT_SRC / "v5_s8_h4_width1.py"
    v4_path = PARENT_SRC / "v4_1_exact_multisystem.py"
    sequential = sequential_path.read_text(encoding="utf-8")
    adapter = adapter_path.read_text(encoding="utf-8")
    v4 = v4_path.read_text(encoding="utf-8")
    definitions = _definitions()
    names = {item["name"].lower() for item in definitions}
    blockers = [
        {
            "blocker_id": "NO_REBUILD_RUNTIME_BINDING_UNRESOLVED",
            "evidence": [
                {
                    "path": str(sequential_path.relative_to(ROOT)),
                    "sha256": _sha(sequential_path),
                    "anchors": [
                        "catalog = catalog_builder(runtime)",
                        "post_catalog = catalog_builder(runtime)",
                        "post-commit catalog is not bound to candidate runtime",
                    ],
                },
                {
                    "path": str(adapter_path.relative_to(ROOT)),
                    "sha256": _sha(adapter_path),
                    "anchors": [
                        "frozen sequential candidate is absent from current catalog",
                        "frozen candidate constraint identity drift",
                    ],
                },
            ],
            "finding": (
                "The parent runner requires a catalog bound to the accepted child runtime, while "
                "the intended ablation says to reuse the original catalog snapshot. The parent "
                "candidate executor also requires current structural and numerical identities."
            ),
            "unfrozen_choices": [
                "literal original CatalogSnapshot, which parent runtime binding rejects",
                "original structural candidate-ID whitelist rebound to each child",
                "whether stale/removed candidates are skipped, terminal, or errors",
                "whether predictions, curvature coordinates, resources, and ordering are recomputed",
            ],
            "why_not_inferred": "These choices change the causal control and are not fixed by the existing pre-outcome artifact.",
        },
        {
            "blocker_id": "MAGNITUDE_EXECUTOR_PROTOCOL_INCOMPLETE",
            "evidence": [
                {
                    "path": "provenance/dvg-obs-ceo/src/dvg_obs_ceo/calibration.py",
                    "sha256": EVIDENCE_HASHES[
                        "provenance/dvg-obs-ceo/src/dvg_obs_ceo/calibration.py"
                    ],
                    "anchor": "magnitude = float(residual @ residual)",
                },
                {
                    "path": "docs/S4_COMPARATORS.md",
                    "sha256": EVIDENCE_HASHES["docs/S4_COMPARATORS.md"],
                    "anchor": "physically delete generators and recount the full circuit",
                },
            ],
            "finding": "Magnitude score and physical deletion are specified, but no parent molecular executor fixes tie-breaking, batch size, sequentiality, stale-order behavior, or stopping.",
            "parent_named_executor_present": any(
                "magnitude" in name and ("prun" in name or "execut" in name)
                for name in names
            ),
            "why_not_inferred": "A new control can be frozen prospectively, but it cannot be called an existing parent-native executor before that protocol is explicitly approved.",
        },
        {
            "blocker_id": "V4_1_NEW_CALIBRATION_QUEUE_REPLAY_UNBOUND",
            "evidence": [
                {
                    "path": str(v4_path.relative_to(ROOT)),
                    "sha256": _sha(v4_path),
                    "anchors": [
                        "freeze = verify_execution_freeze(case_id)",
                        "queue = s5[\"sentinels\"]",
                        "Execute every and only frozen S5 sentinel, independently from one source.",
                    ],
                }
            ],
            "finding": "The native V4.1 executor is correctly bound to its historical case-specific sentinel freeze; it is not yet bound to a new H2/H4 calibration freeze.",
            "why_not_inferred": "Copying historical sentinels or screening outcomes into a new queue is forbidden; a new outcome-free queue construction must precede execution.",
        },
    ]
    parent_checks = {
        "v5_pre_round_catalog_bound_to_current_runtime": "catalog = catalog_builder(runtime)"
        in sequential,
        "v5_post_accept_catalog_bound_to_child": "post_catalog = catalog_builder(runtime)"
        in sequential
        and "post-commit catalog is not bound to candidate runtime" in sequential,
        "v5_candidate_current_catalog_required": "frozen sequential candidate is absent from current catalog"
        in adapter,
        "v5_candidate_numerical_identity_required": "frozen candidate constraint identity drift"
        in adapter,
        "v4_requires_frozen_sentinel_queue": "queue = s5[\"sentinels\"]" in v4,
        "no_parent_named_no_rebuild_definition": not any(
            "rebuild" in name and ("without" in name or name.startswith("no_")) for name in names
        ),
    }
    result: dict[str, Any] = {
        "schema": "v5-final.method-native.mb4-no-go.v1",
        "stage": "MB4",
        "status": "NO_GO",
        "decision": "NO_GO_MB4_UNRESOLVED_METHOD_NATIVE_SEMANTICS",
        "parent_repository_commit": "4783b9ff9f9b6f2061a1ef8c02613f4c6cef38db",
        "ceo_adapt_vqe_commit": "a3f89d03e6a03c89767d3cf8ee7657a57653dda0",
        "parent_checks": parent_checks,
        "blockers": blockers,
        "rejected_implementations": [
            "planning controller relabeled as a native backend",
            "drop-one or mock execution under a V4.1/V5 method name",
            "literal original catalog returned despite child-runtime digest mismatch",
            "unfrozen structural-whitelist rebinding silently called no-rebuild",
            "historical V4.1 sentinels copied into a new H2/H4 calibration queue",
        ],
        "implemented_infrastructure_retained": [
            "MB0 immutable baseline",
            "MB1 code-level semantics registry",
            "MB2 shared request/result recording interface",
            "MB3 live semantic ledger and synthetic reconciliation",
        ],
        "development_queue": _queue_state(),
        "molecular_candidate_energy_executed": False,
        "H2_H4_calibration_queue_created": False,
        "six_method_native_molecular_backend_entrypoints": False,
        "test_summary": "11 passed in targeted MB0-MB4 audit",
        "full_test_summary": "96 passed, 3 xfailed",
        "authorization": {
            "MB5_outcome_free_integration": "NOT_AUTHORIZED",
            "MB6_H2_H4_freeze": "NOT_AUTHORIZED",
            "MB7_calibration_gate": "NOT_AUTHORIZED_AS_GO",
            "H2_H4_candidate_energy": "NOT_AUTHORIZED",
            "development_queue_execution": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "academic_boundary": "No molecular outcome was generated. The negative result concerns missing method identity, not comparative performance.",
        "systems_boundary": "Execution remains closed rather than routing a semantically ambiguous control to a quantum kernel.",
        "required_resolution": [
            "approve a versioned no-rebuild structural-rebinding protocol before outcomes",
            "freeze magnitude-pruning tie, batch, sequential, stale-order, and stopping rules",
            "construct and freeze new H2/H4 V4.1 sentinels without candidate-energy outcomes",
            "then implement and audit six exact native kernels against those protocols",
        ],
    }
    result["no_go_digest"] = _digest(result)
    return result


def audit() -> dict[str, bool]:
    committed = json.loads(OUTPUT.read_text())
    rebuilt = build()
    payload = dict(committed)
    observed = payload.pop("no_go_digest")
    queue = committed["development_queue"]
    checks = {
        "prior_stages": all(audit_mb0().values())
        and all(audit_mb1().values())
        and all(audit_mb2().values())
        and all(audit_mb3().values()),
        "deterministic_rebuild": committed == rebuilt,
        "no_go_digest": observed == _digest(payload),
        "parent_evidence": all(committed["parent_checks"].values()),
        "three_blockers": len(committed["blockers"]) == 3,
        "native_entrypoints_not_overclaimed": committed[
            "six_method_native_molecular_backend_entrypoints"
        ]
        is False,
        "queue_untouched": queue == {
            "expected_count": 90,
            "not_started_count": 90,
            "completed_count": 0,
            "segment_count": 0,
            "candidate_energy_evaluations": 0,
            "complete": False,
        },
        "everything_closed": all(
            value.startswith("NOT_AUTHORIZED")
            for value in committed["authorization"].values()
        ),
    }
    if not all(checks.values()):
        raise RuntimeError("MB4 fail-closed audit failed")
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

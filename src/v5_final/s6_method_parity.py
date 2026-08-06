"""Audit six S5 method controllers without authorizing molecular execution."""

from __future__ import annotations

import argparse
import hashlib
import json
from typing import Any

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .method_executors import (
    CandidateExecutionNotAuthorized,
    causal_ablation_parity,
    controller_registry,
)
from .s0_successor import ROOT
from .s5_freeze import FREEZE_OUTPUT, QUEUE_OUTPUT, SOURCE_OUTPUT, audit_committed


OUTPUT = ROOT / "artifacts/v5-final/s6/method-controller-parity-v1.json"


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def build() -> dict[str, Any]:
    if not all(audit_committed().values()):
        raise RuntimeError("S6 requires the exact S5-v3 freeze")
    freeze = json.loads(FREEZE_OUTPUT.read_text())
    queue = json.loads(QUEUE_OUTPUT.read_text())
    sources = json.loads(SOURCE_OUTPUT.read_text())
    policy = freeze["policy"]
    source = next(value for value in sources["sources"] if value["case_id"] == "h4-1.5-known-development")
    registry = controller_registry()
    plans = {}
    fail_closed = {}
    for method_id, controller in registry.items():
        item = next(
            value
            for value in queue["items"]
            if value["case_id"] == source["case_id"]
            and value["work_envelope"] == "LOW"
            and value["method_id"] == method_id
        )
        plan = controller.build_plan(
            queue_item=item,
            queue_digest=queue["queue_digest"],
            source=source,
            policy=policy,
        )
        plans[method_id] = plan
        try:
            controller.execute_candidate(plan)
        except CandidateExecutionNotAuthorized:
            fail_closed[method_id] = True
        else:
            fail_closed[method_id] = False
    no_rebuild = plans["v5-sequential-without-rebuilding"]
    rebuild = plans["v5-sequential-with-rebuilding"]
    causal_parity = causal_ablation_parity(no_rebuild, rebuild)
    accepted_children = ("a" * 64, "b" * 64)
    traces = {
        "without_rebuilding": registry[
            "v5-sequential-without-rebuilding"
        ].catalog_parent_trace("0" * 64, accepted_children),
        "with_rebuilding": registry[
            "v5-sequential-with-rebuilding"
        ].catalog_parent_trace("0" * 64, accepted_children),
    }
    plan_documents = {
        method_id: plan.payload() | {"plan_id": plan.plan_id}
        for method_id, plan in plans.items()
    }
    common = {
        "source_checkpoint_sha256": {
            value["source_checkpoint_sha256"] for value in plan_documents.values()
        },
        "problem_id": {value["problem_id"] for value in plan_documents.values()},
        "work_cap_digest": {
            _digest(value["semantic_work_cap"]) for value in plan_documents.values()
        },
        "optimizer_digest": {
            _digest(value["optimizer"]) for value in plan_documents.values()
        },
        "acceptance_digest": {
            _digest(value["acceptance"]) for value in plan_documents.values()
        },
        "queue_digest": {value["queue_digest"] for value in plan_documents.values()},
    }
    symmetry = {name: len(values) == 1 for name, values in common.items()}
    result: dict[str, Any] = {
        "schema": "v5-final.s6-method-controller-parity.v1",
        "stage": "S6",
        "status": "IMPLEMENTATION_PARITY_COMPLETE_NO_EXECUTION",
        "s5_freeze_digest": freeze["freeze_digest"],
        "queue_digest": queue["queue_digest"],
        "controller_module": {
            "path": "src/v5_final/method_executors.py",
            "sha256": hashlib.sha256(
                (ROOT / "src/v5_final/method_executors.py").read_bytes()
            ).hexdigest(),
        },
        "method_plans": plan_documents,
        "six_concrete_controllers": len(registry) == 6
        and set(registry) == set(policy["method_order"]),
        "common_interface_symmetry": symmetry,
        "causal_ablation_parity": causal_parity,
        "catalog_parent_trace_probe": {
            "accepted_children": list(accepted_children),
            **{key: list(value) for key, value in traces.items()},
            "no_rebuild_reuses_source": traces["without_rebuilding"]
            == ("0" * 64, "0" * 64, "0" * 64),
            "full_rebuild_tracks_commits": traces["with_rebuilding"]
            == ("0" * 64, *accepted_children),
        },
        "execution_entrypoints_fail_closed": fail_closed,
        "outcome_blind": {
            "candidate_energy_field_absent": all(
                "candidate_energy" not in json.dumps(value, sort_keys=True)
                for value in plan_documents.values()
            ),
            "fci_field_absent": all(
                "fci" not in json.dumps(value, sort_keys=True).lower()
                for value in plan_documents.values()
            ),
        },
        "authorization": {
            "method_controller_implementation": "COMPLETE",
            "production_backend_integration": "NEXT",
            "candidate_molecular_execution": "NOT_AUTHORIZED",
            "performance_experiment": "NOT_AUTHORIZED",
            "S7_or_later": "NOT_AUTHORIZED",
        },
        "academic_boundary": (
            "This proves common planning semantics and isolates the rebuild switch. It does "
            "not prove that six molecular backends execute correctly or that any method performs better."
        ),
        "systems_boundary": (
            "Every controller rejects candidate execution until a queue-bound production "
            "backend integration gate is published."
        ),
        "decision": "GO_S6_PRODUCTION_BACKEND_INTEGRATION_ONLY",
    }
    result["parity_digest"] = _digest(result)
    return result


def audit() -> dict[str, bool]:
    committed = json.loads(OUTPUT.read_text())
    rebuilt = build()
    payload = dict(committed)
    observed_digest = payload.pop("parity_digest")
    checks = {
        "deterministic_rebuild": committed == rebuilt,
        "parity_digest": observed_digest == _digest(payload),
        "six_controllers": committed["six_concrete_controllers"],
        "interface_symmetry": all(committed["common_interface_symmetry"].values()),
        "causal_ablation": all(committed["causal_ablation_parity"].values()),
        "trace_semantics": committed["catalog_parent_trace_probe"][
            "no_rebuild_reuses_source"
        ]
        and committed["catalog_parent_trace_probe"]["full_rebuild_tracks_commits"],
        "execution_fail_closed": all(
            committed["execution_entrypoints_fail_closed"].values()
        ),
        "outcome_blind": all(committed["outcome_blind"].values()),
        "performance_closed": committed["authorization"]["performance_experiment"]
        == "NOT_AUTHORIZED",
    }
    if not all(checks.values()):
        raise RuntimeError("S6 method parity audit failed")
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

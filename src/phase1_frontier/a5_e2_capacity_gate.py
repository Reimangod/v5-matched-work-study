"""Final E2 certification and fail-closed E3 capacity gate for Phase 1."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import struct
from typing import Any, Mapping

from v5_matched_work.atomic_artifacts import canonical_json_bytes

from .a1_vertical_slice import A1_AUDIT, _h4_context, _run_target, prepare_targets
from .a2_source_lock import CASES, ROOT, source_path
from .a3_grammar import (
    GRAMMAR_VERSION,
    candidate_plan_id,
    case_path,
    optimization_initialization_id,
    structural_target_id,
)
from .a4_structural_census import AUDIT_PATH as A4_AUDIT_PATH
from .a4_structural_census import _digest


A5_ROOT = ROOT / "artifacts" / "phase1-v1" / "a5-e2-capacity-gate"
E2_PATH = A5_ROOT / "a5-final-e2-certification-v1.json"
CAPACITY_PATH = A5_ROOT / "a5-e3-capacity-no-go-v1.json"
AUDIT_PATH = A5_ROOT / "a5-e2-capacity-audit-v1.json"
REPORT_PATH = ROOT / "docs" / "phase1-v1" / "A5_E2_CAPACITY_GATE_REPORT.md"
THREAD_POLICY = {
    "OMP_NUM_THREADS": "2",
    "OPENBLAS_NUM_THREADS": "2",
    "MKL_NUM_THREADS": "2",
}


class A5GateError(RuntimeError):
    """Raised when E2 certification or the capacity decision is invalid."""


def _write_exclusive(path: Path, value: Mapping[str, Any]) -> None:
    payload = canonical_json_bytes(dict(value)) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    try:
        offset = 0
        while offset < len(payload):
            count = os.write(descriptor, payload[offset:])
            if count <= 0:
                raise A5GateError("artifact write made no forward progress")
            offset += count
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _float_hex(value: float) -> str:
    return struct.pack(">d", float(value)).hex()


def _without_timings(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _without_timings(item)
            for key, item in value.items()
            if key not in {"elapsed_seconds", "wall_time_seconds"}
        }
    if isinstance(value, list):
        return [_without_timings(item) for item in value]
    return value


def _e2_source_id(context: Any) -> str:
    payload = {
        "schema": "phase1-frontier.e2-source.v1",
        "case_id": context.case_id,
        "ProblemID": context.problem_id,
        "source_snapshot_digest": context.runtime.snapshot().snapshot_digest,
        "source_indices": list(context.runtime.ansatz.indices),
        "source_iteration_counts": list(
            context.runtime.ansatz.cumulative_parameter_counts
        ),
    }
    return "e2-source-v1:" + _digest(payload)


def run_final_e2_certification() -> dict[str, Any]:
    if E2_PATH.exists():
        raise A5GateError(f"E2 certification already exists: {E2_PATH}")
    a4 = json.loads(A4_AUDIT_PATH.read_text(encoding="utf-8"))
    if not a4.get("passed") or a4.get("decision") != "GO_A5_E2_CERTIFICATION_AND_QUEUE_FREEZE":
        raise A5GateError("A4 does not authorize A5")
    for name, expected in THREAD_POLICY.items():
        if os.environ.get(name) != expected:
            raise A5GateError(f"thread policy mismatch: {name}")

    context = _h4_context()
    a1_audit = json.loads(A1_AUDIT.read_text(encoding="utf-8"))
    source_id = _e2_source_id(context)
    prepared = prepare_targets(context)
    first = [_run_target(context, target) for target in prepared]
    second = [_run_target(context, target) for target in prepared]
    repeatable = _without_timings(first) == _without_timings(second)
    identities = []
    for target in prepared:
        plan = target.plan.joint_plan
        plan_id = candidate_plan_id(source_id, plan)
        warm = [_float_hex(value) for value in target.rewrite.target.coefficients]
        zero = [_float_hex(0.0)] * len(warm)
        identities.append(
            {
                "target_class": target.target_class,
                "StructuralTargetID": structural_target_id(context.pool, plan),
                "CandidatePlanID": plan_id,
                "OptimizationInitializationID": {
                    "mapped-warm-start": optimization_initialization_id(
                        plan_id, "mapped-warm-start", warm
                    ),
                    "zero-target-coordinate": optimization_initialization_id(
                        plan_id, "zero-target-coordinate", zero
                    ),
                },
            }
        )
    starts = [start for target in first for start in target["starts"]]
    maximum_iterations = max(start["optimizer"]["iterations"] for start in starts)
    maximum_energy = max(start["optimizer"]["energy_evaluations"] for start in starts)
    maximum_gradient = max(start["optimizer"]["gradient_evaluations"] for start in starts)
    operation_caps = {
        "starts_per_target": 2,
        "optimizer_iterations_per_start": 2 * math.ceil(maximum_iterations / 10) * 10,
        "energy_evaluations_per_start": 2 * math.ceil(maximum_energy / 10) * 10,
        "gradient_vector_evaluations_per_start": 2
        * math.ceil(maximum_gradient / 10)
        * 10,
        "derivation": "twice the E2 observed maximum, rounded upward to tens",
    }
    checks = {
        "A4_authorized": True,
        "actual_H4_kernel": context.case_id == "h4-1.5-first-chemical-accuracy",
        "singleton_and_joint": [target.target_class for target in prepared]
        == ["singleton", "joint-K2"],
        "both_starts": all(len(target["starts"]) == 2 for target in first),
        "all_numerical_certificates_valid": all(
            all(start["valid"] for start in target["starts"]) for target in first
        ),
        "CPU_repeatability_without_timings": repeatable,
        "four_identity_layers_pre_endpoint": all(
            item["StructuralTargetID"]
            and item["CandidatePlanID"]
            and len(item["OptimizationInitializationID"]) == 2
            for item in identities
        ),
        "rollback_and_same_request_retry_in_A1": (
            a1_audit.get("passed") is True
            and a1_audit.get("checks", {}).get(
                "optimizer_failure_was_injected_and_rolled_back"
            )
            is True
            and a1_audit.get("checks", {}).get(
                "artifact_failure_was_injected_and_rolled_back"
            )
            is True
            and a1_audit.get("checks", {}).get("same_request_committed") is True
        ),
    }
    value = {
        "schema": "phase1-frontier.a5-final-e2-certification.v1",
        "stage": "A5-E2",
        "status": "VALID" if all(checks.values()) else "INVALID",
        "checks": checks,
        "E2SourceID": source_id,
        "grammar_version": GRAMMAR_VERSION,
        "identities": identities,
        "first_run": first,
        "second_run_scientific_digest": _digest(_without_timings(second)),
        "optimizer_contract": {
            "family": "pinned-adaptvqe-BFGS",
            "analytic_gradient": True,
            "gradient_infinity_tolerance": 1e-8,
            "energy_agreement_tolerance_hartree": 1e-10,
            "two_start_policy": [
                "mapped-warm-start",
                "zero-target-coordinate",
            ],
            "terminal_selection": "lower valid energy; preserve work from both starts",
            "operation_caps": operation_caps,
            "thread_policy": THREAD_POLICY,
            "seeds": {"candidate_semantics": 11, "native_circuit_semantics": 23},
        },
        "E3_candidate_energy_evaluations": 0,
        "FCI_evaluations": 0,
    }
    value["certification_digest"] = _digest(value)
    _write_exclusive(E2_PATH, value)
    if value["status"] != "VALID":
        raise A5GateError("final E2 certification failed")
    return value


def freeze_capacity_no_go() -> dict[str, Any]:
    if CAPACITY_PATH.exists():
        raise A5GateError(f"capacity artifact already exists: {CAPACITY_PATH}")
    e2 = json.loads(E2_PATH.read_text(encoding="utf-8"))
    e2_digest = e2.pop("certification_digest", None)
    if e2_digest != _digest(e2) or e2["status"] != "VALID":
        raise A5GateError("E2 certification is invalid")
    counts: dict[str, Any] = {}
    total_targets = 0
    total_target_parameter_width = 0
    max_parameters = 0
    for case_id in CASES:
        grammar = json.loads(case_path(case_id).read_text(encoding="utf-8"))
        target_count = grammar["canonical_singleton_count"] + grammar["joint_count"]
        source = json.loads(source_path(case_id).read_text(encoding="utf-8"))
        parameters = len(source["ansatz_indices"])
        target_parameter_width = sum(
            int(row["target_parameter_count"])
            for name in ("singletons", "joints")
            for row in grammar[name]
        )
        counts[case_id] = {
            "targets": target_count,
            "source_parameters_upper_width": parameters,
            "sum_target_parameter_width": target_parameter_width,
        }
        total_targets += target_count
        total_target_parameter_width += target_parameter_width
        max_parameters = max(max_parameters, parameters)
    caps = e2["optimizer_contract"]["operation_caps"]
    requested_starts = total_targets * caps["starts_per_target"]
    requested_iteration_cap = requested_starts * caps[
        "optimizer_iterations_per_start"
    ]
    # This is deliberately only a lower-bound work census: every analytic
    # gradient vector contains one component per target parameter.  No assumed
    # GPU speedup or favorable convergence is used to authorize execution.
    first_gradient_component_work = (
        caps["starts_per_target"] * total_target_parameter_width
    )
    blockers = [
        "no demonstrated runner/checkpoint/ledger capacity for 88,148 molecular targets",
        "no frozen total-study primitive-work cap that admits the complete queue",
        "no CPU/A100 parity or two-A100 throughput evidence for this target class",
        "queue execution cannot be called finite and operationally bounded from E2 evidence alone",
    ]
    value = {
        "schema": "phase1-frontier.a5-e3-capacity-no-go.v1",
        "decision": "NO_GO_A5_E2_OR_QUEUE_INVALID",
        "reason_code": "E3_EXHAUSTIVE_CAPACITY_UNPROVEN",
        "scientific_interpretation": "infrastructure/protocol-size No-Go, not a performance result",
        "A5_E2_certification_digest": e2_digest,
        "case_counts": counts,
        "total_E3_targets": total_targets,
        "requested_optimizer_starts": requested_starts,
        "requested_optimizer_iteration_upper_cap": requested_iteration_cap,
        "first_gradient_vector_component_work_if_every_start_begins": first_gradient_component_work,
        "maximum_source_parameter_width": max_parameters,
        "blockers": blockers,
        "queue_created": False,
        "queue_freeze_authorized": False,
        "E3_candidate_energy_evaluations": 0,
        "E3_optimizer_starts": 0,
        "FCI_evaluations": 0,
        "forbidden_remediations": [
            "post-hoc Top-K or energy ranking",
            "silent random sampling",
            "dropping failed or expensive molecule families",
            "loosening the accuracy endpoint",
            "claiming structural CNOT reachability as accuracy-feasible compression",
        ],
        "required_protocol_successor": (
            "Use only outcome-free CEO algebra/symmetry/resource equivalence to define "
            "a substantially smaller prospective joint language, or demonstrate and "
            "freeze infrastructure capable of exhaustive execution. Existing E3 "
            "outcomes remain inaccessible because none exist."
        ),
    }
    value["no_go_digest"] = _digest(value)
    _write_exclusive(CAPACITY_PATH, value)
    return value


def audit() -> dict[str, Any]:
    e2 = json.loads(E2_PATH.read_text(encoding="utf-8"))
    e2_digest = e2.pop("certification_digest", None)
    no_go = json.loads(CAPACITY_PATH.read_text(encoding="utf-8"))
    no_go_digest = no_go.pop("no_go_digest", None)
    checks = {
        "E2_digest": e2_digest == _digest(e2),
        "E2_valid": e2["status"] == "VALID",
        "NoGo_digest": no_go_digest == _digest(no_go),
        "NoGo_decision": no_go["decision"]
        == "NO_GO_A5_E2_OR_QUEUE_INVALID",
        "NoGo_reason": no_go["reason_code"]
        == "E3_EXHAUSTIVE_CAPACITY_UNPROVEN",
        "all_E3_work_zero": (
            no_go["E3_candidate_energy_evaluations"] == 0
            and no_go["E3_optimizer_starts"] == 0
            and no_go["FCI_evaluations"] == 0
        ),
        "queue_absent": no_go["queue_created"] is False,
        "target_count_exact": no_go["total_E3_targets"] == 88_148,
    }
    return {
        "schema": "phase1-frontier.a5-e2-capacity-audit.v1",
        "passed": all(checks.values()),
        "decision": no_go["decision"],
        "checks": checks,
        "E2_file_sha256": hashlib.sha256(E2_PATH.read_bytes()).hexdigest(),
        "NoGo_file_sha256": hashlib.sha256(CAPACITY_PATH.read_bytes()).hexdigest(),
    }


def freeze_audit() -> dict[str, Any]:
    """Persist the terminal audit without changing either source artifact."""

    value = audit()
    if not value["passed"]:
        raise A5GateError("A5 terminal audit did not pass")
    if AUDIT_PATH.exists():
        existing = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
        if existing != value:
            raise A5GateError("existing A5 audit differs from recomputed audit")
        return existing
    _write_exclusive(AUDIT_PATH, value)
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-e2", action="store_true")
    parser.add_argument("--freeze-capacity-no-go", action="store_true")
    parser.add_argument("--audit", action="store_true")
    parser.add_argument("--freeze-audit", action="store_true")
    args = parser.parse_args()
    if sum(
        (
            args.run_e2,
            args.freeze_capacity_no_go,
            args.audit,
            args.freeze_audit,
        )
    ) != 1:
        parser.error("choose exactly one action")
    if args.run_e2:
        value = run_final_e2_certification()
    elif args.freeze_capacity_no_go:
        value = freeze_capacity_no_go()
    elif args.audit:
        value = audit()
    else:
        value = freeze_audit()
    print(json.dumps(value, indent=2, sort_keys=True))
    if (args.audit or args.freeze_audit) and not value["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

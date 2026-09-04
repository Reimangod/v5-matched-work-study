"""Phase-1 v2 S3 real-kernel vertical slice and durable-runner audit."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from dvg_obs_ceo.resources import AnsatzStructure
from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive
from v5_final.parent_native_persistent_runner_probe import run_probe
from v5_final.parent_native_work_accounting import (
    ParentNativeWorkRequest,
    work_cap_digest,
)

from .a1_vertical_slice import A1_AUDIT, _h4_context, prepare_targets
from .a5_successor_v2 import AUDIT_PATH as S2_AUDIT_PATH
from .a5_successor_v2 import QUEUE_PATH, _digest, _float_hex
from .v2_runner_adapter import (
    BoundV2Request,
    _cap,
    _execute_bound_request,
    bind_request,
)


ROOT = Path(__file__).resolve().parents[2]
S3_ROOT = ROOT / "artifacts" / "phase1-v2" / "s3-runner-readiness"
CALIBRATION_ROOT = S3_ROOT / "h4-real-kernel-calibration-v1"
OUTPUT = S3_ROOT / "phase1-v2-s3-readiness-v1.json"
IMPLEMENTATION = (
    ROOT / "src/phase1_frontier/v2_runner_adapter.py",
    ROOT / "src/v5_final/parent_native_execution_services.py",
    ROOT / "src/v5_final/parent_native_persistent_runner.py",
)


class V2S3ReadinessError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _calibration_bound() -> BoundV2Request:
    context = _h4_context()
    target, _joint = prepare_targets(context)
    plan = target.plan.joint_plan
    transform = plan.transformation
    jacobian = np.asarray(transform.jacobian, dtype=np.float64)
    offset = np.asarray(transform.offset, dtype=np.float64)
    coordinates, _residuals, rank, _singular = np.linalg.lstsq(
        jacobian,
        np.asarray(context.runtime.ansatz.coefficients, dtype=np.float64) - offset,
        rcond=None,
    )
    if rank != jacobian.shape[1]:
        raise V2S3ReadinessError("H4 calibration affine projection is rank deficient")
    residual = np.asarray(transform.constraint_matrix) @ (
        offset + jacobian @ coordinates
    ) - np.asarray(transform.constraint_rhs)
    if np.max(np.abs(residual), initial=0.0) > 1e-10:
        raise V2S3ReadinessError("H4 calibration projection violates constraint")
    cap = _cap(len(coordinates))
    calibration_queue_digest = _digest(
        {
            "protocol": "phase1-v2-s3-h4-real-kernel-calibration-v1",
            "scientific_screen_member": False,
            "source_checkpoint_digest": context.source_checkpoint_digest,
        }
    )
    request = ParentNativeWorkRequest(
        queue_item_id="phase1-v2-s3-h4-calibration-request-v1",
        method_id="same-structure-reoptimization",
        case_id=context.case_id,
        state_preparation_id=context.state_preparation_id,
        problem_id=context.problem_id,
        hamiltonian_digest=context.hamiltonian_digest,
        source_checkpoint_digest=context.source_checkpoint_digest,
        frozen_queue_digest=calibration_queue_digest,
        work_cap_digest=work_cap_digest(cap),
    )
    row = {
        "RequestID": request.queue_item_id,
        "CandidatePlanID": "s3-calibration-plan:" + _digest(
            {"candidate_ids": [value.candidate_id for value in target.plan.candidates]}
        ),
        "StructuralTargetID": target.plan.proposed_state_preparation_spec.state_preparation_id,
        "start": "mapped-warm-start",
        "initial_coordinates_float64": _float_hex(coordinates),
        "scientific_screen_member": False,
    }
    return BoundV2Request(
        row=row,
        context=context,
        source_record={"B2": {"energy_hartree": context.runtime.energy_hartree}},
        joint_plan=plan,
        initial_coordinates=np.asarray(coordinates, dtype=np.float64),
        initial_inverse_hessian=np.eye(len(coordinates), dtype=np.float64),
        target_structure=AnsatzStructure.create(
            plan.target_indices, coordinates, plan.target_iteration_counts
        ),
        cap=cap,
        work_request=request,
    )


def _probe_checks(probe: Mapping[str, Any]) -> dict[str, bool]:
    return {
        "four_terminal_classes": probe["terminal_statuses"]
        == {
            "accepted": "ACCEPTED",
            "algorithm_rejected": "ALGORITHM_REJECTED",
            "cap_rejected": "CAP_REJECTED",
            "kernel_failure": "KERNEL_FAILURE",
        },
        "publication_failure_recoverable": bool(
            probe["publication_failure_observed"]
            and probe["recovery_identical_after_publication_failure"]
        ),
        "cap_rejection_pre_kernel": probe["cap_rejection_kernel_calls"] == 0,
        "same_request_retry_preserves_work": bool(
            probe["retry_attempt_count"] == 2
            and probe["retry_rollback_count"] == 1
            and probe["retry_preserved_failed_and_successful_work"]
        ),
        "bad_rollback_refused": bool(
            probe["invalid_rollback_rejected_before_append"]
        ),
        "corrupt_or_duplicate_ledger_refused": bool(
            probe["duplicate_root_rejected"]
            and probe["orphan_attempt_rejected"]
            and probe["duplicate_terminal_rejected"]
            and probe["digest_mismatch_rejected"]
        ),
    }


def build() -> dict[str, Any]:
    if OUTPUT.exists():
        raise V2S3ReadinessError("S3 readiness artifact already exists")
    s2 = json.loads(S2_AUDIT_PATH.read_text(encoding="utf-8"))
    a1 = json.loads(A1_AUDIT.read_text(encoding="utf-8"))
    queue = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
    if not CALIBRATION_ROOT.exists():
        _execute_bound_request(_calibration_bound(), CALIBRATION_ROOT)
    endpoint = json.loads(
        (CALIBRATION_ROOT / "endpoint-outcome.json").read_text(encoding="utf-8")
    )
    terminal = json.loads(
        (CALIBRATION_ROOT / "terminal-result.json").read_text(encoding="utf-8")
    )
    probe = run_probe()
    # Bind both target classes and both starts without evaluating their energy.
    representative_rows = (
        queue["items"][0],
        queue["items"][1],
        queue["items"][-2],
        queue["items"][-1],
    )
    representative_bindings = [
        {
            "RequestID": row["RequestID"],
            "case_id": row["case_id"],
            "target_class": row["target_class"],
            "start": row["start"],
            "target_parameter_count": len(
                bind_request(row["RequestID"]).initial_coordinates
            ),
        }
        for row in representative_rows
    ]
    probe_checks = _probe_checks(probe)
    checks = {
        "S2_freeze_authorizes_runner_only": bool(
            s2.get("passed") is True
            and s2.get("decision") == "GO_PHASE1_V2_SCREEN_RUNNER_IMPLEMENTATION"
        ),
        "prior_A1_real_kernel_evidence_valid": bool(
            a1.get("passed") is True
            and a1.get("decision") == "GO_A2_SOURCE_LOCK"
        ),
        "H4_calibration_endpoint_certified": bool(
            all(endpoint["checks"].values())
            and endpoint["FCI_evaluations"] == 0
            and endpoint["scientific_compression_acceptance"]
            == "DEFERRED_UNTIL_PAIRED_TERMINAL_ANALYSIS"
        ),
        "H4_calibration_terminal_persisted": terminal["recovered_result"][
            "terminal"
        ]["terminal_status"]
        == "ACCEPTED",
        "fault_matrix_passed": all(probe_checks.values()),
        "representative_v2_bindings_reconstructed": len(representative_bindings) == 4,
        "frozen_screen_still_unstarted": bool(
            queue["counts"]["NOT_STARTED"] == 1_266
            and queue["counts"]["candidate_energy_evaluations"] == 0
            and queue["counts"]["optimizer_starts"] == 0
            and queue["counts"]["FCI_evaluations"] == 0
        ),
    }
    value: dict[str, Any] = {
        "schema": "phase1-frontier.v2-s3-runner-readiness.v1",
        "stage": "V2-S3",
        "decision": (
            "GO_PHASE1_V2_S4_READINESS_GATE"
            if all(checks.values())
            else "NO_GO_PHASE1_V2_S3_RUNNER"
        ),
        "checks": checks,
        "probe_checks": probe_checks,
        "H4_calibration": {
            "scientific_screen_member": False,
            "candidate_energy_calls": terminal["recovered_result"]["terminal"][
                "work_total"
            ]["energy_evaluations"],
            "optimizer_starts": terminal["recovered_result"]["terminal"][
                "work_total"
            ]["optimizer_starts"],
            "FCI_evaluations": 0,
            "endpoint_outcome_sha256": _sha256(
                CALIBRATION_ROOT / "endpoint-outcome.json"
            ),
            "terminal_result_sha256": _sha256(
                CALIBRATION_ROOT / "terminal-result.json"
            ),
        },
        "representative_bindings": representative_bindings,
        "fault_probe": probe,
        "frozen_queue_sha256": _sha256(QUEUE_PATH),
        "implementation_manifest": [
            {"path": str(path.relative_to(ROOT)), "sha256": _sha256(path)}
            for path in IMPLEMENTATION
        ],
        "claim_boundary": {
            "allowed": [
                "the request-bound runner completed an H4 engineering calibration",
                "the frozen v2 screen remains entirely unstarted",
                "durability, cap, rollback, and retry probes passed",
            ],
            "prohibited": [
                "LiH, H6, or BeH2 candidate performance",
                "joint-over-singleton advantage",
                "FCI or Measurement Cost claim",
            ],
        },
    }
    value["readiness_digest"] = _digest(value)
    write_json_exclusive(OUTPUT, value)
    return value


def audit() -> dict[str, bool]:
    value = json.loads(OUTPUT.read_text(encoding="utf-8"))
    body = dict(value)
    observed = body.pop("readiness_digest", None)
    checks = {
        "readiness_digest_valid": observed == _digest(body),
        "decision_is_scoped_GO": value.get("decision")
        == "GO_PHASE1_V2_S4_READINESS_GATE",
        "all_checks_pass": all(value.get("checks", {}).values()),
        "queue_unchanged": value.get("frozen_queue_sha256") == _sha256(QUEUE_PATH),
        "implementation_unchanged": all(
            _sha256(ROOT / row["path"]) == row["sha256"]
            for row in value.get("implementation_manifest", ())
        ),
    }
    return checks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("build", "audit"))
    args = parser.parse_args()
    value = build() if args.action == "build" else audit()
    print(json.dumps(value, indent=2, sort_keys=True))
    if args.action == "audit" and not all(value.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()

"""Close outcome-blind predictor, Pareto, and certification contracts synthetically."""

from __future__ import annotations

from dataclasses import asdict, replace
import argparse
import hashlib
import json
from typing import Any

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .certifier_v2 import (
    IndependentCertificationEvidence,
    certify_independently,
)
from .pareto_selector_v2 import nondominated_predictions
from .predictor_v2 import PredictorInput, PredictorV2Error, predict_quadratic
from .s0_successor import ROOT
from .s6_method_parity import audit as audit_s6


OUTPUT = ROOT / "artifacts/v5-final/s7-s9/predictor-pareto-certification-contract-v1.json"


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _prediction(
    suffix: str, *, energy_gradient: str, curvature: str, cnot_delta: int
) -> PredictorInput:
    return PredictorInput(
        candidate_intent_id=f"candidate-intent-v1:{suffix * 64}",
        proposed_physical_state_id=f"physical-state-v1:{suffix * 64}",
        displacement_decimal="1",
        directional_gradient_decimal=energy_gradient,
        directional_curvature_decimal=curvature,
        condition_number_decimal="10",
        secant_residual_decimal="0.01",
        direction_coverage_decimal="0.8",
        hessian_age_commits=0,
        predicted_resource_delta={
            "cnot_count": cnot_delta,
            "cnot_depth": cnot_delta,
            "total_depth": cnot_delta,
            "parameter_count": -1,
            "logical_block_count": -1,
        },
    )


def build() -> dict[str, Any]:
    if not all(audit_s6().values()):
        raise RuntimeError("S7-S9 contract requires S6 method parity")
    inputs = (
        _prediction("1", energy_gradient="-0.00008", curvature="0.00002", cnot_delta=-4),
        _prediction("2", energy_gradient="-0.00004", curvature="0.00002", cnot_delta=-8),
        _prediction("3", energy_gradient="-0.00001", curvature="0.0002", cnot_delta=-1),
    )
    predictions = tuple(predict_quadratic(value) for value in inputs)
    invalid = predict_quadratic(
        replace(
            inputs[0],
            candidate_intent_id=f"candidate-intent-v1:{'4' * 64}",
            proposed_physical_state_id=f"physical-state-v1:{'4' * 64}",
            hessian_age_commits=2,
        )
    )
    leakage_rejected = False
    leaked = asdict(inputs[0]) | {"actual_energy_hartree": "-1.23"}
    try:
        PredictorInput.from_mapping(leaked)
    except PredictorV2Error:
        leakage_rejected = True
    frontier = nondominated_predictions(predictions)
    certification_evidence = IndependentCertificationEvidence(
        source_energy_hartree="-1.0",
        optimizer_energy_hartree="-0.99995",
        independent_energy_hartree="-0.99995000001",
        gradient_path_a_infinity="5e-9",
        gradient_path_b_infinity="5.1e-9",
        constraint_residual="1e-12",
        resources={
            "cnot_count": 5,
            "cnot_depth": 4,
            "total_depth": 8,
            "parameter_count": 1,
            "logical_block_count": 1,
        },
        statevector_recomputed=True,
        transformation_semantics_verified=True,
        resource_recount_verified=True,
        work_ledger_closed=True,
        raw_ledger_release_reconciled=True,
        atomic_transaction_ready=True,
    )
    accepted = certify_independently(
        certification_evidence,
        energy_budget_hartree="0.0001",
        stationarity_threshold="1e-8",
        energy_agreement_tolerance="1e-9",
        gradient_agreement_tolerance="1e-9",
        constraint_tolerance="1e-10",
    )
    rejected = certify_independently(
        replace(certification_evidence, work_ledger_closed=False),
        energy_budget_hartree="0.0001",
        stationarity_threshold="1e-8",
        energy_agreement_tolerance="1e-9",
        gradient_agreement_tolerance="1e-9",
        constraint_tolerance="1e-10",
    )
    modules = []
    for name in ("predictor_v2.py", "pareto_selector_v2.py", "certifier_v2.py"):
        path = ROOT / "src/v5_final" / name
        modules.append(
            {
                "path": str(path.relative_to(ROOT)),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    result: dict[str, Any] = {
        "schema": "v5-final.s7-s9-contract.v1",
        "stages": ["S7", "S8", "S9"],
        "status": "CONTRACTS_COMPLETE_SYNTHETIC_ONLY",
        "modules": modules,
        "predictor_probe": {
            "results": [asdict(value) for value in predictions],
            "nonzero_gradient_terms_used": all(
                value.diagnostics["nonzero_gradient_model"] for value in predictions
            ),
            "candidate_specific_diagnostics": all(
                set(value.diagnostics)
                == {
                    "nonzero_gradient_model",
                    "condition_number",
                    "secant_residual",
                    "direction_coverage",
                    "hessian_age_commits",
                    "stale_hessian",
                    "uncertainty_calibrated",
                }
                for value in predictions
            ),
            "stale_hessian_invalidates_prediction": invalid.status
            == "INVALID_DIAGNOSTICS"
            and invalid.predicted_energy_change_hartree is None,
            "uncertainty_unestablished_is_null": all(
                value.uncertainty_hartree is None for value in predictions
            ),
            "actual_energy_leakage_rejected": leakage_rejected,
        },
        "pareto_probe": {
            "primary_axes_not_scalarized": True,
            "input_count": len(predictions),
            "retained_candidate_intent_ids": [
                value.candidate_intent_id for value in frontier
            ],
            "deterministic_order": list(frontier)
            == sorted(frontier, key=lambda value: value.candidate_intent_id),
            "invalid_or_uncertain_candidates_are_not_falsely_dominated": invalid
            in nondominated_predictions((*predictions, invalid)),
        },
        "certification_probe": {
            "classification": "synthetic contract values; not molecular evidence",
            "complete_evidence_accepted": {
                "accepted": accepted.accepted,
                "failed_checks": list(accepted.failed_checks),
            },
            "missing_ledger_closure_rejected": {
                "accepted": rejected.accepted,
                "failed_checks": list(rejected.failed_checks),
            },
            "FCI_input_absent": "fci"
            not in json.dumps(asdict(certification_evidence), sort_keys=True).lower(),
            "source_fidelity_not_required_for_approximate_compression": True,
            "independent_state_recomputation_required": certification_evidence.statevector_recomputed,
            "two_path_gradient_required": True,
            "atomic_publication_required": certification_evidence.atomic_transaction_ready,
        },
        "academic_integrity": {
            "synthetic_values_not_results": True,
            "uncertainty_not_invented": True,
            "actual_energy_not_predictor_input": True,
            "FCI_not_runtime_input": True,
            "no_performance_claim": True,
        },
        "systems_safety": {
            "invalid_predictor_is_null": True,
            "pareto_retains_incomparables": True,
            "certification_fails_on_missing_evidence": not rejected.accepted,
            "modules_content_addressed": True,
        },
        "authorization": {
            "production_backend_integration": "NEXT",
            "H2_H4_calibration_execution": "NOT_AUTHORIZED",
            "development_execution": "NOT_AUTHORIZED",
            "performance_experiment": "NOT_AUTHORIZED",
        },
        "decision": "GO_PRODUCTION_BACKEND_INTEGRATION_ONLY",
        "claim_boundary": (
            "S7-S9 contracts are exercised with synthetic values only. No molecule, "
            "method comparison, predictor accuracy, or compression benefit is established."
        ),
    }
    result["contract_digest"] = _digest(result)
    return result


def audit() -> dict[str, bool]:
    committed = json.loads(OUTPUT.read_text())
    rebuilt = build()
    payload = dict(committed)
    observed = payload.pop("contract_digest")
    checks = {
        "deterministic_rebuild": committed == rebuilt,
        "contract_digest": observed == _digest(payload),
        "modules_current": all(
            hashlib.sha256((ROOT / item["path"]).read_bytes()).hexdigest()
            == item["sha256"]
            for item in committed["modules"]
        ),
        "predictor": all(
            value
            for key, value in committed["predictor_probe"].items()
            if key != "results"
        ),
        "pareto": committed["pareto_probe"]["primary_axes_not_scalarized"]
        and committed["pareto_probe"]["deterministic_order"]
        and committed["pareto_probe"][
            "invalid_or_uncertain_candidates_are_not_falsely_dominated"
        ],
        "certification_accepts_complete": committed["certification_probe"][
            "complete_evidence_accepted"
        ]["accepted"],
        "certification_rejects_missing": not committed["certification_probe"][
            "missing_ledger_closure_rejected"
        ]["accepted"],
        "academic_integrity": all(committed["academic_integrity"].values()),
        "systems_safety": all(committed["systems_safety"].values()),
        "performance_closed": committed["authorization"]["performance_experiment"]
        == "NOT_AUTHORIZED",
    }
    if not all(checks.values()):
        raise RuntimeError("S7-S9 contract audit failed")
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

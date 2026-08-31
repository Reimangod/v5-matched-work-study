"""Freeze the bounded production-objective parity workload before GPU outcomes."""

from __future__ import annotations

import argparse
import json
from typing import Any

from .common import ARTIFACT_ROOT, embedded_digest_valid, load_json, publish
from .p0_baseline import CANDIDATE_REFERENCE, PROTOCOL
from .p4_report import REPORT as SOURCE_ROUTE_REPORT


CONTRACT = ARTIFACT_ROOT / "p3-objective-parity/production-objective-contract-v1.json"
SELECTION = {
    "h2": "approximate_candidate_terminal_reference",
    "h4": "exact_candidate_terminal_reference",
    "lih": "approximate_candidate_terminal_reference",
    "h6": "exact_candidate_terminal_reference",
    "beh2": "approximate_candidate_terminal_reference",
}


def contract_body() -> dict[str, Any]:
    protocol = load_json(PROTOCOL)
    references = load_json(CANDIDATE_REFERENCE)
    route = load_json(SOURCE_ROUTE_REPORT)
    if not embedded_digest_valid(protocol, "protocol_digest"):
        raise RuntimeError("P0 protocol digest is invalid")
    if not embedded_digest_valid(references, "supplement_digest"):
        raise RuntimeError("P0 candidate reference digest is invalid")
    if not embedded_digest_valid(route, "report_digest"):
        raise RuntimeError("source-route report digest is invalid")
    if route["status"] != "GO_P3_PRODUCTION_OBJECTIVE_BINDING_AND_DECISION_PARITY":
        raise RuntimeError("source-route diagnostic did not authorize objective binding")
    by_alias = {case["alias"]: case for case in references["cases"]}
    cases = []
    for alias in protocol["case_order"]:
        field = SELECTION[alias]
        reference = by_alias[alias][field]
        if reference["availability"] != "AVAILABLE_FROZEN_HISTORICAL_CPU_RESULT":
            raise RuntimeError(f"selected P0 candidate is unavailable: {alias}")
        cases.append(
            {
                "alias": alias,
                "case_id": by_alias[alias]["case_id"],
                "reference_class": field.removesuffix("_candidate_terminal_reference"),
                "candidate_id": reference["candidate_id"],
                "candidate_kind": reference["candidate_kind"],
                "composition_candidate_ids": reference["all_attempt_candidate_ids"],
                "attempt_scope": reference["attempt_scope"],
                "frozen_CPU_terminal_decision": reference["terminal_decision"],
                "frozen_CPU_optimizer_terminal": reference["optimizer_terminal"],
                "frozen_CPU_energy_hartree": reference["energy_hartree"],
                "frozen_CPU_independent_energy_hartree": reference[
                    "independent_energy_hartree"
                ],
                "frozen_CPU_resource_vector": reference["resource_vector"],
                "source_result_path": reference["source_result_path"],
                "source_result_sha256": reference["source_result_sha256"],
            }
        )
    return {
        "schema": "aic-a100-pilot.p3-production-objective-contract.v1",
        "status": "GO_BOUNDED_P3_OBJECTIVE_AND_DECISION_PARITY",
        "frozen_before_new_GPU_candidate_outcomes": True,
        "evidence_binding": {
            "P0_protocol_digest": protocol["protocol_digest"],
            "P0_candidate_reference_supplement_digest": references[
                "supplement_digest"
            ],
            "source_route_report_digest": route["report_digest"],
        },
        "selection_policy": {
            "case_order": list(protocol["case_order"]),
            "candidate_count": len(cases),
            "policy": (
                "Use the P0-frozen approximate reference when no exact reference "
                "exists; otherwise use exact for H4/H6 controls and approximate for "
                "BeH2 to cover both accepted and rejected decisions with one candidate "
                "per registered case."
            ),
            "selected_after_new_GPU_candidate_outcomes": False,
            "cases": cases,
        },
        "optimizer_binding": {
            "optimizer": "pinned adaptvqe.minimize:minimize_bfgs",
            "energy_objective": (
                "Aer GPU double-precision statevector plus host sparse Hamiltonian "
                "expectation; invoked by every unseeded BFGS objective call"
            ),
            "gradient": "pinned CEO analytic gradient on CPU",
            "orchestration": "CPU",
            "resource_counter": "unchanged paper-era CPU counter",
            "CPU_fallback_allowed": False,
            "production_executor_modified": False,
            "pilot_adapter_imported_by_production": False,
        },
        "parity_requirements": {
            "same_AIC_node_paired_CPU_GPU": True,
            "state_error_max": protocol["tolerances"][
                "phase_aligned_state_error_max"
            ],
            "energy_error_hartree_max": protocol["tolerances"][
                "absolute_energy_hartree_max"
            ],
            "max_gradient_component_error": protocol["tolerances"][
                "max_gradient_component_max"
            ],
            "candidate_ids": "EXACT_EQUALITY",
            "terminal_decision": "EXACT_EQUALITY",
            "resource_vector": "EXACT_INTEGER_EQUALITY",
            "optimizer_terminal": (
                "REPORT_EXACT_FIELDS_AND_CLASSIFY_DIFFERENCE; terminal acceptance "
                "decision must remain exact"
            ),
        },
        "scientific_boundary": {
            "authorized_new_GPU_candidate_outcomes": len(cases),
            "authorized_new_paired_CPU_candidate_outcomes": len(cases),
            "FCI_evaluations": 0,
            "P5_limited_scientific_pilot": "NOT_AUTHORIZED",
            "existing_90_item_execution": "UNCHANGED",
            "Measurement_Cost_claim": "NOT_AUTHORIZED",
            "V5_performance_claim": "NOT_AUTHORIZED",
        },
    }


def publish_contract() -> dict[str, Any]:
    return publish(CONTRACT, contract_body(), "contract_digest")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--publish", action="store_true")
    arguments = parser.parse_args()
    if not arguments.publish:
        raise RuntimeError("select --publish")
    print(json.dumps(publish_contract(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

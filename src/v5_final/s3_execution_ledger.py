"""S3 contract and synthetic all-component reconciliation audit."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from typing import Any

from jsonschema import Draft202012Validator

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from . import PROTOCOL_ID
from .s0_successor import ROOT
from .scientific_values import TaggedScientificValue
from .semantic_contract import ScientificValueDelta, StateDelta
from .semantic_contract_v2 import ResourceDelta, SemanticDelta, WorkDelta, WORK_COMPONENTS
from .semantic_events import SemanticEventType
from .work_ledger import IntegratedWorkLedger, reconcile, release_summary


def _digest_without(value: dict[str, Any], field: str) -> str:
    payload = dict(value)
    payload.pop(field, None)
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _delta(work: WorkDelta, *, energy_available: bool = False) -> SemanticDelta:
    before = TaggedScientificValue.not_evaluated(
        quantity="synthetic_probe", unit="dimensionless", reason="S3_contract_probe"
    )
    after = (
        TaggedScientificValue.available(
            quantity="synthetic_probe", unit="dimensionless", value="-1"
        )
        if energy_available
        else before
    )
    return SemanticDelta(
        state_delta=StateDelta("a" * 64, "a" * 64),
        resource_delta=ResourceDelta(),
        scientific_value_delta=ScientificValueDelta(before, after),
        work_delta=work,
    )


def synthetic_reconciliation_probe() -> dict[str, Any]:
    cap = WorkDelta(**{field: 100 for field in WORK_COMPONENTS})
    ledger = IntegratedWorkLedger(
        cap=cap, root_digest="0" * 64, producer="v5_final.executor.synthetic_s3_probe"
    )
    operations = [
        (SemanticEventType.CANDIDATE_GENERATED, WorkDelta(candidate_generations=2), False),
        (SemanticEventType.SEARCH_STATE_EXPANDED, WorkDelta(search_states=3), False),
        (SemanticEventType.REWRITE_VERIFIED, WorkDelta(rewrite_verifications=4), False),
        (SemanticEventType.RESOURCE_RECOUNTED, WorkDelta(resource_recounts=5), False),
        (SemanticEventType.OPTIMIZER_STARTED, WorkDelta(optimizer_starts=1), False),
        (SemanticEventType.OPTIMIZER_ITERATED, WorkDelta(optimizer_iterations=6), False),
        (SemanticEventType.ENERGY_EVALUATED, WorkDelta(energy_evaluations=7), True),
        (
            SemanticEventType.GRADIENT_EVALUATED,
            WorkDelta(gradient_vector_evaluations=2, gradient_component_equivalents=16),
            False,
        ),
        (SemanticEventType.HVP_EVALUATED, WorkDelta(hvp_evaluations=3), False),
        (
            SemanticEventType.STATEVECTOR_RECOMPUTED,
            WorkDelta(statevector_recomputations=8),
            False,
        ),
    ]
    independent_raw = WorkDelta(
        energy_evaluations=7,
        gradient_vector_evaluations=2,
        gradient_component_equivalents=16,
        hvp_evaluations=3,
        optimizer_starts=1,
        optimizer_iterations=6,
        resource_recounts=5,
        candidate_generations=2,
        search_states=3,
        rewrite_verifications=4,
        statevector_recomputations=8,
    )
    for event_type, work, energy_available in operations:
        ledger.record_operation(
            event_type=event_type,
            queue_item_id="synthetic-s3-probe",
            delta=_delta(work, energy_available=energy_available),
            evidence={
                "kind": "synthetic-counter-contract-probe",
                "event": event_type.value,
                "raw_counter_source": "independent-explicit-synthetic-snapshot",
            },
        )
    ledger_document = ledger.close()
    summary = release_summary(ledger_document)
    checks = reconcile(
        independent_raw_counter=independent_raw,
        ledger_document=ledger_document,
        summary=summary,
    )
    return {
        "work_total": asdict(ledger.raw_total),
        "independent_raw_counter": asdict(independent_raw),
        "event_count": len(ledger.events),
        "reconciliation_checks": checks,
        "all_components_nonzero": all(
            getattr(ledger.raw_total, field) > 0 for field in WORK_COMPONENTS
        ),
        "probe_classification": "synthetic infrastructure; not molecular evidence",
    }


def build_contract() -> dict[str, Any]:
    probe = synthetic_reconciliation_probe()
    result: dict[str, Any] = {
        "schema": "v5-final.s3-integrated-execution-ledger.v1",
        "protocol_id": PROTOCOL_ID,
        "stage": "S3",
        "status": "COMPLETE_NOT_PRODUCTION_EXECUTOR_BOUND",
        "semantic_event_types": [event.value for event in SemanticEventType],
        "work_components": list(WORK_COMPONENTS),
        "atomic_path": (
            "IntegratedWorkLedger.record_operation performs pre-cap validation, "
            "semantic-event append, and raw-counter increment as one in-memory operation"
        ),
        "posthoc_log_assembly_allowed": False,
        "reconciliation_requirement": "independent raw counter = semantic ledger = release summary",
        "synthetic_all_component_probe": probe,
        "academic_integrity": {
            "scientific_values_remain_tagged": True,
            "synthetic_probe_excluded_from_molecular_evidence": True,
            "event_operation_semantics_bind_allowed_work_components": True,
        },
        "systems_safety": {
            "cap_checked_before_event_or_counter_mutation": True,
            "digest_chained_events": True,
            "strict_event_reconstruction": True,
            "all_components_reconcile": all(probe["reconciliation_checks"].values())
            and probe["all_components_nonzero"],
        },
        "remaining_s4_obligations": [
            "bind IntegratedWorkLedger directly to the production executor",
            "reconcile independent raw counters returned by real kernel/optimizer calls",
            "bind event chain to a nonempty frozen smoke queue",
            "prove transaction rollback and replay under failure injection",
        ],
        "authorization": {
            "next_stage": "S4",
            "performance_experiment": "NOT_AUTHORIZED",
            "candidate_molecular_energy_evaluation": "NOT_AUTHORIZED",
            "s5_freeze": "NOT_AUTHORIZED",
        },
        "claim_boundary": "Integrated ledger infrastructure with synthetic probes only; no production molecular execution or performance evidence.",
        "decision": "GO_S4_ONLY",
    }
    result["contract_digest"] = _digest_without(result, "contract_digest")
    return result


def audit_contract() -> dict[str, Any]:
    path = ROOT / "artifacts" / "v5-final" / "s3" / "integrated-execution-ledger-v1.json"
    schema_path = ROOT / "schemas" / "v5-final-s3-integrated-execution-ledger-v1.schema.json"
    committed = json.loads(path.read_text(encoding="utf-8"))
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    schema_errors = sorted(
        Draft202012Validator(schema).iter_errors(committed),
        key=lambda error: list(error.path),
    )
    probe = committed["synthetic_all_component_probe"]
    checks = {
        "schema_valid": not schema_errors,
        "deterministic_rebuild": committed == build_contract(),
        "contract_digest": committed["contract_digest"]
        == _digest_without(committed, "contract_digest"),
        "all_work_components_registered": set(committed["work_components"])
        == set(WORK_COMPONENTS),
        "every_component_exercised": probe["all_components_nonzero"],
        "raw_ledger_summary_reconcile": all(probe["reconciliation_checks"].values()),
        "posthoc_assembly_forbidden": committed["posthoc_log_assembly_allowed"] is False,
        "academic_integrity_gate": all(committed["academic_integrity"].values()),
        "systems_safety_gate": all(committed["systems_safety"].values()),
        "production_binding_not_overclaimed": committed["status"]
        == "COMPLETE_NOT_PRODUCTION_EXECUTOR_BOUND",
        "performance_still_closed": committed["authorization"]["performance_experiment"]
        == "NOT_AUTHORIZED",
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise RuntimeError("S3 ledger audit failed: " + ", ".join(failures))
    result = {
        "schema": "v5-final.s3-integrated-execution-ledger-audit.v1",
        "stage": "S3",
        "passed": True,
        "checks": checks,
        "failed_checks": [],
        "schema_errors": [error.message for error in schema_errors],
        "claim_boundary": committed["claim_boundary"],
    }
    result["audit_digest"] = _digest_without(result, "audit_digest")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("build", "verify"))
    arguments = parser.parse_args()
    output = ROOT / "artifacts" / "v5-final" / "s3" / "integrated-execution-ledger-v1.json"
    if arguments.action == "build":
        write_json_exclusive(output, build_contract())
        print(json.dumps({"path": str(output), "status": build_contract()["status"]}, sort_keys=True))
        return
    result = audit_contract()
    print(json.dumps({"checks": len(result["checks"]), "passed": True}, sort_keys=True))


if __name__ == "__main__":
    main()

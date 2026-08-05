"""Outcome-free adapter integration gate on toy and pinned H2/H4 structures."""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from typing import Any

from .adapters import AdapterBackend, Candidate, ENTRYPOINTS, Evaluation, run_comparator
from .atomic_artifacts import canonical_json_bytes
from .comparators import ImmutableSource, PRIMARY_METHODS
from .s0_common import PARENT
from .work_ledger import FIELDS, WorkLedgerError, WorkVector, reconstruct


CHECKPOINTS = {
    "h2-1.5-integration": PARENT / "artifacts/s8/calibration-bundle/checkpoint-h2-1.5-iteration-1.json",
    "h4-1.5-integration": PARENT / "artifacts/s8/calibration-bundle/checkpoint-h4-1.5-first-chemical-accuracy.json",
}
CAP = WorkVector(N_E=100, N_G=100, N_gradcomp=10000, N_HVP=100, N_exact=100,
                 N_recount=100, N_rewrite=100, N_states=100, N_rounds=10)


class FixtureBackend(AdapterBackend):
    """Deterministic state-machine backend; it performs no molecular energy call."""

    def catalog(self, parent_state_id: str):
        suffix = parent_state_id.split(":")[-1][:12]
        if parent_state_id.startswith("accepted-v2:"):
            return (
                Candidate(f"rebuild-{suffix}", f"proposal-{suffix}-r", 0),
                Candidate(f"rebuild-{suffix}", f"proposal-{suffix}-r", 0),
            )
        return (
            Candidate("candidate-a", "proposal-a", 0),
            Candidate("candidate-a", "proposal-a", 0),
            Candidate("candidate-b-reject", "proposal-b", 1),
        )

    def evaluate(self, candidate: Candidate, parent_state_id: str) -> Evaluation:
        if candidate.candidate_id.endswith("reject"):
            return Evaluation(False, None, "rejected")
        digest = hashlib.sha256(canonical_json_bytes({
            "candidate": candidate.candidate_id,
            "parent": parent_state_id,
        })).hexdigest()
        return Evaluation(True, "accepted-v2:" + digest, "accepted")


def _identity(prefix: str, value: Any) -> str:
    return prefix + hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _source(case_id: str) -> tuple[ImmutableSource, dict[str, Any]]:
    if case_id == "toy-structural-integration":
        coefficients = (0.3, -0.2, 0.1)
        indices = (1, 2, 3)
        provenance = {"kind": "synthetic-toy", "candidate_energy_execution": False}
    else:
        path = CHECKPOINTS[case_id]
        checkpoint = json.loads(path.read_text(encoding="utf-8"))
        coefficients = tuple(float(value) for value in checkpoint["ansatz_coefficients"])
        indices = tuple(int(value) for value in checkpoint["ansatz_indices"])
        provenance = {
            "kind": "pinned-checkpoint-structure-only",
            "path": str(path.relative_to(PARENT)),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "candidate_energy_execution": False,
        }
    structure_digest = hashlib.sha256(canonical_json_bytes({
        "coefficients": coefficients, "indices": indices,
    })).hexdigest()
    source = ImmutableSource(
        _identity("state-v1:", {"case_id": case_id, "structure_digest": structure_digest}),
        _identity("problem-v1:", {"case_id": case_id, "gate": "adapter-integration-v2"}),
        coefficients,
        indices,
        structure_digest,
    )
    return source, provenance


def build() -> dict[str, Any]:
    backend = FixtureBackend()
    records: list[dict[str, Any]] = []
    all_events = []
    cases = ("toy-structural-integration", *CHECKPOINTS)
    for case_id in cases:
        source, provenance = _source(case_id)
        for method_id in PRIMARY_METHODS:
            first, ledger = run_comparator(method_id, case_id=case_id, source=source,
                                           backend=backend, cap=CAP)
            second, second_ledger = run_comparator(method_id, case_id=case_id, source=source,
                                                   backend=backend, cap=CAP)
            total = reconstruct(ledger.events)
            records.append({
                "case_id": case_id,
                "method_id": method_id,
                "entrypoint": ENTRYPOINTS[method_id],
                "source_provenance": provenance,
                "deterministic": first == second and ledger.events == second_ledger.events,
                "source_immutable": first.source_digest_before == first.source_digest_after,
                "stop_reason": first.stop_reason,
                "accepted_state_count": len(first.accepted_state_ids),
                "work": asdict(total),
                "event_count": len(ledger.events),
                "event_digest": first.event_digest,
            })
            all_events.extend(ledger.events)
    tiny_cap_failed_closed = False
    source, _ = _source("toy-structural-integration")
    try:
        run_comparator(PRIMARY_METHODS[3], case_id="toy-cap", source=source,
                       backend=backend, cap=WorkVector(N_rounds=1))
    except WorkLedgerError:
        tiny_cap_failed_closed = True
    checks = {
        "three_integration_structures": len(cases) == 3,
        "six_adapters_each": len(records) == len(cases) * len(PRIMARY_METHODS),
        "all_entrypoints_bound": all(record["entrypoint"] for record in records),
        "all_deterministic": all(record["deterministic"] for record in records),
        "all_sources_immutable": all(record["source_immutable"] for record in records),
        "pre_operation_cap_fail_closed": tiny_cap_failed_closed,
        "deduplication_observed": any(event.outcome == "duplicate" for event in all_events),
        "rollback_observed": any(event.outcome == "rollback" for event in all_events),
        "resource_recount_observed": any(event.operation == "full-physical-resource-recount" for event in all_events),
        "all_counter_fields_reconstructable": all(set(record["work"]) == set(FIELDS) for record in records),
        "no_molecular_candidate_energy_executed": all(not record["source_provenance"]["candidate_energy_execution"] for record in records),
    }
    failures = [name for name, passed in checks.items() if not passed]
    result = {
        "schema": "v5-matched-work.adapter-integration-gate.v2",
        "stage": "S4_V2_INTEGRATION",
        "status": "PASS" if not failures else "FAIL",
        "checks": checks,
        "failed_checks": failures,
        "records": records,
        "claim_boundary": (
            "Deterministic adapter/control-flow integration on one synthetic and two pinned checkpoint "
            "structures. No molecular candidate energy was evaluated; this is not performance evidence."
        ),
    }
    result["artifact_digest"] = hashlib.sha256(canonical_json_bytes(result)).hexdigest()
    if failures:
        raise RuntimeError("adapter integration failed: " + ", ".join(failures))
    return result

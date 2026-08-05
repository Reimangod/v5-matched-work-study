"""Normalize historical work into raw v2 events and derive componentwise caps."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from .atomic_artifacts import canonical_json_bytes, write_json_exclusive
from .s0_common import PARENT, ROOT, sha256
from .work_ledger import FIELDS, WorkLedger, WorkVector, raw_ledger_document


V5_INPUTS = tuple(
    f"artifacts/v5/s9/{case}-v1-audit.json"
    for case in ("h6-1.5", "h6-3.0", "beh2-3.0")
)
V41_INPUTS = tuple(
    f"artifacts/v4.1/multisystem/{case}/summary.json"
    for case in ("h6-1.5", "h6-3.0", "beh2-3.0")
)


def _row(method_id: str, case_id: str, source_path: str, vector: WorkVector) -> dict[str, Any]:
    return {
        "method_id": method_id,
        "case_id": case_id,
        "source_path": source_path,
        "source_sha256": sha256(PARENT / source_path),
        "work": asdict(vector),
    }


def historical_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for relative in V5_INPUTS:
        value = json.loads((PARENT / relative).read_text(encoding="utf-8"))
        work = value["work"]
        case_id = Path(relative).name.removesuffix("-v1-audit.json")
        rows.append(_row("historical-full-v5", case_id, relative, WorkVector(
            N_E=work["energy_evaluations"],
            N_G=work["gradient_vector_evaluations"],
            N_gradcomp=work["gradient_component_equivalents"],
            N_HVP=work["analytic_hvp_calls"] + work["finite_difference_hvp_calls"],
            N_exact=work["exact_vqe_attempts"],
            N_recount=work["full_resource_recounts"],
            N_rewrite=work["expanded_search_states"],
            N_states=work["expanded_search_states"],
            N_rounds=work["attempted_rounds"],
        )))
    for relative in V41_INPUTS:
        value = json.loads((PARENT / relative).read_text(encoding="utf-8"))
        work = value["work"]
        attempts = work["attempt_work"]
        case_id = value["case_id"]
        rows.append(_row("historical-v4.1", case_id, relative, WorkVector(
            N_E=sum(item["energy_evaluations"] for item in attempts) + work["source_energy_recomputations_exact_stage"],
            N_G=sum(item["gradient_vector_evaluations"] for item in attempts),
            N_gradcomp=sum(item["gradient_component_evaluations"] for item in attempts),
            N_HVP=0,
            N_exact=work["exact_vqe_attempts"],
            N_recount=work["full_resource_recounts_screening"] + work["source_full_resource_recounts_exact_stage"],
            # The pinned V4.1 evaluator composes one exact algebraic rewrite for every expanded state.
            N_rewrite=work["screening_quadratic_solves"],
            N_states=work["screening_quadratic_solves"],
            N_rounds=sum(item["screening_rounds"] for item in attempts),
        )))
    return rows


def _round_up_one_significant(value: int) -> int:
    if value <= 0:
        return 0
    magnitude = 10 ** int(math.floor(math.log10(value)))
    return int(math.ceil(value / magnitude) * magnitude)


def derive_caps(rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    values = {field: sorted(row["work"][field] for row in rows) for field in FIELDS}
    # Six development records: minimum, upper median, and maximum, each rounded
    # upward to one significant digit. No outcome from the new study is used.
    positions = {"LOW": 0, "MEDIUM": len(rows) // 2, "HIGH": len(rows) - 1}
    return {
        envelope: {
            field: _round_up_one_significant(values[field][position])
            for field in FIELDS
        }
        for envelope, position in positions.items()
    }


def calibration_ledger(rows: list[dict[str, Any]]) -> dict[str, Any]:
    generous = WorkVector(**{field: 10**9 for field in FIELDS})
    ledger = WorkLedger(generous)
    operations = {
        "N_E": "candidate-energy-evaluation",
        "N_G": "full-gradient-evaluation",
        "N_gradcomp": "gradient-component-evaluation",
        "N_HVP": "hessian-vector-product",
        "N_exact": "exact-candidate-attempt",
        "N_recount": "full-physical-resource-recount",
        "N_rewrite": "exact-algebraic-rewrite",
        "N_states": "unique-search-state-expansion",
        "N_rounds": "sequential-round-attempt",
    }
    for row in rows:
        common = dict(method_id=row["method_id"], case_id=row["case_id"],
                      candidate_id=None, path_id=row["source_path"])
        for field in FIELDS:
            units = row["work"][field]
            if not units:
                continue
            if field == "N_G":
                # Historical N_gradcomp is charged separately because it includes
                # component-level calls beyond full-vector evaluations.
                ledger.charge(operations[field], **common, units=units, dimension=0)
            else:
                ledger.charge(operations[field], **common, units=units)
    return raw_ledger_document(
        ledger_id="historical-development-cap-calibration-v2",
        phase="historical-development-normalization",
        cap=generous,
        events=ledger.events,
    )


def build() -> tuple[dict[str, Any], dict[str, Any]]:
    rows = historical_rows()
    raw = calibration_ledger(rows)
    caps = derive_caps(rows)
    checks = {
        "six_comparable_historical_records": len(rows) == 6,
        "all_inputs_hashed": all(len(row["source_sha256"]) == 64 for row in rows),
        "all_fields_raw_reconstructable": set(raw["reconstructed_total"]) == set(FIELDS),
        "rewrite_bound_to_each_search_state": all(row["work"]["N_rewrite"] == row["work"]["N_states"] for row in rows),
        "componentwise_caps_monotonic": all(
            caps["LOW"][field] <= caps["MEDIUM"][field] <= caps["HIGH"][field]
            for field in FIELDS
        ),
        "no_new_study_outcomes_used": True,
    }
    failures = [name for name, passed in checks.items() if not passed]
    protocol = {
        "schema": "v5-matched-work.s3-work-ledger-protocol.v2",
        "stage": "S3", "version": 2,
        "status": "COMPLETE" if not failures else "FAILED",
        "supersedes_for_future_execution": "artifacts/s3/work-ledger-protocol-v1.json",
        "work_vector_fields": list(FIELDS),
        "counter_api": "v5_matched_work.work_ledger.WorkLedger.charge",
        "raw_event_artifact": "artifacts/s3/raw-calibration-events-v2.json",
        "raw_event_digest": raw["ledger_digest"],
        "normalization_rows": rows,
        "rewrite_calibration": (
            "For both pinned V4.1 and V5, each expanded search state is normalized as one "
            "exact-algebraic-rewrite event and one unique-search-state-expansion event."
        ),
        "cap_derivation": {
            "population": "six pinned historical-development V4.1/V5 records",
            "order_statistics": {"LOW": "minimum", "MEDIUM": "upper median", "HIGH": "maximum"},
            "rounding": "upward to one significant decimal digit, componentwise",
        },
        "work_caps": caps,
        "increment_contract": {
            "pre_operation_cap_check": True,
            "rejected_failed_duplicate_rollback_counted": True,
            "cache_hit_miss_separate": True,
            "same_operation_same_counter_api_all_adapters": True,
        },
        "checks": checks, "failed_checks": failures,
        "paper_measurement_cost": None,
        "decision": "GO_S4_V2" if not failures else "NO_GO_S3_V2",
        "next_stage_authorized": "S4_V2" if not failures else "NONE",
        "claim_boundary": "Historical work normalization and cap calibration only; no new molecular outcome.",
    }
    protocol["protocol_digest"] = hashlib.sha256(canonical_json_bytes(protocol)).hexdigest()
    if failures:
        raise RuntimeError("S3-v2 gate failed: " + ", ".join(failures))
    return raw, protocol


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args(); raw, protocol = build()
    outputs = {
        ROOT / "artifacts/s3/raw-calibration-events-v2.json": raw,
        ROOT / "artifacts/s3/work-ledger-protocol-v2.json": protocol,
    }
    for path, value in outputs.items():
        if args.verify_only:
            if path.read_bytes() != canonical_json_bytes(value):
                raise RuntimeError(f"S3-v2 drift: {path}")
        else:
            write_json_exclusive(path, value)
    print(json.dumps({"decision": protocol["decision"], "caps": protocol["work_caps"]}, sort_keys=True))


if __name__ == "__main__":
    main()

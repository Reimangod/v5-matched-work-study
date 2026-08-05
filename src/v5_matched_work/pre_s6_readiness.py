"""Fail-closed executable-readiness audit before any S6 candidate outcome."""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
from typing import Any
from .atomic_artifacts import canonical_json_bytes,write_json_exclusive
from .s0_common import ROOT,sha256


DEPENDENT_STAGES=tuple(range(6,15))


def build()->dict[str,Any]:
    s2=json.loads((ROOT/"artifacts/s2/stationary-source-protocol-v1.json").read_text());s3=json.loads((ROOT/"artifacts/s3/work-ledger-protocol-v1.json").read_text());s4=json.loads((ROOT/"artifacts/s4/comparator-protocol-v1.json").read_text());s5=json.loads((ROOT/"artifacts/s5/development-freeze-v1.json").read_text())
    stationary={item["case_id"] for item in s2["quantum_probe"]["cases"]};scheduled=set(s5["case_order"])
    checks={
        "no_candidate_energy_seen":s5["candidate_energy_evaluations_at_s5"]==0,
        "all_scheduled_sources_stationarity_audited":scheduled.issubset(stationary),
        "six_executable_comparator_entrypoints":all(isinstance(item.get("entrypoint"),str) and item["entrypoint"] for item in s4["comparators"]),
        "shared_counter_increment_locations_bound_to_each_comparator":all("counter_binding" in item for item in s4["comparators"]),
        "toy_h2_h4_new_integration_evidence_present":bool(s4["toy_h2_h4_gate"].get("new_integration_artifact")),
        "n_rewrite_calibrated_from_comparable_raw_events":bool(s3["cap_basis"].get("N_rewrite_raw_event_calibration")),
        "same_structure_and_structural_magnitude_executors_present":all(any(item["method_id"]==method and item.get("entrypoint") for item in s4["comparators"]) for method in ("same-structure-reoptimization","structural-magnitude-pruning")),
    }
    failed=[name for name,passed in checks.items() if not passed]
    result={
        "schema":"v5-matched-work.pre-s6-readiness-incident.v1","stage":"PRE_S6","status":"FAIL_CLOSED","checks":checks,"failed_checks":failed,
        "decision":"NO_GO_EXECUTABLE_MATCHED_WORK_INFRASTRUCTURE_INCOMPLETE","candidate_energy_evaluations":0,"performance_execution_started":False,
        "supersedes_authorizations":["S3 GO_S4 for performance readiness","S4 GO_S5","S5 AUTHORIZED_S6_FROM_TAG_ONLY"],
        "preserved_valid_evidence":["S0 repository isolation","S1 historical correctness replay","S2 four-source stationarity/identity audit","S3 generic work-ledger primitives","S4 comparator contract definitions","S5 pre-outcome queue and protocol draft"],
        "required_repairs_before_new_freeze":["Implement six executable adapters against the immutable source object","instrument identical counter increments in every adapter","run new toy/H2/H4 integration, rollback, deduplication, recount, and determinism tests","add and audit the scheduled H4 source or remove it in a new pre-outcome version","recalibrate all caps from comparable raw events","issue new S3/S4/S5 versions and annotated tags"],
        "claim_boundary":"Infrastructure readiness failure before candidate outcomes; this is not a negative molecular-performance result and supports no V5 matched-work conclusion.",
    }
    result["incident_digest"]=hashlib.sha256(canonical_json_bytes(result)).hexdigest();return result


def not_authorized(stage:int,incident:dict[str,Any])->dict[str,Any]:
    result={"schema":"v5-matched-work.not-authorized.v1","stage":f"S{stage}","status":"NOT_AUTHORIZED","blocking_decision":incident["decision"],"blocking_incident_digest":incident["incident_digest"],"candidate_energy_evaluations":0,"scientific_execution_performed":False,"claim_boundary":"Dependent stage not executed; no performance evidence."};result["record_digest"]=hashlib.sha256(canonical_json_bytes(result)).hexdigest();return result


def main()->None:
    parser=argparse.ArgumentParser();parser.add_argument("--verify-only",action="store_true");args=parser.parse_args();incident=build();root=ROOT/"artifacts/pre-s6"
    outputs={root/"readiness-incident-v1.json":incident,**{ROOT/f"artifacts/s{stage}/not-authorized-v1.json":not_authorized(stage,incident) for stage in DEPENDENT_STAGES}}
    for path,value in outputs.items():
        if args.verify_only:
            if path.read_bytes()!=canonical_json_bytes(value):raise RuntimeError(f"readiness closure drift: {path}")
        else:write_json_exclusive(path,value)
    print(json.dumps({"decision":incident["decision"],"failed_checks":incident["failed_checks"],"not_authorized":[f"S{i}" for i in DEPENDENT_STAGES]},sort_keys=True))
if __name__=="__main__":main()

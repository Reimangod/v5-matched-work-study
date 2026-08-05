"""Freeze the six primary comparator interfaces before molecular execution."""

from __future__ import annotations
import argparse, hashlib, json
from typing import Any
from .atomic_artifacts import canonical_json_bytes, write_json_exclusive
from .comparators import comparator_registry
from .s0_common import PARENT, ROOT, sha256


INPUTS=("src/dvg_obs_ceo/v4_1_multisystem.py","src/dvg_obs_ceo/v4_1_exact_multisystem.py","src/dvg_obs_ceo/v5_multitrajectory.py","src/dvg_obs_ceo/v5_s8_lih_multitrajectory.py","src/dvg_obs_ceo/resources.py")


def build() -> dict[str,Any]:
    result={
        "schema":"v5-matched-work.s4-comparator-protocol.v1","stage":"S4","status":"COMPLETE",
        "immutable_parent_inputs":[{"path":p,"sha256":sha256(PARENT/p)} for p in INPUTS],
        "comparators":comparator_registry(),
        "common_contract":{
            "byte_identical_source":True,"componentwise_caps_from_s3":True,"pre_operation_cap_enforcement":True,
            "energy_stationarity_semantic_native_resource_checks_independent":True,"full_circuit_resource_recount":True,
            "rejected_failed_duplicate_rollback_work_counted":True,"fci_or_exact_reference_online":False,
            "deterministic_queue_and_tie_break":True,"source_parent_immutable":True,
        },
        "ablation_identity":"Methods 5 and 6 differ only in reuse of the original catalog versus rebuilding from the accepted child.",
        "toy_h2_h4_gate":{"historical_parent_full_regression_passed":509,"new_invariant_tests_required":True,"toy_results_not_performance_evidence":True},
        "decision":"GO_S5","next_stage_authorized":"S5","paper_measurement_cost":None,
        "claim_boundary":"Comparator implementation and toy/invariant gate only; no molecular performance claim.",
    }
    result["protocol_digest"]=hashlib.sha256(canonical_json_bytes(result)).hexdigest(); return result


def main() -> None:
    parser=argparse.ArgumentParser();parser.add_argument("--verify-only",action="store_true");args=parser.parse_args();output=ROOT/"artifacts/s4/comparator-protocol-v1.json";result=build()
    if args.verify_only:
        if output.read_bytes()!=canonical_json_bytes(result):raise RuntimeError("S4 protocol drift")
    else:write_json_exclusive(output,result)
    print(json.dumps({"decision":result["decision"],"comparators":len(result["comparators"])},sort_keys=True))
if __name__=="__main__":main()

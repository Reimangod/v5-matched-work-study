"""Pre-outcome development protocol, queue, work-cap, and success freeze."""

from __future__ import annotations
import argparse,hashlib,json
from typing import Any
from .atomic_artifacts import canonical_json_bytes,write_json_exclusive
from .comparators import PRIMARY_METHODS
from .s0_common import PARENT,ROOT,git,sha256


CASES=("lih-3.0","h6-1.5","h6-3.0","beh2-3.0","h4-1.5-known-development")
CAPS=("LOW","MEDIUM","HIGH")
TAG="v5-matched-work-s5-development-freeze-v1"


def _id(prefix:str,payload:Any)->str:return prefix+":"+hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def build()->dict[str,Any]:
    s3=json.loads((ROOT/"artifacts/s3/work-ledger-protocol-v1.json").read_text())
    queue=[]
    for case in CASES:
        for cap in CAPS:
            for method in PRIMARY_METHODS:
                payload={"case_id":case,"work_envelope":cap,"method_id":method}
                queue.append({"queue_item_id":_id("s6-queue-v1",payload),**payload})
    result={
        "schema":"v5-matched-work.s5-development-freeze.v1","stage":"S5","status":"FROZEN_PRE_OUTCOME",
        "planned_annotated_tag":TAG,"builder_commit":git(ROOT,"rev-parse","HEAD"),"dependency_lock":{"path":"uv.lock","sha256":sha256(ROOT/"uv.lock")},
        "source_selection_rule":"Use registered byte-identical development checkpoint; independently reconstruct and require parameter-gradient infinity <=1e-8 before every method. H4 1.5 source is the known V5-S8 checkpoint and must pass the same pre-run source gate.",
        "case_order":list(CASES),"work_envelope_order":list(CAPS),"method_order":list(PRIMARY_METHODS),"work_caps":s3["work_caps"],
        "queue":queue,"queue_generation_rule":"case order × work-envelope order × method order; no outcome-based omission",
        "comparators":list(PRIMARY_METHODS),
        "candidate_order":"frozen parent canonical semantic ID ordering; endpoint then predicted loss then candidate ID; no exact/FCI/actual-energy field",
        "tie_break":"actual nondominated set; CNOT, parameters, total depth, CNOT depth, energy increase, canonical point ID only for display; all frontier points retained",
        "optimizer":{"primary":"pinned parent BFGS","maximum_iterations":1000,"gradient_tolerance":1e-8,"fallback":"registered parent fallback only when frozen trigger fires; all starts/work charged"},
        "tolerances":{"source_relative_energy_budget_hartree":1e-4,"parameter_stationarity_infinity":1e-8,"independent_energy_hartree":1e-10,"state_fidelity_minimum":0.9999999999,"constraint_residual_maximum":1e-10,"dominance_energy_hartree":1e-12,"resource_tolerance":0},
        "pareto":{"axes":["energy_increase_hartree","cnot_count","cnot_depth","total_depth","parameter_count"],"context_unit":"case_id + work_envelope","all_accepted_points_primary":True},
        "failure_policy":{"rerun_only_documented_engineering_incident":True,"threshold_optimizer_catalog_budget_change_after_outcome":False,"partial_failed_rollback_no_candidate_preserved":True,"next_queue_item_runs_after_scientific_failure":True},
        "primary_outputs":["energy loss vs CNOT","energy loss vs CNOT depth","energy loss vs total depth","energy loss vs parameter count","cumulative componentwise work vs resource reduction","context nondominated-point indicator","accepted/rejected/no-candidate/stationarity-failure counts"],
        "go_gate":{"minimum_independent_contexts_full_v5_adds_point_absent_from_v4_1":2,"minimum_contexts_full_v5_adds_point_absent_without_rebuilding":1},
        "no_go":["V4.1 difference disappears after work matching","full V5 and without-rebuilding do not differ","positive is explained by same-structure reoptimization","unresolved certification failure or artifact corruption"],
        "fci_firewall":True,"paper_measurement_cost":None,"candidate_energy_evaluations_at_s5":0,
        "literature_ledger":[
            {"id":"ceo-adapt-vqe-star","doi":"10.1038/s41534-025-01039-4","status":"peer-reviewed","primary_url":"https://www.nature.com/articles/s41534-025-01039-4","supplement_verified":True,"public_code":"https://github.com/mafaldaramoa/ceo-adapt-vqe","local_code_commit":"a3f89d03e6a03c89767d3cf8ee7657a57653dda0"},
            {"id":"pruned-adapt-vqe","doi":"10.1021/acs.jctc.5c00535","status":"peer-reviewed","primary_url":"https://pubs.acs.org/doi/10.1021/acs.jctc.5c00535","supplement_verified":True,"public_code_claim_verified":True,"exact_code_commit":None,"use_now":False},
            {"id":"param-adapt-vqe","doi":"10.1021/acs.jctc.6c00269","status":"DOI_NOT_INDEPENDENTLY_RESOLVED; arXiv preprint verified","primary_url":"https://arxiv.org/abs/2602.04253","supplement_verified":False,"public_code":None,"use_now":False},
            {"id":"circuit-efficient-qeb-vqe","doi":"10.1021/acs.jctc.5c00119","status":"peer-reviewed bibliographic record plus arXiv full text verified","primary_url":"https://arxiv.org/abs/2406.11699","supplement_verified":False,"public_code":None,"use_now":False},
            {"id":"physical-review-a-scope","status":"official-journal-scope-verified","primary_url":"https://journals.aps.org/pra/about","internal_gate_is_official_acceptance_criterion":False},
        ],
        "decision":"AUTHORIZED_S6_FROM_TAG_ONLY","next_stage_authorized":"S6_AFTER_ANNOTATED_TAG",
        "claim_boundary":"Pre-outcome development protocol only. Internal gates are not PRA acceptance criteria; unresolved literature/code details cannot be estimated.",
    }
    result["freeze_digest"]=hashlib.sha256(canonical_json_bytes(result)).hexdigest();return result


def audit(value:dict[str,Any])->dict[str,bool]:
    return {
        "queue_size":len(value["queue"])==len(CASES)*len(CAPS)*len(PRIMARY_METHODS),
        "queue_unique":len({i["queue_item_id"] for i in value["queue"]})==len(value["queue"]),
        "no_candidate_energy":value["candidate_energy_evaluations_at_s5"]==0,
        "six_comparators":tuple(value["comparators"])==PRIMARY_METHODS,
        "caps_fixed":set(value["work_caps"])==set(CAPS),
        "fci_firewall":value["fci_firewall"] is True,
        "success_fixed":value["go_gate"]["minimum_independent_contexts_full_v5_adds_point_absent_from_v4_1"]==2,
        "rerun_fixed":value["failure_policy"]["threshold_optimizer_catalog_budget_change_after_outcome"] is False,
        "literature_boundaries":all(not i.get("use_now",False) for i in value["literature_ledger"] if i["id"]!="ceo-adapt-vqe-star"),
        "measurement_cost_null":value["paper_measurement_cost"] is None,
    }


def main()->None:
    parser=argparse.ArgumentParser();parser.add_argument("--verify-only",action="store_true");args=parser.parse_args();output=ROOT/"artifacts/s5/development-freeze-v1.json";result=build();checks=audit(result)
    if not all(checks.values()):raise RuntimeError("S5 freeze audit failed")
    if args.verify_only:
        stored=json.loads(output.read_text());rebuilt=dict(result);rebuilt["builder_commit"]=stored["builder_commit"];rebuilt["freeze_digest"]=hashlib.sha256(canonical_json_bytes({k:v for k,v in rebuilt.items() if k!="freeze_digest"})).hexdigest()
        if output.read_bytes()!=canonical_json_bytes(rebuilt):raise RuntimeError("S5 freeze drift")
    else:write_json_exclusive(output,result)
    print(json.dumps({"checks":checks,"queue":len(result["queue"]),"decision":result["decision"]},sort_keys=True))
if __name__=="__main__":main()

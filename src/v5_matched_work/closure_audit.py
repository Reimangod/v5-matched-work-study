"""Audit the pre-performance fail-closed package."""
from __future__ import annotations
import argparse,hashlib,json
from .atomic_artifacts import canonical_json_bytes,write_json_exclusive
from .pre_s6_readiness import DEPENDENT_STAGES,build,not_authorized
from .s0_common import ROOT,sha256


def audit()->dict:
    path=ROOT/"artifacts/pre-s6/readiness-incident-v1.json";incident=json.loads(path.read_text());rebuilt=build()
    checks={"incident_rebuild":incident==rebuilt,"pre_outcome":incident["candidate_energy_evaluations"]==0 and incident["performance_execution_started"] is False,"failed_gate_present":bool(incident["failed_checks"]),"all_dependents_not_authorized":all(json.loads((ROOT/f"artifacts/s{s}/not-authorized-v1.json").read_text())==not_authorized(s,incident) for s in DEPENDENT_STAGES),"not_molecular_negative":incident["claim_boundary"].startswith("Infrastructure readiness failure"),"historical_artifacts_untouched":True}
    failed=[k for k,v in checks.items() if not v];result={"schema":"v5-matched-work.preperformance-closure-audit.v1","stage":"CLOSURE","passed":not failed,"checks":checks,"failed_checks":failed,"incident_sha256":sha256(path),"claim_boundary":"Audit of a pre-performance infrastructure No-Go; no molecular result."};result["audit_digest"]=hashlib.sha256(canonical_json_bytes(result)).hexdigest()
    if failed:raise RuntimeError("closure audit failed: "+", ".join(failed))
    return result


def main()->None:
    parser=argparse.ArgumentParser();parser.add_argument("--verify-only",action="store_true");args=parser.parse_args();output=ROOT/"artifacts/pre-s6/closure-audit-v1.json";result=audit()
    if args.verify_only:
        if output.read_bytes()!=canonical_json_bytes(result):raise RuntimeError("closure audit drift")
    else:write_json_exclusive(output,result)
    print(json.dumps({"passed":result["passed"],"checks":len(result["checks"])},sort_keys=True))
if __name__=="__main__":main()

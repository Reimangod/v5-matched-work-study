"""Independent pre-outcome S5 freeze audit."""
from __future__ import annotations
import argparse,hashlib,json,subprocess
from jsonschema import Draft202012Validator
from .atomic_artifacts import canonical_json_bytes,write_json_exclusive
from .s0_common import ROOT,git,sha256
from .s5_freeze import TAG,audit as freeze_checks


def audit()->dict:
    path=ROOT/"artifacts/s5/development-freeze-v1.json";value=json.loads(path.read_text());schema=json.loads((ROOT/"schemas/s5-development-freeze-v1.schema.json").read_text());errors=list(Draft202012Validator(schema).iter_errors(value))
    digest=hashlib.sha256(canonical_json_bytes({k:v for k,v in value.items() if k!="freeze_digest"})).hexdigest()
    checks={"schema_valid":not errors,"freeze_digest":value["freeze_digest"]==digest,**freeze_checks(value),"builder_ancestor":subprocess.run(["git","-C",str(ROOT),"merge-base","--is-ancestor",value["builder_commit"],"HEAD"],check=False).returncode==0,"planned_tag":value["planned_annotated_tag"]==TAG,"s2_s3_s4_present":all((ROOT/f"artifacts/s{stage}").is_dir() for stage in (2,3,4)),"exactly_zero_outcomes":value["candidate_energy_evaluations_at_s5"]==0}
    failed=[k for k,v in checks.items() if not v];result={"schema":"v5-matched-work.s5-freeze-audit.v1","stage":"S5","passed":not failed,"checks":checks,"failed_checks":failed,"schema_errors":[e.message for e in errors],"freeze_sha256":sha256(path),"claim_boundary":"Pre-outcome protocol/queue audit only; no performance evidence."};result["audit_digest"]=hashlib.sha256(canonical_json_bytes(result)).hexdigest()
    if failed:raise RuntimeError("S5 audit failed: "+", ".join(failed))
    return result


def main()->None:
    parser=argparse.ArgumentParser();parser.add_argument("--verify-only",action="store_true");args=parser.parse_args();output=ROOT/"artifacts/s5/development-freeze-audit-v1.json";result=audit()
    if args.verify_only:
        if output.read_bytes()!=canonical_json_bytes(result):raise RuntimeError("S5 audit drift")
    else:write_json_exclusive(output,result)
    print(json.dumps({"passed":result["passed"],"checks":len(result["checks"])},sort_keys=True))
if __name__=="__main__":main()

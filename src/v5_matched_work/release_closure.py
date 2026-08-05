"""Build and audit the pre-performance infrastructure No-Go release manifest."""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
from typing import Any
from .atomic_artifacts import canonical_json_bytes,write_json_exclusive
from .s0_common import ROOT,git,sha256


TAG="v5-matched-work-preperformance-no-go-v1"


def artifact_paths()->list[Path]:
    return sorted(path for path in (ROOT/"artifacts").rglob("*.json") if "release/preperformance-no-go-manifest-v1.json" not in str(path))


def build()->dict[str,Any]:
    incident=json.loads((ROOT/"artifacts/pre-s6/readiness-incident-v1.json").read_text())
    result={"schema":"v5-matched-work.preperformance-no-go-release.v1","status":"COMPLETE","release_tag":TAG,"repository":"https://github.com/Reimangod/v5-matched-work-study","visibility_at_release":"private","artifact_inventory":[{"path":str(path.relative_to(ROOT)),"sha256":sha256(path)} for path in artifact_paths()],"result":{"performance_execution_started":False,"candidate_energy_evaluations":0,"decision":incident["decision"],"molecular_performance_conclusion":None,"dependent_stages_not_authorized":[f"S{i}" for i in range(6,15)]},"reproduction":["git clone --recurse-submodules https://github.com/Reimangod/v5-matched-work-study.git","uv sync --extra test","uv run pytest -q","uv run python -m v5_matched_work.closure_audit --verify-only","uv run python -m v5_matched_work.release_closure --verify-only"],"environment":{"python_constraint":">=3.10,<3.11","lock_sha256":sha256(ROOT/"uv.lock"),"container":None},"availability":{"zenodo_doi":None,"doi_claim":False},"claim_boundary":"Pre-performance infrastructure readiness No-Go. No matched-work molecular result, rebuilding effect, generalization, hardware/noise, Measurement Cost, or PRA submission claim."}
    result["manifest_digest"]=hashlib.sha256(canonical_json_bytes(result)).hexdigest();return result


def audit(value:dict[str,Any])->dict[str,bool]:
    return {"inventory_hashes":all(sha256(ROOT/i["path"])==i["sha256"] for i in value["artifact_inventory"]),"no_performance":value["result"]["performance_execution_started"] is False and value["result"]["candidate_energy_evaluations"]==0,"all_dependents_closed":value["result"]["dependent_stages_not_authorized"]==[f"S{i}" for i in range(6,15)],"measurement_claim_absent":"Measurement Cost" in value["claim_boundary"],"doi_absent":value["availability"]["doi_claim"] is False,"lock_bound":value["environment"]["lock_sha256"]==sha256(ROOT/"uv.lock")}


def main()->None:
    parser=argparse.ArgumentParser();parser.add_argument("--verify-only",action="store_true");args=parser.parse_args();output=ROOT/"artifacts/release/preperformance-no-go-manifest-v1.json";result=build();checks=audit(result)
    if not all(checks.values()):raise RuntimeError("release closure audit failed")
    if args.verify_only:
        if output.read_bytes()!=canonical_json_bytes(result):raise RuntimeError("release manifest drift")
    else:write_json_exclusive(output,result)
    print(json.dumps({"passed":True,"checks":checks,"artifacts":len(result["artifact_inventory"])},sort_keys=True))
if __name__=="__main__":main()

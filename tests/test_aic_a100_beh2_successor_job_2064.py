import hashlib
import json
from pathlib import Path

from v5_matched_work.atomic_artifacts import canonical_json_bytes


ROOT = Path(__file__).resolve().parents[1]
RESULT_ROOT = (
    ROOT
    / "artifacts/aic-a100-dual-optimizer-v1/results/beh2-successor-job-2064"
)
EXECUTION_ROOT = RESULT_ROOT / "7067e7893000aafe602ed812aef4ab07d9b9b235"
ATTESTATION = RESULT_ROOT / "attestation/terminal-attestation-v1.json"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_job_2064_terminal_attestation_is_digest_bound_and_claim_safe():
    attestation = load(ATTESTATION)
    body = {key: value for key, value in attestation.items() if key != "record_digest"}
    assert attestation["record_digest"] == hashlib.sha256(
        canonical_json_bytes(body)
    ).hexdigest()
    assert attestation["status"] == "GO_DUAL_A100_SCIENTIFIC_EXECUTION_SUCCESSOR_V1"
    assert attestation["successor"]["job_id"] == "2064"
    assert attestation["successor"]["state"] == "COMPLETED"
    assert all(attestation["checks"].values())
    assert attestation["scientific_boundary"]["FCI_evaluations"] == 0
    assert attestation["scientific_boundary"]["performance_claim"] == "NOT_AUTHORIZED"


def test_job_2064_raw_evidence_hashes_are_exact():
    attestation = load(ATTESTATION)
    paths = {
        "beh2_start": EXECUTION_ROOT / "beh2/start.json",
        "beh2_scientific_result": EXECUTION_ROOT / "beh2/scientific-result.json",
        "beh2_terminal": EXECUTION_ROOT / "beh2/terminal.json",
        "merged_decision": EXECUTION_ROOT / "merged-decision-v1.json",
        "slurm_stdout": RESULT_ROOT / "slurm-2064.out",
    }
    assert {name: sha256(path) for name, path in paths.items()} == attestation[
        "evidence_sha256"
    ]


def test_job_2064_scientific_and_merged_certificates_pass_without_speed_claim():
    scientific = load(EXECUTION_ROOT / "beh2/scientific-result.json")
    terminal = load(EXECUTION_ROOT / "beh2/terminal.json")
    merged = load(EXECUTION_ROOT / "merged-decision-v1.json")
    assert scientific["status"] == "PASS"
    assert all(scientific["checks"].values())
    assert scientific["route_counters"]["gpu"]["N_cpu_fallback"] == 0
    assert terminal["status"] == "PASS"
    assert terminal["speed_used_for_decision"] is False
    assert merged["status"] == "GO_DUAL_A100_SCIENTIFIC_EXECUTION_SUCCESSOR_V1"
    assert all(merged["checks"].values())
    assert merged["scientific_boundary"]["CPU_speed_comparison"] == (
        "NOT_REQUIRED_AND_NOT_USED"
    )

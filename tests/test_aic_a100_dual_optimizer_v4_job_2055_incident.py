import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INCIDENT = (
    ROOT
    / "artifacts"
    / "aic-a100-dual-optimizer-v1"
    / "incidents"
    / "v4-job-2055-timeout-v1"
    / "incident-v1.json"
)
RESULT_ROOT = (
    ROOT
    / "artifacts"
    / "aic-a100-dual-optimizer-v1"
    / "results"
    / "v4-job-2055"
)
EXECUTION_ROOT = (
    RESULT_ROOT / "c6521c2057e67faa45041fcf0f84e828268317a3"
)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_job_2055_is_a_fail_closed_three_case_no_go():
    incident = load(INCIDENT)
    assert incident["status"] == "NO_GO_DUAL_A100_BEH2_TIME_CAP_V1"
    assert incident["scientific_terminal_states"] == {
        "h2": "PASS",
        "h6": "PASS",
        "beh2": "NO_TERMINAL_SCIENTIFIC_RESULT",
    }
    assert incident["checks"]["all_three_cases_passed"] is False
    assert incident["checks"]["merged_go_authorized"] is False
    assert incident["scientific_boundary"]["performance_claim"] == "NOT_AUTHORIZED"
    assert incident["scientific_boundary"]["FCI_evaluations"] == 0


def test_job_2055_raw_evidence_is_complete_and_digest_bound():
    incident = load(INCIDENT)
    paths = {
        "h2_start": EXECUTION_ROOT / "shards/0000-h2/start.json",
        "h2_scientific_result": EXECUTION_ROOT
        / "shards/0000-h2/scientific-result.json",
        "h2_terminal": EXECUTION_ROOT / "shards/0000-h2/terminal.json",
        "h6_start": EXECUTION_ROOT / "shards/0001-h6/start.json",
        "h6_scientific_result": EXECUTION_ROOT
        / "shards/0001-h6/scientific-result.json",
        "h6_terminal": EXECUTION_ROOT / "shards/0001-h6/terminal.json",
        "beh2_start": EXECUTION_ROOT / "shards/0002-beh2/start.json",
        "beh2_slurm_stderr": RESULT_ROOT / "slurm-2055_2.err",
    }
    assert {name: sha256(path) for name, path in paths.items()} == incident[
        "evidence_sha256"
    ]
    assert not (EXECUTION_ROOT / "shards/0002-beh2/scientific-result.json").exists()
    assert not (EXECUTION_ROOT / "shards/0002-beh2/terminal.json").exists()
    assert "DUE TO TIME LIMIT" in (RESULT_ROOT / "slurm-2055_2.err").read_text(
        encoding="utf-8"
    )


def test_completed_cases_preserve_gpu_and_cpu_certificate_boundaries():
    records = [
        load(EXECUTION_ROOT / "shards/0000-h2/scientific-result.json"),
        load(EXECUTION_ROOT / "shards/0001-h6/scientific-result.json"),
    ]
    for record in records:
        assert record["status"] == "PASS"
        assert all(record["checks"].values())
        assert record["checks"]["GPU_objective_was_invoked"] is True
        assert record["checks"]["no_CPU_fallback"] is True
        assert record["checks"]["no_full_cpu_optimization"] is True
        assert record["scientific_boundary"]["performance_claim"] == "NOT_AUTHORIZED"

    h2_terminal = load(EXECUTION_ROOT / "shards/0000-h2/terminal.json")
    h6_terminal = load(EXECUTION_ROOT / "shards/0001-h6/terminal.json")
    assert max(
        h2_terminal["started_unix_ns"], h6_terminal["started_unix_ns"]
    ) < min(h2_terminal["ended_unix_ns"], h6_terminal["ended_unix_ns"])
    assert (
        h2_terminal["gpu"]["gpu_uuid_sha256"]
        != h6_terminal["gpu"]["gpu_uuid_sha256"]
    )

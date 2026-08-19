from __future__ import annotations

import json

from v5_final import gpu_rtx2080ti_s1_hardware_audit_v1 as s1


def _runner(arguments: list[str]) -> dict[str, object]:
    if "--query-gpu=index,uuid,name,memory.total,driver_version,compute_cap,compute_mode" in arguments:
        return {
            "arguments": arguments,
            "returncode": 0,
            "stdout": "0, GPU-test, NVIDIA GeForce RTX 2080 Ti, 11019, 535.1, 7.5, Default",
            "stderr": "",
        }
    if any(value.startswith("--query-compute-apps") for value in arguments):
        return {"arguments": arguments, "returncode": 0, "stdout": "", "stderr": ""}
    return {
        "arguments": arguments,
        "returncode": 0,
        "stdout": "Cuda compilation tools, release 11.8",
        "stderr": "",
    }


def test_gpu_row_parser_is_strict() -> None:
    rows = s1._parse_gpu_rows(
        "0, GPU-test, NVIDIA GeForce RTX 2080 Ti, 11019, 535.1, 7.5, Default"
    )
    assert rows == [
        {
            "index": 0,
            "uuid": "GPU-test",
            "name": "NVIDIA GeForce RTX 2080 Ti",
            "memory_total_mib": 11019,
            "driver_version": "535.1",
            "compute_capability": "7.5",
            "compute_mode": "Default",
        }
    ]


def test_missing_optional_diagnostic_command_is_recorded(monkeypatch) -> None:
    def missing(*args, **kwargs):
        raise FileNotFoundError("nvcc not found")

    monkeypatch.setattr(s1.subprocess, "run", missing)
    result = s1._run(["nvcc", "--version"])
    assert result["returncode"] == 127
    assert result["stdout"] == ""
    assert "nvcc not found" in result["stderr"]


def test_capture_go_requires_exact_hardware_and_capacity(monkeypatch) -> None:
    monkeypatch.setattr(s1.platform, "system", lambda: "Linux")
    monkeypatch.setattr(s1.platform, "platform", lambda: "Linux-test")
    monkeypatch.setattr(s1.os, "cpu_count", lambda: 2)
    monkeypatch.setattr(s1, "_memory_total_bytes", lambda: 8 * s1.GIB)
    monkeypatch.setattr(
        s1.shutil,
        "disk_usage",
        lambda _: s1.shutil._ntuple_diskusage(100 * s1.GIB, 40 * s1.GIB, 60 * s1.GIB),
    )
    artifact = s1.capture(runner=_runner)
    assert artifact["decision"] == "GO_RTX2080TI_S2_ENVIRONMENT_ONLY"
    assert not artifact["failed_checks"]
    assert artifact["authorization"]["molecular_candidate_outcomes"] == "NOT_AUTHORIZED"


def test_active_gpu_process_fails_closed(monkeypatch) -> None:
    def active_runner(arguments: list[str]) -> dict[str, object]:
        value = _runner(arguments)
        if any(item.startswith("--query-compute-apps") for item in arguments):
            value["stdout"] = "GPU-test, 123, python, 100"
        return value

    monkeypatch.setattr(s1.platform, "system", lambda: "Linux")
    monkeypatch.setattr(s1.os, "cpu_count", lambda: 2)
    monkeypatch.setattr(s1, "_memory_total_bytes", lambda: 8 * s1.GIB)
    monkeypatch.setattr(
        s1.shutil,
        "disk_usage",
        lambda _: s1.shutil._ntuple_diskusage(100 * s1.GIB, 40 * s1.GIB, 60 * s1.GIB),
    )
    artifact = s1.capture(runner=active_runner)
    assert artifact["decision"] == "NO_GO_RTX2080TI_S1_HARDWARE_AUDIT"
    assert "no_preexisting_compute_process" in artifact["failed_checks"]


def test_audit_accepts_digest_bound_go_artifact(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(s1.platform, "system", lambda: "Linux")
    monkeypatch.setattr(s1.os, "cpu_count", lambda: 2)
    monkeypatch.setattr(s1, "_memory_total_bytes", lambda: 8 * s1.GIB)
    monkeypatch.setattr(
        s1.shutil,
        "disk_usage",
        lambda _: s1.shutil._ntuple_diskusage(100 * s1.GIB, 40 * s1.GIB, 60 * s1.GIB),
    )
    artifact = s1.capture(runner=_runner)
    path = tmp_path / "s1.json"
    path.write_text(json.dumps(artifact), encoding="utf-8")
    assert s1.audit(path)["passed"] is True

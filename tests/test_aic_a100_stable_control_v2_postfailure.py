from __future__ import annotations

from aic_a100_pilot.common import (
    ROOT,
    embedded_digest_valid,
    load_json,
    sha256_file,
)
from aic_a100_pilot.stable_control_v2_contract import CONTRACT as V2_CONTRACT
from aic_a100_pilot.stable_control_v2_h6_no_go import (
    EXPECTED_FAILED_CHECKS,
    EXPECTED_H6_RESULT_SHA256,
    H6_RESULT,
    NO_GO,
    no_go_body,
    validate_h6_result,
)
from aic_a100_pilot.stable_control_v2_postfailure_contract import (
    CONTRACT,
    SOURCE_PATHS,
    VALIDATION_PATHS,
    contract_body,
)
from aic_a100_pilot import stable_control_v2_postfailure_route as diagnostic_route
from aic_a100_pilot import stable_control_v2_route as v2_route


EXPECTED_V2_CONTRACT_SHA256 = (
    "ebceff005c7ce1aab2f483d1f4273fa2b2a1f102e9c63f98b86d7b2e3d36b185"
)


def test_h6_raw_terminal_result_is_exact_and_fail_closed():
    result = validate_h6_result()
    assert sha256_file(H6_RESULT) == EXPECTED_H6_RESULT_SHA256
    assert result["status"] == "FAIL"
    assert {key for key, value in result["checks"].items() if not value} == (
        EXPECTED_FAILED_CHECKS
    )
    assert result["cpu"]["terminal_decision"] == "REJECTED"
    assert result["gpu"]["terminal_decision"] == "REJECTED"
    assert result["route_counters"]["gpu"]["N_cpu_fallback"] == 0
    assert result["scientific_boundary"]["FCI_evaluations"] == 0


def test_h6_no_go_does_not_misclassify_failure_as_gpu_hardware_failure():
    value = no_go_body()
    assert value["status"] == "NO_GO_A100_STABLE_CONTROL_V2_H6_PARITY"
    interpretation = value["scientific_interpretation"]
    assert not interpretation["engineering_exception"]
    assert interpretation["CPU_terminal_decision"] == "REJECTED"
    assert interpretation["GPU_terminal_decision"] == "REJECTED"
    assert interpretation["frozen_historical_CPU_terminal_decision"] == (
        "ACCEPTED"
    )
    assert value["authorized_successor"]["H6_retry"] == "NOT_AUTHORIZED"
    assert value["authorized_successor"]["BeH2_single_diagnostic"].startswith(
        "AUTHORIZED"
    )
    published = load_json(NO_GO)
    assert embedded_digest_valid(published, "incident_digest")


def test_postfailure_contract_changes_policy_scope_but_not_numerics():
    value = contract_body()
    v2 = load_json(V2_CONTRACT)
    assert sha256_file(V2_CONTRACT) == EXPECTED_V2_CONTRACT_SHA256
    assert value["status"] == "GO_ONE_BEH2_POST_FAILURE_DIAGNOSTIC_ONLY"
    assert value["execution_scope"]["alias"] == "beh2"
    assert value["execution_scope"]["maximum_attempts"] == 1
    assert value["execution_scope"]["H6_retry"] == "NOT_AUTHORIZED"
    unchanged = value["unchanged_numerical_contract"]
    assert unchanged["route_contract"] == v2["route_contract"]
    assert unchanged["optimizer_contract"] == v2["optimizer_contract"]
    assert unchanged["parity_requirements"] == v2["parity_requirements"]
    assert not any(
        unchanged[key]
        for key in (
            "candidate_changed",
            "ansatz_changed",
            "optimizer_changed",
            "control_quantization_changed",
            "threshold_changed",
            "molecular_source_changed",
        )
    )
    assert value["required_terminal_prefix"]["h6"] == "FAIL_BOUND_TO_NO_GO"
    assert value["scientific_boundary"]["A100_production_adoption"] == (
        "NOT_AUTHORIZED"
    )
    assert value["scientific_boundary"]["BeH2_independent_confirmation_claim"] == (
        "NOT_AUTHORIZED"
    )
    assert value["source_binding"] == {
        path.relative_to(ROOT).as_posix(): sha256_file(path)
        for path in SOURCE_PATHS
    }
    assert value["validation_binding"] == {
        path.relative_to(ROOT).as_posix(): sha256_file(path)
        for path in VALIDATION_PATHS
    }


def test_postfailure_batch_is_one_case_non_overwriting_diagnostic():
    batch = (
        ROOT / "scripts/aic/a100_stable_control_v2_beh2_diagnostic.sbatch"
    ).read_text(encoding="utf-8")
    assert 'namespace="${root}/p9-stable-control-v2-postfailure-diagnostic"' in batch
    assert 'source_results="${root}/p8-unified-stable-v2/results"' in batch
    assert "stable_control_v2_prepare" in batch
    assert "--case beh2" in batch
    assert "stable_control_v2_postfailure_route" in batch
    assert "A100_CASE" not in batch
    assert "candidate_attempt_timing" not in batch


def test_published_postfailure_contract_is_content_addressed():
    if not CONTRACT.is_file():
        return
    value = load_json(CONTRACT)
    assert embedded_digest_valid(value, "contract_digest")
    assert value["source_binding"] == {
        path.relative_to(ROOT).as_posix(): sha256_file(path)
        for path in SOURCE_PATHS
    }


def test_diagnostic_runner_relabels_policy_without_changing_v2_module(
    monkeypatch, tmp_path
):
    original_predecessor = v2_route._require_predecessors

    def fake_prefix(alias, source_results, numerical, successor):
        del source_results, numerical, successor
        assert alias == "beh2"
        return [
            {"alias": alias, "status": status, "record_digest": alias, "sha256": alias}
            for alias, status in (
                ("h2", "PASS"),
                ("h4", "PASS"),
                ("lih", "PASS"),
                ("h6", "FAIL"),
            )
        ]

    def fake_run(alias, **kwargs):
        assert alias == "beh2"
        prefix = v2_route._require_predecessors(
            alias, kwargs["output_dir"], kwargs["contract"]
        )
        assert [item["status"] for item in prefix] == [
            "PASS",
            "PASS",
            "PASS",
            "FAIL",
        ]
        return {
            "schema": "aic-a100-pilot.stable-control-trajectory-case.v2",
            "status": "PASS",
            "record_digest": "synthetic-v2-digest",
            "contract_digest": kwargs["contract"]["contract_digest"],
            "checks": {"predecessor_prefix_passed": True, "numerical": True},
            "scientific_boundary": {},
            "predecessors": prefix,
        }

    monkeypatch.setattr(diagnostic_route, "_terminal_prefix", fake_prefix)
    monkeypatch.setattr(v2_route, "_run_case_impl", fake_run)
    result = diagnostic_route.run_diagnostic(
        prepared_bundle=tmp_path / "unused.pickle",
        prepared_manifest=tmp_path / "unused.json",
        source_results=tmp_path / "source-results",
        start={"start_digest": "synthetic-start"},
        capture={},
    )
    assert v2_route._require_predecessors is original_predecessor
    assert result["status"] == "DIAGNOSTIC_PASS"
    assert result["checks"]["registered_postfailure_terminal_prefix"]
    assert "predecessor_prefix_passed" not in result["checks"]
    assert result["execution_policy"][
        "H6_failure_was_not_reclassified_as_PASS"
    ]
    assert result["scientific_boundary"]["A100_production_adoption"] == (
        "NOT_AUTHORIZED"
    )

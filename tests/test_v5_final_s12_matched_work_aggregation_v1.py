from collections import Counter

from v5_final.s12_matched_work_aggregation_v1 import (
    EXPECTED_STATUSES,
    METHOD_SOURCE,
    PARETO_OBJECTIVES,
    build_long_form_rows,
    build_paired_records,
    build_pareto,
    build_status_records,
)


def test_long_form_is_exact_90_and_preserves_all_terminal_statuses() -> None:
    rows, bindings = build_long_form_rows()
    assert len(rows) == 90
    assert dict(Counter(row["terminal_status"] for row in rows)) == EXPECTED_STATUSES
    assert len(bindings["queue_v2_digest"]) == 64
    assert len(bindings["FCI_result_digest"]) == 64
    assert all(row["FCI_evaluations"] == 0 for row in rows)
    assert all(row["production_N_dense_expm"] == 0 for row in rows)


def test_item000_is_permanent_engineering_NA_without_imputation() -> None:
    rows, _ = build_long_form_rows()
    item = rows[0]
    assert item["case_id"] == "lih-3.0"
    assert item["budget"] == "LOW"
    assert item["method_id"] == METHOD_SOURCE
    assert item["terminal_status"] == "FAILED_ENGINEERING_PRESERVED"
    assert item["energy_hartree"] is None
    assert item["parameter_count"] is None
    assert item["comparison_eligible"] is False


def test_rejected_observations_are_never_comparison_eligible() -> None:
    rows, _ = build_long_form_rows()
    rejected = [row for row in rows if row["terminal_status"] == "ALGORITHM_REJECTED"]
    assert len(rejected) == 23
    assert all(row["metric_semantics"] == "nonaccepted_terminal_observation" for row in rejected)
    assert all(row["comparison_eligible"] is False for row in rejected)
    assert all(row["accepted_candidate_count"] == 0 for row in rejected)


def test_work_totals_are_nonnegative_and_exclude_dimension_metadata() -> None:
    rows, _ = build_long_form_rows()
    for row in rows:
        expected = sum(
            row[name] for name in (
                "N_symbolic_checks", "N_sparse_expm_multiply",
                "N_state_probe_vectors", "N_dense_expm",
                "N_circuit_operator_builds", "N_generator_materializations",
                "candidate_generations", "unique_semantic_candidates",
                "unique_physical_states", "rewrite_verifications",
                "resource_recounts", "optimizer_iterations", "energy_evaluations",
                "gradient_vector_evaluations", "gradient_component_equivalents",
                "hvp_evaluations", "optimizer_starts", "search_states",
                "statevector_recomputations",
            )
        )
        assert row["total_registered_work"] == expected
        assert expected >= 0


def test_paired_comparisons_require_both_completed_and_report_sample_loss() -> None:
    rows, _ = build_long_form_rows()
    paired = build_paired_records(rows)
    assert len(paired) == 75
    assert any(record["ineligibility_reason"] == "immutable_source_not_completed" for record in paired)
    for record in paired:
        if not record["paired_eligible"]:
            assert record["reduction_cnot_count_percent"] is None
            assert record["delta_energy_hartree"] is None


def test_status_summary_records_one_shot_zero_completed() -> None:
    rows, _ = build_long_form_rows()
    records = build_status_records(rows)
    one_shot = next(
        record for record in records
        if record["group_type"] == "method"
        and record["group_id"] == "v4.1-one-shot-joint-compression"
    )
    assert one_shot["n_COMPLETED"] == 0
    assert one_shot["n_ALGORITHM_REJECTED"] == 12
    assert one_shot["n_CAP_REJECTED"] == 3


def test_pareto_is_non_scalar_and_excludes_noncompleted_rows() -> None:
    rows, _ = build_long_form_rows()
    pareto = build_pareto(rows)
    assert tuple(pareto["definition"]["objectives"]) == PARETO_OBJECTIVES
    assert pareto["definition"]["scalar_weighting"] == "not used"
    assert len(pareto["paired_source_dominance"]) == 75
    assert all(
        record["terminal_status"] != "COMPLETED"
        for record in pareto["exclusions"]
    )

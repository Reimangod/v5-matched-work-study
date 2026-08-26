from v5_final.s12_scientific_report_v1 import build_summary, render_report


def test_summary_preserves_exact_population_and_negative_results() -> None:
    summary = build_summary()
    assert summary["population"]["queue_items"] == 90
    assert summary["population"]["terminal_status_counts"] == {
        "ALGORITHM_REJECTED": 23,
        "CAP_REJECTED": 8,
        "COMPLETED": 58,
        "FAILED_ENGINEERING_PRESERVED": 1,
    }
    one_shot = next(
        item for item in summary["method_status"]
        if item["method_id"] == "v4.1-one-shot-joint-compression"
    )
    assert one_shot["COMPLETED"] == 0
    assert one_shot["ALGORITHM_REJECTED"] == 12
    assert one_shot["CAP_REJECTED"] == 3


def test_paired_summary_has_explicit_sample_sizes_and_no_imputation() -> None:
    summary = build_summary()
    paired = {item["method_id"]: item for item in summary["paired_summary"]}
    assert paired["same-structure-reoptimization"]["paired_n"] == 14
    assert paired["structural-magnitude-pruning"]["paired_n"] == 9
    assert paired["v4.1-one-shot-joint-compression"]["paired_n"] == 0
    assert paired["v4.1-one-shot-joint-compression"][
        "reduction_cnot_count_percent"
    ] is None
    assert paired["v5-fixed-source-whitelist-no-replenishment"]["paired_n"] == 9


def test_pareto_and_v5_method_interpretation_are_non_scalar_and_bounded() -> None:
    summary = build_summary()
    dominance = {
        item["method_id"]: item
        for item in summary["pareto"]["paired_source_dominance"]
    }
    assert dominance["same-structure-reoptimization"]["SOURCE_DOMINATES_COMPARATOR"] == 14
    assert dominance["v5-fixed-source-whitelist-no-replenishment"][
        "COMPARATOR_DOMINATES_SOURCE"
    ] == 0
    assert summary["fixed_vs_sequential"][
        "terminal_energy_and_physical_resources_equal_all_15_cells"
    ]
    assert len(summary["fixed_vs_sequential"]["registered_work_difference_cells"]) == 4


def test_report_states_generalization_measurement_and_H4_boundaries() -> None:
    report = render_report(build_summary())
    assert "H4 is known development" in report
    assert "Measurement Cost" in report
    assert "not substituted" in report
    assert "General superiority" in report
    assert "does not establish inferior energy performance" in report

from v5_final.parent_native_development_runtime_factory_v1 import (
    build_queue_bound_development_runtime_v1,
)
from v5_final.s11_v2_execution_readiness_v3 import inspect_outcome_free


ITEM000_PREDECESSOR = (
    "development-queue-item-v4:"
    "7e9fb84e4398661a325bc2e75ccbe81a0130e6761b73872183edebf052c42553"
)


def test_post_incident_inspection_preserves_terminal_and_zero_outcomes() -> None:
    evidence = inspect_outcome_free()
    assert all(evidence["checks"].values())
    assert evidence["observed_outcomes"]["terminal_count"] == 1
    assert evidence["observed_outcomes"]["candidate_energy_evaluations"] == 0


def test_exact_one_thread_queue_environment_rebuilds_source_without_outcomes() -> None:
    context = build_queue_bound_development_runtime_v1(ITEM000_PREDECESSOR)
    assert context._actual_algorithm.molecule.fci_energy is None
    assert context._actual_algorithm.molecule.ccsd_energy is None
    assert context.runtime.metadata["source_checkpoint_digest"]

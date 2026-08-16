from pathlib import Path

import pytest

from v5_final.full_repository_suite_v2 import (
    FullRepositorySuiteError,
    THREAD_KEYS,
    frozen_environment,
    partition_test_modules,
    suite_plan,
)


def test_partition_is_complete_disjoint_and_uses_historical_lineage() -> None:
    plan = suite_plan()
    one = set(plan["partitions"]["1"]["modules"])
    two = set(plan["partitions"]["2"]["modules"])
    assert plan["coverage_exactly_once"] is True
    assert not one & two
    assert len(one | two) == plan["total_modules"]
    assert two
    assert all(
        Path(path).name.startswith(("test_v5_final_s8", "test_v5_final_s9"))
        for path in two
    )
    assert all(
        not Path(path).name.startswith(("test_v5_final_s8", "test_v5_final_s9"))
        for path in one
    )


@pytest.mark.parametrize("threads", [1, 2])
def test_environment_exactly_matches_frozen_contract(threads: int) -> None:
    environment = frozen_environment(threads)
    assert {key: environment[key] for key in THREAD_KEYS} == {
        key: str(threads) for key in THREAD_KEYS
    }


def test_duplicate_discovery_input_is_fail_closed(tmp_path: Path) -> None:
    module = tmp_path / "test_example.py"
    with pytest.raises(FullRepositorySuiteError, match="duplicate"):
        partition_test_modules((module, module))

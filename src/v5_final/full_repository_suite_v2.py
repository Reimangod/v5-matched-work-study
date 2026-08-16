"""Run every repository test under its frozen thread-environment contract.

The S8/S9 lineage was frozen with two BLAS/OpenMP threads.  The current
S11-v2 lineage is frozen with one.  A single pytest process cannot honestly
represent both contracts, so this launcher partitions test modules before
Python imports NumPy and proves that every discovered module is run once.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Iterable

from .s0_successor import ROOT


THREAD_KEYS = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")
HISTORICAL_TWO_THREAD_PREFIXES = (
    "test_v5_final_s8",
    "test_v5_final_s9",
)


class FullRepositorySuiteError(RuntimeError):
    pass


def discover_test_modules(tests_dir: Path | None = None) -> tuple[Path, ...]:
    directory = tests_dir or ROOT / "tests"
    return tuple(sorted(directory.glob("test_*.py")))


def partition_test_modules(
    modules: Iterable[Path],
) -> dict[int, tuple[Path, ...]]:
    discovered = tuple(modules)
    if len(discovered) != len(set(discovered)):
        raise FullRepositorySuiteError("duplicate test module in discovery input")
    two_thread = tuple(
        path for path in discovered
        if path.name.startswith(HISTORICAL_TWO_THREAD_PREFIXES)
    )
    two_thread_set = set(two_thread)
    one_thread = tuple(path for path in discovered if path not in two_thread_set)
    if set(one_thread) & two_thread_set:
        raise FullRepositorySuiteError("thread-contract partitions overlap")
    if set(one_thread) | two_thread_set != set(discovered):
        raise FullRepositorySuiteError("thread-contract partitions are incomplete")
    return {1: one_thread, 2: two_thread}


def frozen_environment(thread_count: int) -> dict[str, str]:
    if thread_count not in (1, 2):
        raise FullRepositorySuiteError(f"unsupported frozen thread count: {thread_count}")
    environment = dict(os.environ)
    environment.update({key: str(thread_count) for key in THREAD_KEYS})
    source_paths = (
        str(ROOT / "src"),
        str(ROOT / "provenance/dvg-obs-ceo/src"),
        str(ROOT / "provenance/dvg-obs-ceo/vendor/ceo-adapt-vqe"),
    )
    existing = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        os.pathsep.join(source_paths)
        if not existing
        else os.pathsep.join((*source_paths, existing))
    )
    return environment


def suite_plan(tests_dir: Path | None = None) -> dict[str, object]:
    modules = discover_test_modules(tests_dir)
    partitions = partition_test_modules(modules)
    partition_records = {
        str(threads): {
            "thread_environment": {key: str(threads) for key in THREAD_KEYS},
            "modules": [str(path.relative_to(ROOT)) for path in paths],
        }
        for threads, paths in partitions.items()
    }
    return {
        "schema": "v5-final.full-repository-suite-plan.v2",
        "total_modules": len(modules),
        "partitions": partition_records,
        "coverage_exactly_once": sum(
            len(paths) for paths in partitions.values()
        ) == len(modules),
    }


def run_suite(*, extra_pytest_args: tuple[str, ...] = ()) -> int:
    modules = discover_test_modules()
    partitions = partition_test_modules(modules)
    return_codes: list[int] = []
    for threads in (1, 2):
        paths = partitions[threads]
        if not paths:
            continue
        command = [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            *(str(path.relative_to(ROOT)) for path in paths),
            *extra_pytest_args,
        ]
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env=frozen_environment(threads),
            check=False,
        )
        return_codes.append(completed.returncode)
    return next((code for code in return_codes if code != 0), 0)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", action="store_true")
    args, pytest_args = parser.parse_known_args()
    if args.plan:
        print(json.dumps(suite_plan(), indent=2, sort_keys=True))
        return
    raise SystemExit(run_suite(extra_pytest_args=tuple(pytest_args)))


if __name__ == "__main__":
    main()

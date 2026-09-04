from __future__ import annotations

import json

import pytest

from phase1_frontier.a5_successor_v2 import QUEUE_PATH
from phase1_frontier.v2_runner_adapter import (
    V2RunnerBindingError,
    bind_request,
    execute_bound_request,
    load_frozen_queue,
)


def test_frozen_queue_loads_without_outcome_work() -> None:
    queue = load_frozen_queue()
    assert queue["counts"]["requests"] == 1_266
    assert queue["counts"]["candidate_energy_evaluations"] == 0
    assert queue["counts"]["optimizer_starts"] == 0
    assert queue["counts"]["FCI_evaluations"] == 0


@pytest.mark.parametrize("ordinal", [0, 1, 1264, 1265])
def test_representative_requests_reconstruct_exactly(ordinal: int) -> None:
    queue = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
    row = queue["items"][ordinal]
    bound = bind_request(row["RequestID"])
    assert bound.row == row
    assert len(bound.initial_coordinates) == row["target_parameter_count"]
    assert bound.initial_inverse_hessian.shape == (
        row["target_parameter_count"],
        row["target_parameter_count"],
    )
    assert bound.work_request.queue_item_id == row["RequestID"]
    assert bound.work_request.frozen_queue_digest == queue["queue_digest"]
    assert bound.cap.optimizer_iterations == 2_000
    assert bound.cap.energy_evaluations == 2_500


def test_unknown_request_is_rejected_before_kernel_work() -> None:
    with pytest.raises(V2RunnerBindingError, match="unknown or duplicate"):
        bind_request("phase1-v2-request:" + "f" * 64)


def test_molecular_execution_is_blocked_before_s4(tmp_path) -> None:
    with pytest.raises(V2RunnerBindingError, match="blocked until a valid S4"):
        execute_bound_request(
            "phase1-v2-request:" + "f" * 64,
            tmp_path / "must-not-exist",
        )
    assert not (tmp_path / "must-not-exist").exists()

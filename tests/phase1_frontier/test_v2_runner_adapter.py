from __future__ import annotations

import json

import pytest

from phase1_frontier.a5_successor_v2 import QUEUE_PATH
from phase1_frontier.v2_runner_adapter import (
    V2RunnerBindingError,
    _validate_frozen_execution_order,
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


def test_unregistered_molecular_request_is_blocked_before_kernel_work(tmp_path) -> None:
    with pytest.raises(
        V2RunnerBindingError,
        match="valid S4.2 authority Go|not in the frozen queue",
    ):
        execute_bound_request(
            "phase1-v2-request:" + "f" * 64,
            tmp_path / "must-not-exist",
        )
    assert not (tmp_path / "must-not-exist").exists()


def test_frozen_order_accepts_only_item_zero_in_fresh_namespace(tmp_path) -> None:
    queue = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
    first, second = queue["items"][:2]
    first_root = tmp_path / f"0000-{first['RequestID'].rsplit(':', 1)[-1]}"
    _validate_frozen_execution_order(
        first["RequestID"], first_root, base_root=tmp_path
    )
    second_root = tmp_path / f"0001-{second['RequestID'].rsplit(':', 1)[-1]}"
    with pytest.raises(V2RunnerBindingError, match="prior frozen request"):
        _validate_frozen_execution_order(
            second["RequestID"], second_root, base_root=tmp_path
        )


def test_frozen_order_rejects_noncanonical_path_and_future_artifact(tmp_path) -> None:
    queue = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
    first, second = queue["items"][:2]
    with pytest.raises(V2RunnerBindingError, match="canonical frozen index"):
        _validate_frozen_execution_order(
            first["RequestID"], tmp_path / "wrong", base_root=tmp_path
        )
    later = tmp_path / f"0001-{second['RequestID'].rsplit(':', 1)[-1]}"
    later.mkdir()
    first_root = tmp_path / f"0000-{first['RequestID'].rsplit(':', 1)[-1]}"
    with pytest.raises(V2RunnerBindingError, match="later frozen request"):
        _validate_frozen_execution_order(
            first["RequestID"], first_root, base_root=tmp_path
        )

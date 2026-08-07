from __future__ import annotations

from dataclasses import asdict

import pytest

from v5_final.semantic_contract import ScientificValueDelta, StateDelta
from v5_final.semantic_contract_v2 import (
    RESOURCE_COMPONENTS,
    WORK_COMPONENTS,
    ResourceDelta,
    SemanticDelta,
    WorkDelta,
)
from v5_final.scientific_values import TaggedScientificValue


def test_resource_and_work_namespaces_are_disjoint() -> None:
    assert set(RESOURCE_COMPONENTS).isdisjoint(WORK_COMPONENTS)


def test_independent_energy_recomputation_has_zero_resource_but_nonzero_work() -> None:
    value = TaggedScientificValue.available(
        quantity="candidate_energy", unit="hartree", value="-1.0"
    )
    delta = SemanticDelta(
        state_delta=StateDelta("a" * 64, "a" * 64),
        resource_delta=ResourceDelta(),
        scientific_value_delta=ScientificValueDelta(value, value),
        work_delta=WorkDelta(energy_evaluations=1),
    )
    assert not any(asdict(delta.resource_delta).values())
    assert delta.work_delta.energy_evaluations == 1


def test_resource_reduction_is_signed_but_work_cannot_be_negative() -> None:
    assert ResourceDelta(cnot_count=-2).cnot_count == -2
    with pytest.raises(ValueError, match="nonnegative"):
        WorkDelta(energy_evaluations=-1)

from pathlib import Path

import json
import pytest

from v5_final.s11_cap_precheck_recovery_item023_v1 import (
    DECLARATION_PATH,
    RECOVERY_SOURCES,
    S11Item023RecoveryError,
    _embedded_state,
    audit_declaration,
)
from v5_matched_work.atomic_artifacts import canonical_json_bytes


def test_item023_declaration_is_canonical_and_passes() -> None:
    assert DECLARATION_PATH.read_bytes() == canonical_json_bytes(
        json.loads(DECLARATION_PATH.read_bytes())
    )
    assert all(audit_declaration().values())


def test_item023_incident_has_no_terminal_or_candidate_energy() -> None:
    declaration = json.loads(DECLARATION_PATH.read_bytes())
    state, checkpoint = _embedded_state(declaration)
    assert state.terminal is None
    assert len(state.records) == 4
    assert checkpoint["outcome_payload"]["terminal_status"] == "CAP_REJECTED"
    assert not any(event.operation == "candidate-energy-evaluation" for event in state.work_events)


def test_item023_declaration_tampering_fails_closed() -> None:
    declaration = json.loads(DECLARATION_PATH.read_bytes())
    declaration["deterministic_precheck"]["exceeded_components"] = []
    with pytest.raises(S11Item023RecoveryError):
        audit_declaration(declaration)


def test_item023_recovery_source_is_zero_kernel() -> None:
    assert all(path.is_file() for path in RECOVERY_SOURCES)
    source = Path(RECOVERY_SOURCES[0]).read_text()
    recovery = source[source.index("def execute_terminal_recovery") : source.index("def main")]
    assert "recorder._precheck" in recovery
    assert "persist_new_work_events" in recovery
    assert "recover_frozen_item_result" in recovery
    assert "prepared.execute" not in recovery
    assert "build_queue_bound_runtime" not in recovery

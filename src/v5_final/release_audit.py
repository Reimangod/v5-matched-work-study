"""Authoritative S4 smoke audit; performance and S5 remain closed."""

from __future__ import annotations

import hashlib
from typing import Any, Mapping

from v5_matched_work.atomic_artifacts import canonical_json_bytes

from .frozen_queue import verify_frozen_queue
from .semantic_contract_v2 import WorkDelta
from .semantic_events import SemanticEventType, event_from_dict_strict
from .work_ledger import reconcile


class ReleaseAuditError(RuntimeError):
    pass


def audit_smoke(smoke: Mapping[str, Any]) -> dict[str, bool]:
    payload = dict(smoke)
    observed_digest = payload.pop("smoke_digest", None)
    ledger = smoke["integrated_ledger"]
    events = [event_from_dict_strict(value) for value in ledger["events"]]
    expected_queue_ids = verify_frozen_queue(smoke["frozen_queue"])
    terminal_events = [
        event for event in events if event.event_type is SemanticEventType.TERMINAL_REACHED
    ]
    expected_events = [event for event in events if event.queue_item_id in expected_queue_ids]
    frozen_position = next(
        event.sequence for event in events if event.event_type is SemanticEventType.QUEUE_FROZEN
    )
    commit_positions = [
        event.sequence for event in events if event.event_type is SemanticEventType.STATE_COMMITTED
    ]
    rebuild_positions = [
        event.sequence for event in events if event.event_type is SemanticEventType.CATALOG_REBUILT
    ]
    reconciliation = reconcile(
        independent_raw_counter=WorkDelta(**dict(smoke["independent_raw_counter"])),
        ledger_document=ledger,
        summary=smoke["release_summary"],
    )
    checks = {
        "smoke_digest_valid": observed_digest
        == hashlib.sha256(canonical_json_bytes(payload)).hexdigest(),
        "classification_is_not_performance": smoke["classification"]
        == "bounded infrastructure smoke; not performance evidence",
        "pinned_upstream": smoke["upstream"]["commit"]
        == "a3f89d03e6a03c89767d3cf8ee7657a57653dda0",
        "frozen_queue_nonempty": len(expected_queue_ids) == 1,
        "one_terminal_per_queue_item": len(terminal_events) == 1
        and terminal_events[0].queue_item_id == expected_queue_ids[0],
        "all_postfreeze_execution_events_queue_bound": all(
            event.queue_item_id == expected_queue_ids[0]
            for event in events
            if event.sequence >= frozen_position
        ),
        "candidate_energy_reconstructed_from_s4_chain": any(
            event.event_type is SemanticEventType.ENERGY_EVALUATED
            for event in expected_events
        ),
        "catalog_rebuilt_after_commit": bool(commit_positions)
        and bool(rebuild_positions)
        and min(rebuild_positions) > max(commit_positions),
        "raw_ledger_release_reconcile": all(reconciliation.values()),
        "terminal_matches_record": terminal_events[0].evidence["terminal_status"]
        == smoke["terminal_status"],
        "claim_boundary_explicit": "cannot support method-performance claims"
        in smoke["claim_boundary"],
    }
    return checks


def require_smoke(smoke: Mapping[str, Any]) -> dict[str, bool]:
    checks = audit_smoke(smoke)
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise ReleaseAuditError("S4 smoke audit failed: " + ", ".join(failures))
    return checks

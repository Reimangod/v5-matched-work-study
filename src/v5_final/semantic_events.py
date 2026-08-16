"""Strict semantic events emitted on the executor's counted operation path."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import hashlib
from typing import Any, Mapping

from v5_matched_work.atomic_artifacts import canonical_json_bytes

from . import PROTOCOL_ID
from .scientific_values import ScientificValueState, scientific_value_from_dict
from .semantic_contract import ScientificValueDelta, SemanticContractError, StateDelta
from .semantic_contract_v2 import ResourceDelta, SemanticDelta, WorkDelta, WORK_COMPONENTS


class SemanticEventError(ValueError):
    pass


class SemanticEventType(str, Enum):
    SOURCE_LOADED = "SOURCE_LOADED"
    CATALOG_BUILT = "CATALOG_BUILT"
    CANDIDATE_GENERATED = "CANDIDATE_GENERATED"
    CANDIDATE_DEDUPLICATED = "CANDIDATE_DEDUPLICATED"
    RESOURCE_RECOUNTED = "RESOURCE_RECOUNTED"
    PREDICTOR_EVALUATED = "PREDICTOR_EVALUATED"
    QUEUE_FROZEN = "QUEUE_FROZEN"
    OPTIMIZER_STARTED = "OPTIMIZER_STARTED"
    OPTIMIZER_ITERATED = "OPTIMIZER_ITERATED"
    ENERGY_EVALUATED = "ENERGY_EVALUATED"
    GRADIENT_EVALUATED = "GRADIENT_EVALUATED"
    HVP_EVALUATED = "HVP_EVALUATED"
    SEARCH_STATE_EXPANDED = "SEARCH_STATE_EXPANDED"
    REWRITE_VERIFIED = "REWRITE_VERIFIED"
    STATEVECTOR_RECOMPUTED = "STATEVECTOR_RECOMPUTED"
    CANDIDATE_CERTIFIED = "CANDIDATE_CERTIFIED"
    CANDIDATE_REJECTED = "CANDIDATE_REJECTED"
    STATE_COMMITTED = "STATE_COMMITTED"
    STATE_ROLLED_BACK = "STATE_ROLLED_BACK"
    CATALOG_REBUILT = "CATALOG_REBUILT"
    TERMINAL_REACHED = "TERMINAL_REACHED"


EVENT_WORK_FIELDS: dict[SemanticEventType, frozenset[str]] = {
    event_type: frozenset() for event_type in SemanticEventType
}
EVENT_WORK_FIELDS.update(
    {
        SemanticEventType.CANDIDATE_GENERATED: frozenset({"candidate_generations"}),
        SemanticEventType.RESOURCE_RECOUNTED: frozenset({"resource_recounts"}),
        SemanticEventType.OPTIMIZER_STARTED: frozenset({"optimizer_starts"}),
        SemanticEventType.OPTIMIZER_ITERATED: frozenset({"optimizer_iterations"}),
        SemanticEventType.ENERGY_EVALUATED: frozenset({"energy_evaluations"}),
        SemanticEventType.GRADIENT_EVALUATED: frozenset(
            {"gradient_vector_evaluations", "gradient_component_equivalents"}
        ),
        SemanticEventType.HVP_EVALUATED: frozenset({"hvp_evaluations"}),
        SemanticEventType.SEARCH_STATE_EXPANDED: frozenset({"search_states"}),
        SemanticEventType.REWRITE_VERIFIED: frozenset({"rewrite_verifications"}),
        SemanticEventType.STATEVECTOR_RECOMPUTED: frozenset(
            {"statevector_recomputations"}
        ),
    }
)


def _canonical_data(value: Any, path: str = "evidence") -> None:
    if value is None or isinstance(value, (bool, int, str)):
        return
    if isinstance(value, float):
        raise SemanticEventError(f"{path} cannot contain binary floats")
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                raise SemanticEventError(f"{path} keys must be strings")
            _canonical_data(child, f"{path}.{key}")
        return
    if isinstance(value, (tuple, list)):
        for index, child in enumerate(value):
            _canonical_data(child, f"{path}[{index}]")
        return
    raise SemanticEventError(f"{path} contains noncanonical {type(value).__name__}")


def _validate_delta(event_type: SemanticEventType, delta: SemanticDelta) -> None:
    charged = {
        field
        for field in WORK_COMPONENTS
        if getattr(delta.work_delta, field) != 0
    }
    disallowed = charged - EVENT_WORK_FIELDS[event_type]
    if disallowed:
        raise SemanticEventError(
            f"{event_type.value} cannot charge work components: {sorted(disallowed)}"
        )
    if event_type is not SemanticEventType.STATE_COMMITTED and delta.state_delta.committed:
        raise SemanticEventError(
            f"{event_type.value} cannot commit a source-state transition"
        )
    if event_type is not SemanticEventType.STATE_COMMITTED and not delta.resource_delta.is_zero():
        raise SemanticEventError(
            f"{event_type.value} cannot change committed architecture resources"
        )
    if (
        delta.scientific_value_delta.previous != delta.scientific_value_delta.current
        and event_type
        not in {
            SemanticEventType.PREDICTOR_EVALUATED,
            SemanticEventType.ENERGY_EVALUATED,
            SemanticEventType.GRADIENT_EVALUATED,
            SemanticEventType.HVP_EVALUATED,
        }
    ):
        raise SemanticEventError(
            f"{event_type.value} cannot create a scientific-value transition"
        )
    if event_type is SemanticEventType.CANDIDATE_DEDUPLICATED and (
        not delta.state_delta.is_zero()
        or not delta.resource_delta.is_zero()
        or not delta.work_delta.is_zero()
    ):
        raise SemanticEventError("deduplication event must be zero delta")
    if event_type is SemanticEventType.STATE_COMMITTED and not delta.state_delta.committed:
        raise SemanticEventError("STATE_COMMITTED requires a committed state delta")
    if event_type is SemanticEventType.STATE_ROLLED_BACK and not delta.state_delta.is_zero():
        raise SemanticEventError("STATE_ROLLED_BACK must restore the exact source digest")
    if event_type is SemanticEventType.ENERGY_EVALUATED and (
        delta.scientific_value_delta.current.state is not ScientificValueState.AVAILABLE
    ):
        raise SemanticEventError("ENERGY_EVALUATED requires an AVAILABLE scientific value")


@dataclass(frozen=True)
class SemanticEvent:
    event_id: str
    event_digest: str
    previous_event_digest: str
    sequence: int
    event_type: SemanticEventType
    protocol_id: str
    producer: str
    queue_item_id: str
    execution_request_id: str | None
    candidate_intent_id: str | None
    proposed_physical_state_id: str | None
    delta: SemanticDelta
    evidence: Mapping[str, Any]

    @classmethod
    def _create(
        cls,
        *,
        previous_event_digest: str,
        sequence: int,
        event_type: SemanticEventType,
        producer: str,
        queue_item_id: str,
        execution_request_id: str | None,
        candidate_intent_id: str | None,
        proposed_physical_state_id: str | None,
        delta: SemanticDelta,
        evidence: Mapping[str, Any],
    ) -> "SemanticEvent":
        if len(previous_event_digest) != 64:
            raise SemanticEventError("previous event digest must be SHA-256")
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
            raise SemanticEventError("event sequence must be nonnegative")
        if not producer.startswith("v5_final.executor"):
            raise SemanticEventError("semantic events must identify the production executor producer")
        if not queue_item_id:
            raise SemanticEventError("queue item identity is required")
        if not evidence:
            raise SemanticEventError("semantic event evidence is required")
        _canonical_data(evidence)
        _validate_delta(event_type, delta)
        if not delta.work_delta.is_zero() and not evidence.get("raw_counter_source"):
            raise SemanticEventError("counted event evidence requires raw_counter_source")
        payload = {
            "previous_event_digest": previous_event_digest,
            "sequence": sequence,
            "event_type": event_type.value,
            "protocol_id": PROTOCOL_ID,
            "producer": producer,
            "queue_item_id": queue_item_id,
            "execution_request_id": execution_request_id,
            "candidate_intent_id": candidate_intent_id,
            "proposed_physical_state_id": proposed_physical_state_id,
            "delta": delta.to_dict(),
            "evidence": dict(evidence),
        }
        digest = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
        return cls(
            event_id="semantic-event-v1:" + digest,
            event_digest=digest,
            event_type=event_type,
            delta=delta,
            **{key: value for key, value in payload.items() if key not in {"event_type", "delta"}},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_digest": self.event_digest,
            "previous_event_digest": self.previous_event_digest,
            "sequence": self.sequence,
            "event_type": self.event_type.value,
            "protocol_id": self.protocol_id,
            "producer": self.producer,
            "queue_item_id": self.queue_item_id,
            "execution_request_id": self.execution_request_id,
            "candidate_intent_id": self.candidate_intent_id,
            "proposed_physical_state_id": self.proposed_physical_state_id,
            "delta": self.delta.to_dict(),
            "evidence": dict(self.evidence),
        }


def semantic_delta_from_dict(value: Mapping[str, Any]) -> SemanticDelta:
    scientific = value["scientific_value_delta"]
    try:
        return SemanticDelta(
            state_delta=StateDelta(**dict(value["state_delta"])),
            resource_delta=ResourceDelta(**dict(value["resource_delta"])),
            scientific_value_delta=ScientificValueDelta(
                scientific_value_from_dict(dict(scientific["previous"])),
                scientific_value_from_dict(dict(scientific["current"])),
            ),
            work_delta=WorkDelta(**dict(value["work_delta"])),
        )
    except (KeyError, TypeError, SemanticContractError) as error:
        raise SemanticEventError("semantic event delta is malformed") from error


def event_from_dict_strict(value: Mapping[str, Any]) -> SemanticEvent:
    if value.get("protocol_id") != PROTOCOL_ID:
        raise SemanticEventError("semantic event protocol mismatch")
    rebuilt = SemanticEvent._create(
        previous_event_digest=str(value["previous_event_digest"]),
        sequence=value["sequence"],
        event_type=SemanticEventType(value["event_type"]),
        producer=str(value["producer"]),
        queue_item_id=str(value["queue_item_id"]),
        execution_request_id=value.get("execution_request_id"),
        candidate_intent_id=value.get("candidate_intent_id"),
        proposed_physical_state_id=value.get("proposed_physical_state_id"),
        delta=semantic_delta_from_dict(value["delta"]),
        evidence=dict(value["evidence"]),
    )
    if rebuilt.to_dict() != dict(value):
        raise SemanticEventError("semantic event digest or canonical content mismatch")
    return rebuilt

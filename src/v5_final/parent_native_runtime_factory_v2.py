"""MB6-v3-bound successor molecular runtime factory.

Construction recomputes the frozen source statevector but never evaluates a
candidate energy.  Releasing the actual algorithm additionally requires the
successor S8-v2 gate bound to the exact MB6-v4 plan digest.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from dvg_obs_ceo.molecular_identity import problem_spec, state_preparation_spec
from dvg_obs_ceo.resources import (
    AnsatzStructure,
    evaluate_full_circuit_resources,
    paper_era_backend,
)
from dvg_obs_ceo.telemetry import WorkCounters
from dvg_obs_ceo.transaction import CompressionRuntime

from .mb6_source_catalog_probe import CASES, _algorithm_outcome_free
from .parent_native_runtime_factory import (
    CandidateOutcomeNotAuthorized,
    OutcomeBlockedAlgorithm,
    QueueBoundRuntimeError,
    _resource_vector,
    _verify_catalog,
    _verify_embedded_digest,
    _verify_environment,
)
from .s0_successor import ROOT


PLAN_PATH = ROOT / "artifacts/v5-final/parent-native/mb6-v4/h2-h4-calibration-plan-v4.json"
FALLBACK_PLAN_PATH = ROOT / "artifacts/v5-final/parent-native/mb6-v3/h2-h4-calibration-plan-v3.json"
CATALOG_PATH = ROOT / "artifacts/v5-final/mb6-v2/h2-h4-source-catalog-v2.json"
ENVIRONMENT_PATH = ROOT / "artifacts/v5-final/parent-native/mb6-v3/execution-environment-v3.json"
S8_GO_PATH = ROOT / "artifacts/v5-final/parent-native/s8-production-go-v2.json"


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _digest(value: Any) -> str:
    from v5_matched_work.atomic_artifacts import canonical_json_bytes

    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _verify_plan(plan: Mapping[str, Any]) -> None:
    _verify_embedded_digest(plan, "plan_digest")
    items = list(plan.get("items", ()))
    if (
        plan.get("schema")
        not in {
            "v5-final.mb6-h2-h4-calibration-plan.v3",
            "v5-final.mb6-h2-h4-calibration-plan.v4",
        }
        or plan.get("status") != "FROZEN_NOT_AUTHORIZED_FOR_EXECUTION"
        or plan.get("frozen_item_count") != 36
        or len(items) != 36
        or plan.get("candidate_energy_evaluations") != 0
    ):
        raise QueueBoundRuntimeError("plan is not a frozen zero-outcome 36-item plan")
    version = "v4" if plan["schema"].endswith("v4") else "v3"
    ids: list[str] = []
    for item in items:
        body = {key: value for key, value in item.items() if key != "queue_item_id"}
        expected = f"mb6-calibration-item-{version}:" + _digest(body)
        if item.get("queue_item_id") != expected:
            raise QueueBoundRuntimeError("MB6 plan item identity mismatch")
        if item.get("terminal_status") != "NOT_STARTED":
            raise QueueBoundRuntimeError("MB6 plan item is not outcome-free")
        ids.append(expected)
    if len(set(ids)) != 36:
        raise QueueBoundRuntimeError("MB6 plan item identities are duplicated")


@dataclass(frozen=True)
class QueueBoundMolecularRuntimeV2:
    queue_item_id: str
    case_id: str
    method_id: str
    plan_digest: str
    catalog_digest: str
    environment_digest: str
    source_checkpoint_digest: str
    source_statevector_sha256: str
    problem_id: str
    hamiltonian_digest: str
    state_preparation_id: str
    source_resources: dict[str, int]
    source_statevector_recomputations: int
    algorithm: OutcomeBlockedAlgorithm
    pool: Any
    runtime: CompressionRuntime
    _actual_algorithm: Any

    @property
    def queue_digest(self) -> str:
        """Compatibility alias used by the prepared executor."""

        return self.plan_digest

    def release_for_h2_h4_execution(self) -> Any:
        if not S8_GO_PATH.is_file():
            raise CandidateOutcomeNotAuthorized("successor S8-v2 GO is absent")
        gate = _json(S8_GO_PATH)
        _verify_embedded_digest(gate, "gate_digest")
        if (
            gate.get("schema") != "v5-final.s8-parent-native-production-go.v2"
            or gate.get("decision") != "GO_H2_H4_CALIBRATION_ONLY"
            or gate.get("candidate_molecular_energy_evaluations_before_GO") != 0
            or gate.get("plan_digest") != self.plan_digest
            or gate.get("authorization", {}).get("H2_H4_execution")
            != "AUTHORIZED_FROZEN_MB6_V4_PLAN_ONLY"
            or not all(gate.get("checks", {}).values())
        ):
            raise CandidateOutcomeNotAuthorized("successor S8-v2 GO is invalid")
        return self._actual_algorithm


@dataclass(frozen=True)
class QueueSourceBindingV2:
    queue_item: dict[str, Any]
    catalog_case: dict[str, Any]
    checkpoint: dict[str, Any]
    checkpoint_path: Path
    plan_digest: str
    catalog_digest: str
    environment_digest: str
    environment_observation: dict[str, Any]


def preflight_plan_binding(
    queue_item_id: str,
    *,
    plan_record: Mapping[str, Any] | None = None,
    catalog_record: Mapping[str, Any] | None = None,
    environment_record: Mapping[str, Any] | None = None,
) -> QueueSourceBindingV2:
    selected_plan_path = PLAN_PATH if PLAN_PATH.exists() else FALLBACK_PLAN_PATH
    plan = deepcopy(dict(plan_record)) if plan_record is not None else _json(selected_plan_path)
    catalog = deepcopy(dict(catalog_record)) if catalog_record is not None else _json(CATALOG_PATH)
    environment = (
        deepcopy(dict(environment_record))
        if environment_record is not None
        else _json(ENVIRONMENT_PATH)
    )
    _verify_plan(plan)
    _verify_catalog(catalog)
    observation = _verify_environment(environment)
    if plan["catalog_digest"] != catalog["probe_digest"]:
        raise QueueBoundRuntimeError("plan catalog binding mismatch")
    if plan["catalog_sha256"] != _sha(CATALOG_PATH):
        raise QueueBoundRuntimeError("plan catalog artifact digest mismatch")
    if plan["environment_digest"] != environment["environment_digest"]:
        raise QueueBoundRuntimeError("plan environment binding mismatch")
    matches = [item for item in plan["items"] if item["queue_item_id"] == queue_item_id]
    if len(matches) != 1:
        raise QueueBoundRuntimeError("plan item is absent or duplicated")
    item = matches[0]
    cases = [value for value in catalog["cases"] if value["case_id"] == item["case_id"]]
    if len(cases) != 1:
        raise QueueBoundRuntimeError("catalog case is absent or duplicated")
    case = cases[0]
    identity_fields = (
        "StatePreparationID",
        "ProblemID",
        "Hamiltonian_digest",
        "source_checkpoint_digest",
        "source_checkpoint_sha256",
    )
    if any(item.get(field) != case.get(field) for field in identity_fields):
        raise QueueBoundRuntimeError("plan and catalog source identities differ")
    if item["environment_digest"] != environment["environment_digest"]:
        raise QueueBoundRuntimeError("plan item environment differs")
    checkpoint_path = (ROOT / str(case["source_checkpoint_path"])).resolve()
    allowed = CASES[str(item["case_id"])].resolve()
    if checkpoint_path != allowed or checkpoint_path.parent != allowed.parent:
        raise QueueBoundRuntimeError("source checkpoint path is not pinned")
    if _sha(checkpoint_path) != item["source_checkpoint_sha256"]:
        raise QueueBoundRuntimeError("source checkpoint SHA-256 differs")
    checkpoint = _json(checkpoint_path)
    _verify_embedded_digest(checkpoint, "checkpoint_digest", parent_encoding=True)
    if (
        checkpoint["case_id"] != item["case_id"]
        or checkpoint["checkpoint_digest"] != item["source_checkpoint_digest"]
    ):
        raise QueueBoundRuntimeError("checkpoint semantic identity differs")
    return QueueSourceBindingV2(
        item,
        case,
        checkpoint,
        checkpoint_path,
        str(plan["plan_digest"]),
        str(catalog["probe_digest"]),
        str(environment["environment_digest"]),
        observation,
    )


def build_queue_bound_runtime_v2(
    queue_item_id: str,
    *,
    plan_record: Mapping[str, Any] | None = None,
    catalog_record: Mapping[str, Any] | None = None,
    environment_record: Mapping[str, Any] | None = None,
    work_recorder: Any | None = None,
) -> QueueBoundMolecularRuntimeV2:
    binding = preflight_plan_binding(
        queue_item_id,
        plan_record=plan_record,
        catalog_record=catalog_record,
        environment_record=environment_record,
    )
    item = binding.queue_item
    case = binding.catalog_case
    checkpoint = binding.checkpoint
    algorithm, pool = _algorithm_outcome_free(str(item["case_id"]))
    if algorithm.molecule.fci_energy is not None or algorithm.molecule.ccsd_energy is not None:
        raise QueueBoundRuntimeError("FCI/CCSD outcome entered source construction")
    problem = problem_spec(algorithm=algorithm, case_id=str(item["case_id"]))
    if (
        problem.problem_id != item["ProblemID"]
        or problem.hamiltonian_digest != item["Hamiltonian_digest"]
        or problem.payload() != case["problem_payload"]
    ):
        raise QueueBoundRuntimeError("actual molecular problem identity differs")
    structure = AnsatzStructure.create(
        checkpoint["ansatz_indices"],
        checkpoint["ansatz_coefficients"],
        checkpoint["iteration_counts"],
    )
    resource_call = lambda: evaluate_full_circuit_resources(
        pool, structure, paper_era_backend()
    )
    resources = (
        resource_call()
        if work_recorder is None
        else work_recorder.invoke("full-physical-resource-recount", resource_call)
    )
    resource_vector = _resource_vector(resources)
    if resource_vector != case["source_resources"]:
        raise QueueBoundRuntimeError("actual source resource recount differs")
    state_call = lambda: algorithm.compute_state(
        list(structure.coefficients), list(structure.indices)
    )
    raw_state = (
        state_call()
        if work_recorder is None
        else work_recorder.invoke("statevector-recomputation", state_call)
    )
    state = np.asarray(raw_state.toarray(), dtype=np.complex128).ravel()
    state /= np.linalg.norm(state)
    state_sha = hashlib.sha256(np.asarray(state, dtype=">c16").tobytes()).hexdigest()
    if state_sha != checkpoint["statevector_sha256"]:
        raise QueueBoundRuntimeError("actual source statevector differs")
    runtime = CompressionRuntime.create(
        ansatz=structure,
        energy_hartree=float(checkpoint["energy_hartree"]),
        gradient=checkpoint["gradient"],
        inverse_hessian=checkpoint["recycled_inverse_hessian"],
        statevector=state,
        work=WorkCounters(),
        adapt_iteration=len(structure.cumulative_parameter_counts),
        metadata={
            "resource_structure_digest": resources.snapshot.structure_digest,
            "budget_reference_energy_hartree": float(checkpoint["energy_hartree"]),
            "queue_item_id": queue_item_id,
            "source_checkpoint_digest": checkpoint["checkpoint_digest"],
            "ProblemID": problem.problem_id,
            "source_statevector_recomputations": 1,
            "MB6_plan_digest": binding.plan_digest,
        },
    )
    preparation = state_preparation_spec(runtime, algorithm=algorithm, pool=pool)
    if (
        preparation.state_preparation_id != item["StatePreparationID"]
        or preparation.payload() != case["state_preparation_payload"]
    ):
        raise QueueBoundRuntimeError("actual source preparation differs")
    return QueueBoundMolecularRuntimeV2(
        queue_item_id=queue_item_id,
        case_id=str(item["case_id"]),
        method_id=str(item["method_id"]),
        plan_digest=binding.plan_digest,
        catalog_digest=binding.catalog_digest,
        environment_digest=binding.environment_digest,
        source_checkpoint_digest=str(checkpoint["checkpoint_digest"]),
        source_statevector_sha256=state_sha,
        problem_id=problem.problem_id,
        hamiltonian_digest=problem.hamiltonian_digest,
        state_preparation_id=preparation.state_preparation_id,
        source_resources=resource_vector,
        source_statevector_recomputations=1,
        algorithm=OutcomeBlockedAlgorithm(algorithm),
        pool=pool,
        runtime=runtime,
        _actual_algorithm=algorithm,
    )

"""Queue-bound parent-native runtime for the frozen S11 development successor.

The factory rebuilds molecular integrals without FCI or CCSD, verifies the
frozen problem/source identities, and recomputes only the already-frozen source
state.  Candidate energy and optimizer entrypoints remain blocked until the
exact S11 owner authorization artifact exists.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import tempfile
from typing import Any, Mapping

import numpy as np

from dvg_obs_ceo.baseline import _load_upstream
from dvg_obs_ceo.molecular_identity import problem_spec, state_preparation_spec
from dvg_obs_ceo.resources import (
    AnsatzStructure,
    evaluate_full_circuit_resources,
    paper_era_backend,
)
from dvg_obs_ceo.telemetry import WorkCounters
from dvg_obs_ceo.transaction import CompressionRuntime

from .parent_native_runtime_factory import (
    CandidateOutcomeNotAuthorized,
    OutcomeBlockedAlgorithm,
    QueueBoundRuntimeError,
    _resource_vector,
    _verify_embedded_digest,
    _verify_environment,
)
from .s0_successor import ROOT


S11_FREEZE_DIR = (
    ROOT / "artifacts/v5-final/parent-native/s11-development-queue-v4"
)
PLAN_PATH = S11_FREEZE_DIR / "development-plan-v4.json"
CATALOG_PATH = S11_FREEZE_DIR / "development-source-catalog-v1.json"
REGISTRY_PATH = ROOT / "artifacts/v5-final/s5/source-checkpoint-registry-v3.json"
ENVIRONMENT_PATH = (
    ROOT / "artifacts/v5-final/mb6-v2/execution-environment-v2.json"
)
AUTHORIZATION_PATH = (
    ROOT
    / "artifacts/v5-final/parent-native/s11-development-execution-v1"
    / "s11-execution-authorization-v1.json"
)

DEVELOPMENT_CASES: dict[str, dict[str, Any]] = {
    "lih-3.0": {
        "atoms": ("Li", "H"),
        "distance_angstrom": 3.0,
        "multiplicity": 1,
        "description": "LiH",
        "gradient_threshold": 1e-6,
    },
    "h6-1.5": {
        "atoms": ("H",) * 6,
        "distance_angstrom": 1.5,
        "multiplicity": 1,
        "description": "H6",
        "gradient_threshold": 1e-6,
    },
    "h6-3.0": {
        "atoms": ("H",) * 6,
        "distance_angstrom": 3.0,
        "multiplicity": 1,
        "description": "H6",
        "gradient_threshold": 1e-6,
    },
    "beh2-3.0": {
        "atoms": ("H", "Be", "H"),
        "distance_angstrom": 3.0,
        "multiplicity": 1,
        "description": "BeH2",
        "gradient_threshold": 1e-5,
    },
    "h4-1.5-known-development": {
        "atoms": ("H",) * 4,
        "distance_angstrom": 1.5,
        "multiplicity": 1,
        "description": "H4",
        "gradient_threshold": 1e-6,
    },
}

METHOD_IDS = (
    "immutable-ceo-star-source",
    "same-structure-reoptimization",
    "structural-magnitude-pruning",
    "v4.1-one-shot-joint-compression",
    "v5-fixed-source-whitelist-no-replenishment",
    "v5-sequential-with-rebuilding",
)
WORK_ENVELOPES = ("LOW", "MEDIUM", "HIGH")


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise QueueBoundRuntimeError(f"expected JSON object: {path}")
    return value


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _digest(value: Any) -> str:
    from v5_matched_work.atomic_artifacts import canonical_json_bytes

    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _algorithm_outcome_free(case_id: str) -> tuple[Any, Any]:
    """Build the registered molecular Hamiltonian without FCI/CCSD outcomes."""

    if case_id not in DEVELOPMENT_CASES:
        raise QueueBoundRuntimeError(f"unregistered development case: {case_id}")
    from openfermion import MolecularData
    from openfermionpyscf import run_pyscf

    definition = DEVELOPMENT_CASES[case_id]
    distance = float(definition["distance_angstrom"])
    geometry = [
        (str(atom), (0.0, 0.0, distance * index))
        for index, atom in enumerate(definition["atoms"])
    ]
    filename = Path(tempfile.gettempdir()) / (
        "v5-s11-" + case_id.replace(".", "_").replace("-", "_")
    )
    molecule = MolecularData(
        geometry,
        "sto-3g",
        int(definition["multiplicity"]),
        0,
        description=str(definition["description"]),
        filename=str(filename),
    )
    molecule = run_pyscf(
        molecule,
        run_scf=True,
        run_mp2=False,
        run_cisd=False,
        run_ccsd=False,
        run_fci=False,
    )
    if molecule.fci_energy is not None or molecule.ccsd_energy is not None:
        raise QueueBoundRuntimeError("development FCI/CCSD firewall failed")
    LinAlgAdapt, DVG_CEO, _, _ = _load_upstream()
    pool = DVG_CEO(molecule)
    algorithm = LinAlgAdapt(
        pool=pool,
        molecule=molecule,
        verbose=False,
        max_adapt_iter=100,
        max_opt_iter=10000,
        full_opt=True,
        threshold=float(definition["gradient_threshold"]),
        convergence_criterion="total_g_norm",
        tetris=True,
        progressive_opt=False,
        candidates=1,
        sel_criterion="gradient",
        recycle_hessian=True,
        penalize_cnots=False,
        rand_degenerate=False,
        shots=None,
    )
    return algorithm, pool


def _verify_plan(plan: Mapping[str, Any]) -> None:
    _verify_embedded_digest(plan, "plan_digest")
    schema = plan.get("schema")
    prefixes = {
        "v5-final.s11-development-preparation-plan.v1": (
            "s11-development-preparation-item-v1:"
        ),
        "v5-final.s11-development-plan.v4": "development-queue-item-v4:",
    }
    if schema not in prefixes:
        raise QueueBoundRuntimeError("unregistered S11 plan schema")
    items = list(plan.get("items", ()))
    if (
        len(items) != 90
        or plan.get("frozen_item_count") != 90
        or plan.get("candidate_energy_evaluations") != 0
        or {item.get("case_id") for item in items} != set(DEVELOPMENT_CASES)
        or {item.get("method_id") for item in items} != set(METHOD_IDS)
        or {item.get("work_envelope") for item in items} != set(WORK_ENVELOPES)
    ):
        raise QueueBoundRuntimeError("S11 plan is not an exact zero-outcome 90-item grid")
    expected_order = [
        (case_id, envelope, method)
        for case_id in DEVELOPMENT_CASES
        for envelope in WORK_ENVELOPES
        for method in METHOD_IDS
    ]
    observed_order = [
        (item.get("case_id"), item.get("work_envelope"), item.get("method_id"))
        for item in items
    ]
    if observed_order != expected_order:
        raise QueueBoundRuntimeError("S11 plan order differs from the frozen grid")
    rebuilt: list[str] = []
    for item in items:
        body = {key: value for key, value in item.items() if key != "queue_item_id"}
        expected = prefixes[str(schema)] + _digest(body)
        if item.get("queue_item_id") != expected:
            raise QueueBoundRuntimeError("S11 plan item identity mismatch")
        if item.get("terminal_status") != "NOT_STARTED":
            raise QueueBoundRuntimeError("S11 plan item is not outcome-free")
        rebuilt.append(expected)
    if len(set(rebuilt)) != 90:
        raise QueueBoundRuntimeError("S11 plan item identities are duplicated")


def _verify_catalog(catalog: Mapping[str, Any]) -> None:
    _verify_embedded_digest(catalog, "catalog_digest")
    cases = list(catalog.get("cases", ()))
    if (
        catalog.get("schema")
        != "v5-final.s11-development-outcome-free-source-catalog.v1"
        or len(cases) != 5
        or {case.get("case_id") for case in cases} != set(DEVELOPMENT_CASES)
        or catalog.get("candidate_energy_evaluations") != 0
        or any(catalog.get("molecular_kernel_guard_calls", {}).values())
    ):
        raise QueueBoundRuntimeError("S11 development source catalog is invalid")


@dataclass(frozen=True)
class DevelopmentSourceBindingV1:
    queue_item: dict[str, Any]
    catalog_case: dict[str, Any]
    registry_source: dict[str, Any]
    checkpoint: dict[str, Any]
    checkpoint_path: Path
    plan_digest: str
    catalog_digest: str
    environment_digest: str
    environment_observation: dict[str, Any]


def preflight_development_binding_v1(
    queue_item_id: str,
    *,
    plan_record: Mapping[str, Any] | None = None,
    catalog_record: Mapping[str, Any] | None = None,
    registry_record: Mapping[str, Any] | None = None,
    environment_record: Mapping[str, Any] | None = None,
) -> DevelopmentSourceBindingV1:
    plan = deepcopy(dict(plan_record)) if plan_record is not None else _json(PLAN_PATH)
    catalog = (
        deepcopy(dict(catalog_record))
        if catalog_record is not None
        else _json(CATALOG_PATH)
    )
    registry = (
        deepcopy(dict(registry_record))
        if registry_record is not None
        else _json(REGISTRY_PATH)
    )
    environment = (
        deepcopy(dict(environment_record))
        if environment_record is not None
        else _json(ENVIRONMENT_PATH)
    )
    _verify_plan(plan)
    _verify_catalog(catalog)
    _verify_embedded_digest(registry, "registry_digest")
    observation = _verify_environment(environment)
    if plan.get("catalog_digest") != catalog["catalog_digest"]:
        raise QueueBoundRuntimeError("S11 plan/catalog digest binding mismatch")
    if plan.get("source_registry_digest") != registry["registry_digest"]:
        raise QueueBoundRuntimeError("S11 plan/source registry digest binding mismatch")
    if plan.get("environment_digest") != environment["environment_digest"]:
        raise QueueBoundRuntimeError("S11 plan/environment digest binding mismatch")
    if plan.get("schema") == "v5-final.s11-development-plan.v4":
        if plan.get("catalog_sha256") != _sha(CATALOG_PATH):
            raise QueueBoundRuntimeError("S11 catalog artifact SHA-256 mismatch")
        if plan.get("source_registry_sha256") != _sha(REGISTRY_PATH):
            raise QueueBoundRuntimeError("S11 source registry SHA-256 mismatch")
        if plan.get("environment_sha256") != _sha(ENVIRONMENT_PATH):
            raise QueueBoundRuntimeError("S11 environment SHA-256 mismatch")
    matches = [item for item in plan["items"] if item["queue_item_id"] == queue_item_id]
    if len(matches) != 1:
        raise QueueBoundRuntimeError("S11 plan item is absent or duplicated")
    item = matches[0]
    cases = [case for case in catalog["cases"] if case["case_id"] == item["case_id"]]
    sources = [
        source
        for source in registry["sources"]
        if source["case_id"] == item["case_id"]
    ]
    if len(cases) != 1 or len(sources) != 1:
        raise QueueBoundRuntimeError("S11 source case is absent or duplicated")
    case = cases[0]
    source = sources[0]
    identity_fields = (
        "StatePreparationID",
        "ProblemID",
        "source_checkpoint_digest",
        "source_checkpoint_sha256",
    )
    if any(item.get(field) != case.get(field) for field in identity_fields):
        raise QueueBoundRuntimeError("S11 item/catalog source identities differ")
    if (
        source["StatePreparationID"] != item["StatePreparationID"]
        or source["ProblemID"] != item["ProblemID"]
        or source["checkpoint_sha256"] != item["source_checkpoint_sha256"]
    ):
        raise QueueBoundRuntimeError("S11 item/source registry identities differ")
    checkpoint_path = (ROOT / str(source["checkpoint_path"])).resolve()
    if ROOT.resolve() not in checkpoint_path.parents:
        raise QueueBoundRuntimeError("S11 checkpoint path escapes the repository")
    if _sha(checkpoint_path) != source["checkpoint_sha256"]:
        raise QueueBoundRuntimeError("S11 source checkpoint SHA-256 differs")
    checkpoint = _json(checkpoint_path)
    _verify_embedded_digest(checkpoint, "checkpoint_digest", parent_encoding=True)
    if checkpoint["checkpoint_digest"] != item["source_checkpoint_digest"]:
        raise QueueBoundRuntimeError("S11 source checkpoint digest differs")
    return DevelopmentSourceBindingV1(
        item,
        case,
        source,
        checkpoint,
        checkpoint_path,
        str(plan["plan_digest"]),
        str(catalog["catalog_digest"]),
        str(environment["environment_digest"]),
        observation,
    )


@dataclass(frozen=True)
class QueueBoundDevelopmentRuntimeV1:
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
        return self.plan_digest

    def release_for_h2_h4_execution(self) -> Any:
        """Compatibility entrypoint used by the immutable execution service.

        Despite the historical method name, this releases only an S11-bound
        development item and only after exact S11 authorization.
        """

        if not AUTHORIZATION_PATH.is_file():
            raise CandidateOutcomeNotAuthorized("S11 development authorization is absent")
        authorization = _json(AUTHORIZATION_PATH)
        _verify_embedded_digest(authorization, "authorization_digest")
        scope = authorization.get("authorization", {})
        if (
            authorization.get("schema")
            != "v5-final.s11-development-local-owner-execution-authorization.v1"
            or authorization.get("decision")
            != "GO_S11_EXACT_FROZEN_90_ITEM_DEVELOPMENT_ONLY"
            or authorization.get("plan_digest") != self.plan_digest
            or authorization.get("candidate_molecular_energy_evaluations_before_authorization")
            != 0
            or scope.get("development_execution")
            != "AUTHORIZED_EXACT_FROZEN_90_ITEM_ORDER_ONLY"
            or scope.get("performance_claim") != "NOT_AUTHORIZED"
            or not all(authorization.get("checks", {}).values())
        ):
            raise CandidateOutcomeNotAuthorized("S11 development authorization is invalid")
        return self._actual_algorithm


def build_queue_bound_development_runtime_v1(
    queue_item_id: str,
    *,
    plan_record: Mapping[str, Any] | None = None,
    catalog_record: Mapping[str, Any] | None = None,
    registry_record: Mapping[str, Any] | None = None,
    environment_record: Mapping[str, Any] | None = None,
    work_recorder: Any | None = None,
) -> QueueBoundDevelopmentRuntimeV1:
    binding = preflight_development_binding_v1(
        queue_item_id,
        plan_record=plan_record,
        catalog_record=catalog_record,
        registry_record=registry_record,
        environment_record=environment_record,
    )
    item = binding.queue_item
    case = binding.catalog_case
    checkpoint = binding.checkpoint
    algorithm, pool = _algorithm_outcome_free(str(item["case_id"]))
    if algorithm.molecule.fci_energy is not None or algorithm.molecule.ccsd_energy is not None:
        raise QueueBoundRuntimeError("FCI/CCSD outcome entered S11 source construction")
    problem = problem_spec(algorithm=algorithm, case_id=str(item["case_id"]))
    if (
        problem.problem_id != item["ProblemID"]
        or problem.hamiltonian_digest != item["Hamiltonian_digest"]
        or problem.payload() != case["problem_payload"]
    ):
        raise QueueBoundRuntimeError("actual S11 molecular problem identity differs")
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
        raise QueueBoundRuntimeError("actual S11 source resource recount differs")
    if resources.snapshot.structure_digest != binding.registry_source["resources"][
        "structure_digest"
    ]:
        raise QueueBoundRuntimeError("actual S11 source structure digest differs")
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
    if state_sha != binding.registry_source["statevector_sha256"]:
        raise QueueBoundRuntimeError("actual S11 source statevector differs")
    energy = float(checkpoint["energy_hartree"])
    runtime = CompressionRuntime.create(
        ansatz=structure,
        energy_hartree=energy,
        gradient=checkpoint["gradient"],
        inverse_hessian=checkpoint["recycled_inverse_hessian"],
        statevector=state,
        work=WorkCounters(),
        adapt_iteration=int(checkpoint.get("adapt_iteration", len(structure.cumulative_parameter_counts))),
        metadata={
            "resource_structure_digest": resources.snapshot.structure_digest,
            "budget_reference_energy_hartree": energy,
            "queue_item_id": queue_item_id,
            "source_checkpoint_digest": checkpoint["checkpoint_digest"],
            "ProblemID": problem.problem_id,
            "source_statevector_recomputations": 1,
            "S11_plan_digest": binding.plan_digest,
        },
    )
    preparation = state_preparation_spec(runtime, algorithm=algorithm, pool=pool)
    if (
        preparation.state_preparation_id != item["StatePreparationID"]
        or preparation.payload() != case["state_preparation_payload"]
    ):
        raise QueueBoundRuntimeError("actual S11 source preparation differs")
    return QueueBoundDevelopmentRuntimeV1(
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

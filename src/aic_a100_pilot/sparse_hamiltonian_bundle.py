"""Additive v2 transfer of the exact P0 sparse Hamiltonian matrices.

The v1 MolecularData files fix the integrals, but OpenFermion sparse assembly
was observed to differ bytewise across architectures.  This successor freezes
the already-verified sparse matrices themselves.  The v1 bundle is read-only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any

from .common import (
    ARTIFACT_ROOT,
    A100PilotError,
    embedded_digest_valid,
    load_json,
    publish,
    sha256_file,
)
from .hamiltonian_bundle import MANIFEST as V1_MANIFEST


TRANSFER_V2 = ARTIFACT_ROOT / "p2-source-transfer-v2"
MATRIX_ROOT = TRANSFER_V2 / "sparse-hamiltonians"
MANIFEST_V2 = TRANSFER_V2 / "exact-sparse-hamiltonian-bundle-v2.json"


def _matrix_digest(matrix: Any) -> str:
    from dvg_obs_ceo.identity import canonical_json_bytes
    from dvg_obs_ceo.molecular_identity import _hamiltonian_payload

    return hashlib.sha256(canonical_json_bytes(_hamiltonian_payload(matrix))).hexdigest()


def build_sparse_bundle() -> dict[str, Any]:
    from openfermion import MolecularData, get_sparse_operator
    from scipy import sparse

    v1 = load_json(V1_MANIFEST)
    if not embedded_digest_valid(v1, "bundle_digest"):
        raise A100PilotError("P2 transfer v1 digest is invalid")
    if MATRIX_ROOT.exists() or MANIFEST_V2.exists():
        raise A100PilotError("P2 sparse transfer v2 already exists")
    MATRIX_ROOT.mkdir(parents=True, exist_ok=False)
    cases: list[dict[str, Any]] = []
    try:
        for record in v1["cases"]:
            alias = str(record["alias"])
            source = (ARTIFACT_ROOT.parent.parent / str(record["path"])).resolve()
            if sha256_file(source) != record["sha256"]:
                raise A100PilotError(f"P2 transfer v1 file differs: {alias}")
            molecule = MolecularData(filename=str(source.with_suffix("")))
            molecule.load()
            if molecule.fci_energy is not None or molecule.ccsd_energy is not None:
                raise A100PilotError(f"forbidden outcome in P2 transfer v1: {alias}")
            matrix = get_sparse_operator(
                molecule.get_molecular_hamiltonian(), n_qubits=molecule.n_qubits
            ).tocsc()
            observed = _matrix_digest(matrix)
            if observed != record["Hamiltonian_digest"]:
                raise A100PilotError(f"P0 Hamiltonian reconstruction differs: {alias}")
            destination = MATRIX_ROOT / f"{alias}.npz"
            sparse.save_npz(destination, matrix, compressed=True)
            cases.append(
                {
                    "alias": alias,
                    "case_id": record["case_id"],
                    "source_hdf5_sha256": record["sha256"],
                    "path": destination.relative_to(ARTIFACT_ROOT.parent.parent).as_posix(),
                    "sha256": sha256_file(destination),
                    "size_bytes": destination.stat().st_size,
                    "shape": [int(value) for value in matrix.shape],
                    "nonzero_count": int(matrix.nnz),
                    "Hamiltonian_digest": observed,
                }
            )
    except Exception:
        shutil.rmtree(MATRIX_ROOT, ignore_errors=True)
        raise
    return {
        "schema": "aic-a100-pilot.p2-exact-sparse-hamiltonian-transfer.v2",
        "status": "FROZEN_EXACT_P0_SPARSE_HAMILTONIANS",
        "supersedes_without_mutation": {
            "v1_bundle_digest": v1["bundle_digest"],
            "v1_remains_immutable": True,
            "reason": (
                "Sparse assembly from identical integrals was not byte-identical "
                "across the audited architectures."
            ),
        },
        "case_order": [case["alias"] for case in cases],
        "cases": cases,
        "provenance": {
            "SCF_runs": 0,
            "candidate_molecular_energy_evaluations": 0,
            "optimizer_runs": 0,
            "FCI_evaluations": 0,
            "tolerances_changed": False,
            "source_ansatz_changed": False,
            "candidate_order_changed": False,
        },
    }


def publish_sparse_bundle() -> dict[str, Any]:
    return publish(MANIFEST_V2, build_sparse_bundle(), "bundle_digest")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--publish", action="store_true")
    arguments = parser.parse_args()
    if not arguments.publish:
        raise RuntimeError("select --publish")
    print(json.dumps(publish_sparse_bundle(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

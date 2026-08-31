"""Freeze the exact P0 molecular-integral files for cross-platform transfer.

PySCF integral reconstruction is not byte-identical across macOS/arm64 and
Linux/x86_64.  The P0 CPU run left outcome-free ``MolecularData`` HDF5 files.
This module copies those inputs as content-addressed pilot evidence and proves
that each reconstructs the already-frozen Hamiltonian digest.  It does not run
SCF, candidate energy, optimization, or FCI.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
from typing import Any

from .common import ARTIFACT_ROOT, A100PilotError, load_json, publish, sha256_file
from .p0_baseline import REFERENCE


TRANSFER = ARTIFACT_ROOT / "p2-source-transfer"
HDF5_ROOT = TRANSFER / "hdf5"
MANIFEST = TRANSFER / "outcome-free-molecular-integral-bundle-v1.json"
SOURCE_NAMES = {
    "h2": "v5-mb6-h2-1.5-iteration-1.hdf5",
    "h4": "v5-s11-h4_1_5_known_development.hdf5",
    "lih": "v5-s11-lih_3_0.hdf5",
    "h6": "v5-s11-h6_1_5.hdf5",
    "beh2": "v5-s11-beh2_3_0.hdf5",
}


def _hamiltonian_digest(molecule: Any) -> tuple[str, int]:
    from openfermion import get_sparse_operator
    from dvg_obs_ceo.identity import canonical_json_bytes
    from dvg_obs_ceo.molecular_identity import _hamiltonian_payload

    matrix = get_sparse_operator(
        molecule.get_molecular_hamiltonian(), n_qubits=molecule.n_qubits
    )
    return (
        hashlib.sha256(canonical_json_bytes(_hamiltonian_payload(matrix))).hexdigest(),
        int(matrix.nnz),
    )


def build_bundle(source_root: Path) -> dict[str, Any]:
    from openfermion import MolecularData

    references = {
        str(case["alias"]): case
        for case in load_json(REFERENCE)["cases"]
    }
    if HDF5_ROOT.exists() or MANIFEST.exists():
        raise A100PilotError("P2 source-transfer bundle already exists")
    HDF5_ROOT.mkdir(parents=True, exist_ok=False)
    cases: list[dict[str, Any]] = []
    try:
        for alias in ("h2", "h4", "lih", "h6", "beh2"):
            source = source_root / SOURCE_NAMES[alias]
            if not source.is_file():
                raise A100PilotError(f"missing P0 molecular cache for {alias}")
            destination = HDF5_ROOT / f"{alias}.hdf5"
            with source.open("rb") as reader, destination.open("xb") as writer:
                shutil.copyfileobj(reader, writer)
            molecule = MolecularData(filename=str(destination.with_suffix("")))
            molecule.load()
            if molecule.fci_energy is not None or molecule.ccsd_energy is not None:
                raise A100PilotError(f"forbidden FCI/CCSD outcome in {alias} transfer")
            observed_digest, nonzero_count = _hamiltonian_digest(molecule)
            expected_digest = str(references[alias]["Hamiltonian_digest"])
            if observed_digest != expected_digest:
                raise A100PilotError(f"transferred Hamiltonian digest differs: {alias}")
            cases.append(
                {
                    "alias": alias,
                    "case_id": references[alias]["case_id"],
                    "path": destination.relative_to(ARTIFACT_ROOT.parent.parent).as_posix(),
                    "sha256": sha256_file(destination),
                    "size_bytes": destination.stat().st_size,
                    "qubit_count": int(molecule.n_qubits),
                    "hamiltonian_nonzero_count": nonzero_count,
                    "Hamiltonian_digest": observed_digest,
                    "FCI_energy": None,
                    "CCSD_energy": None,
                }
            )
    except Exception:
        shutil.rmtree(HDF5_ROOT, ignore_errors=True)
        raise
    return {
        "schema": "aic-a100-pilot.p2-outcome-free-integral-transfer.v1",
        "status": "FROZEN_EXACT_P0_HAMILTONIAN_INPUTS",
        "P0_reference_digest": load_json(REFERENCE)["reference_digest"],
        "case_order": [case["alias"] for case in cases],
        "cases": cases,
        "provenance": {
            "source": "outcome-free MolecularData HDF5 files produced during P0 CPU reconstruction",
            "source_absolute_path_persisted": False,
            "copy_is_byte_identical": True,
            "Hamiltonian_digest_verified_against_P0": True,
            "SCF_runs_during_bundle_creation": 0,
            "candidate_molecular_energy_evaluations": 0,
            "optimizer_runs": 0,
            "FCI_evaluations": 0,
        },
        "scientific_boundary": (
            "The bundle fixes the Hamiltonian input across operating systems; it does "
            "not alter the frozen P0 tolerances, ansatz, candidate order, or outcomes."
        ),
    }


def publish_bundle(source_root: Path) -> dict[str, Any]:
    return publish(MANIFEST, build_bundle(source_root), "bundle_digest")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--publish", action="store_true")
    arguments = parser.parse_args()
    source_root = arguments.source_root
    if source_root is None:
        raw = os.environ.get("A100_P0_HDF5_ROOT")
        if not raw:
            raise RuntimeError("set --source-root or A100_P0_HDF5_ROOT")
        source_root = Path(raw)
    if not arguments.publish:
        raise RuntimeError("select --publish")
    print(json.dumps(publish_bundle(source_root), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

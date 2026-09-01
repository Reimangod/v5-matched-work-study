# A0 Environment Note

Phase 1 uses a dedicated parent-runtime virtual environment at
`provenance/dvg-obs-ceo/.venv`.  It was created from the pinned parent
`uv.lock`; no dependency version was relaxed or upgraded.

Observed scientific runtime versions:

- Python 3.10.19
- NumPy 1.23.5
- SciPy 1.10.1
- PySCF 2.2.0
- Qiskit 0.24.2
- OpenFermion 1.5.1

PySCF 2.2.0 uses a legacy CMake policy declaration that CMake 4.4 no longer
accepts by default.  The locked package was therefore built with
`CMAKE_POLICY_VERSION_MINIMUM=3.5`.  This is a build-system compatibility
setting only: the resolved package versions and `uv.lock` digest are
unchanged.

The root project environment is kept separate from this parent runtime.
Phase-1 tests and commands must explicitly bind
`src`, `provenance/dvg-obs-ceo/src`, and
`provenance/dvg-obs-ceo/vendor/ceo-adapt-vqe` on `PYTHONPATH`.  This avoids
changing the historical root `pyproject.toml`, whose byte identity is checked
by immutable MB0 provenance tests.

This note contains no molecular candidate outcome and does not authorize A1
until the A0 manifest audit and scoped regression checks pass.

# S1 — V5 correctness baseline

S1 replays the immutable historical V5/V5.1 development release without
changing its stored winners, candidate order, or artifacts. The corrected
baseline is a new versioned reporting/runtime contract, not a retroactive
rewrite.

Corrections fixed before new performance execution:

- online energy acceptance is source-relative only; FCI/exact reference energy
  is offline reporting data;
- the primary reporting object is the complete accepted nondominated
  energy–physical-resource frontier, while the historical resource-first raw
  winner remains visible and unchanged;
- future endpoint provenance must be copied directly from runtime selection
  evidence; rank/modulo reconstruction is forbidden;
- a zero uncertainty margin is labelled risk-neutral and supports no
  risk-aware-improvement claim;
- checkpoint, full-source-candidate, target-coordinate, and orthonormal-tangent
  gradients have distinct field names and evaluation points;
- failed candidates cannot commit into the parent, and rollback/parent
  immutability remain mandatory.

Changing candidate order or the actual winner rule is explicitly classified as
a scientific change requiring a later separate version and pre-outcome freeze.

Historical environment incident: PySCF 2.2.0 required a source build on Apple
Silicon. The first attempt lacked CMake; CMake 4 then failed against bundled
libxc. Supplying build-only CMake 3.31.10 resolved the build without changing
`uv.lock` or any scientific dependency.

S1 is `GO_S2` only if the immutable release audit, all 509 parent regression
tests, new property/invariant tests, schema validation, frontier replay, FCI
firewall contract, endpoint provenance contract, and rollback/immutability
checks pass.

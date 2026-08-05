# V2 audit remediation and strict pre-performance closure

The original `v5-matched-work-preperformance-no-go-v1` release is not changed.
Its fail-closed conclusion remains valid. This supplement corrects evidence
language, adds independently rebuildable checks, and records what is still
missing before molecular performance execution.

## Audit corrections

1. Param-ADAPT-VQE is now recorded as the peer-reviewed Version of Record:
   DOI `10.1021/acs.jctc.6c00269`, *Journal of Chemical Theory and
   Computation* 22(10), 5090–5101, published online 2026-05-13. The official
   ACS record was verified on 2026-08-05. `use_now` remains false.
2. Closure v2 recomputes all 486 historical SHA-256 values and verifies the
   parent tree, parent commit, CEO* submodule commit, and lock digest. It does
   not use the v1 constant `historical_artifacts_untouched=True` assertion.
3. The pre-S5 candidate-energy count is reconstructed from an initialized raw
   event ledger. The exact claim is: **the repository work-chain record contains
   zero candidate-energy events**. This does not prove that no calculation was
   performed on another machine or outside the recorded chain.
4. S2-v2 is described as checkpoint reconstruction using the pinned
   implementation. It is not a different-engine verification, and its
   recomputed state SHA-256 values are not cross-engine state-fidelity tests.
5. Test counts are separated: S1 construction records 509 parent regression
   tests; ordinary clean-clone reproduction runs this repository's tests.

## Versioned remediation

- `v5-matched-work-s2-stationary-source-v2` adds the scheduled H4 1.5 source.
  Its reconstructed parameter-gradient infinity norm is
  `3.975397840777495e-9`, the maximum sampled central-difference discrepancy is
  `4.446157504667238e-11`, and the checkpoint-energy discrepancy is
  `6.661338147750939e-16 Ha`.
- `v5-matched-work-s3-work-ledger-v2` normalizes six pinned V4.1/V5 historical
  records into raw events. Each expanded search state is charged as one exact
  algebraic rewrite and one unique state expansion. LOW/MEDIUM/HIGH caps are
  mechanically derived from the minimum, upper median, and maximum vectors,
  rounded upward componentwise.
- `v5-matched-work-s4-comparators-v2` adds six callable orchestration adapters,
  one shared counter API, and deterministic structure-level toy/H2/H4 tests for
  cap enforcement, rollback, deduplication, recount, and source immutability.
- `v5-matched-work-pre-s5-readiness-v2` was tagged before
  `v5-matched-work-s5-development-freeze-v2`; the latter fixes the literature
  ledger and freezes the 90-item queue without candidate outcomes.

## Strict audit result

The S4-v2 gate is useful control-flow evidence but is not sufficient production
evidence. Its H2/H4 tests consume pinned checkpoint structures without running
molecular candidate energies, and its backend is a protocol supplied by the
caller rather than a concrete pinned quantum backend.

The strict pre-S6 audit therefore supersedes the S5-v2 authorization and fails
closed on four checks:

- six concrete serialized-source molecular backend entrypoints;
- counter binding inside the pinned energy, gradient, optimizer, rewrite,
  state-expansion, and physical recount kernels;
- outcome-free quantum integration on toy/H2/H4 rather than structure-only
  control-flow integration;
- native executor evidence for same-structure reoptimization, physical
  magnitude pruning, V4.1 joint one-shot compression, V5 without rebuilding,
  and full rebuilding V5.

S6–S14 have version-2 `NOT_AUTHORIZED` records. No molecular candidate
performance was executed. This remains a pre-performance infrastructure No-Go,
not a scientific result about V5 or matched-work performance.

## Clean-clone verification

A fresh recursive clone at the final commit was checked with the root test
environment and the parent's locked `baseline` extra. The observed results were
25 repository tests passed, S0 19/19 checks passed, S2-v2 five-source
byte-identical reconstruction passed, and closure-v2 8/8 checks passed. S1's
historical record remains 509 parent regression tests passed at S1 construction;
the fresh-clone repository suite is the separate 25-test count.

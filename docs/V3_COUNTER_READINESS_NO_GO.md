# V3 counter-correctness and authoritative pre-S5 No-Go

V1 and V2 artifacts and tags remain immutable. V3 addresses the two new
counter findings without claiming that the missing production molecular layer
has been implemented.

## Counter corrections

- Duplicate generation may retain its actual algebraic rewrite charge, but it
  records a separate zero-delta `duplicate-detection` evidence event and does
  not increment `N_states`.
- The toy catalog has two canonical unique candidates. V3 reconstructs
  `N_states=2` for structural magnitude, V4.1 one-shot, and V5 without
  rebuilding. Full V5 reconstructs five unique expansions across its actually
  invoked source/rebuilt catalogs, rather than the v2 value of eight.
- Historical V4.1/V5 aggregates are stored as
  `historical-normalized-events-v3`, explicitly not as raw kernel events.
  The assumption that one expanded state corresponds to one exact rewrite is
  reference-only and unverified across production kernels.
- Historical envelopes remain visible for audit comparison, but
  `production_work_caps` is `null`. They cannot authorize S5 or S6.

## Future raw ledger

The v3 chain protocol requires content-addressed immutable segments with a
previous digest, queue item ID, StatePreparationID, ProblemID, monotonic global
sequence, and segment digest. Its completeness manifest binds the expected and
completed queue, all segment digests, total event count, and reconstructed
candidate-energy count. The protocol is implemented and tested but is not yet
bound to quantum production kernels.

## One authoritative readiness gate

V3 replaces the v2 orchestration-readiness/strict-readiness sequence with one
authoritative gate before S5. It passes the H4, historical evidence, duplicate
counter, provenance-label, ledger-chain, and repository-zero checks. It fails
before S5 on:

- absence of actual kernel events and production cap calibration;
- absence of six concrete molecular executors;
- absence of counter bindings inside pinned quantum kernels;
- absence of toy/H2/H4 quantum integration;
- absence of method-native executor evidence.

No `development-freeze-v3` is published. S5–S14 are `NOT_AUTHORIZED`, candidate
performance remains zero in the repository event record, and this is not a
molecular result.

## Version terminology

V2 is an audit supplement/tag set, not a GitHub Release with assets. Cite both
`v5-matched-work-preperformance-no-go-v2` for the scientific closure and
`v5-matched-work-preperformance-no-go-v2-reproduction-amendment-1` for its
complete clean-clone instructions. V3 is likewise a versioned counter/readiness
supplement unless a separate GitHub Release is explicitly published.

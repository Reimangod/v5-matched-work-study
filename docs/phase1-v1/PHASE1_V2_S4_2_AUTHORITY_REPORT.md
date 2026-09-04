# Phase 1 v2 S4.2 consolidated execution authority

## Decision

`GO_PHASE1_V2_S4_2_EXECUTION`

S4.2 is an additive engineering successor. It does not change the 1,266-row
queue, candidate membership, frozen order, optimizer starts, BFGS settings,
componentwise caps, endpoint certification, or scientific endpoints.

The already observed five-item prefix was replayed from the raw ledgers. All
five queue bindings, terminal artifacts, work totals, caps, and digest chains
were valid. The prefix remains one `ACCEPTED` start followed by four
`ALGORITHM_REJECTED` starts. No item was rerun and no new molecular outcome was
obtained while constructing this gate.

## Remediation

- Live execution now checks the current adapter and integrity-module SHA-256
  against S4.2 before kernel work.
- Every terminal item receives a replay-derived, content-addressed
  attestation.
- Every terminal prefix receives an immutable manifest chained to its exact
  predecessor.
- The next item is refused unless the exact prior prefix validates.
- A bounded contiguous batch runner reuses only immutable case
  reconstruction material in one process. It does not share optimizer state,
  parameters, Hessians, work ledgers, or outcomes between requests.
- Parallel execution remains unauthorized.

S3, S4, and S4.1 remain immutable historical evidence. S4.2 is the sole live
execution authority after this point.

## Verification

- Phase 1 scoped suite: `42 passed, 3 intentional branch-bound skipped`
- Four representative request reconstructions: passed
- New integrity unit tests: passed
- Existing five raw ledgers: replayed and cap-valid
- FCI evaluations added: `0`
- Free-space floor: `40 GiB`; observed at freeze: above floor

The deprecation warnings originate from the pinned historical
Qiskit/OpenFermion/PySCF stack and are not treated as numerical failures. They
must remain visible in logs and must not be silently filtered from release
evidence.

## Authorization boundary

Authorized:

- the exact frozen queue beginning at index 5;
- bounded, contiguous, sequential batch execution;
- append-only terminal attestations and prefix manifests.

Not authorized:

- queue, cap, optimizer, start, or endpoint changes;
- result-dependent scheduling or reordering;
- parallel execution;
- interim performance analysis;
- FCI use or S6 aggregation before all 1,266 requests are terminal.

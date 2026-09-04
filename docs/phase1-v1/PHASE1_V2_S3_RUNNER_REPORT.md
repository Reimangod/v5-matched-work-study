# Phase 1 v2 S3 runner report

## Outcome

`GO_PHASE1_V2_S4_READINESS_GATE`

This decision authorizes only the independent S4 readiness audit. It does not
authorize any LiH, H6, or BeH2 outcome from the 1,266-request screen.

## Real-kernel vertical slice

One H4 calibration request was reconstructed as an exact affine singleton,
initialized by the v2 Euclidean projection with an identity inverse Hessian,
and passed through the same durable execution function intended for S5.

- terminal status: `ACCEPTED` (certified optimizer endpoint, not a compression claim);
- optimizer starts: 1;
- candidate-energy calls: 20;
- FCI evaluations: 0;
- all finite-value, energy, state, gradient, stationarity, exact-constraint,
  and repeated-resource checks passed;
- the calibration request is explicitly not a member of the scientific screen.

The run first used the H4 frozen two-thread route. The subsequent representative
queue audit initially stopped because the v2 source route requires one thread.
No scientific request was run during that stop. The already-committed H4 ledger
was preserved, and the queue-only audit resumed under its distinct frozen
one-thread environment.

## Request binding

The v2 adapter now refuses an absent, corrupted, duplicate, reordered, mutated,
or non-`NOT_STARTED` queue before kernel work. It independently reconstructs:

- B2 source identity;
- A3 CandidatePlan membership;
- final StructuralTargetID;
- exact affine constraint satisfaction;
- byte-exact float64 initialization and OptimizationInitializationID;
- identity inverse-Hessian policy;
- request-specific componentwise work cap.

A3 census IDs and the runtime composer's internal constraint IDs are treated as
separate namespaces. The adapter verifies the registered A3 plan, candidate
membership, and the materialized target instead of incorrectly requiring those
two namespace-specific constraint digests to be identical.

Representative joint/singleton and mapped/zero requests for BeH2 and LiH were
reconstructed without energy or optimizer calls.

## Failure and persistence matrix

Synthetic non-molecular probes re-established:

- accepted, scientific-rejection, cap-rejection, and kernel-failure terminals;
- cap rejection before a kernel call;
- failed-call accounting;
- exact rollback and same-request retry without counter reset;
- recovery after result-publication failure;
- rejection of invalid rollback, overlapping attempts, duplicate terminal,
  duplicate ledger root, and digest corruption.

The optimizer boundary now accepts a positive request-bound `maxiter` and passes
it to the pinned CEO-era BFGS implementation. Invalid values fail before importing
or invoking the optimizer. Runtime `nit`, `nfev`, and `njev` remain reconciled
against durable events.

## Frozen scientific state

- screen requests: 1,266/1,266 `NOT_STARTED`;
- screen candidate-energy calls: 0;
- screen optimizer starts: 0;
- screen FCI evaluations: 0;
- interim performance claim: prohibited.

The public execution entrypoint is hard-blocked until a digest-valid S4 artifact
authorizes this exact queue SHA-256. S4 must still check source integrity, full
queue reconstruction, repository/submodule cleanliness, storage headroom, and
route qualification before S5 can begin.

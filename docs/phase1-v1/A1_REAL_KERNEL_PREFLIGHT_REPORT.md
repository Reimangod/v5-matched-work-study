# A1 Real-Kernel Engineering Preflight Report

## Decision

`GO_A2_SOURCE_LOCK`

This decision is an engineering-readiness decision, not a compression result.
The authoritative records are:

- `artifacts/phase1-v1/a1-real-kernel-preflight/a1-real-kernel-preflight-v1.json`;
- `artifacts/phase1-v1/a1-real-kernel-preflight/a1-readiness-audit-v2.json`.

## What actually ran

The pinned H4 1.5 Å molecular source was reconstructed through the real parent
kernel.  Candidate selection used only registered structure and canonical IDs:

1. the lexicographically first registered whole-block deletion;
2. the lexicographically first compatible pair of disjoint whole-block
   deletions.

The singleton changed the canonical circuit from 80 to 71 CNOTs.  The K=2
joint target changed it from 80 to 62 CNOTs.  These are structural E2 probe
values only.

Each target was optimized from both registered initialization classes:

| E2 target | Starts | Selected start | Energy change from source | Accuracy-feasible at 1e-4 Ha |
|---|---:|---|---:|---|
| singleton deletion | 2 | mapped warm start | +0.0172896563373 Ha | no |
| disjoint K=2 deletion | 2 | zero target coordinates | +0.0359489137736 Ha | no |

All four optimizer endpoints independently passed:

- direct-circuit statevector reconstruction;
- direct Hamiltonian expectation agreement;
- a fresh analytic-gradient call;
- the 1e-8 gradient criterion;
- constraint residual validation;
- two identical full canonical circuit recounts.

No FCI value was evaluated.  No E3 case was constructed or executed.

## Transaction and failure evidence

The preflight injected:

- one failure inside the pinned optimizer path;
- one exclusive artifact-write collision;
- one failure immediately before atomic result publication.

The runtime snapshot digest was exactly restored in both rollback probes.  The
publication failure created no terminal result, and the identical request ID
was committed on its second attempt.

The committed transaction is deliberately labelled
`COMPLETED_ACCEPTED_ENGINEERING_EVIDENCE`.  It proves atomic persistence and
same-request retry.  It is not a scientific acceptance of either transformed
H4 target.  The E2 scientific acceptance count is zero, and this fact is
preserved rather than converted into a success.

## Why A1 can pass with zero scientifically accepted E2 probes

A1 asks whether the complete real path—molecular source, structural mutation,
two-start optimizer, independent certifier, physical-resource recount,
rollback, and atomic publication—works.  It does not estimate E3 performance,
and it must not select a convenient H4 candidate after observing energy.

The two deterministic H4 transformations were therefore retained as accuracy
rejections.  Their rejection is compatible with proceeding to A2 source
construction.  Before A5 authorizes the E3 queue, the formal E2 gate must still
exercise the final production acceptance/rollback rules under the frozen
grammar.  A1 does not waive that later requirement.

## Claim boundary

Allowed now:

- a real H4 singleton and K=2 joint target reached the actual optimizer;
- all four endpoints passed independent numerical and resource certification;
- injected failures rolled back exactly and same-request retry succeeded.

Not allowed now:

- joint improvement over singleton;
- Phase-1 molecular performance;
- a useful H4 compression result;
- FCI, Measurement Cost, noise, hardware, or generalization claims.

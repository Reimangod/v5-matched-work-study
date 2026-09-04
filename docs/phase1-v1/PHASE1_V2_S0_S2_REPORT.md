# Phase 1 v2 S0–S2 report

## Outcome

`GO_PHASE1_V2_SCREEN_RUNNER_IMPLEMENTATION`

Phase 1 v1 remains an immutable pre-outcome No-Go. V2 changes the estimand
openly from an exhaustive joint frontier to a prospective stratified screen.

## Exact reduction before sampling

The joint manifold is contained in each constituent singleton manifold. A
joint whose canonical CNOT count is not strictly lower than both constituents
cannot improve the primary CNOT frontier. Applying this outcome-free rule
reduced 87,399 registered joints to 34,245 eligible joints.

The complete set of 485 CNOT-improving singletons remains in the queue. Thus
the singleton comparator is not sampled.

## Frozen screen

| Quantity | Count |
|---|---:|
| Complete eligible singletons | 485 |
| Eligible joint population | 34,245 |
| Frozen joint screen | 148 |
| Frozen targets | 633 |
| Two-start requests | 1,266 |

LiH 3.0 A retains all 60 eligible joints. Each nonempty
transformation-kind/exact-CNOT-saving stratum in the other three cases retains
the two lowest deterministic SHA-256 ranks. Inclusion probabilities are stored
with every selected joint.

## Pre-queue incident and correction

The first queue build stopped before publication because a recycled-Hessian
OBS warm start violated a registered exact constraint. No energy, optimizer,
or FCI call occurred. Rather than regularizing a target-dependent Hessian, v2
now uses the Euclidean projection of B2 coordinates into the exact affine
target manifold and an identity initial inverse Hessian for both starts. All
mapped coordinates are checked against the exact constraints before queue
publication.

## Frozen state

- Queue generation repeated twice with identical bytes.
- 1,266 unique RequestIDs.
- 1,266/1,266 `NOT_STARTED`.
- Candidate energy evaluations: 0.
- Optimizer starts: 0.
- FCI evaluations: 0.
- Maximum registered optimizer iterations: 2,532,000.

S3 may implement and test the request-bound runner. Molecular screen execution
is not yet authorized.

## Claim boundary

A future positive screen is a signal requiring held-out confirmation. A
negative screen is not proof of absence from the full eligible universe.

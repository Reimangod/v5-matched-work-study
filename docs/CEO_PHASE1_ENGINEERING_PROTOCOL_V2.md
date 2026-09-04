# CEO post-growth compression — Phase 1 engineering protocol v2

## Objective

Execute the smaller prospective screen without weakening v1 provenance,
identity, rollback, or kernel-bound accounting.

## Frozen workload

- 485 complete primary-CNOT-improving singleton targets;
- 148 prospectively selected joint targets;
- 633 targets total;
- two starts per target;
- 1,266 immutable request rows.

Every request binds the v2 protocol, case, B2SourceID, CandidatePlanID,
StructuralTargetID, candidate IDs, start policy, exact float64 initialization,
OptimizationInitializationID, and the identity initial-inverse-Hessian policy.

The first pre-queue build correctly failed before artifact publication because
an OBS/recycled-Hessian warm start violated a registered constraint for one
target. No energy or optimizer ran. V2 therefore uses a directly verified
Euclidean affine projection and identity initial inverse Hessian for both
starts; it does not silently regularize or repair source Hessians.

## Work caps

Before candidate outcomes, each start is capped at 2,000 optimizer iterations,
2,500 energy calls, and 2,500 analytic gradient vectors. The iteration limit is
larger than twice the largest 884-iteration zero-start B2 calibration already
recorded in A2. Cap rejection is a terminal operational result and may not be
replaced by another sampled candidate.

## Runner requirements

The runner must use the existing actual molecular kernel and:

1. reconstruct the exact frozen target and verify all bound identities;
2. append request, kernel events, checkpoint, result, and terminal receipt;
3. count failed calls at the kernel boundary;
4. support same-RequestID resume only;
5. rollback exact runtime state after failure;
6. refuse unknown, duplicate, reordered, or mutated requests;
7. perform independent endpoint and full resource certification;
8. retain all rejected, cap-rejected, failed, and completed rows.

CPU is the reference route. A100 execution is optional and is authorized only
after objective, gradient, terminal optimizer, and resource parity for that
target class. A GPU qualification failure falls back to CPU without changing
queue order, caps, or scientific meaning.

## Release gates

No outcome execution is allowed until the queue reconstructs byte-identically,
all 1,266 rows are `NOT_STARTED`, runner failure probes pass, disk headroom is
verified, and the authoritative readiness artifact is green.

No interim performance table, FCI comparison, frontier conclusion, or method
claim is allowed while a frozen request lacks a terminal record.

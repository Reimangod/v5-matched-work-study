# Phase 1 v2 S5 bounded sequential batch pilot

## Scope

The S4.2-authorized pilot executed the exact frozen queue indices 5 through 12
in one process. Queue order, candidates, two-start design, caps, pinned BFGS,
endpoint certification, and all scientific endpoints were unchanged.

The process reused only immutable case reconstruction material. Each request
retained a separate work request, cap, raw ledger, terminal result, terminal
attestation, and prefix manifest. No optimizer state, coordinates, inverse
Hessian, energy, or outcome was reused between requests.

## Integrity result

- Previous terminal prefix: `5 / 1266`
- New terminal prefix: `13 / 1266`
- Pilot statuses: `6 ACCEPTED`, `2 ALGORITHM_REJECTED`
- Complete prefix statuses: `7 ACCEPTED`, `6 ALGORITHM_REJECTED`
- Prefix digest: `d983c9e78da4a7eaea29a31cb5c24c7d0623553b9f0203b6adb693cf4cd52e28`
- Full raw-ledger replay of all 13 terminal items: passed
- Componentwise cap reconciliation: passed
- Production dense exponentials: unchanged by this infrastructure work
- FCI evaluations: `0`

The statuses are recorded as required terminal evidence. They were not used
to alter scheduling, queue membership, caps, optimizer settings, or the next
scientific protocol.

## Engineering timing

Filesystem publication times place the bounded eight-item interval between
`2026-09-05T05:30:06+0900` and `2026-09-05T05:53:50+0900`, or approximately
1,424 seconds. This is observational engineering telemetry, not a matched-work
metric and not part of a performance claim.

The observed mean is approximately 178 seconds per request. A purely serial
extrapolation for the remaining 1,253 requests is about 62 hours, before
allowing for heavier H6 cases. This timing, rather than any energy or terminal
status, is sufficient to evaluate a separately frozen deterministic CPU
window schedule.

## Claim boundary

This pilot demonstrates only that bounded in-process execution preserves the
frozen request semantics and improves operational throughput. It does not
establish compression success, joint-over-singleton advantage, Pareto
dominance, molecular generalization, or superiority over CEO*.

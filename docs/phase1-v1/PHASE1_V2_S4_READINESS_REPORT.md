# Phase 1 v2 S4 readiness report

## Outcome

`GO_PHASE1_V2_FROZEN_SCREEN_EXECUTION`

This Go applies only to the exact queue with SHA-256
`8966e0ee06b0f79e44a6ac5d344232b533409765a10ae34f7eeef6e7cebf2173`.

## Passed gates

- S3 digest, implementation hashes, and claim boundary are valid.
- All four B2 source cases remain eligible under the pinned one-thread route.
- All 1,266 queue rows were regenerated and matched the exact on-disk bytes.
- All rows remain `NOT_STARTED`; screen energy, optimizer, and FCI counts are zero.
- The scientific/identity/optimizer-accounting/persistence partition passed:
  `46 passed, 1 intentional branch-bound skip`.
- Parent and both recursive submodules are clean and pinned.
- Local and remote readiness commits are identical.
- Free space was 84,001,828,864 bytes, above the 40 GiB floor.

The frozen queue file contains two terminal LF bytes because
`canonical_json_bytes` already emits one LF and the original exclusive freezer
adds one more. S4 explicitly reconstructed and compared this exact historical
on-disk serialization; no artifact was rewritten.

## Scope

S5 may execute RequestIDs only in frozen order and under the bound componentwise
caps. It may not change the queue, initialization, sampling strata, target,
optimizer, or cap after observing outcomes. Interim performance tables and FCI
reporting remain prohibited until all 1,266 requests are terminal.

The inherited full-history secret-scanner was not used as the S4 authority
because it repeatedly scans the full tree over 422 commits. This exclusion is
recorded in the readiness artifact, and no full-suite-green claim is made.

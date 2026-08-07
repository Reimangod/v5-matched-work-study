# Sequential Rebuilding V1

## Scientific purpose

This successor fixes one primary hypothesis: under the same
stationarity-normalized CEO* source and the same componentwise work envelope,
sequential catalog rebuilding after commit produces nondominated points absent
from V4.1 and V5-no-rebuild across multiple contexts.

V5-Core contains only sequential catalog rebuilding and is the primary causal
method. V5-Pro adds exact rewrite pre- and post-passes and is secondary; its
results cannot be used as evidence for the isolated V5-Core mechanism.

## Fail-closed stage boundary

S0 through S4 establish production semantics. Until the authoritative S4
closure passes both gates below, S5 freeze, candidate molecular energy
evaluation, and every performance claim are `NOT_AUTHORIZED`.

### Academic-integrity gate

- Candidate energy states cannot confuse absence or non-evaluation with a
  scientific zero.
- Intent identity, physical-state identity, and execution-request identity are
  distinct.
- Matched-work comparisons use the same frozen source and componentwise work
  envelope.
- V5-Core and V5-Pro remain separate causal claims.

### Systems-safety gate

- Semantic events originate inside the production executor.
- Raw counters, semantic ledger totals, and release totals reconcile exactly.
- A failed transaction restores the exact source digest and leaves no orphan
  artifact.
- Frozen queues are nonempty, digest-bound, complete, and substitution-safe.
- Duplicate physical states receive at most one quantum evaluation while all
  intent aliases remain traceable.

S0 authorizes only S1 semantic-contract work. It supplies no molecular or
performance evidence.

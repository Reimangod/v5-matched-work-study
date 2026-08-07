# MB5.1 — outcome-free production-backend binding

MB5.1 adds six separate production-backend modules. Shared code is limited to
request validation, identity, componentwise cap precheck, raw boundary events,
exact transaction rollback, and result serialization. Candidate construction,
selection, pruning, and replenishment remain method-specific.

The pinned parent Python environment imports and hashes the actual APIs for
source block recovery, candidate enumeration, rewrite verification,
statevector recomputation, energy, analytic gradient, BFGS optimization, and
full circuit recount. Import inspection does not instantiate a molecule and
does not call a molecular kernel.

Every MB5.1 dry-run requires an energy-blocking sentinel and rejects production
mode before a kernel call because no MB7 authorization artifact exists. The
audit also checks wrong schema/method/source identities, pre-operation cap
rejection, exact rollback, linked retry provenance, physical-state deduplication,
fixed-whitelist exclusion, child-dependent replenishment, physical magnitude
deletion, and the rule that zero resource reduction is not success.

The first locally generated audit exposed a control-plane defect before commit:
the upstream optimizer had been bound as one opaque call, so iteration events
could not be counted at their actual callback boundary. That record is retained
as `mb5-1-production-backends-v1.json`. The v2 successor binds the pinned
`minimize_bfgs` energy, gradient, optimizer-start, and per-iteration callbacks
and explicitly supersedes v1. A second self-audit found that v2 embedded a
host-specific macOS platform string and therefore could not rebuild identically
on Linux CI. The v3 successor makes the import identity cross-platform and
defers exact execution-platform identity to the MB6 queue freeze. No molecular
outcome existed in any version.

Authoritative current records:

- `artifacts/v5-final/method-native/mb5-1-owner-directive-v1.json`
- `artifacts/v5-final/method-native/mb5-1-production-backends-v3.json`
- `artifacts/v5-final/pre-execution/p0-capacity-no-go-v1.json`

The decision is `GO_MB6_OUTCOME_BLIND_QUEUE_FREEZE_ONLY`. The P0 capacity No-Go
remains active, so molecular candidate energy, H2/H4 execution, the existing
90-item queue, and performance claims remain `NOT_AUTHORIZED`.

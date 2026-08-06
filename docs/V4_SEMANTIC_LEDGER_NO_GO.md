# V4 semantic identity and frozen-queue ledger No-Go

V1–V3 artifacts and tags remain immutable. V4 closes three additional design
holes while keeping the authoritative gate before S5.

## Canonical state deduplication

V4 orchestration deduplicates using canonical `proposed_state_id`, not
`candidate_id`. Its integration fixture includes two distinct candidate IDs
that propose the same state and verifies that only one increments `N_states`.
Production still must derive and bind this identity from the post-rewrite
ansatz structure/state; the fixture is not molecular evidence.

## Semantic kernel events

The v4 event format binds operation, units, dimension, delta, queue item,
StatePreparationID, ProblemID, path, and content digest. Strict reading
recomputes the permitted delta from operation semantics. Charged events require
positive units, full gradients require a positive dimension, and duplicate
detection is a zero-unit/zero-delta evidence event. Events must match their
segment's queue item and source identity.

## Frozen nonempty queue binding

The chain root and completeness manifest require a canonical frozen queue
artifact with:

- nonempty expected queue;
- unique queue item IDs;
- exact queue count;
- canonical queue digest;
- frozen artifact SHA-256.

The manifest verifies every expected item was completed and has a segment,
global sequence monotonicity, all segment digests, and candidate-energy totals.
An empty queue is rejected when constructing the binding and cannot become a
complete manifest.

## Current gate

No S5-v4 queue exists, so no production queue binding, semantic kernel segment,
completeness manifest, candidate-energy total, or production cap is published.
The existing v2 empty root still supports only the limited pre-S5 statement
that the repository record contains zero candidate-energy events. Production
candidate-energy count is explicitly `null`, not zero.

The authoritative gate therefore fails before S5-v4. S5–S14 are
`NOT_AUTHORIZED`; no candidate performance or molecular result exists. V4 is a
versioned supplement/tag, not a GitHub Release.

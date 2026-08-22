# MB3.1 — method-native ledger hardening

MB3.1 is an additive, infrastructure-only layer. It does not revise the
historical MB2/MB3 artifacts and does not authorize candidate-energy work.

The supported result-publication function now performs request/result binding
and exact executor binding before an exclusive-create write. Every hardened
event is bound to the executor method ID, entrypoint, implementation SHA-256,
pinned parent commit, and pinned CEO* commit. Content IDs and ledger roots use
one strict lowercase SHA-256 validator.

Candidate registration uses an explicit matched-work rule: work already spent
on candidate generation remains charged. If unique-state expansion would cross
the cap, expansion returns `CAP_REJECTED`; it emits no expansion event, calls no
kernel, and does not mutate the canonical-state set.

Segment lifecycle is explicit. Each queue item has unique attempt IDs and
contiguous attempt ordinals. A rolled-back attempt may be followed by a retry.
Exactly one item-terminal segment is allowed, and no attempt may follow it.
Completeness is derived from the terminal segments rather than a caller-supplied
completed-item list. The queue binding also includes the digest of a successful,
artifact-bound schema audit.

All tests are synthetic and molecule-free. This hardening closes publication
and lifecycle ambiguity; it is not proof that a native molecular kernel exists.


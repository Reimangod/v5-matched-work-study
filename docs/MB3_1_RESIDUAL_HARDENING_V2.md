# MB3.1 residual hardening v2

This is an additive infrastructure repair. It does not replace the v1 artifact
and does not authorize molecular execution.

Executor identity is now verified by importing the canonical `module:qualname`,
requiring a callable, resolving its source with `inspect`, requiring that source
to equal the declared implementation path, hashing the exact bytes, and checking
both pinned provenance commits. Publication repeats this verification.

Queue binding no longer accepts caller-supplied `checks=True`. The pinned Draft
2020-12 JSON Schema is loaded and validated, and the schema path, ID, SHA-256,
validator name/version, queue SHA-256, zero error count, and schema-audit digest
are bound into a reproducible v3 queue binding.

If unique-state expansion would exceed its cap, completed candidate-generation
work remains charged. Expansion work is zero, the canonical-state set is not
mutated, and a `CAP_REJECTED` record is retained in the integrity-bound journal.
Replay and item completeness require that record; deletion, reordering, or
semantic alteration fails closed.

The supported v3 publication path revalidates the request, result, callable,
executor, queue, persistent ledger, completeness manifest, transaction, and any
required rollback record before exclusive creation.

All evidence in the v2 audit is synthetic and molecule-free. Its decision only
allows MB4.1 v2 protocol drafting and review preparation.

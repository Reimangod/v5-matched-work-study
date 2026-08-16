# MB5 — six outcome-free method-native executors

MB5 provides six concrete callable entrypoints for deterministic structural
semantics. Every audit invocation uses a declared synthetic fixture with no
molecule, Hamiltonian, candidate energy, development result, or performance
outcome. The entrypoints reject outcome-bearing fields, production mode,
production queue bindings, nonzero candidate-energy counts, and protocol
digests that do not match the committed MB4.2 freeze.

The six canonical methods are:

1. immutable CEO* source;
2. same-structure reoptimization transaction preparation;
3. single-coordinate structural magnitude pruning;
4. V4.1 deterministic one-shot sentinel selection;
5. V5 fixed-source-whitelist / no-replenishment; and
6. V5 sequential with rebuilding.

Magnitude validation physically removes one synthetic generator and performs a
full deterministic structural resource recount. Zero resource reduction is
recorded as zero and is not reported as a successful reduction. The V4.1 path
selects the lowest canonical ID per equivalence class and at most four classes.
The two V5 paths share current-state ranking; only the full rebuilding path may
select a replenished structural candidate.

This is not molecular execution evidence. The terminal decision is
`GO_MB6_QUEUE_FREEZE_ONLY`. MB6 may create and audit an outcome-blind queue
freeze, but may not execute H2/H4, the development queue, a molecular energy
kernel, or any performance experiment.

The authoritative artifact is
`artifacts/v5-final/method-native/mb5-outcome-free-executors-v1.json`.

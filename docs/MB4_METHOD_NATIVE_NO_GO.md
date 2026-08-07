# MB4 — method-native backend No-Go

MB4 stops fail-closed before molecular candidate execution. The blocker is not
an observed performance failure. It is that three method identities are not yet
defined strongly enough to implement six production backends without silently
changing the comparison.

## V5 no-rebuild contradiction

The parent runner calls `catalog_builder(runtime)` at every round
(`v5_sequential.py:108`) and again after an accepted child (`:157`). It rejects
a post-commit catalog whose runtime digest is not the candidate runtime
(`:158-159`). The parent candidate executor also recovers the current catalog,
requires every frozen atomic ID to be present, and requires both semantic and
numerical constraint identity (`v5_s8_h4_width1.py:340-356`).

The frozen control says “reuse the original catalog snapshot.” A literal source
snapshot violates the parent child-binding checks. A plausible alternative is
to freeze the original structural candidate-ID whitelist and rebind only those
IDs to each current child. That is implementable because block and candidate
IDs are structural, while numerical context has a separate digest. However,
the current freeze does not decide:

- whether this structural rebinding is the intended meaning of reuse;
- how removed/stale candidates terminate;
- whether predictions, curvature coordinates, resources, or ordering update;
- whether a current candidate that was absent from the source is always barred.

Those choices affect the causal control. Selecting one inside implementation
would create a new algorithm under an already frozen name.

## Magnitude control

The parent code defines the magnitude predictor as squared constraint residual
(`calibration.py:137-160`), and S4 correctly requires physical generator
deletion plus a full recount. But neither the parent source nor official CEO*
implementation supplies a named post-ansatz magnitude-pruning executor. The
existing freeze does not fix tie-breaking, batch size, sequential behavior,
stale ordering, or stopping. These can be prospectively frozen, but cannot be
inferred and then described as a pre-existing parent-native method.

## V4.1 replay

The native V4.1 executor is intentionally bound to its historical, case-specific
S5 sentinel freeze (`v4_1_exact_multisystem.py:182-278`). A new H2/H4
calibration requires new outcome-free screening and sentinel freezing. Copying
historical sentinels or results into that queue would violate provenance.

## Preserved result

MB0-MB3 remain valid infrastructure: immutable baseline, code-level method
registry, shared recording interface, and live semantic ledger. No proxy shell
is counted as a molecular backend. No H2/H4 calibration queue is created, no
molecular candidate energy is evaluated, and the development queue remains
90/90 `NOT_STARTED` with zero completed items and zero segments.

The decision is `NO_GO_MB4_UNRESOLVED_METHOD_NATIVE_SEMANTICS`. MB5-MB7,
H2/H4 candidate energy, development execution, and performance claims remain
unauthorized. Resolution requires a new versioned pre-outcome protocol for the
no-rebuild and magnitude controls, followed by a new V4.1 calibration sentinel
freeze and six exact kernel implementations.

The closing audit passed 11 targeted MB0-MB4 tests and the complete suite passed
96 tests with 3 expected historical xfails.

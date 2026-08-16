# MB2 — shared method-native recording interface

MB2 implements a common request/result envelope for six distinct native
executors. It standardizes records, not algorithms. The module contains no
candidate construction, catalog selection, optimizer, acceptance, or rollback
control flow.

Every request content-addresses the queue item, method, case,
`StatePreparationID`, `ProblemID`, source checkpoint, Hamiltonian, frozen queue,
work cap, optimizer policy, acceptance policy, RNG identity, and environment.
Changing any one of these fields changes `method-native-request-v1` identity.

Every result records terminal status, exact executor identity and code hash,
parent/child state identity, raw semantic events, work ledger, resource recount,
transaction evidence, failure/rollback evidence, and completeness. Result and
event identities must bind back to their request. An `INFRASTRUCTURE_ONLY`
record is prohibited from claiming a child, raw events, or completeness.

The exact executor identity includes a classification and entrypoint so a
parent-native V4.1/V5 implementation, a parent control, a parent-primitive
composition, and the new no-rebuild causal ablation cannot be silently
interchanged under one method label.

The six round-trip probes are synthetic, zero-work serialization checks. They
are explicitly `INFRASTRUCTURE_ONLY/NO_PERFORMANCE_EVIDENCE`; they neither load
a molecular kernel nor evaluate candidate energy. The targeted MB0-MB2 audit is
5 passed, and the complete suite is 90 passed with 3 expected xfails. The
90-item development queue remains 90/90 `NOT_STARTED`, with zero
completed items, zero segments, and zero candidate-energy evaluations.

MB2 authorizes only MB3 live ledger binding. H2/H4 calibration, development
execution, and performance claims remain unauthorized.

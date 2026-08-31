# MB3 — live semantic ledger

MB3 provides the operation recorder that method-native kernels must call at the
actual catalog, quantum, optimizer, statevector, rewrite, and resource-recount
sites. Controllers cannot supply arbitrary work deltas. Operation name, units,
dimension, outcome, and delta are reconstructed together and fail closed.

The registered work components are energy evaluations, gradient vectors,
gradient-component equivalents, HVPs, optimizer starts and iterations, resource
recounts, candidate generations, unique search states, rewrite verifications,
and statevector recomputations. A full gradient charges one vector plus
`dimension` component equivalents. A candidate-energy operation charges an
energy evaluation. Evidence-only duplicate events must have zero units and zero
delta.

`execute_kernel` checks the componentwise cap before calling its supplied kernel
function. If the cap would be exceeded, the function is not called and neither
event nor counter state changes. A called function, including one that fails,
is charged and recorded.

Candidate generation and unique search-state expansion are separate. The
unique-state key is `ProposedPhysicalStateID`, never candidate ID. The audit
registers two different synthetic candidate IDs for one physical-state ID and
observes two generations, one unique search state, and one zero-delta duplicate
event.

Every event binds request, queue item, method, case, `StatePreparationID`,
`ProblemID`, Hamiltonian digest, path, and producer. Strict reconstruction feeds
content-addressed segments with a global sequence and a nonempty frozen-queue
binding. An empty completed set is incomplete. Raw totals, reconstructed ledger
totals, and release totals must match component by component.

The audit's single candidate-energy event invokes only a constant-returning
synthetic function. No molecular Hamiltonian, source checkpoint, circuit, H2/H4
case, or development queue is loaded. It is
`SYNTHETIC_INFRASTRUCTURE_ONLY/NO_PERFORMANCE_EVIDENCE`.

The targeted MB0-MB3 audit is 10 passed; the complete suite is 95 passed with 3
expected xfails. The 90-item development queue remains 90/90 `NOT_STARTED`,
with zero completed items, zero segments, and zero candidate-energy evaluations.
MB3 authorizes only MB4 native executor implementation; it does not authorize
molecular execution.

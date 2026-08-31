# MB1 — parent method semantics

MB1 is a code-reading and identity-freeze stage. It executes no molecular
candidate energy and creates no scientific outcome. Source references below are
bound by SHA-256 in `mb1-parent-semantics-v1.json` at parent commit
`4783b9ff9f9b6f2061a1ef8c02613f4c6cef38db` and CEO* commit
`a3f89d03e6a03c89767d3cf8ee7657a57653dda0`.

## Evidence classification

The six labels do not all correspond to pre-existing named parent algorithms.
That distinction is essential: a control composed from parent primitives must
not be presented as a historical parent entrypoint.

| Method | Evidence class | Production basis |
|---|---|---|
| immutable CEO* source | parent primitive composition | frozen checkpoint reconstruction plus paper-era recount; no optimizer or rewrite |
| same-structure reoptimization | parent-native control | `ns10_h6_optimizer_ablation.py:450` retains source indices and optimizes only its coefficients |
| structural magnitude pruning | parent primitive composition | `calibration.py:137-160` defines magnitude as squared constraint residual; S4 requires physical deletion and full recount |
| V4.1 one-shot joint | native parent entrypoint | `v4_1_multisystem.py:172` and `v4_1_exact_multisystem.py:182` |
| V5 sequential rebuilding | native parent entrypoint | `v5_sequential.py:89` plus `v5_s8_h4_width1.py:103` |
| V5 sequential no-rebuild | new causal ablation | same V5 kernels with a separately named original-catalog policy |

The official CEO-ADAPT-VQE paper and pinned upstream repository define CEO*
growth and Hessian recycling, but no post-ansatz magnitude-pruning algorithm.
The parent evidence repository likewise has no standalone magnitude-pruning or
no-rebuild executor. Therefore those two labels must not falsely claim such an
entrypoint. Magnitude tie-breaking/stopping must be frozen before outcomes;
no-rebuild must be implemented as an explicit new causal policy.

## V4.1 joint semantics

`v4_1_multisystem.py:191-218` reconstructs one immutable source, recounts it,
recovers DVG blocks, enumerates atomic candidates, and deduplicates by
equivalence class. `screen_case` composes compatible atomic candidates using
`compose_registered_candidates` (`:229`, `:241`) and performs deterministic
joint search (`:255`). The unit of a V4.1 candidate is consequently one ordered,
compatible set of atomic registered rewrites, not one arbitrary dropped
parameter.

The canonical joint target is built in `composition.py:183-319`. Unselected
source positions remain in order; selected contiguous blocks are replaced by
their registered target indices; exact constraint systems are combined; and
iteration boundaries are recomputed. This target is always source-relative.

`v4_1_exact_multisystem.py:182-300` replays only the frozen sentinel queue.
Every sentinel is reconstructed against the same source and sent independently
to the parent `_execute_attempt`; a rejected transaction must prove exact source
rollback. Lines 238-240 and 352-355 explicitly exclude FCI/exact ground energy
from runtime selection and acceptance.

## V5 sequential semantics

`v5_s8_h4_width1.py:141-311` builds a catalog from the current runtime digest.
It recounts the current source, recovers current blocks, enumerates and
deduplicates candidates, composes registered rewrites, maps the recycled model
to target-native coordinates with `obs_warm_start`, recounts structural targets,
and selects a risk-aware Pareto queue.

`candidate_executor` (`:329-619`) re-recovers the current catalog, rejects stale
atomic IDs, recomposes the canonical target, uses recycled-OBS initialization
and the registered least-squares fallback, runs the parent optimizer, performs
independent energy/state/gradient checks, and recounts both physical and
deterministic-structural circuits. On the candidate runtime, lines 551-555 store
the new ansatz, energy, gradient, selected final inverse Hessian, and
statevector.

`v5_sequential.py:89-196` binds each round to the latest committed runtime.
Critically, after acceptance it calls `catalog_builder(runtime)` again at line
157 and commits that child-bound catalog digest at lines 160-167. Thus full V5
rebuilds from the accepted child rather than editing the parent catalog.

There is no parent no-rebuild runner. The scientifically valid ablation must
reuse the exact V5 catalog, candidate, optimizer, acceptance, recount, and
transaction kernels while keeping the original source catalog identity after
commit. It must have a new executor identity and an audit proving that catalog
policy is the only intended difference.

## Warm start, curvature, transaction, and resources

`calibration.py:188-202` maps the source coefficients, gradient, and recycled
inverse Hessian into native target coordinates. Accepted V5 candidates inherit
the selected final inverse Hessian (`v5_s8_h4_width1.py:553`).

`v5_nested_transaction.py:373-445` commits only a fully accepted, resource-bound,
source-budget-bound child. Its rollback at `:447-463` restores the complete
parent runtime snapshot; `__exit__` at `:465-471` rolls back any uncommitted
scope. The snapshot includes structure, energy, gradient, inverse Hessian,
statevector, work, RNG, and metadata (`transaction.py:193-323`).

`resources.py:91-105` binds the pinned paper-era QASM, CNOT count, and CNOT depth
implementation. `evaluate_full_circuit_resources` (`:120-199`) composes the full
ansatz without adding a new compiler path and reports CNOT count, CNOT depth,
total depth, parameter count, and recovered logical block count.

## Stage boundary

MB1 proves code identity and records negative findings. It does not prove that
the six production wrappers exist, that live semantic ledger events reconcile,
or that either catalog policy has been observed in a molecular execution. MB2
may implement the common recording interface only. H2/H4 calibration, the
90-item development queue, and every performance claim remain unauthorized.

The closing audit passed the targeted MB0+MB1 tests (2 passed) and the complete
suite (87 passed, 3 expected xfails). The development queue remained 90/90
`NOT_STARTED`, with zero completed items, zero segments, and zero candidate
energy evaluations.

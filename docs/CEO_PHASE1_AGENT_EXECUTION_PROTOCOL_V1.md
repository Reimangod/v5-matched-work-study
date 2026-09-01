# CEO Post-Growth Compression Phase 1 — Agent Execution Protocol v1

## 0. Document status

**Purpose:** executable instructions for an autonomous coding/research Agent

**Status:** draft; outcome-bearing execution is not authorized until Agent Stage A5 issues the frozen E3 queue gate

**Repository:** `/Users/rei/Documents/ceo-adapt-vqe/v5-matched-work-study`

**Preferred scientific parent:** `bca77f26aad98937e69e824cb8024960c6994e60`, subject to A0 audit

**Dedicated branch:** `feature/phase1-joint-frontier-v1`

**Dedicated worktree:** `/Users/rei/Documents/ceo-adapt-vqe/ceo-phase1-joint-frontier`

This file does not authorize alteration of historical algorithms, artifacts,
tags, releases, or existing user-authored planning documents.

## 1. Agent mission

Execute Phase 1 as the smallest scientifically defensible test of the
following question:

> Under a common source and optimization contract, does the registered
> pairwise joint transformation language attain a lower observed
> accuracy-feasible canonical CNOT frontier than the complete registered
> singleton language, and does that advantage remain below the fully
> reoptimized CEO* prefix frontier?

The Agent must optimize for:

1. scientific correctness;
2. transparent negative as well as positive results;
3. real molecular end-to-end execution before scale;
4. the shortest critical path that preserves 1–3;
5. recoverable and auditable software behavior.

The Agent must not optimize for a preferred outcome, publication claim, large
percentage reduction, or reuse of a historical winner.

## 2. Authority order

Before taking implementation action, read these files completely in order:

1. `docs/CEO_PHASE1_SCIENTIFIC_PROTOCOL_V1.md`;
2. `docs/CEO_PHASE1_ENGINEERING_PROTOCOL_V1.md`;
3. `docs/CEO_PHASE1_SCOPE_REDUCTION_RATIONALE_V1.md`;
4. this Agent protocol;
5. `docs/CEO_PHASE1_PHASE2_PLAN_INDEX_V1.md` for branch decisions only.

Authority precedence is:

```text
Phase-1 Scientific Protocol
  > Phase-1 Engineering Protocol
  > this Agent Execution Protocol
  > historical plans and artifacts
```

Phase-2 documents are inactive. If this file conflicts with the scientific or
engineering protocol, stop before outcomes, preserve the conflict as an
incident, and repair this file rather than silently choosing an interpretation.

## 3. Fixed scientific contract

The Agent may not change the following protected fields after A0 protocol
freeze:

- exact noiseless simulation regime;
- B2 as the uniformly reoptimized canonical final CEO* source;
- primary loss
  `DeltaE_comp = E_opt(target) - E_opt(B2)`;
- accuracy threshold `DeltaE_comp <= 1e-4 Ha`;
- primary resource: paper-era canonical logical CNOT count;
- complete singleton universe relative to the frozen grammar;
- primary joint bounds `K=2`, structural locality `L=1`, source depth `D=1`;
- no energy-informed candidate generation, filtering, ordering, or retry;
- common optimizer family, tolerances, caps, gradients, and failure taxonomy;
- two starts per target: mapped warm start and deterministic zero target start;
- FCI reporting-only firewall;
- fully reoptimized CEO* prefix as a retrospective oracle comparator;
- molecule-family, rather than geometry, as the replication unit;
- E3 systems: LiH 3.0 Å, H6 1.5 Å, H6 3.0 Å, BeH2 3.0 Å;
- E4 unexecuted and untouched in Phase 1.

The primary comparison is:

```text
min canonical CNOT
subject to DeltaE_comp <= 1e-4 Ha
and endpoint certification passes
```

All minima are reported as **observed** minima under the frozen optimizer
contract. Never call them global optima.

## 4. Evidence firewall

Use the evidence classes exactly as follows:

- `E0`: literature and pinned upstream code; definitions and prior-art only;
- `E1`: V1–V6, V4.1/V5/V5.1, S12 matched-work; motivation and fixtures only;
- `E2`: analytic, synthetic, H2, H4; engineering and numerical calibration;
- `E3`: Phase-1 molecular development decision;
- `E4`: Phase-2 untouched evidence; inaccessible to Phase-1 execution.

Historical LiH/BeH2 winners may be replay fixtures only after the grammar is
frozen. They may not alter `K`, `L`, transformation families, tie-breaking,
thresholds, optimizer caps, or the E3 queue.

The Agent must add an automated protected-input test that rejects:

- FCI energy in generation, ranking, optimization scheduling, acceptance, or
  stopping inputs;
- E1 result/winner identifiers in grammar or queue-generator inputs;
- E3 outcome fields in candidate generation or retry decisions;
- E4 identities or outcomes in any Phase-1 worker request.

## 5. Scope lock

The following are outside the Phase-1 critical path:

- Hessian/OBS/CEO-aware ranking;
- B3e/B5 development;
- `K>2`, `D>1`, sequential rebuilding, beam search;
- lifecycle, scaffold, QGT, survivor-only replay;
- TETRIS or Co-ADAPT source construction;
- OGM, measurement reuse, shot allocation, or Measurement Cost reconstruction;
- noise, hardware performance, routing, and broad compiler studies;
- break-even analysis;
- A100 speedup claims;
- five-objective dominance as the primary conclusion.

Do not create placeholder implementations or generalized frameworks for these
items. Add them only to a Phase-2 backlog document if needed.

## 6. Minimal implementation boundary

Create only:

```text
src/phase1_frontier/
tests/phase1_frontier/
configs/phase1_frontier/
artifacts/phase1-v1/
docs/phase1-v1/
```

Implement six production responsibilities:

1. `SourceBuilder`;
2. `TargetEnumerator`;
3. `TargetMaterializer`;
4. `ParityOptimizer`;
5. `EndpointCertifier`;
6. `ResultStore`.

An abstraction is allowed only when at least two real production components
need it. A synthetic fixture is never a production backend.

Reuse existing low-level code only after semantic parity tests. Do not copy a
historical method controller simply because it already runs.

## 7. Identity and artifact contract

Keep these identities separate:

- `ProblemID`;
- `StatePreparationID`;
- `StructuralTargetID`;
- `CandidatePlanID`;
- `OptimizationInitializationID`;
- `OptimizedEndpointID`;
- `MeasurementContextID`, present only where applicable and never folded into
  state identity.

Pre-outcome deduplication may use structural and plan identities. It may not
use `OptimizedEndpointID`.

Every immutable request binds:

- scientific protocol digest;
- source/checkpoint/code/dependency digests;
- problem, state, structural target, plan, and initialization IDs;
- materialization and optimizer-contract digests;
- resource-counter and numerical-tolerance digests;
- backend route;
- queue index and shard.

Every request ends in exactly one visible terminal status:

```text
COMPLETED_ACCEPTED
COMPLETED_ACCURACY_REJECTED
SOURCE_INELIGIBLE
SEMANTIC_REJECTED
OPTIMIZER_REJECTED
CAP_REJECTED
ENGINEERING_FAILED_PRESERVED
NOT_AUTHORIZED
```

Never encode failure as zero, delete it from aggregation, or replace a failed
candidate with a newly selected candidate.

## 8. Required raw counters

Count at the operation boundary, not by orchestration inference:

- `N_energy`;
- `N_gradient_vector`;
- `N_gradient_component`;
- `N_optimizer_start`;
- `N_optimizer_iteration`;
- `N_state_preparation`;
- `N_transform_materialization`;
- `N_full_resource_recount`;
- wall time, CPU time, peak memory;
- GPU time and GPU identity only when used.

Do not scalarize these counters into the CEO-paper Measurement Cost in
Phase 1.

## 9. Autonomous execution rules

Proceed from A0 to A8 automatically when the current exit gate passes. Do not
pause merely to request confirmation that the next registered stage should
start.

Pause and request user direction only when:

- the scientific estimand or a protected field must change;
- a required external credential, permission, or irreversible action is
  needed;
- historical/user-owned data would need deletion or mutation;
- the same genuine blocker remains after safe alternatives are exhausted;
- a Phase-2 branch would be entered.

For a normal software defect, preserve evidence, add a reproducing test, make
the smallest additive fix, rerun only affected work, audit, and continue.

Do not create a new protocol version for a pure engineering fault that produced
no protected outcome and did not change scientific semantics.

Send a concise progress update at least once per stage and during any run that
lasts more than 60 minutes. Report facts, not performance interpretations,
until A8.

## 10. Stage A0 — isolate, audit, and freeze authority

### Actions

1. Inspect the current branch, worktree, running processes, disk, dependencies,
   and submodules without modifying them.
2. Verify that commit `bca77f26aad98937e69e824cb8024960c6994e60` exists and
   that its S12 archive evidence reconstructs.
3. Create the dedicated worktree and branch without touching the current A100
   diagnostic checkout.
4. Create the new Phase-1 namespaces.
5. Hash the three authoritative Phase-1 planning files and this file.
6. Freeze an authority manifest containing protected scientific fields,
   parent/submodule/lock digests, permitted paths, and zero-outcome assertion.
7. Add a test proving Phase-1 artifact roots are empty of candidate outcomes.

### Mandatory checks

- dedicated worktree clean;
- historical worktree and untracked plans unchanged;
- parent/submodules/dependency lock match expected values;
- no Phase-1 candidate energy, optimizer endpoint, or FCI record;
- sufficient disk/memory for E2 only.

### Exit

- pass: `GO_A1_REAL_KERNEL_PREFLIGHT`;
- fail: `NO_GO_A0_AUTHORITY_OR_ISOLATION`.

Commit the A0 manifest and tests. Do not tag or release yet.

## 11. Stage A1 — real-kernel engineering preflight

This stage prevents another queue-first infrastructure cycle.

### Actions

1. Connect one real H2 or H4 source to the pinned molecular kernel.
2. Materialize one legal singleton target.
3. Materialize one simple legal pairwise joint target.
4. Run the actual optimizer with both registered starts.
5. Independently recompute terminal energy and analytic gradient.
6. Rebuild and recount the materialized circuit.
7. Publish one accepted transaction.
8. Inject one optimizer failure and one artifact-write failure.
9. Prove complete rollback and same-request retry behavior.

### Prohibited substitutes

- structural-only fixture presented as molecular execution;
- proxy optimizer;
- controller that does not mutate the real ansatz;
- inferred rather than kernel-bound counters.

### Exit

- pass: `GO_A2_SOURCE_LOCK`;
- fail: `NO_GO_A1_REAL_KERNEL_BINDING`.

Create the first and only pre-queue readiness tag after clean-clone tests pass.

## 12. Stage A2 — canonical B2 source lock

### Actions

For every E3 source:

1. reconstruct B0 from immutable evidence;
2. reoptimize the unchanged topology under the Phase-1 optimizer contract;
3. create B2 IDs and resource snapshot;
4. independently verify energy, parameters, gradient, mapping, ordering, state,
   and canonical circuit resources;
5. classify failure as `SOURCE_INELIGIBLE`; never fall back silently to B0.

### Eligibility

- finite values;
- independent energy agreement within frozen E2 tolerance;
- target-coordinate gradient infinity norm at most `1e-8`;
- canonical resource recount parity;
- no identity or Hamiltonian drift.

### Exit

- eligible inventory exists: `GO_A3_GRAMMAR_AND_IDENTITIES`;
- no scientifically useful eligible source: `STOP_A2_NO_ELIGIBLE_SOURCE`.

## 13. Stage A3 — grammar, identities, and property proofs

### Singleton path

1. enumerate every legal singleton primitive;
2. canonicalize singleton semantics;
3. complete registered singleton closure;
4. freeze `CompleteSingletonUniverseID`.

No Top-K, Hessian, historical result, or resource-gain filter may truncate this
universe.

### Pairwise joint path

1. construct the registered structural-dependency graph over singleton nodes;
2. connect nodes only when they touch a common source CEO block or share a
   registered canonical resource-removal dependency;
3. enumerate every legal unordered edge pair with `K=2`, `L=1`, `D=1`;
4. apply frozen conflict/order and semantic-closure rules;
5. freeze `RegisteredJointUniverseID`.

### Required property tests

- byte-identical double generation;
- identity determinism and collision separation;
- sign/order/canonicalization cases;
- deliberate coarse/fine grammar collisions;
- affine constraint manifold equals the materialized target manifold for every
  affine transformation class;
- exact non-affine classes are not scored with an affine model;
- approximate non-affine classes are excluded.

### Exit

- pass: `GO_A4_CPU_STRUCTURAL_CENSUS`;
- fail: `NO_GO_A3_GRAMMAR_OR_IDENTITY_INVALID`.

## 14. Stage A4 — outcome-free CPU structural census

### Actions

Without candidate Hamiltonian energy or optimization:

1. enumerate singleton and pairwise joint targets;
2. deduplicate by `StructuralTargetID`;
3. materialize complete target circuits;
4. perform full canonical resource recount;
5. record singleton reachability, joint-only reachability, resource deltas,
   certificate class, and failure reason;
6. generate the census twice and require byte identity.

The census may use source topology and canonical resource information. It may
not use historical or current candidate energy.

If the registered joint enumeration exceeds the frozen structural safety cap,
stop before candidate energy. Do not sample or rank pairs.

### Scientific stop

If no eligible E3 source contains a joint-only resource-positive target:

`STOP_P1_NO_JOINT_RESOURCE_SIGNAL`.

This is a bounded negative structural result, not proof that all higher-order
CEO compression is impossible.

### Exit

- signal exists: `GO_A5_E2_CERTIFICATION_AND_QUEUE_FREEZE`;
- no signal: terminal Phase-1 structural stop;
- invalid census: `NO_GO_A4_CENSUS_INVALID`.

## 15. Stage A5 — formal E2 certification and E3 queue freeze

### E2 certification

Repeat the A1 vertical path under the now-frozen production grammar and IDs:

- one registered H2/H4 singleton;
- one registered H2/H4 pairwise joint target;
- both starts;
- independent energy/gradient/resource certificates;
- accepted commit, deliberate rejection, rollback, crash/resume;
- counter reconciliation;
- CPU repeatability.

Freeze optimizer version, analytic-gradient semantics, tolerances, maximum
starts/iterations, primitive operation caps, seeds, and thread policy using E2
only.

### Queue freeze

1. verify disk, memory, runtime, dependency, and worker capacity for the frozen
   E3 queue, including rollback and artifact headroom;
2. generate all authorized B2, singleton, and pairwise joint requests;
3. freeze conditional prefix eligibility rules, but create no outcome-selected
   prefix work yet;
4. bind protocol/code/environment/source/grammar/optimizer/counter digests;
5. deterministically shard by RequestID;
6. generate twice from clean state and require byte identity;
7. assert every row is `NOT_STARTED` and candidate energy/FCI count is zero;
8. run a clean-clone queue reconstruction audit.

### Exit

- pass: `GO_P1_FROZEN_E3_EXECUTION`;
- fail: `NO_GO_A5_E2_OR_QUEUE_INVALID`.

Only this pass authorizes Phase-1 E3 candidate outcomes. Tag the exact queue
freeze. Do not create a publication release.

## 16. Stage A6 — frozen E3 execution

### Execution rules

- execute exact frozen RequestIDs only;
- preserve frozen order within each deterministic shard;
- checkpoint only at request boundaries or optimizer-safe points;
- never reprioritize based on intermediate energy;
- never replace a failed request with another candidate;
- preserve failed, rejected, cap-rejected, and duplicate rows;
- retry only the same RequestID under a registered same-request rule;
- reconcile request/result/counters after each terminal request;
- audit disk, process, ledger prefix, and protected digests continuously.

### CPU/A100

CPU is always authorized after A5. A100 is authorized by target class only
after CPU/A100 objective, gradient, optimizer-terminal, and resource parity.

For two GPU workers:

```text
shard = integer(SHA256(RequestID), 16) mod 2
```

Each Slurm task sees exactly one A100. There is no silent CPU fallback. CPU
performs terminal independent certification. GPU speed is telemetry only.

If GPU qualification fails, preserve the incident and continue on CPU. Do not
change scientific work caps or candidate order to compensate for hardware.

### Incident handling

1. stop only the affected request/shard;
2. preserve command, PID/PGID, environment, checkpoint, partial ledger, and
   hashes;
3. rollback all protected state;
4. add the smallest reproducing test;
5. make an additive fix;
6. rerun affected requests only;
7. continue when the same scientific request and semantics remain valid.

### Exit

- all singleton/joint rows terminal and reconciled:
  `GO_A7_CONDITIONAL_PREFIX`;
- scientific-semantic defect: formal No-Go and protocol successor required;
- recoverable engineering defect: preserve, repair, audit, and resume.

## 17. Stage A7 — conditional fully reoptimized prefix oracle

Run this stage only for molecule families where the joint observed frontier is
strictly below the singleton observed frontier.

### Actions

1. load every prefix eligible under the A5-frozen prefix rule;
2. reoptimize each prefix with the same optimizer, two starts, tolerances, and
   caps;
3. certify energy, gradient, identities, and full canonical resources;
4. construct the accuracy-feasible observed prefix frontier;
5. compare the best joint point against that frontier.

This is a retrospective oracle comparator. Do not call it a prospective
early-stopping policy.

### Exit

- every authorized prefix row terminal: `GO_A8_LOCKED_AGGREGATION`;
- no positive singleton/joint family: skip with an explicit `NOT_APPLICABLE`.

## 18. Stage A8 — locked analysis and Phase-1 closure

### Actions

1. reconcile every request, result, counter, duplicate, retry, and failure;
2. freeze the analysis input manifest;
3. only now join FCI references for reporting;
4. run one immutable analyzer;
5. report per-case and molecule-family singleton, joint, and prefix frontiers;
6. report parameter, CNOT depth, total depth, block count, raw work, failure
   flow, and route telemetry as secondary outcomes;
7. reproduce all tables and figures from raw immutable artifacts in a clean
   recursive clone;
8. issue exactly one Phase-1 decision artifact;
9. tag the positive, null, negative, or infrastructure terminal state;
10. do not enter Phase 2 automatically.

### Decision tree

```text
source/grammar/vertical-slice invalid
  -> infrastructure/scientific No-Go; no performance interpretation

no joint-only resource-positive target
  -> bounded structural stop

joint targets exist but no accuracy-feasible singleton gap
  -> bounded negative language-value result

gap in exactly one molecule family
  -> authorize targeted Phase-2 replication only

gap in >=2 families but no prefix advantage
  -> structural compression signal only; no deployment claim

gap and prefix advantage in >=2 families
  -> authorize Phase-2 structural validation
  -> ranking only if complete enumeration exceeded the frozen prospective cap
```

The two H6 geometries count as one molecule family.

## 19. Required tests

### Unit/property

- identity determinism and separation;
- complete singleton generation relative to grammar fixtures;
- joint `K=2/L=1/D=1` bounds and conflict rules;
- affine/materialized-manifold parity;
- semantic deduplication;
- canonical resource recount;
- FCI/E1/E3/E4 input firewall;
- kernel-bound counter increments.

### Integration

- real molecular H2/H4 singleton and joint vertical slices;
- both optimizer starts and lower-valid endpoint selection;
- accepted commit and rejected rollback;
- crash/resume with same RequestID;
- cap boundary, cap equality, cap rejection, failed-work accounting;
- queue double-generation and completeness;
- CPU/A100 parity for accelerated classes only;
- clean-clone terminal reconstruction.

Do not require tests for Phase-2-only abstractions.

## 20. Git and provenance rules

- inspect dirty/untracked state before every stage;
- preserve unrelated user changes;
- use additive commits; never rewrite historical commits or tags;
- do not use destructive reset/checkout commands;
- one focused commit per completed Agent stage or incident fix;
- push only after local tests and artifact audit pass;
- tag only A1 readiness, A5 queue freeze, and A8 terminal result;
- do not create a GitHub Release before A8;
- bind artifact manifests to commit and file SHA-256 digests;
- record local/remote HEAD and clean/dirty worktree state in each stage report.

## 21. Progress report template

At each stage report:

```text
Stage:
Decision:
Scientific outcomes observed in this stage:
Candidate energy / optimizer / FCI counts:
Completed work:
Checks and tests:
Incidents and preserved evidence:
Protected digests changed? why?:
Git branch / HEAD / upstream / worktree:
Disk and active processes:
Next authorized stage:
Claims currently permitted:
Claims currently prohibited:
```

Never report a percentage improvement before A8 locked aggregation.

## 22. Agent Definition of Done

The Agent may report Phase 1 complete only when:

1. A0 authority and isolation preceded all new Phase-1 outcomes;
2. a real molecular vertical slice preceded the full queue;
3. B2 sources and four identity layers are independently certified;
4. singleton enumeration is complete relative to the frozen grammar;
5. the pairwise joint universe is complete relative to `K=2/L=1/D=1`;
6. the E3 queue was byte-identically regenerated and frozen outcome-free;
7. every authorized E3 and conditional prefix request is terminal and visible;
8. FCI was joined only after terminal molecular execution;
9. one locked analyzer reconstructs all conclusions from raw artifacts;
10. a clean clone reproduces the terminal decision;
11. negative, null, rejected, capped, and failed evidence remains present;
12. no Phase-2 feature entered the Phase-1 primary result.

If any item is false, report the exact incomplete state. Do not call Phase 1
complete and do not make a performance or publication claim.

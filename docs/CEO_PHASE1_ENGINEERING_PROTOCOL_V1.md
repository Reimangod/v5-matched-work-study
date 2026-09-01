# CEO Post-Growth Compression — Phase 1 Engineering Protocol v1

## Minimal Vertical-Slice Infrastructure for the Singleton-versus-Joint Study

**Status:** draft for implementation lock

**Scientific authority:** `CEO_PHASE1_SCIENTIFIC_PROTOCOL_V1.md`

**Design priority:** correct end-to-end execution first, scale second

**A100 role:** optional accelerator, never scientific authority

## 0. Engineering decision

Phase 1 will not extend the previous controller/adapter hierarchy. It will
build one thin production path around the already pinned molecular kernels and
prove that path on one real candidate before freezing a large queue.

The order is mandatory:

```text
one real H2/H4 source
-> one singleton target
-> one joint target
-> actual materialized circuit
-> actual optimizer
-> independent certificate
-> resource recount
-> atomic result
-> only then full queue freeze and parallel execution
```

This reverses the earlier pattern in which queue, cap, and controller layers
were frozen before a concrete method-native molecular vertical slice existed.

## 1. Repository and branch isolation

### 1.1 Parent

The preferred scientific parent is the audited matched-work S12 archive commit
`bca77f26`, subject to an initial digest and submodule audit. The current A100
diagnostic branch is not the scientific parent.

Create a dedicated worktree and branch:

```text
worktree: ../ceo-phase1-joint-frontier
branch: feature/phase1-joint-frontier-v1
```

Do not delete, move, stage, or rewrite the currently untracked v1.5–v1.8
planning documents in the existing checkout.

### 1.2 New namespaces

```text
src/phase1_frontier/
tests/phase1_frontier/
configs/phase1_frontier/
artifacts/phase1-v1/
docs/phase1-v1/
```

Historical artifacts and candidate outcomes are read-only. Phase-1 outcomes
are never written into `artifacts/v5-final`, `artifacts/v6`, or historical
provenance directories.

### 1.3 Reuse policy

Low-level code may be reused only after direct tests establish identical
semantics:

- pinned CEO* source/checkpoint loader;
- Hamiltonian and state construction;
- paper-era canonical circuit/resource counter;
- exact energy and analytic gradient kernels;
- transaction/rollback primitive;
- atomic publication and content hashing;
- StatePreparationID and ProblemID canonicalization;
- qualified BFGS implementation;
- qualified CPU/A100 objective kernel, conditionally.

Do not reuse as scientific logic:

- historical V4/V5 candidate lists or winners;
- V4/V5 ranking, threshold, beam, or sentinel decisions;
- result-dependent fallback order;
- proxy/synthetic production executors;
- old queue IDs or performance caps;
- human-approval workflow as a scientific gate;
- old Measurement Cost conversions not proven compatible.

## 2. Minimal architecture

Phase 1 needs six production components, not a general workflow framework.

1. `SourceBuilder` — reconstruct and certify B0/B2.
2. `TargetEnumerator` — complete singleton and bounded joint generation.
3. `TargetMaterializer` — build the actual target ansatz/circuit.
4. `ParityOptimizer` — run the two frozen starts and record raw work.
5. `EndpointCertifier` — independently recompute energy, gradient, state,
   semantics, and physical resources.
6. `ResultStore` — append-only request/result publication and aggregation input.

Introduce a new abstraction only when at least two real production
implementations require it. Synthetic fixtures are tests, not backends.

## 3. Request, result, and identity schema

### 3.1 Immutable request

Each request contains:

- Phase-1 protocol digest;
- source commit/checkpoint and B2 IDs;
- ProblemID and StatePreparationID;
- StructuralTargetID;
- CandidatePlanID;
- OptimizationInitializationID;
- target class and materialization digest;
- optimizer contract digest;
- resource-counter digest;
- backend route and numerical tolerance digest;
- queue index and deterministic shard.

Protected request fields cannot be changed by a worker.

### 3.2 Terminal result

Every request receives exactly one visible terminal status:

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

Failures are never replaced with zeros or dropped from aggregation.

### 3.3 Minimal raw counters

Record without scalarization:

- `N_energy`;
- `N_gradient_vector`;
- `N_gradient_component`;
- `N_optimizer_start`;
- `N_optimizer_iteration`;
- `N_state_preparation`;
- `N_transform_materialization`;
- `N_full_resource_recount`;
- wall time, CPU time, peak memory, and GPU time when applicable.

HVP, shots, and measurement groups remain absent or zero unless Phase 1
actually performs them. A counter is bound inside the kernel that performs the
operation; orchestration does not infer kernel work after the fact.

## 4. One authoritative readiness chain

Phase 1 uses four engineering gates only.

### ENG-G0 — source and environment readiness

Require:

- clean dedicated worktree;
- expected parent/submodule/lock digests;
- sufficient disk and memory;
- source reconstruction parity;
- canonical resource-counter parity;
- zero Phase-1 outcome records.

### ENG-G1 — real vertical slice

Require a real H2/H4 singleton and joint request to pass through the exact
production path. Tests must verify:

- request-to-kernel binding;
- actual target structure mutation;
- actual two-start optimizer execution;
- raw counters from inside kernels;
- independent endpoint certification;
- accepted commit and deliberate rejected rollback;
- atomic result and clean replay.

No full E3 queue may exist before ENG-G1 passes.

### ENG-G2 — frozen queue readiness

After ENG-G1:

- double-generate source, singleton, joint, and conditional prefix queues;
- require byte-identical queue output;
- bind queue digest, schema, optimizer contract, code, environment, and
  resource counter;
- prove no candidate/FCI outcome is present in the generator inputs;
- run a read-only queue completeness audit.

### ENG-G3 — execution and release readiness

Require:

- every authorized queue row terminal;
- no duplicate endpoint payment or missing request;
- successful request/result/counter reconciliation;
- independent aggregation from immutable terminal artifacts;
- clean-clone reproduction of the selected result subset and all tables.

There is no release/tag for every small internal step. Tags are limited to:

1. vertical-slice readiness;
2. E3 queue freeze;
3. terminal Phase-1 result.

## 5. Step-by-step implementation

### ENG-P1-S0 — isolate and audit the parent

- create the dedicated worktree/branch;
- verify parent, submodules, dependencies, historical artifact immutability;
- create the empty Phase-1 package and artifact roots;
- write one machine-readable authority manifest.

**Done:** one command reproduces all checks; no scientific outcome exists.

### ENG-P1-S1 — build the real vertical slice

- connect one pinned H2/H4 source directly to the actual source builder;
- materialize one existing singleton and one simple registered joint target;
- run the exact optimizer and independent certifier;
- inject optimizer failure and artifact-write failure;
- prove complete rollback and retry policy.

**Done:** integration test uses the molecular kernel, not a structural fixture.

### ENG-P1-S2 — implement grammar and identity kernels

- implement complete singleton enumeration and closure;
- implement bounded joint generation;
- implement four Phase-1 IDs;
- implement affine/materialized-manifold parity tests;
- add deliberate coarse/fine grammar, sign, order, and warm-start collisions.

**Done:** deterministic double generation and property tests pass.

### ENG-P1-S3 — implement CPU structural census

- enumerate targets without Hamiltonian candidate energy;
- materialize and recount full canonical circuits;
- deduplicate by StructuralTargetID;
- output all targets, resource deltas, reachability status, and failure reasons;
- apply only the scientific structural stop rule.

**Done:** census reruns byte-identically and contains no outcome-bearing field.

### ENG-P1-S4 — freeze optimizer and small-system parity

- calibrate tolerances and operation caps on analytic/H2/H4 only;
- verify both starts, independent gradients, and terminal failure taxonomy;
- verify CPU repeatability;
- optionally verify one CPU/A100 target parity before GPU authorization.

**Done:** the common optimizer contract is immutable before E3 queue creation.

### ENG-P1-S5 — generate and freeze the E3 queue

- generate eligible B2, singleton, and joint requests;
- freeze conditional prefix-generation rules, not outcome-selected prefixes;
- shard deterministically by request ID;
- publish queue and completeness manifest atomically;
- refuse execution from any other code/config digest.

**Done:** two fresh generations are byte-identical and zero outcomes exist.

### ENG-P1-S6 — execute and monitor

- run frozen order within each deterministic shard;
- checkpoint only at request boundaries and optimizer-defined safe points;
- resume the same request from durable optimizer state or restart it under a
  registered same-request rule; never create a replacement candidate;
- preserve failures before remediation;
- send concise progress telemetry without changing priorities from outcomes.

### ENG-P1-S7 — conditional prefix execution

After the scientific singleton/joint gate is locked, generate B1 requests only
for eligible positive molecule families using the already frozen prefix rule
and optimizer contract. Candidate outcomes do not change which historical
prefixes are eligible.

### ENG-P1-S8 — aggregate, reproduce, and close

- reconcile every request/result/counter;
- join reporting-only FCI only after all rows are terminal;
- run the locked analyzer once;
- create tables, frontiers, failure flow, and Phase-2 decision artifact;
- reproduce from a clean recursive clone;
- tag the terminal result whether positive, null, or negative.

## 6. CPU and dual-A100 execution policy

### 6.1 CPU is the control plane

CPU owns:

- queue generation and IDs;
- source and target semantics;
- authorization and cap checks;
- ledger and atomic publication;
- canonical resource recount;
- terminal scientific decision.

### 6.2 A100 is optional

Phase 1 does not wait for a generalized GPU platform. A100 may execute only
the already qualified dense/statevector objective and analytic-gradient work
for a request whose CPU/A100 parity test passed under the same source/target
class.

Rules:

- one Slurm task sees exactly one A100;
- no silent CPU fallback;
- two workers receive disjoint immutable shards;
- GPU UUID and runtime digest are recorded;
- scheduling order is outcome-independent;
- CPU performs the terminal independent certificate;
- GPU speed is engineering telemetry, not a scientific objective.

If adapting the A100 route blocks Phase 1, continue the structural census and
small/medium CPU requests. GPU readiness never blocks the scientific CPU path.

### 6.3 Fast deterministic sharding

For two authorized workers:

```text
shard = integer(SHA256(RequestID), 16) mod 2
```

Within a shard, sort by frozen queue index. Failed jobs do not cause another
shard to steal or reprioritize a candidate. A later registered recovery may
resume the same RequestID.

## 7. Testing budget

Phase 1 intentionally limits testing to risks that can change the result:

### Required unit/property tests

- identity determinism and collision separation;
- singleton completeness relative to fixtures;
- joint bound and conflict rules;
- affine/materialized-target parity;
- resource recount parity;
- FCI/outcome firewall;
- counter increments inside kernels.

### Required integration tests

- real H2/H4 singleton and joint vertical slices;
- two-start optimization and lower-valid-endpoint selection;
- accepted commit and rejected rollback;
- crash/resume at a safe boundary;
- CPU/A100 parity for every accelerated target class;
- clean-clone result reconstruction.

### Not required in Phase 1

- general plugin architecture;
- synthetic implementations of all future methods;
- release artifact for every readiness micro-step;
- support for noise, shots, routing, QGT, or arbitrary nonlinear target maps;
- distributed database or external orchestration service.

## 8. Incident policy

On an incident:

1. stop only the affected request/shard;
2. preserve command, process, partial files, environment, request, and hashes;
3. classify scientific impact;
4. add the smallest reproducing test;
5. fix through an additive commit;
6. rerun only results touched by the defective code path;
7. do not issue a new global protocol version for a pure operational incident
   whose protected scientific fields and outputs were never produced.

A protocol successor is required only when source, grammar, candidate universe,
optimizer, acceptance, resource definition, comparator, or analysis semantics
change.

## 9. Timeboxed fast path

These are management targets, not scientific shortcuts:

| Timebox | Deliverable |
|---|---|
| working day 1 | isolated branch, authority manifest, parent/source audit |
| days 2–3 | real H2/H4 singleton/joint vertical slice |
| days 4–5 | identities, complete singleton grammar, bounded joint generator |
| days 6–7 | CPU structural census and structural Go/No-Go |
| days 8–9 | optimizer parity lock and frozen E3 queue |
| thereafter | E3 execution; CPU and up to two qualified A100 workers in parallel |

If the structural census is negative, Phase 1 can terminate during the first
week without building ranking, measurement, or confirmation infrastructure.

## 10. Engineering Definition of Done

Phase-1 engineering is complete when:

1. one actual molecular vertical slice preceded the full queue;
2. there is one authoritative request/result/counter path;
3. the queue is immutable, complete, and outcome-free at freeze;
4. all scientific operations are counted at their kernel boundary;
5. CPU-only execution remains available;
6. accelerated results have route-specific CPU parity and terminal certificate;
7. failures and retries preserve the same RequestID and evidence chain;
8. every authorized row is terminal and independently reconstructible;
9. clean-clone tests reproduce the Phase-1 decision;
10. the implementation has not introduced Phase-2-only abstractions.

# CEO Post-Growth Compression — Conditional Phase 2 Engineering Plan v1

## Scale Only the Phase-1 Path That Earned Scientific Authorization

**Status:** inactive until a terminal Phase-1 decision

**Parent:** immutable Phase-1 terminal tag

**Execution model:** CPU control plane with zero, one, or two qualified A100 workers

## 0. Engineering entry rule

Do not implement all Phase-2 branches in advance. The terminal Phase-1
decision activates exactly one of:

```text
P2-A targeted replication
P2-B structural confirmation
P2-C structural confirmation + ranking comparison
```

Unselected branches remain documents, not code.

## 1. Branch and artifact isolation

Create the selected branch from the terminal Phase-1 result tag:

```text
feature/phase2-replication-v1
feature/phase2-structural-validation-v1
feature/phase2-ranking-validation-v1
```

Use separate roots:

```text
src/phase2_<selected_route>/
tests/phase2_<selected_route>/
artifacts/phase2-v1/<selected_route>/
```

Phase-1 requests, terminal results, queues, and analysis outputs remain
immutable. A Phase-2 result references them by digest and never migrates them
in place.

## 2. Reuse and change policy

Reuse the Phase-1 production path unchanged for:

- source and B2 construction;
- target identities and materialization;
- optimizer contract;
- endpoint certification;
- canonical resource recount;
- raw counters and atomic result storage.

Permitted additions depend on the selected route:

- P2-A/B: new source generator and new immutable queues only;
- P2-C: one common ranking interface with B3e and B5 implementations.

Any change to Phase-1 grammar, optimizer, accuracy guard, resource definition,
or endpoint analyzer creates a new exploratory protocol and invalidates the
confirmatory label.

## 3. E4/result firewall

The CPU controller enforces:

- E4 identifiers and queue digest frozen before candidate outcomes;
- workers cannot query aggregate or prior E4 results;
- no result-dependent retry, reprioritization, or shard migration;
- no FCI/reference energy in runtime input;
- B3e/B5 protected fields and work cap equality;
- all terminal statuses visible before analysis unlock.

Reference energies and manuscript tables are produced in a reporting-only
environment after the terminal completeness manifest passes.

## 4. Ranking-route implementation

Only P2-C introduces a `Ranker` interface:

```text
rank(frozen_source,
     frozen_candidate_universe,
     frozen_information_bundle,
     frozen_work_cap)
  -> ordered CandidatePlanIDs + accounting
```

B3e and B5 receive byte-identical source, universe, gradient/curvature bundle,
and cap. The interface prohibits hidden candidate generation.

Implementation requirements:

- common counter hooks inside every scoring kernel;
- deterministic tie-breaking;
- unknown/missing descriptor fail policy fixed in Ranking Lock;
- no Hessian hard rejection masquerading as infeasibility;
- full VQE certification remains outside the ranker;
- exhaustive B4 remains an immutable reference, not an input carrying E4
  outcomes into ranking.

## 5. CPU and dual-A100 dispatch

CPU remains authoritative for semantics, queue, caps, counters, certificates,
and aggregation.

Two A100 workers may run independent immutable requests when:

- the target class passed CPU/A100 parity;
- one Slurm task sees exactly one device;
- no CPU fallback occurs silently;
- each request records GPU UUID, runtime, and dependency digest;
- terminal CPU certification is available;
- accelerator choice is not based on candidate outcome.

Shard using the immutable RequestID hash. For expensive sources, batch several
requests per scheduler allocation while retaining request-level checkpoints
and results. Batch composition is frozen before outcomes.

## 6. Phase-2 vertical slice

Before the full E4 queue, run one non-holdout rehearsal using E2 or an E3
fixture:

- new source generation path;
- source/B2 certification;
- Phase-1 target pipeline;
- selected Phase-2 route;
- CPU and optional A100 execution;
- terminal result and analysis firewall.

For P2-C, the rehearsal must demonstrate B3e/B5 receive identical protected
inputs and caps. It may not select or tune B5 using E4.

## 7. Engineering stages

### ENG-P2-S0 — import and route selection

- verify Phase-1 terminal decision;
- create only the authorized branch/package;
- prove Phase-1 artifacts are read-only;
- freeze selected E4 source rules.

### ENG-P2-S1 — source-production rehearsal

- generate one non-holdout source through the exact production path;
- verify paper-era source semantics and B2 parity;
- test crash, rollback, and atomic publication.

### ENG-P2-S2 — selected-route implementation

- P2-A/B: no new algorithm implementation;
- P2-C: implement B3e/B5 common interface and equality tests;
- run the complete non-holdout vertical slice.

### ENG-P2-S3 — E4 queue freeze

- double-generate queues byte-identically;
- bind code, source, grammar, optimizer, ranker, cap, and backend digests;
- verify zero E4 outcomes and no result access from workers.

### ENG-P2-S4 — parallel execution

- dispatch disjoint immutable shards;
- monitor capacity, heartbeat, checkpoint, and terminal status;
- preserve incidents before repair;
- do not modify queue or ranker after E4 begins.

### ENG-P2-S5 — terminal aggregation

- require all authorized rows terminal;
- reconcile logical work independent of parallel makespan;
- unlock reporting references;
- run one locked route-specific analyzer;
- reproduce in a clean clone.

### ENG-P2-S6 — release

- publish source, queue, terminal, analysis, environment, and incident manifests;
- generate manuscript tables only from the locked analyzer;
- tag the result once, including negative outcomes.

## 8. Scaling and capacity policy

Before queue freeze, estimate per-request:

- statevector memory;
- optimizer checkpoint size;
- expected temporary storage;
- scheduler wall-time class;
- CPU and GPU memory floor.

Reserve at least:

```text
2 x estimated largest concurrent request storage
+ immutable queue/results allowance
+ 20% safety margin
```

An allocation or disk shortage pauses unstarted requests. It does not change
scientific caps, candidate order, or method definitions.

## 9. Minimal Phase-2 tests

- Phase-1 artifact immutability;
- E4/result firewall;
- source-generation parity;
- same request on CPU/A100 within frozen tolerances;
- B3e/B5 protected-input equality when applicable;
- deterministic sharding and batch composition;
- request-level retry and rollback;
- terminal completeness and reference unlock;
- clean-clone table reproduction.

Do not build support for unselected Phase-2 routes, noise, hardware shots,
external databases, or generalized architecture search.

## 10. Phase-2 engineering Definition of Done

The selected route is complete when:

1. it descends from the immutable Phase-1 tag;
2. no Phase-1 scientific semantic changed;
3. one non-holdout vertical slice passed before E4 freeze;
4. E4 queue and selected ranking lock preceded outcomes;
5. all accelerated classes passed route-specific parity;
6. every authorized row is terminal and reconciled;
7. logical work is independent of CPU/GPU parallel makespan;
8. one locked analyzer reproduces every reported value;
9. negative and infrastructure outcomes are retained;
10. no code was created for an unauthorized branch.

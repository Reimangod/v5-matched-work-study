# CEO Post-Growth Compression — Phase 1 Scientific Protocol v1

## Registered Singleton-versus-Joint Frontier Existence and Value Study

**Status:** draft for pre-outcome freeze

**Role:** the only authoritative scientific plan for Phase 1 after approval

**Regime:** exact noiseless simulation

**Historical evidence:** hypothesis-generating only

**Performance claim before completion:** none

## 0. Executive decision

Phase 1 does not design another pruning or ranking algorithm. It answers one
falsifiable question:

> Under one canonical CEO* source and one optimization-parity contract, does a
> frozen bounded joint transformation language produce a lower observed
> accuracy-feasible canonical CNOT frontier than the complete registered
> singleton language, and does that point remain better than a fully
> reoptimized CEO* prefix?

Phase 1 ends after this question is answered. Hessian ranking, sequential
rebuilding, lifecycle analysis, Measurement Cost reconstruction, hardware
claims, and new transformation families are not Phase-1 objectives.

This protocol treats V1–V6, V4.1/V5/V5.1, and the completed matched-work study
as E1 historical evidence. Their outcomes may justify the question and supply
test fixtures, but may not choose the Phase-1 grammar, thresholds, candidates,
or confirmation cases.

## 1. Why this is the Phase-1 question

The historical record establishes three facts:

1. large best-found post-growth reductions can occur, including the historical
   LiH witness;
2. the completed matched-work study did not routinely recover that scale of
   reduction, and fixed-source and sequential-rebuild V5 produced identical
   physical outputs on its frozen grid;
3. generic parameter fading, deletion, and reoptimization are already close to
   prior art, while CEO-native physical-resource non-additivity remains a
   narrower unresolved question.

Therefore Phase 1 tests the value of the candidate language before spending
work on a smarter acquisition algorithm.

## 2. Evidence roles

| Class | Contents | Permitted use | Forbidden use |
|---|---|---|---|
| E0 | peer-reviewed literature and pinned upstream code | definitions, prior-art boundary, source parity | proof of a Phase-1 outcome |
| E1 | all V1–V6, V4.1/V5/V5.1, and prior matched-work results | hypothesis generation, fixtures, failure modes | threshold selection, confirmation, expected-effect claim |
| E2 | analytic quadratics, synthetic circuits, H2, H4 | implementation, optimizer, numerical and transaction calibration | molecular performance claim |
| E3 | LiH 3.0 A, H6 1.5 A, H6 3.0 A, BeH2 3.0 A | Phase-1 development decision | transfer/generalization claim |
| E4 | outcome-blind selected new geometries/families | reserved for Phase 2 | any Phase-1 tuning or execution |

H6 geometries are one molecule-family cluster, not independent molecules.
E4 identities or their outcome-independent selection rule must be frozen before
the first E3 candidate energy, but E4 is not executed in Phase 1.

## 3. Canonical source contract

### 3.1 B0 and B2

- **B0:** immutable stored CEO* checkpoint.
- **B2:** the same stored topology reoptimized under the frozen Phase-1
  optimization contract.

B2 is the canonical post-growth source for all Phase-1 candidate generation,
ranking-free enumeration, state identities, gradients, curvature diagnostics,
and energy-loss comparisons.

The rule is applied uniformly to every source. B2 is never selected only when
it improves a particular case.

### 3.2 Source eligibility

A source is eligible only if B2 passes all of the following:

- source/problem/topology identity reconstruction;
- finite energy and parameters;
- independent energy agreement within the frozen numerical tolerance;
- target-coordinate gradient infinity norm at most `1e-8`;
- full canonical circuit recount parity;
- no unexplained state, mapping, ordering, or Hamiltonian drift.

If B2 fails, the case is `SOURCE_INELIGIBLE`; stored B0 is not silently used as
a replacement.

### 3.3 Energy quantities

Primary compression loss is

\[
\Delta E_{\mathrm{comp}}(x)
=E_{\mathrm{opt}}(x)-E_{\mathrm{opt}}(B2).
\]

The primary Phase-1 guard is

\[
\Delta E_{\mathrm{comp}}(x)\le 10^{-4}\ {\rm Ha}.
\]

Absolute FCI error is reporting-only and is joined after all registered E3
candidate outcomes are terminal. FCI is inaccessible to generation,
ordering, optimization scheduling, retry, acceptance, and stopping.

## 4. Primary endpoint and observed frontiers

The primary resource is the canonical paper-era logical CNOT count:

\[
C(x)=N_{\mathrm{CNOT}}^{\mathrm{canonical}}(x).
\]

Secondary outcomes are CNOT depth, total depth, parameter count, logical block
count, and raw computational work. They are not silently combined into one
weighted score.

Let \(\mathcal U_1\) be the complete legal registered singleton universe after
singleton semantic closure. Let \(\mathcal U_{2,1}^{\mathrm{joint}}\) be the
frozen pairwise, one-hop joint universe defined below. It is not described as
the set of all possible joint transformations.

Under the common optimization protocol \(\Pi_{\mathrm{opt}}\), define

\[
\widehat C_{\mathrm{single,obs}}^*(\varepsilon;\Pi_{\mathrm{opt}})
=\min_{x\in\mathcal U_1}
\{C(x):\Delta E_{\mathrm{comp}}(x)\le\varepsilon,
\ x\text{ passes certification}\},
\]

\[
\widehat C_{\mathrm{joint,obs}}^*(\varepsilon;\Pi_{\mathrm{opt}})
=\min_{x\in\mathcal U_{2,1}^{\mathrm{joint}}}
\{C(x):\Delta E_{\mathrm{comp}}(x)\le\varepsilon,
\ x\text{ passes certification}\}.
\]

The hat and `obs` are mandatory: nonconvex optimization does not prove a global
variational optimum.

The central Phase-1 signal is

\[
\widehat C_{\mathrm{joint,obs}}^*
<
\widehat C_{\mathrm{single,obs}}^*.
\]

## 5. Candidate-language contract

### 5.1 Complete singleton universe

The following order is mandatory:

```text
enumerate every legal registered singleton
-> canonicalize singleton semantics
-> complete registered singleton closure
-> freeze CompleteSingletonUniverseID
-> generate bounded joint plans
```

Top-K, resource filters, Hessian scores, or composite caps may not remove a
legal singleton before `CompleteSingletonUniverseID` is frozen.

### 5.2 Bounded joint universe

The Phase-1 primary language uses:

- maximum joint cardinality `K=2`;
- one-step source transformation depth `D=1`;
- locality `L=1` on a registered structural-dependency graph;
- every legal unordered pair connected by an edge in that graph;
- no accepted child, reoptimization result, or energy outcome generates a new
  candidate.

Graph nodes are members of the complete singleton universe. An edge exists
only when the two singleton plans modify a common CEO source block or share a
registered canonical resource-removal dependency. The exact edge predicate,
allowed primitive families, conflict/order rules, and semantic closure are
frozen and property-tested on analytic/synthetic/H2/H4 evidence before any
target-specific E1 replay audit or E3 candidate energy.

There is no top-K ranking or energy-informed truncation. If complete
enumeration of this registered pairwise language exceeds the frozen structural
safety cap, Phase 1 stops before candidate energy and requires a protocol
successor; it does not silently sample pairs.

Joint generation may use source structure and canonical resource information,
but not historical or current candidate energy. `RegisteredJointUniverseID`
binds the graph predicate and all generated pairs.

### 5.3 Transformation classes

- **Affine-predictable:** materialized target manifold is exactly represented
  by `A theta = b`; eligible for optional diagnostics.
- **Exact non-affine:** exact registered transformation but not represented by
  the affine predictor; evaluated without pretending that an affine Hessian
  score applies.
- **Approximate non-affine:** excluded from Phase 1.

For every affine class, property tests must establish

\[
\{\theta:A\theta=b\}=\mathcal M_{\mathrm{materialized}}
\]

within the declared parameterization and domain.

### 5.4 Identities

Phase 1 uses four distinct layers:

1. `StructuralTargetID` — target architecture/family independent of warm start;
2. `CandidatePlanID` — exact transformation plan and provenance;
3. `OptimizationInitializationID` — start coordinates and mapping rule;
4. `OptimizedEndpointID` — outcome-bearing terminal optimizer result.

`OptimizedEndpointID` must not be used for pre-outcome deduplication.
StatePreparationID, ProblemID, and MeasurementContextID remain separate.

Reachability reports distinguish:

- registered structural reachability;
- certified global-unitary equivalence;
- certified source-state equivalence;
- no certificate found.

Absence of a certificate is never called mathematical nonexistence.

## 6. Optimization-parity contract

Every singleton, joint target, B2 source, and later prefix uses one frozen
policy:

- identical optimizer family and version;
- identical analytic gradient semantics;
- identical convergence and numerical tolerances;
- identical maximum optimizer starts and iterations;
- identical energy/gradient operation caps;
- identical failure classification;
- deterministic thread and seed policy.

The initial fixed contract uses two starts for every target:

1. the canonical source-to-target mapped warm start;
2. a deterministic zero target-coordinate start.

The lower valid terminal energy is the observed endpoint. Failure of one start
does not erase its consumed work. Both starts are attempted for all eligible
singleton and joint targets unless E2 demonstrates that one start is
mathematically undefined for a registered target class; such an exception is
frozen by class, not by molecule or outcome.

Hessian or OBS quantities may be recorded as diagnostics. They do not reject,
admit, or reorder Phase-1 candidates.

## 7. Comparators

| ID | Comparator | Role |
|---|---|---|
| B0 | immutable stored CEO* | provenance reference |
| B2 | same-topology reoptimized final CEO* | canonical Phase-1 source |
| S | complete registered singleton universe | strongest singleton language control |
| J | bounded registered joint universe | target language under test |
| B1 | fully reoptimized eligible CEO* prefixes | retrospective optimization-parity prefix oracle |

B1 is not an operational early-stopping rule because final resource
information is used retrospectively. It answers whether post-growth processing
adds value beyond an optimized historical prefix.

## 8. Phase-1 stages and gates

### SCI-P1-S0 — authority and outcome firewall

- freeze this protocol, primary endpoint, E1/E2/E3 roles, E4 selection rule,
  and prohibited claims;
- create an empty `phase1-v1` outcome namespace;
- verify zero Phase-1 candidate energies.

**Exit:** `GO_P1_SOURCE_LOCK` or `STOP_P1_AUTHORITY_INVALID`.

### SCI-P1-S1 — canonical source lock

- reconstruct every B0 source;
- create and certify B2 uniformly;
- freeze B2 identities, resource snapshots, and optimizer contract.

**Exit:** eligible-source inventory. Ineligible sources remain visible.

### SCI-P1-S2 — grammar, identities, and constraint parity

- complete singleton grammar and closure;
- freeze bounded joint grammar;
- implement four identity layers;
- prove affine/materialized-target parity;
- double-generate both universes byte-identically.

**Exit:** `GO_P1_STRUCTURAL_CENSUS` or `STOP_P1_GRAMMAR_INVALID`.

### SCI-P1-S3 — CPU structural census

Without candidate energy:

- enumerate all singleton and bounded joint targets;
- deduplicate by `StructuralTargetID`;
- rebuild and recount canonical physical circuits;
- report singleton reachability and joint-only resource-positive targets;
- record exact/non-affine/uncertified classes separately.

If no joint-only resource-positive target exists in any eligible E3 source,
stop as `STOP_P1_NO_JOINT_RESOURCE_SIGNAL`.

Structural-minimum equality alone is not a hard stop because energy feasibility
can separate the frontiers.

### SCI-P1-S4 — E2 vertical scientific calibration

- run one singleton and one joint target end to end on H2/H4;
- verify source, transformation, optimizer, independent energy/gradient,
  resource recount, ledger, commit/rollback, and artifact reconstruction;
- freeze numerical tolerances and common optimization caps without E3 outcomes.

**Exit:** `GO_P1_E3_FREEZE` or `STOP_P1_VERTICAL_SLICE_INVALID`.

### SCI-P1-S5 — E3 singleton/joint execution

- evaluate every member of \(\mathcal U_1\) under the common optimizer contract;
- evaluate the frozen bounded \(\mathcal U_{K,L}\) under the same contract;
- preserve every completed, rejected, cap-rejected, failed, and duplicate row;
- compute observed accuracy-feasible frontiers only after all authorized rows
  are terminal.

Apply the language-value gate at the molecule-family level.

### SCI-P1-S6 — conditional prefix oracle

Run only for molecule families where the joint frontier strictly improves the
singleton frontier.

- load eligible stored CEO* prefixes;
- fully reoptimize them using the same fixed start policy and caps;
- construct the accuracy-feasible prefix frontier;
- compare the joint point with B1 at the same primary accuracy endpoint.

### SCI-P1-S7 — locked aggregation and Phase-2 decision

Run one immutable analyzer. Report case rows, molecule-family clusters,
frontiers, failure flow, and raw work. Only after all Phase-1 rows are terminal
may FCI reference errors be joined for reporting.

## 9. Phase-1 decision tree

```text
grammar/source/vertical slice invalid
  -> infrastructure or scientific No-Go; no performance interpretation

no joint-only resource-positive target
  -> stop semantic-joint route

joint structural targets exist but no accuracy-feasible singleton gap
  -> stop; registered language adds no observed value

gap in exactly one molecule family
  -> single-family signal; allow targeted Phase-2 replication only

gap in >=2 molecule families but no prefix advantage
  -> post-growth joint language helps singleton search but not deployment frontier

gap and prefix advantage in >=2 molecule families
  -> GO_PHASE2_STRUCTURAL_VALIDATION
  -> test ranking only if bounded enumeration exceeds the frozen work cap
```

The two H6 geometries count as one family.

## 10. Permitted and prohibited Phase-1 claims

### Permitted when supported

- a complete registered singleton versus bounded registered joint observed
  frontier comparison under a named optimizer contract;
- case- and family-specific accuracy-feasible CNOT gaps;
- a retrospective optimization-parity prefix-oracle comparison;
- complete failure and raw-work accounting;
- a bounded negative result for the registered grammar.

### Prohibited

- global optimum;
- universal CEO compressibility;
- post-growth superiority without the prefix result;
- CEO-aware ranking superiority;
- paper Measurement Cost or shot reduction;
- hardware or noise advantage;
- population-level generalization;
- mathematical nonexistence from an incomplete prover;
- treating LiH/H6/BeH2 as untouched confirmation.

## 11. Phase-1 Definition of Done

Phase 1 is complete when:

1. the scientific and engineering locks precede all Phase-1 E3 outcomes;
2. eligible B2 sources are independently certified;
3. the singleton universe is complete relative to the frozen grammar;
4. the joint universe is bounded and byte-identically reproducible;
5. one real H2/H4 vertical slice passes before the E3 queue is frozen;
6. all authorized E3 rows have visible terminal status;
7. singleton, joint, and conditional prefix frontiers are rebuilt from raw
   artifacts by one locked analyzer;
8. the Phase-2 decision follows the frozen tree without adding a method;
9. a clean-clone audit reproduces the result package;
10. negative and null outcomes are retained.

## 12. Literature boundary for the Phase-1 claim

Phase 1 is intentionally narrower than a general pruning or ADAPT-landscape
claim.

- Ramôa et al. introduced MVP/OVP coupled exchange operators, their efficient
  circuits, and CEO-ADAPT-VQE*. That work studies adaptive CEO construction and
  its resources; it does not establish the complete-singleton versus bounded-
  joint post-growth frontier defined here.
- Carreras et al. remove individual ADAPT operators during growth using a
  parameter-magnitude and position-dependent rule. Phase 1 neither claims that
  operator fading is new nor uses fading as its endpoint. It fixes a completed
  CEO* source and tests materialized CEO structural targets, including joint
  transformations, under a prefix control.
- Grimsley et al. show that sequential ADAPT construction and recycled
  initialization can navigate rough landscapes. Therefore optimization-path or
  “temporary scaffold” explanations are not treated as Phase-1 discoveries.

Primary references:

1. M. Ramôa et al., “Reducing the resources required by ADAPT-VQE using
   coupled exchange operators and improved subroutines,” *npj Quantum
   Information* 11, 86 (2025),
   https://doi.org/10.1038/s41534-025-01039-4.
2. A. Carreras et al., “Pruned-ADAPT-VQE: Compacting Molecular Ansätze by
   Removing Irrelevant Operators,” *Journal of Chemical Theory and
   Computation* (2025), https://doi.org/10.1021/acs.jctc.5c00535.
3. H. R. Grimsley et al., “Adaptive, problem-tailored variational quantum
   eigensolver mitigates rough parameter landscapes and barren plateaus,”
   *npj Quantum Information* 9, 19 (2023),
   https://doi.org/10.1038/s41534-023-00681-0.

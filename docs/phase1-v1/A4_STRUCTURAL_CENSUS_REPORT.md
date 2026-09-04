# A4 outcome-free structural census report

## Decision

`GO_A5_E2_CERTIFICATION_AND_QUEUE_FREEZE`

A4 completed two independent deterministic passes over all 88,148 unique
`StructuralTargetID` values.  The identity payloads agree exactly between
passes.  Candidate Hamiltonian energy, optimization, and FCI evaluations all
remain zero.

## Primary structural result

The preregistered primary resource is the paper-era canonical logical CNOT
count.  A target is therefore `primary_CNOT_resource_positive` only when its
CNOT delta from B2 is negative.

| Case | All unique targets | Registered joints | CNOT-positive joints |
|---|---:|---:|---:|
| LiH 3.0 A | 75 | 60 | 60 |
| H6 1.5 A | 40,946 | 40,627 | 34,783 |
| H6 3.0 A | 46,101 | 45,742 | 39,454 |
| BeH2 3.0 A | 1,026 | 970 | 918 |

This is a structural reachability result only.  It does not show that any
joint target preserves accuracy after reoptimization, and it does not compare
the observed singleton and joint energy-feasible frontiers.

## Safety cap and complete enumeration

The structural cap is a disclosed power-of-ten engineering ceiling of 100,000
unique structures.  It was fixed after the registered counts were known, but
before any candidate outcome.  This limitation is explicit in the cap
artifact.  Because all 88,148 frozen structures fit below the cap, it excludes
no Phase-1 target and creates no within-panel sampling or ranking.

## Exact factorized counter

The naive implementation rebuilt the complete Qiskit QASM independently for
every H6 target.  Four outcome-free processes were terminated with SIGTERM
before they produced a case artifact because that path projected to hours of
duplicated circuit synthesis.

A factorized exact counter was then implemented.  It uses the pinned upstream
`DVG_CEO` implementation to build each distinct circuit fragment and applies
the paper-era barrier, gate-depth, and CNOT scheduling rules to the complete
ordered fragment stream.  It was accepted only after:

- all 628 distinct fragment classes retained the same gate/qubit topology at
  three deterministic coefficient offsets;
- all four B2 source snapshots matched the original full-circuit evaluator;
- all LiH and BeH2 targets matched the original evaluator;
- all 678 H6 singleton targets matched the original evaluator.

In total, 1,779 full target snapshots were checked.  The first certification
attempt correctly failed because it compared parameterized gate labels and
used a one-byte-different JSON serializer for the upstream structure digest.
That failed artifact remains preserved; the corrected v2 certification is a
separate immutable artifact.

## Endpoint correction incident

The first uncommitted census used reduction in any primary or secondary metric
to set `resource_positive`.  That contradicted the preregistered primary CNOT
endpoint.  The stored CNOT deltas themselves were correct and no candidate
outcome had run.  All eight files were hash-recorded, removed from the
authoritative set, and regenerated from scratch as v2 with the CNOT-only rule.

## Claim boundary

Allowed now:

- the complete registered joint language contains many targets with lower
  canonical CNOT count than B2;
- the A4 census is deterministic and outcome-free;
- A5 E2 certification and E3 queue freeze may begin.

Not allowed now:

- any accuracy-feasible joint advantage;
- any superiority over singleton compression or CEO* prefixes;
- any V5 performance, Pareto, Measurement Cost, noise, or hardware claim.

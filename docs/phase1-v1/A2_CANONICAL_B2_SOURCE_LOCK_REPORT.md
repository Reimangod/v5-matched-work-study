# A2 canonical B2 source lock report

## Decision

`GO_A3_GRAMMAR_AND_IDENTITIES`

A2 reconstructed the four frozen molecular CEO* checkpoints and reoptimized
the unchanged topology with both registered starts.  All four cases have an
eligible canonical B2 source.  No compression candidate was generated and no
FCI or CCSD value was evaluated.

## Certified endpoints

| Case | Start | Terminal status | Energy (Ha) | `||g||inf` | BFGS iterations | CNOT | Parameters |
|---|---|---|---:|---:|---:|---:|---:|
| LiH 3.0 A | warm | certified | -7.797909682470 | 7.75e-9 | 0 | 107 | 15 |
| LiH 3.0 A | zero | rejected | -7.797909682456 | 1.10e-8 | 41 | 107 | 15 |
| H6 1.5 A | warm | certified | -2.994173530325 | 6.45e-9 | 0 | 879 | 137 |
| H6 1.5 A | zero | rejected | -2.993467509226 | 1.34e-8 | 884 | 879 | 137 |
| H6 3.0 A | warm | certified | -2.799451659012 | 1.91e-9 | 0 | 785 | 149 |
| H6 3.0 A | zero | certified | -2.798571916108 | 9.65e-9 | 720 | 785 | 149 |
| BeH2 3.0 A | warm | certified | -15.335468001671 | 8.51e-9 | 0 | 284 | 38 |
| BeH2 3.0 A | zero | rejected | -15.335467139044 | 5.33e-8 | 203 | 284 | 38 |

The frozen rule selects the lowest-energy endpoint among valid endpoints.
Accordingly, every case selected the mapped warm start.  A zero start was not
converted into a failure-as-zero observation and was not used when it failed
the optimizer/stationarity certificate.

## Defects and incidents

The first LiH warm record compared a five-field B0 resource vector against a
seven-field recount record and therefore produced a false mismatch.  The
original v1 record is preserved.  A v2 additive correction projects both
records onto the five registered scientific resource fields; it did not rerun
an optimizer or change any scientific value.  A regression test fixes this
boundary.

During the first H6 1.5 A zero-start attempt, an operator SIGINT was sent while
diagnosing missing process visibility.  No endpoint or intermediate energy had
been exposed.  The failed engineering attempt, the missing durable in-memory
counter limitation, and the same-case/same-start retry rule are preserved in a
separate incident artifact.  The retry used the unchanged protocol and its
terminal result is retained.

## Claim boundary

A2 establishes eligible post-growth sources only.  It does not show that any
CEO block is removable, that joint compression outperforms singleton deletion,
or that any method improves energy, CNOT count, depth, measurement cost, or
wall time.  Candidate outcome execution and FCI reporting remain closed.

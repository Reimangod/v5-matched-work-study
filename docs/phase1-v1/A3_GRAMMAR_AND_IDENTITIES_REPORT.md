# A3 grammar and identity report

## Decision

`GO_A4_CPU_STRUCTURAL_CENSUS`

A3 froze a complete registered block-local singleton language and a bounded
one-hop, pairwise joint language for every eligible B2 source.  Generation used
no Hamiltonian candidate energy, optimizer endpoint, FCI result, historical
winner, Hessian rank, or Top-K filter.

## Frozen universe sizes

| Case | Raw aliases | Canonical singletons | Registered K=2 joints |
|---|---:|---:|---:|
| LiH 3.0 A | 15 | 15 | 60 |
| H6 1.5 A | 427 | 319 | 40,627 |
| H6 3.0 A | 419 | 359 | 45,742 |
| BeH2 3.0 A | 68 | 56 | 970 |

The singleton grammar contains whole-block deletion, MVP constituent deletion,
MVP-to-single-QE, and registered MVP-to-OVP sum/difference reductions.  Raw
kind aliases that express the same exact transformation are retained in an
alias table, while one lexicographic representative defines the canonical
singleton node.

The joint graph connects two singleton nodes only when their source CEO blocks
share qubit support, the registered proxy for a canonical CNOT-removal
dependency.  Same-block nodes are generated as local edges and then rejected
by the frozen mutual-exclusion/conflict rule.  Compatible pairs act on disjoint
source-coordinate blocks; therefore their exact affine manifolds compose by a
direct sum.  Complete LiH parity tests compare every singleton and all 60
registered pairs against the pre-existing general composer.

## Scope boundary

Cross-iteration exact OVP/MVP fusion is an already historical but separate
transformation family.  It is not silently mixed into this block-local Phase-1
singleton grammar.  Approximate non-affine transformations are excluded.
Consequently, Phase 1 will support claims only about this explicitly bounded
language, not every conceivable CEO rewrite.

## Engineering corrections

Three outcome-free implementation issues were found before A3 freeze:

1. global Fraction-RREF construction was repeated for every H6 pair;
2. every atomic candidate was unnecessarily embedded into a global numerical
   constraint state;
3. complete target arrays were repeated in every joint JSON record.

The candidate set and graph rules were not altered.  Compatible affine maps
are now composed using the proved direct-sum property, and joint storage is
dictionary encoded through two singleton ordinals.  Superseded derived
artifacts are represented by hashes in incident manifests.  Every
authoritative file remains below the GitHub 100 MB single-file limit.

## Remaining risk for A4

The two H6 sources contain 86,369 registered joints in total.  A full native
circuit resource recount for every joint may be expensive.  A4 must therefore
use an outcome-free, E2-justified structural safety cap.  If complete census
cannot fit that cap, the protocol requires a structural No-Go; it does not
permit sampling, energy ranking, or silent truncation.

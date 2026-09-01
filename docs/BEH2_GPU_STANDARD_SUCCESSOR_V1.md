# BeH2 gpu-standard successor v1

## Purpose

Job 2055 established valid GPU-backed VQE terminal certificates for H2 and H6,
but BeH2 reached the frozen `gpu-short` one-hour limit before publishing a
scientific result. This additive successor changes only the scheduler envelope
for BeH2. It does not reinterpret the timeout as a molecular result and does
not overwrite any job 2055 artifact.

## Frozen change

| Field | Job 2055 | Successor v1 |
|---|---:|---:|
| Case | BeH2 | BeH2 |
| Partition | `gpu-short` | `gpu-standard` |
| Time limit | 1 hour | 4 hours |
| GPUs | 1 | 1 |
| CPUs | 4 | 4 |
| Memory | 32 GB | 32 GB |
| Numerical threads | 1 | 1 |

All molecular, optimizer, gradient, circuit, acceptance, terminal CPU
certificate, and resource-counting semantics remain unchanged. The four-hour
limit is an outcome-blind scheduler allowance: the predecessor produced no
BeH2 scientific result, optimizer terminal, or energy artifact.

## Decision boundary

The successor is an engineering qualification only. A GO requires a digest-
valid BeH2 scientific PASS and terminal PASS, one visible allocated A100, GPU
objective invocation, zero CPU fallback, no full CPU optimization, and exact
terminal CPU certification. The final additive merger also revalidates the
preserved H2/H6 v4 evidence and their overlapping use of distinct A100 UUID
digests.

FCI reporting, CPU speed claims, molecular performance claims, V5 superiority,
and CEO-MESC Phase I remain unauthorized.

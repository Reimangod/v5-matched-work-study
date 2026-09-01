# Dual-A100 v4 job 2055: formal infrastructure No-Go

## Decision

`NO_GO_DUAL_A100_BEH2_TIME_CAP_V1`

The frozen `gpu-short` Slurm array completed H2 and H6 with valid GPU-backed
VQE terminal certificates. BeH2 reached the frozen one-hour time limit before
writing either a scientific result or a terminal record. Therefore the
three-case merger was not run and no partial GO was declared.

## Observed terminal states

| Case | Slurm state | Elapsed | Scientific certificate |
|---|---|---:|---|
| H2 | `COMPLETED` | 00:00:06 | `PASS` |
| H6 | `COMPLETED` | 00:27:56 | `PASS` |
| BeH2 | `TIMEOUT` | 01:00:16 | absent |

For H2 and H6, every registered certificate check passed, the GPU objective
was invoked, CPU fallback was zero, no full CPU optimization was performed,
and the terminal CPU certificate agreed with the GPU-backed result. H2 and H6
also overlapped on distinct CUDA UUID digests, which proves concurrent use of
two allocated A100 devices without publishing the physical UUIDs.

The BeH2 result is not a molecular negative result. It only establishes that
the present BeH2 engineering fixture did not finish under the pre-registered
`gpu-short` one-hour cap. No BeH2 energy, optimizer terminal result, FCI value,
or performance comparison exists in this execution.

## Integrity boundary

- Exact code commit: `c6521c2057e67faa45041fcf0f84e828268317a3`.
- Frozen contract digest:
  `d0c33ae85c4db4212275fc1012cebf266c930b0ebddb0587fd221b25fbb12dd4`.
- Slurm array: `2055`.
- Existing v1-v3 incidents and the v4 execution namespace were not modified.
- The copied raw artifacts and Slurm logs are preserved under
  `artifacts/aic-a100-dual-optimizer-v1/results/v4-job-2055/`.
- Speed was not compared and was not used in the decision.
- FCI evaluation, CEO-MESC Phase I, and performance claims remain unauthorized.

## Allowed next step

A longer BeH2 run may only be performed as an additive successor protocol. It
must retain the same scientific inputs and decision rules, justify changing
only the scheduler time/partition, use a new immutable output namespace, and
report job 2055 as the predecessor No-Go. Automatic retry or overwriting job
2055 evidence is forbidden.

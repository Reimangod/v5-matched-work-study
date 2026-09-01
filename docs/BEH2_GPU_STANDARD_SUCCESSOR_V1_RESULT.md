# BeH2 gpu-standard successor v1 result

## Final decision

`GO_DUAL_A100_SCIENTIFIC_EXECUTION_SUCCESSOR_V1`

The diagnosis was correct: job 2055 failed because its BeH2 task exceeded the
frozen one-hour `gpu-short` scheduler cap, not because of a GPU/CPU scientific
disagreement. The scheduler-only successor completed in 1:05:39 under
`gpu-standard`, about five minutes beyond the predecessor limit.

| Evidence | H2 | H6 | BeH2 successor |
|---|---:|---:|---:|
| Slurm state | `COMPLETED` | `COMPLETED` | `COMPLETED` |
| GPU scientific certificate | `PASS` | `PASS` | `PASS` |
| CPU fallback | 0 | 0 | 0 |
| Full CPU reoptimization | no | no | no |
| Terminal CPU certificate | `PASS` | `PASS` | `PASS` |

The additive merger revalidated the preserved H2/H6 v4 records, their overlap
on distinct A100 UUID digests, and the new BeH2 v1 record. Every registered
merger check is true. Wall time is operational metadata only and was not used
in the scientific decision.

## Engineering incident and closure

The successor sbatch file did not declare a dedicated Slurm stdout path, so
`slurm-2064.out` initially appeared as an untracked file in the remote Git
worktree. The log was copied into the local evidence namespace, verified byte-
identical by SHA-256, moved into the dedicated remote logs directory, and the
remote worktree was then verified clean. Source files, contracts, and quantum
results were not modified. Any future dispatch must freeze explicit Slurm
stdout and stderr paths.

## Claim boundary

This GO proves engineering feasibility only: the registered GPU-backed VQE
objective can run for H2, H6, and BeH2 and can be independently certified by
the terminal CPU route, while H2 and H6 demonstrate concurrent use of two
distinct A100s. It does not establish CPU speedup, molecular performance
superiority, V5 superiority, FCI accuracy, or CEO-MESC Phase I results.

# RTX 2080 Ti platform replication: terminal No-Go

## Decision

`NO_GO_RTX2080TI_NO_END_TO_END_ADVANTAGE`

S0–S8 completed. S8 did not authorize S9–S12, so no GPU queue was frozen or
executed. This is the protocol-defined successful safety termination, not a V5
performance result.

## What was established

- The device is an NVIDIA GeForce RTX 2080 Ti with working CUDA allocation.
- The implementation is a hybrid backend: sparse state propagation, energy,
  and analytic gradient arithmetic run through CuPy; circuit construction,
  resource counting, candidate control, and bookkeeping remain on the CPU.
- Synthetic CPU/GPU parity passed.
- Pinned H2 and H4 source states passed the preregistered state, energy, and
  gradient tolerances with zero unexpected CPU fallback.
- The original resource-counting environment and CPU study remained unchanged.

## Why execution stopped

The formal warm-up-separated, three-repetition source workload required median
`CPU wall time / GPU wall time >= 1.0` for both calibration cases. The observed
medians were approximately 0.218 for H2 and 0.192 for H4. Thus the GPU path was
about 4.6x and 5.2x slower, respectively. Small sparse matrices and repeated
GPU scalar synchronization dominate these cases.

## Claim boundary

No compression-candidate energy, optimizer start, FCI reference, GPU 90-item
queue item, Pareto analysis, or molecular-performance comparison was executed.
S7 was source-kernel parity only; it did not establish candidate-sequence or
optimizer-terminal-status parity. Therefore this work supports only a negative
conclusion about this RTX 2080 Ti port for the tested source workload.

## Validation

- GPU-specific tests: 31 passed before terminal-manifest addition.
- Core suite with external live-GitHub-CLI test files excluded: 438 passed,
  3 expected xfails.
- Full suite: 450 passed, 3 expected xfails, 9 infrastructure failures.
  Eight failures were caused by `gh` not being installed/authenticated on the
  JupyterHub instance; one was a historical test expecting two CPU threads when
  the GPU benchmark intentionally fixed one CPU thread. No failure was a GPU or
  scientific-code regression.

The terminal manifest verifies the S0–S8 artifact chain and explicitly records
S9–S12 as `NOT_AUTHORIZED_BY_S8`.

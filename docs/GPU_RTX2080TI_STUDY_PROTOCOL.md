# RTX 2080 Ti matched-work platform study

## Purpose

This repository branch is an independent platform study of the frozen V5
matched-work protocol on a Keio AIC RTX 2080 Ti node.  It is not a continuation
of the partially completed local CPU execution.

The scientific question is whether a CUDA or explicitly recorded hybrid
backend can reproduce the frozen CPU semantics and then provide a useful
end-to-end speedup without changing the candidate set, ranking, tie-breaks,
optimizer contract, work caps, or registered Qiskit resource-counting path.

## Immutable source

- CPU source commit: `94a54a5396b7595454880474b8a9adae99758080`
- Parent submodule: `4783b9ff9f9b6f2061a1ef8c02613f4c6cef38db`
- CEO* submodule: `a3f89d03e6a03c89767d3cf8ee7657a57653dda0`
- Frozen queue: S11-v2 queue v2, 90 items
- Frozen work caps: S11-v2 outcome-cap freeze v1
- Frozen authorization source: P7 gate v5

The exact file and embedded digests are recorded in the S0 scope-freeze
artifact.  The existing CPU terminal prefix is provenance only.  Its outcomes,
candidate rankings, checkpoints, and terminal records are forbidden inputs to
the GPU execution.

## Identity and evidence separation

GPU artifacts use a new platform-study identifier, a new execution identifier,
and the dedicated artifact root:

`artifacts/v5-final/gpu-rtx2080ti/`

The backend and CUDA/hybrid execution context belong to the measurement and
execution context.  They do not redefine the prepared quantum state.  CPU and
GPU terminal records must never be concatenated into one 90-item run.

## Stage gates

S0 authorizes S1 hardware and access audit only.  Molecular candidate outcomes,
the 90-item GPU queue, FCI reporting, Pareto tables, figures, and performance
claims remain unauthorized until their explicit successor gates pass.

The intended sequence is S0 through S12.  A failed parity, provenance, resource,
fallback, cap, or performance gate produces a No-Go artifact.  It does not
authorize silently changing the scientific protocol.

## Backend safety rules

- Unexpected CPU fallback count must be zero.
- Planned CPU work in a hybrid backend must be classified and counted.
- Production dense matrix exponential use remains forbidden where the frozen
  CPU protocol forbids it.
- Registered circuit resources continue to use the frozen Qiskit path.
- GPU numerical tolerances must be frozen before molecular outcome execution.
- Existing CPU artifacts, tags, branches, and running processes are read-only.

## Current claim boundary

Completion of S0 is evidence of isolation and provenance only.  It is not
evidence that CUDA is faster, numerically equivalent, scientifically valid for
the molecular queue, or superior in VQE performance.

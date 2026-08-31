# Dual-A100 GPU-backed VQE execution v3

## Purpose

This is an engineering qualification, not a molecular performance study. It
tests whether two independent Slurm tasks can safely use two A100 GPUs while
the already-registered VQE objective adapter is exercised and the terminal
result is certified against the CPU route.

CPU-only speed is not compared and speed is not a GO/No-Go criterion.

## Scientific boundary

- Cases: H2, historical H6 fixture, historical BeH2 fixture.
- Reused unchanged: molecular source, candidate, Hamiltonian, circuit,
  optimizer, gradient, stopping rule, acceptance rule, and resource recount.
- GPU role: Aer double-precision state preparation for objective-energy calls.
- CPU role: sparse expectation, analytic gradient, optimizer control, and the
  independent paired certification already implemented by `objective_parity`.
- FCI reporting, candidate selection from outcomes, CEO-MESC Phase I, resource
  superiority, and performance claims are not authorized.

This is accurately described as **GPU-backed VQE optimization**, not as an
optimizer that runs entirely on the GPU.

## New work and non-duplication

Earlier A100 pilots tested one allocated GPU at a time and exposed historical
optimizer-semantics parity limitations. This additive test does not modify or
supersede them. Its new question is concurrent dispatch and artifact isolation:

1. a Slurm array runs at most two one-GPU tasks concurrently;
2. every task sees exactly one allocated A100 and rejects fallback;
3. at least one pair has overlapping execution intervals and distinct GPU UUID
   digests;
4. each task writes to an immutable private shard;
5. a deterministic merger verifies all CPU/GPU scientific certificates.

The v1 dispatch attempts (Slurm 2043 and 2046) are retained as infrastructure
incidents. Job 2043 demonstrated exact-HEAD rejection after a manual SHA
transcription error. Job 2046 identified case-specific thread binding and
Slurm/cgroup GPU-index interpretation errors. No v1 result is eligible for a
scientific or performance claim. V2 uses a new output namespace and never
overwrites a v1 shard.

V2 (Slurm 2049) produced one certified H2 PASS and rejected H6/BeH2 before
their scientific kernel because management-visible `nvidia-smi` indices were
not equivalent to the Slurm/cgroup execution-device index. V3 binds identity
to the UUID returned by the CUDA driver for the process-visible logical device
zero and separately requires that exactly one CUDA device is visible. The V2
namespace remains immutable.

## Frozen dispatch

```text
partition       gpu-short
array           0-2%2
GPU/task        1
CPU/task        4
memory/task     32 GB
time/task       1 hour
case order      h2, h6, beh2
```

The test uses a new project root at
`/share/$USER/aic-a100-dual-optimizer-v1`. The already-qualified pinned GPU
environment is mounted read-only by convention from the earlier pilot root;
the earlier repository checkout and all historical Slurm logs are left
untouched.

## GO conditions

`GO_DUAL_A100_SCIENTIFIC_EXECUTION_V3` requires all of the following:

- all three task terminals and scientific results are present and digest-valid;
- at least two task intervals overlap on different GPU UUID digests;
- each task sees exactly one allocated GPU;
- no Aer CPU fallback occurs;
- the GPU objective is invoked;
- CPU/GPU terminal decision and physical resources agree under the existing
  scientific certificate;
- no artifact collision occurs;
- speed remains excluded from the decision.

Any missing or false condition yields a fail-closed No-Go. A No-Go is an
infrastructure result and cannot be presented as VQE performance evidence.

After the array reaches a terminal state, the merger is intentionally run as a
small login-node verification command rather than requesting an unnecessary
GPU or assuming that a site-specific CPU partition exists:

```bash
python -m aic_a100_pilot.dual_optimizer_execution merge \
  --output-root "$OUTPUT_ROOT" \
  --output "$OUTPUT_ROOT/merged-decision-v1.json"
```

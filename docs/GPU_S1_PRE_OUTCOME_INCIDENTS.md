# GPU S1 pre-outcome implementation incidents

No molecular candidate energy, optimizer, FCI evaluation, or queue item was
executed during either incident.

## Optional `nvcc` diagnostic

The first S1 capture attempt raised `FileNotFoundError` when `nvcc` was absent.
`nvcc` is diagnostic at S1 and its absence must be recorded, not crash the
hardware audit.  The command wrapper now records return code 127 and preserves
the error text.  A regression test covers the behavior.

## Container memory reporting

The next unpublished S1 capture used `sysconf` and observed physical-host
memory rather than the JupyterHub container allocation.  The capture was not
accepted as evidence.  Effective memory now uses the smaller of physical
memory and the cgroup v1/v2 limit.  A regression test fixes this boundary.

Both defects were discovered before S2 environment construction and before any
scientific outcome.  The corrected S1 artifact must be regenerated from the
same running instance.

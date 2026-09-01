# A1 Clean-Clone Attestation

The A1 implementation commit `a305d6f3` was cloned recursively from the
GitHub remote into `/tmp/ceo-phase1-a1-clean-a305d6f3`.

The clone checked out:

- parent submodule `4783b9ff9f9b6f2061a1ef8c02613f4c6cef38db`;
- CEO* submodule `a3f89d03e6a03c89767d3cf8ee7657a57653dda0`.

The parent scientific environment was reconstructed from its frozen lock with:

```bash
CMAKE_POLICY_VERSION_MINIMUM=3.5 uv sync --frozen --extra baseline --extra test
```

The first test invocation correctly failed two subprocess-based legacy tests
because a recursive Git clone does not contain an untracked `.venv`.  No
scientific test failed.  After the documented lock-based environment build,
the following clean-clone test partition passed:

```text
17 passed in 22.27s
```

It covered all Phase-1 A0/A1 tests plus the actual parent rewrite, runtime
factory, pinned binding, and immutable MB0 checks.  No molecular calculation
was rerun in the clean clone; the immutable A1 result and its independent audit
were reconstructed and verified.

This attestation contains no new candidate outcome and does not expand the A1
claim boundary.

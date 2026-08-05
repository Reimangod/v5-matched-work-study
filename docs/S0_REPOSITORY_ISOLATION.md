# S0 — repository isolation and immutable import ledger

Decision: `GO_S1` only after the machine-readable ledger, independent audit,
tests, clean-commit check, private remote check, and annotated tag all pass.

The study uses the recommended isolation method: the historical repository is
a Git submodule pinned to the peeled commit of
`pra-critical-path-negative-result-v1`. Its nested CEO* dependency remains
pinned to the recorded upstream commit. No historical artifact is copied into
the new `artifacts/` namespace.

New artifacts are published by same-directory staging, file `fsync`, atomic
hard-link creation, directory `fsync`, and staging cleanup. The canonical
target must not already exist. Publication therefore refuses destructive
replacement.

Repository policy:

- initial GitHub visibility: private;
- default branch: `main`;
- no force-push or history rewrite;
- annotated stage/result tags are never moved or replaced;
- historical submodule and artifacts are read-only;
- branch/ruleset enforcement status is recorded separately after remote setup.

S0 contains provenance and infrastructure evidence only. It contains no
candidate energy, molecular optimization, or performance outcome.

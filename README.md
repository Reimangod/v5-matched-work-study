# V5 matched-work robustness study

This is an independent, private-by-default study of sequential catalog
rebuilding in V5 under componentwise matched-work envelopes.

The historical `dvg-obs-ceo` repository is a read-only Git submodule pinned to
`pra-critical-path-negative-result-v1` (`4783b9ff9f9b6f2061a1ef8c02613f4c6cef38db`).
Historical artifacts remain development evidence and are never copied into the
new result namespace.

Scientific and engineering constraints are recorded in
[`docs/CLAIM_BOUNDARY.md`](docs/CLAIM_BOUNDARY.md) and stage-specific protocols.

The immutable v1 No-Go release remains valid. Audit remediation is recorded in
[`docs/V2_AUDIT_REMEDIATION.md`](docs/V2_AUDIT_REMEDIATION.md). S2-v2 and
S3-v2 close the H4, raw-event, and cap-calibration gaps. S4-v2 supplies a
shared-counter orchestration layer, but the strict pre-S6 audit correctly
rejects it as a substitute for concrete pinned molecular backends. S6–S14
therefore remain unexecuted and not authorized.

## S0 reproduction

```bash
git clone --recurse-submodules https://github.com/Reimangod/v5-matched-work-study.git
cd v5-matched-work-study
uv sync --extra test
cd provenance/dvg-obs-ceo
uv sync --frozen --extra baseline
cd ../..
uv run python -m v5_matched_work.s0_build --verify-only
uv run python -m v5_matched_work.s0_audit --verify-only
uv run python -m v5_matched_work.s2_build_v2 --verify-only
uv run python -m v5_matched_work.s3_build_v2 --verify-only
uv run python -m v5_matched_work.s4_build_v2 --verify-only
uv run python -m v5_matched_work.s5_freeze_v2 --verify-only
uv run python -m v5_matched_work.strict_pre_s6_v2 --verify-only
uv run python -m v5_matched_work.closure_audit_v2 --verify-only
uv run pytest -q
```

Initial publication uses exclusive-create semantics and refuses replacement.
The clean-clone commands above independently rebuild the records in memory and
require byte-identical committed artifacts.

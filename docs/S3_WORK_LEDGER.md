# S3 — work ledger and cap calibration

Work is the nine-component vector `(N_E, N_G, N_gradcomp, N_HVP, N_exact,
N_recount, N_rewrite, N_states, N_rounds)`. Unlike operations are never summed
into a weighted scalar. Every next operation is checked componentwise before it
starts; rejected, failed, duplicate, and rollback paths remain charged.

LOW/MEDIUM/HIGH are rounded numerical envelopes derived only from historical
development V4.1/V5 ledgers. LOW intentionally disallows HVP (`N_HVP=0`). They
are internal experimental envelopes, not the CEO paper's Measurement Cost.

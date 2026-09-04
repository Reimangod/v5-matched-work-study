# Phase 1 v2 S4.1 frozen-order gate

## Outcome

`GO_PHASE1_V2_ORDERED_SCREEN_EXECUTION`

S4.1 is an additive safety correction after S4. The scientific protocol,
queue, targets, starts, optimizer, and caps are unchanged.

The public execution entrypoint now accepts only the RequestID at the next
contiguous frozen index, only at its canonical artifact path. It rejects a
gap, a noncanonical path, or any future-index artifact. The probe passed all
four conditions before candidate outcomes.

At freeze time the S5 namespace was empty, all 1,266 rows remained
`NOT_STARTED`, and candidate-energy, optimizer-start, and FCI counts for the
screen were zero. Interim reporting and out-of-order direct dispatch remain
prohibited.

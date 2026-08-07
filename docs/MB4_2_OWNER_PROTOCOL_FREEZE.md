# MB4.2 — repository-owner outcome-blind protocol freeze

MB4.2 is an additive governance transition. The immutable MB4.1 v1/v2
proposal artifacts and the v2 independent-human review template remain
unchanged. The repository owner explicitly removed independent-human approval
as a required gate and authorized a new content-addressed outcome-blind freeze.

The former “V5 no-rebuild” name is replaced prospectively by **V5
fixed-source-whitelist / no-replenishment**. The implementation reconstructs a
current-runtime catalog, recomputes current-state ranks, keeps only candidates
whose structural IDs occur in the source whitelist, and records unavailable
whitelisted candidates as `STALE_UNAVAILABLE`. It does not freeze source order.
The old `v5-sequential-without-rebuilding` ID remains only as an explicit alias
for immutable queue and historical-artifact compatibility.

The freeze is prospective and outcome-blind. It authorizes MB5 synthetic
structural executor implementation only. Molecular candidate energy, H2/H4
queue construction or execution, the 90-item development queue, production
molecular execution, and performance claims remain unauthorized.

The authoritative artifact is
`artifacts/v5-final/method-native/mb4-2-owner-protocol-freeze-v1.json`.

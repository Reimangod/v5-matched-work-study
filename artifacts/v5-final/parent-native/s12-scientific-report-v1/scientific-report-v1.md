# V5 frozen matched-work study — final scientific report v1

## Scope and conclusion

This report covers the exact frozen 90-item development population (5 cases × 3 budgets × 6 methods). The protocol, queue, caps, ranking, threshold, method semantics, and case set were not changed after outcomes. Results support case- and budget-specific resource/accuracy tradeoffs inside this population; they do not support general superiority or independent molecular generalization.

The central result is mixed rather than universally positive: V5 compression produced verified circuit-resource reductions in nine CEO*-paired cells, while absolute FCI error increased slightly and total registered work prevented five-objective dominance over the immutable CEO* source. V4.1 One-Shot produced no accepted compression under the frozen rule/caps. These negative and tradeoff results are retained.

## Offline FCI references

FCI was executed once, after S11 completion, for the five case identities frozen before outcomes. It was never used for selection, ranking, thresholds, method choice, or reruns.

| Case | FCI energy (Hartree) | ProblemID | Hamiltonian digest |
|---|---:|---|---|
| beh2-3.0 | -15.336804236064967 | `problem-v1:aefe2444aa77f7167f2e29aeb0ddad7f7af00cdfa9a7bc2f236d5676a2e86d6a` | `2beea8c8311c3c9f53769711f2f7acf081c698e77b0516239f09657b1d394772` |
| h4-1.5-known-development | -1.996150325518809 | `problem-v1:f5f8d7ed5471fc044924e7c8c7e49e5989a0bfe35f467f2612a55e810124edfd` | `d34322dc8c4b42ba3016d7b75a077047d64396510c40bdf99cdd79958f5ccecb` |
| h6-1.5 | -2.995565425831942 | `problem-v1:032aec6eb74a2a125ae81a60d803161a4742fb015f36704cbdf544c065e6d527` | `84490dbb61a91e10122fa23a703d6494e43ecf726e30adaef117d95839738cc6` |
| h6-3.0 | -2.800958899654442 | `problem-v1:5329cbf53d911bc2f013159c042250debc88230ea9a69933b7245cb74485b2cf` | `a2d0ffb58e86e9ed9428e97667438dd9e21ab8d21bd7e0b65f67c9aaad450892` |
| lih-3.0 | -7.798843159502407 | `problem-v1:f7ece52b3d2c22c1b893a4ed78719f594fc0cbc9adfde0c6764cbee2f92d6d06` | `f26e9d0617b9e577133e61c5fff9cb440b1ce16bb07c372b7e7c6a45daddf278` |

Audit counters: FCI evaluations = 5; S11 reruns = 0; S12 candidate-energy evaluations = 0; S12 optimizer starts = 0; production `N_dense_expm` = 0.

## Terminal outcomes

| Method | COMPLETED | ALGORITHM_REJECTED | CAP_REJECTED | Engineering NA | Total |
|---|---:|---:|---:|---:|---:|
| Immutable CEO* source | 14 | 0 | 0 | 1 | 15 |
| Same-structure reoptimization | 15 | 0 | 0 | 0 | 15 |
| Magnitude pruning | 9 | 5 | 1 | 0 | 15 |
| V4.1 One-Shot Joint | 0 | 12 | 3 | 0 | 15 |
| V5 fixed-source whitelist | 10 | 3 | 2 | 0 | 15 |
| V5 sequential rebuild | 10 | 3 | 2 | 0 | 15 |

Status codes below: C = COMPLETED, A = ALGORITHM_REJECTED, K = CAP_REJECTED, E = preserved engineering NA.

| Case / budget | CEO* | Same | Magnitude | One-Shot | V5 fixed | V5 sequential |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| lih-3.0 / LOW | E | C | K | A | C | C |
| lih-3.0 / MEDIUM | C | C | A | A | C | C |
| lih-3.0 / HIGH | C | C | A | A | C | C |
| h6-1.5 / LOW | C | C | C | K | K | K |
| h6-1.5 / MEDIUM | C | C | C | K | C | C |
| h6-1.5 / HIGH | C | C | C | A | C | C |
| h6-3.0 / LOW | C | C | C | K | K | K |
| h6-3.0 / MEDIUM | C | C | C | A | C | C |
| h6-3.0 / HIGH | C | C | C | A | C | C |
| beh2-3.0 / LOW | C | C | C | A | C | C |
| beh2-3.0 / MEDIUM | C | C | C | A | C | C |
| beh2-3.0 / HIGH | C | C | C | A | C | C |
| h4-1.5-known-development / LOW | C | C | A | A | A | A |
| h4-1.5-known-development / MEDIUM | C | C | A | A | A | A |
| h4-1.5-known-development / HIGH | C | C | A | A | A | A |

`lih-3.0 / LOW / CEO*` is the permanent pre-outcome thread-environment engineering failure. It was not rerun or imputed; consequently, paired sample counts are below the number of comparator completions where that source is required.

## Verified CEO*-paired physical-resource reductions

Only pairs where both source and comparator are COMPLETED with verified numeric metrics are included. Means are descriptive over the stated `n`, not population-general estimates.

| Method | paired n / 15 | Parameters mean % | CNOT mean % | CNOT depth mean % | Total depth mean % | Mean Δ absolute FCI error (Hartree) |
|---|---:|---:|---:|---:|---:|---:|
| Same-structure reoptimization | 14 / 15 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000e+00 |
| Magnitude pruning | 9 / 15 | 1.967 | 1.082 | 1.809 | 1.125 | 1.789e-07 |
| V4.1 One-Shot Joint | 0 / 15 | NA | NA | NA | NA | NA |
| V5 fixed-source whitelist | 9 / 15 | 5.714 | 3.952 | 1.300 | 4.490 | 1.293e-06 |
| V5 sequential rebuild | 9 / 15 | 5.714 | 3.952 | 1.300 | 4.490 | 1.293e-06 |

### Budget-stratified means

| Method | Budget | paired n | Parameters % | CNOT % | CNOT depth % | Total depth % |
|---|---|---:|---:|---:|---:|---:|
| Same-structure reoptimization | LOW | 4 | 0.000 | 0.000 | 0.000 | 0.000 |
| Same-structure reoptimization | MEDIUM | 5 | 0.000 | 0.000 | 0.000 | 0.000 |
| Same-structure reoptimization | HIGH | 5 | 0.000 | 0.000 | 0.000 | 0.000 |
| Magnitude pruning | LOW | 3 | 1.344 | 1.056 | 1.773 | 0.946 |
| Magnitude pruning | MEDIUM | 3 | 1.811 | 1.056 | 1.773 | 1.076 |
| Magnitude pruning | HIGH | 3 | 2.745 | 1.132 | 1.882 | 1.352 |
| V4.1 One-Shot Joint | LOW | 0 | NA | NA | NA | NA |
| V4.1 One-Shot Joint | MEDIUM | 0 | NA | NA | NA | NA |
| V4.1 One-Shot Joint | HIGH | 0 | NA | NA | NA | NA |
| V5 fixed-source whitelist | LOW | 1 | 2.632 | 3.169 | 0.000 | 2.838 |
| V5 fixed-source whitelist | MEDIUM | 4 | 4.999 | 3.476 | 0.532 | 3.970 |
| V5 fixed-source whitelist | HIGH | 4 | 7.198 | 4.623 | 2.394 | 5.422 |
| V5 sequential rebuild | LOW | 1 | 2.632 | 3.169 | 0.000 | 2.838 |
| V5 sequential rebuild | MEDIUM | 4 | 4.999 | 3.476 | 0.532 | 3.970 |
| V5 sequential rebuild | HIGH | 4 | 7.198 | 4.623 | 2.394 | 5.422 |

The 58 COMPLETED rows have absolute FCI errors from 9.334770e-04 to 1.507280e-03 Hartree.

## Pareto result

Dominance minimizes five objectives simultaneously: absolute FCI error, CNOT count, total depth, parameter count, and total registered work. No scalar weighting was introduced. Non-COMPLETED or numerically incomplete rows are listed as exclusions rather than assigned artificial values.

| Comparator | paired n | Comparator dominates CEO* | CEO* dominates comparator | Nondominated tradeoff/tie |
|---|---:|---:|---:|---:|
| Same-structure reoptimization | 14 | 0 | 14 | 0 |
| Magnitude pruning | 9 | 0 | 0 | 9 |
| V4.1 One-Shot Joint | 0 | 0 | 0 | 0 |
| V5 fixed-source whitelist | 9 | 0 | 0 | 9 |
| V5 sequential rebuild | 9 | 0 | 0 | 9 |

There are 39 front memberships across the 15 case-budget fronts and 32 explicit numeric exclusions. Front membership is case/budget-specific and is not a global method ranking.

## Direct findings and negative results

- Same-structure reoptimization completed all 15 cells, but its 14 valid CEO*-paired cells changed neither energy nor physical resources; CEO* source dominated it because reoptimization added registered work.
- Magnitude pruning completed 9 of 15 cells; its valid paired reductions were modest and accompanied by small positive absolute-FCI-error changes.
- Both V5 methods completed 10 of 15 cells and had 9 valid CEO*-paired cells; they reduced several circuit resources but did not dominate CEO* under the five-objective definition.
- V4.1 One-Shot Joint had zero COMPLETED cells (12 algorithm rejections and 3 cap rejections); this does not establish inferior energy performance.
- The two V5 methods had identical terminal status, energy, and physical-resource values in all 15 cells; only registered work differed in four cells.

Magnitude pruning's nine valid pairs averaged 1.967% fewer parameters, 1.082% fewer CNOTs, 1.809% lower CNOT depth, and 1.125% lower total depth, with mean absolute-FCI-error increase 1.789e-7 Hartree.

Each V5 method's nine valid pairs averaged 5.714% fewer parameters, 3.952% fewer CNOTs, 1.300% lower CNOT depth, and 4.490% lower total depth, with mean absolute-FCI-error increase 1.293e-6 Hartree. These are tradeoffs, not dominance or general superiority.

Fixed-source and sequential-rebuild produced identical terminal status, energy, and physical resources in all 15 cells. Registered work differed in only four cells; therefore this grid does not establish a scientific/resource advantage from rebuilding.

On the known-development H4 case, CEO* source and same-structure completed at every budget, while the four compression methods were algorithm-rejected at every budget. This is a case-specific frozen-rule result, not evidence against those methods generally.

## Claim boundary

Allowed:

- Exact terminal-rate statements for the frozen 90-item population.
- Status-aware COMPLETED-only physical-resource summaries.
- Verified paired reductions with the reported paired sample size.
- Case- and budget-specific non-scalar Pareto tradeoffs.
- Negative results and infrastructure limitations documented here.

Not allowed:

- General superiority outside this frozen matched-work population.
- Independent generalization: H4 is known development and no unseen molecule was run.
- Calling One-Shot the worst-energy method from zero accepted completions.
- Replacing missing/rejected/cap values with zero or an imputed success.
- Calling registered work the paper Measurement Cost.
- Hardware/noise/runtime superiority claims or retrospective protocol tuning.

## Reproducible artifacts

- Long-form JSON/CSV: `../s12-matched-work-aggregation-v1/matched-work-long-form-v1.*`
- Status summary: `../s12-matched-work-aggregation-v1/terminal-status-summary-v1.*`
- Paired comparisons: `../s12-matched-work-aggregation-v1/paired-comparisons-v1.*`
- Pareto fronts and exclusions: `../s12-matched-work-aggregation-v1/pareto-fronts-v1.*`
- Figures (PNG/PDF) and progression data: `../s12-matched-work-figures-v1/`
- FCI result and audit: `../s12-offline-fci-reference-v1/`

Paper Fig. 11/14/15 correspondence figures are endpoint/axis correspondences only. They do not reconstruct unavailable ADAPT growth trajectories, and registered-work counters are not substituted for paper Measurement Cost.

Scientific-summary digest: `d632951a1748f24bbca506c06adc7096add438429816809175ac588a47ccbc72`

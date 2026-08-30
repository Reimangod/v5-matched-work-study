# CEO-MESC 研究計画

## Measurement-Efficient Structural Compression of Optimized CEO-ADAPT-VQE* Ansätze

**文書版:** v0.1（実装開始前の研究計画）<br>
**作成日:** 2026-08-28<br>
**対象repository:** [Reimangod/v5-matched-work-study](https://github.com/Reimangod/v5-matched-work-study)<br>
**根拠としたrepository HEAD:** `bca77f26aad98937e69e824cb8024960c6994e60`<br>
**上流CEO* commit:** [`a3f89d03e6a03c89767d3cf8ee7657a57653dda0`](https://github.com/mafaldaramoa/ceo-adapt-vqe/commit/a3f89d03e6a03c89767d3cf8ee7657a57653dda0)<br>
**working name:** `CEO-MESC`（CEO Measurement-Efficient Structural Compression）

---

## 0. この文書の目的とclaim boundary

この文書は、最適化済みのCEO-ADAPT-VQE*（以下CEO*）ansatzから、精度を明示的に保護しながらCNOT、CNOT depth、total depth、parameters、logical CEO blocksを減らし、そのために追加される測定コストも定量化・制限する次期研究の実行計画である。

本計画は、次の3種類の証拠を混同しない。

1. **査読済み論文の結果**
   - CEO*、Hessian recycling、TETRIS、Pruned-ADAPT-VQEなど、論文が実際に示した範囲。
2. **公開コードから確認できる実装**
   - 論文に書かれた方法と、GitHub上で実際に実行可能な方法は同一とは限らない。
3. **本projectのdevelopment evidence**
   - V4.1/V5/V5.1のbest-found結果と、完了済み90-item matched-work結果を分離する。

現時点で許される主張は次だけである。

- CEO*の特定checkpointには、物質・geometry・budgetに依存して、精度をほぼ維持したまま削減可能な構造的冗長性が存在する。
- historical best-foundでは大きな削減が得られた場合がある。
- frozen matched-workでは平均削減は小さく、Sequential-Rebuildの優位性は確認できなかった。
- したがって、「大幅削減が一般に可能」「追加測定コストがほぼゼロ」「V5がCEO*を一般に上回る」とはまだ言えない。

本計画の成功条件は、これらの未証明主張を段階的に検証可能な形へ変えることであり、成功を前提に結果を選ぶことではない。

---

## 1. 結論：次に進むべき研究方向

次期研究の主軸は、**CEO*を再成長させる新しいADAPT選択法**ではなく、すでにstationaryなCEO* sourceに対する**測定効率を制約した構造圧縮**とする。

推奨するアルゴリズムは、次の5段階で構成する。

1. **Exact-first structural pass**
   - exact coordinate fusion、MVP constituent removal、MVP-to-single-QE、MVP-to-registered-OVPなど、generator algebraで厳密に証明できる変換を最初に適用する。
   - exact certificateが成立する限り、candidate energy測定やoptimizerを要求しない。
2. **Resource-real candidate filter**
   - parameterを0にするだけではなく、generator/blockを物理的に削除し、paper-era circuit counterでCNOT/depthが実際に減る候補だけを残す。
3. **Curvature-aware, outcome-blind ranking**
   - CEO*がHessian recyclingで保持している近似逆Hessianを、OBS型の予測損失に利用する。
   - ただしOBSは順位付けであり、acceptance certificateではない。
4. **Progressive certificate ladder**
   - 安価な代数検査・resource recount・warm-start energy probeを通過した候補だけをfull-ansatz reoptimizationへ送る。
   - 失敗候補に高価なoptimizer/gradient/state validationを使わない。
5. **Conditional sequential rebuild**
   - accepted childによりblock topologyまたはcandidate catalog digestが変わった場合だけcatalogをrebuildする。
   - catalogが実質不変ならfixed-source経路を継続し、Sequential-Rebuildの無駄な追加workを避ける。

この構成を選ぶ理由は明確である。

- historical V4.1はLiHで約46%、BeH2で約14–16%の回路削減を示した。
- しかしmatched-work V5は平均CNOT削減3.952%、total depth削減4.490%に留まった。
- matched-workのfixed-source V5とsequential-rebuild V5は15/15 cellでenergy/resources/statusが一致した。
- V4.1 One-Shot Jointは0/15 completedであり、同時圧縮は現在のacceptance/cap下では攻撃的すぎた。
- Pruned-ADAPT-VQEは小振幅・位置情報による削除が小さな追加costで有効な場合を示すが、threshold依存・再追加・物質依存も示す。
- Hessian recyclingはすでに逆Hessian情報を生成しているため、追加量子測定なしでより良い候補順位を構成できる。

したがって、最も現実的なのは「探索を広げる」ことではなく、**量子測定不要の候補を先に確定し、測定を使う候補を少数に絞り、rebuildを必要時だけ実行すること**である。

---

## 2. 用語と研究対象の固定

### 2.1 CEO* source

本計画でいうCEO*は、[Ramôa et al., npj Quantum Information 11, 86 (2025)](https://www.nature.com/articles/s41534-025-01039-4)のCEO poolに、TETRIS、optimized gradient measurement（OGM）、Hessian recycling（HR）を組み合わせたCEO-ADAPT-VQE*を指す。

本研究は原則としてCEO*のadaptive growthを変更しない。入力は、次を満たす最適化済みcheckpointである。

- ansatz indicesとordered CEO block structureが固定されている。
- coefficients、gradient、inverse-Hessian approximationが保存されている。
- source energyとfull circuit resourcesが再構成できる。
- stationarityが検証されている。
- molecule、geometry、basis、active space、mappingがProblemIDに固定されている。

### 2.2 構造圧縮

圧縮後ansatzを (U_c(\boldsymbol\phi))、sourceを (U_s(\boldsymbol\theta)) とする。物理resource vectorを

\[
\mathbf R(U)=
\left(
N_{\mathrm{CNOT}},
D_{\mathrm{CNOT}},
D_{\mathrm{total}},
N_{\mathrm{param}},
N_{\mathrm{block}}
\right)
\]

と定義する。

本研究で「圧縮成功」と呼ぶには、少なくとも次を満たす必要がある。

1. generatorまたはCEO blockが物理的なtarget ansatzから除かれている。
2. full ansatz circuitを同一counterで再構成している。
3. $\mathbf R(U_c)$の少なくとも1成分が厳密に改善し、登録したcomponentwise policyに反しない。
4. energy、state、constraint、stationarityのguardを通過する。

したがって、

- coefficientを0へ固定しただけ、
- parameter listだけを短くした、
- compilerが偶然gateを消した、

という事実だけでは回路圧縮とは呼ばない。

### 2.3 three-layer identity

既存実装の3層identityをそのまま維持する。

- **StatePreparationID**: reference、generator digest、block構造、indices、canonical coefficient bytes、orbital parameters、mapping、qubit ordering。
- **ProblemID**: Hamiltonian digest、molecule、geometry、basis、active space、frozen orbitals、mapping convention。
- **MeasurementContextID**: StatePreparationID、ProblemID、observable set、measurement plan、grouping、estimator、backend context。

実装根拠は [`identity.py`](../provenance/dvg-obs-ceo/src/dvg_obs_ceo/identity.py) にある。measurement-plan versionは量子状態そのものを定義しないため、StatePreparationIDへ入れない。

---

## 3. 現在までに得られた結果

### 3.1 論文CEO*と通常GSD-ADAPTの直接再現

LiH 3.0 Å、STO-3G、Jordan–Wigner、noiseless exact simulationで得られた直接比較は次である。

| Method | Error (Ha) | Parameters | CNOT | CNOT depth | Total depth |
|---|---:|---:|---:|---:|---:|
| GSD-ADAPT | 0.0006843315 | 6 | 392 | 384 | 500 |
| CEO* | 0.0009334770 | 15 | 107 | 30 | 171 |

CEO*は同一のfirst-chemical-accuracy endpointで、GSDに対してCNOT 72.7%、CNOT depth 92.2%、total depth 65.8%を削減した。これはCEO* source自体が強いbaselineであり、そこからさらに削る研究は容易ではないことを意味する。

証拠: [`S11_LIH_DIRECT_COMPARISON.md`](../provenance/dvg-obs-ceo/docs/S11_LIH_DIRECT_COMPARISON.md)

### 3.2 historical V4.1 best-found development results

V4.1は、同じCEO* checkpointにsource-relative joint compressionを適用し、energy budget $10^{-4}$ Ha以内で次を得た。

| Case | ΔE (Ha) | Parameters削減 | CNOT削減 | CNOT depth削減 | Total depth削減 | Blocks削減 |
|---|---:|---:|---:|---:|---:|---:|
| LiH 3.0 Å | 8.6901e-5 | 46.67% | 45.79% | 0.00% | 46.20% | 46.67% |
| H6 1.5 Å | 8.8214e-5 | 4.38% | 2.39% | 1.96% | 3.07% | 1.27% |
| H6 3.0 Å | 7.1345e-5 | 3.36% | 2.17% | 0.34% | 2.55% | 1.05% |
| BeH2 3.0 Å | 9.6615e-5 | 13.16% | 15.85% | 5.32% | 14.19% | 15.63% |

特にLiHの45–47%削減とBeH2の約14–16%削減は、CEO*にもpost-growth redundancyが存在し得る強いdevelopment evidenceである。

ただし、これはmatched computational workではない。H6/BeH2ではsearch statesが10,000に達し、最大4回のexact VQE attemptを行った。よって「低costで一般に得られる削減」ではなく、**大きな削減候補が存在したことを示すbest-found evidence**である。

証拠: [`V4_1_CEO_STAR_COMPARISON.md`](../provenance/dvg-obs-ceo/docs/V4_1_CEO_STAR_COMPARISON.md)

### 3.3 V5 / V5.1 development results

V5のSequential-Rebuildは、V4.1より良いstrict pointを4 development cases中H6 3.0 Åの1件で得た。

- V4.1: 768 CNOT、144 parameters、ΔE=7.134e-5 Ha
- V5: 758 CNOT、142 parameters、ΔE=6.915e-5 Ha

BeH2 3.0 ÅではV5のraw minimum-CNOT pointが221 CNOT、31 parametersまで減ったが、V4.1 pointよりenergy increaseが1.9033e-6 Ha大きく、事前のsame-or-lower-energy条件を満たさなかったためstrict successには数えていない。

V5.1 exact fusionはH6 1.5 Åで次を得た。

| Point | ΔE (Ha) | CNOT | Parameters | Total depth | CNOT depth | Blocks |
|---|---:|---:|---:|---:|---:|---:|
| CEO* | 0 | 879 | 137 | 1595 | 306 | 79 |
| V5.1 resource point | 8.8214e-5 | 840 | 129 | 1520 | 300 | 76 |

これはexact fusionが、追加optimizer startを増やさずにV4.1/V5 pointからさらにCNOT 18、parameters 2、total depth 26、blocks 2を削減できた事例である。ただしcandidate discoveryはoutcome-informed developmentであり、一般性は未証明である。

証拠:

- [`V5_S9_RESULT.md`](../provenance/dvg-obs-ceo/docs/V5_S9_RESULT.md)
- [`V5_V5_1_RELEASE_RESULT.md`](../provenance/dvg-obs-ceo/docs/V5_V5_1_RELEASE_RESULT.md)

### 3.4 完了済み90-item matched-work結果

現在の最も強い内部証拠は、5 cases × 3 budgets × 6 methodsのfrozen 90-item studyである。queue、case、budget、ranking、acceptance、method semanticsはoutcome取得前に固定された。

対象case:

- LiH 3.0 Å
- H6 1.5 Å
- H6 3.0 Å
- BeH2 3.0 Å
- H4 1.5 Å（known development）

terminal outcomeは次である。

| Method | Completed | Algorithm rejected | Cap rejected | Engineering NA |
|---|---:|---:|---:|---:|
| Immutable CEO* | 14 | 0 | 0 | 1 |
| Same-structure reoptimization | 15 | 0 | 0 | 0 |
| Structural magnitude pruning | 9 | 5 | 1 | 0 |
| V4.1 One-Shot Joint | 0 | 12 | 3 | 0 |
| V5 fixed-source whitelist | 10 | 3 | 2 | 0 |
| V5 sequential rebuild | 10 | 3 | 2 | 0 |

CEO*とのpaired comparisonの平均は次である。

| Method | paired n | Parameters | CNOT | CNOT depth | Total depth | Mean Δ absolute FCI error |
|---|---:|---:|---:|---:|---:|---:|
| Magnitude | 9 | -1.967% | -1.082% | -1.809% | -1.125% | +1.789e-7 Ha |
| V5 fixed | 9 | -5.714% | -3.952% | -1.300% | -4.490% | +1.293e-6 Ha |
| V5 sequential | 9 | -5.714% | -3.952% | -1.300% | -4.490% | +1.293e-6 Ha |

budget別のV5平均は次である。

| Budget | paired n | Parameters | CNOT | CNOT depth | Total depth |
|---|---:|---:|---:|---:|---:|
| LOW | 1 | -2.632% | -3.169% | 0.000% | -2.838% |
| MEDIUM | 4 | -4.999% | -3.476% | -0.532% | -3.970% |
| HIGH | 4 | -7.198% | -4.623% | -2.394% | -5.422% |

重要なcase-specific結果:

- LiH MEDIUM/HIGH V5は15→13 parameters、107→96 CNOT、171→151 total depthで、CNOT削減10.28%、total depth削減11.70%、ΔE=5.669e-6 Haだった。
- BeH2 HIGH V5は38→34 parameters、284→266 CNOT、94→85 CNOT depth、458→426 total depthで、CNOT削減6.34%、total depth削減6.99%、ΔE=1.463e-7 Haだった。
- H6 1.5/3.0のmatched-work削減はおおむね0–2%台に留まった。
- H4では全budgetで4つのcompression methodがalgorithm-rejectedされた。

証拠:

- [`scientific-report-v1.md`](../artifacts/v5-final/parent-native/s12-scientific-report-v1/scientific-report-v1.md)
- [`paired-comparisons-v1.csv`](../artifacts/v5-final/parent-native/s12-matched-work-aggregation-v1/paired-comparisons-v1.csv)
- [`matched-work-long-form-v1.csv`](../artifacts/v5-final/parent-native/s12-matched-work-aggregation-v1/matched-work-long-form-v1.csv)

### 3.5 registered workの現状

completed rowsだけを記述的に集計すると、V5は平均で次の追加workを要した。

- energy evaluations: 52.5（range 6–215）
- gradient vectors: 40.7（range 5–155）
- gradient-component equivalents: 1504.2（range 222–4439）
- optimizer starts: 2.8（range 1–6）
- candidate generations: fixed 428.2、sequential 430.2
- resource recounts: fixed 696.1、sequential 699.2

これらは**paper Measurement Costではない**。candidate generation、matrix verification、resource recountなどのclassical/software workを含む単純加算のregistered workであり、各primitiveの量子shot costは同じではない。

一方、energy/gradient/optimizer countersは、次期計画でpaper-compatible Measurement Costへ変換するためのraw evidenceとして利用できる。

### 3.6 現行matched-work実装が実際に行っていること

現行V5を概念名だけで説明せず、production codeの挙動を固定する。

| 挙動 | 実装 | 現在の意味 | 次期計画での扱い |
|---|---|---|---|
| block/candidate recovery | [`build_typed_catalog`](../src/v5_final/parent_native_candidate_adapter.py) | actual `DVGBlock`と`CompressionCandidate`を上流codeから取得 | 維持 |
| candidate composition | [`compose_parent_native_plan`](../src/v5_final/parent_native_candidate_adapter.py) | registered linear constraintをcomposeし、OBS warm startとtarget identityを作る | 維持 |
| matrix/circuit verification | [`prepare_rewrite_for_optimizer`](../src/v5_final/parent_native_rewrite.py) | source/target generator matrixとnative circuitを検証し、full resourcesをrecount | 維持 |
| V5 ranking | [`_rank_parent_candidates`](../src/v5_final/parent_native_executors.py) | predicted loss、resource Pareto、energy screening budget $10^{-4}$、endpoint当たりtop-2、最大4 attempts | quality marginとvalidation-cost軸を追加 |
| magnitude control | [`_dynamic_magnitude_preparation`](../src/v5_final/parent_native_execution_services.py) | current stateで最小 $|\theta_i|^2$ を1件選び、物理generatorを削除 | Pruned-inspired position controlを別ablationで追加 |
| acceptance | [`_optimize_and_decide`](../src/v5_final/parent_native_execution_services.py) | BFGS後にindependent energy/state、constraint、KKT、componentwise resourceを検査 | 維持。前段に安価なprobeを追加 |
| fixed-source whitelist | [`_dynamic_v5_preparation`](../src/v5_final/parent_native_execution_services.py) | child catalog自体は再構築するが、source時点のstructural whitelist keyに属する候補だけをadmit | 「no rebuild」ではなく「no replenishment」と呼ぶ |
| sequential rebuild | [`execute_prepared`](../src/v5_final/parent_native_execution_services.py) | accepted childをcommit後、current stateからcatalogを作り直し、新候補もadmit | catalog変化時だけ行うconditional policyへ |

このcode auditから、matched-workのfixedとsequentialが同じ結果だった理由を「rebuild codeが動かなかった」と解釈してはいけない。両者ともchild catalogを再構築し、違いは**source whitelist外の新しいcandidateをadmitするか**である。今回の15 cellsでは、その差がterminal energy/resourcesへつながらなかった。

また現行rankingはすでにOBS predicted lossとresource Paretoを使っている。したがって次期研究の新規性は「OBSを初めて入れる」ことではない。必要なのは、

- exact candidateをquantum-outcome-freeに先に処理する、
- Hessian quality/uncertaintyをrankingへ反映する、
- full BFGS前にsingle-point rejectionを入れる、
- validation costをPareto軸にする、
- replenishmentが実際に必要な場合だけcatalog expansionを許可する、

という**measurement-efficient execution policy**である。

---

## 4. 先行研究と公開コードの徹底整理

### 4.1 CEO-ADAPT-VQE*

**論文:** [Ramôa et al., “Reducing the resources required by ADAPT-VQE using coupled exchange operators and improved subroutines,” npj Quantum Information 11, 86 (2025)](https://www.nature.com/articles/s41534-025-01039-4)<br>
**公式GitHub:** [mafaldaramoa/ceo-adapt-vqe](https://github.com/mafaldaramoa/ceo-adapt-vqe)<br>
**本研究で固定したcommit:** [`a3f89d0`](https://github.com/mafaldaramoa/ceo-adapt-vqe/commit/a3f89d03e6a03c89767d3cf8ee7657a57653dda0)

論文が示したこと:

- CEOは同一spin-orbitals上の複数QEをcoupleする。
- MVP-CEOは最大3 QEを、単一QEと同程度の13 CNOTで実装できる。
- OVP-CEOは9 CNOTの構成を持つ。
- CEO*はLiH、H6、BeH2（12–14 qubits）で、初期GSD-ADAPTに対し最大88% CNOT、96% CNOT depth、99.6% Measurement Costを削減した。
- CEO*のMeasurement Costはnoiseless energy-evaluation multiplierによるlower-bound modelであり、shot noiseを直接simulateした値ではない。
- gradient evaluationはparameter-shiftに基づきenergy evaluationの2倍として扱う。
- OGMによるpool-gradient cost、HRによるoptimization cost、TETRISによるdepth/iteration削減を組み合わせる。

本計画への導出:

- CEO*はすでに強い回路baselineなので、単なるparameter deletionでは不十分。
- compression overheadを論じるには、CEO論文と同じenergy-equivalent measurement modelを別途再構築する必要がある。
- CEO* source生成時に得たinverse Hessianを再利用すれば、compression rankingのための新しい量子測定を増やさずに済む可能性がある。

### 4.2 Hessian recycling

**論文:** [Ramôa et al., “Reducing measurement costs by recycling the Hessian in adaptive variational quantum algorithms,” Quantum Science and Technology 10, 015031 (2025)](https://doi.org/10.1088/2058-9565/ad904e)<br>
**実装:** [mafaldaramoa/ceo-adapt-vqe](https://github.com/mafaldaramoa/ceo-adapt-vqe)

論文が示したこと:

- BFGSの近似逆HessianをADAPT iteration間で拡張・再利用する。
- LiH/H6/BeH2の複数geometry/poolで、canonical optimizerに対するVQE measurement costを13–36%程度まで減らした例が報告される。
- inverse Hessianはoptimizer収束を速めるための情報であり、削除後energyを厳密に保証するものではない。

本計画への導出:

- 逆Hessianはすでにsource artifactに存在するため、OBS型screeningに再利用しても、その行列を新規測定で取得する必要はない。
- ただし、近似がpoor/indefinite/staleな場合はfail-closedにし、magnitude/resource-only rankingへfallbackする。
- target coordinateへ移す際は、既存の`obs_warm_start`とconstraint mapを利用する。

### 4.3 OGM: pool-gradient measurement

**論文:** [Anastasiou et al., “How to really measure operator gradients in ADAPT-VQE,” arXiv:2306.03227](https://arxiv.org/abs/2306.03227)<br>
**CEO*での使用:** [CEO* paper, Measurement Cost discussion](https://www.nature.com/articles/s41534-025-01039-4)

論文が示したこと:

- hardware-efficient poolのgradient observablesをcommuting groupsへまとめる。
- naive energy measurementに対するpool-gradient overheadを、qubit数に対し線形程度へ抑えるstrategyを提示する。

本計画への導出:

- compressionは新しいADAPT growth roundを追加しないため、原則としてfull pool gradientを再測定しない。
- candidate validationで同一state上のenergy/gradient Pauli termsが重複する場合だけ、OGM-compatible grouping/reuseを利用する。
- 異なるStatePreparationID間の測定値は再利用しない。

### 4.4 TETRIS-ADAPT-VQE

**論文:** [Anastasiou et al., “TETRIS-ADAPT-VQE,” Physical Review Research 6, 013254 (2024)](https://journals.aps.org/prresearch/abstract/10.1103/PhysRevResearch.6.013254)<br>
**arXiv:** [arXiv:2209.10562](https://arxiv.org/abs/2209.10562)<br>
**実装:** [mafaldaramoa/ceo-adapt-vqe](https://github.com/mafaldaramoa/ceo-adapt-vqe)

論文が示したこと:

- qubit supportが重ならない複数operatorを同一ADAPT iterationで追加し、shallower and denser ansatzを構成する。

本計画への導出:

- TETRISはsource growthの一部であり、post-compression algorithmでは変更しない。
- ただし、同一iterationに追加されたCEO blocksはtopology上のまとまりを持つため、candidate featureとしてselection iteration、qubit support、block adjacencyを保存する。
- TETRIS由来の並列性を壊してdepthが増えるrewriteは拒否する。

### 4.5 Pruned-ADAPT-VQE

**査読論文:** [Vaquero-Sabater, Carreras, Casanova, JCTC 21, 8720–8728 (2025)](https://pubs.acs.org/doi/10.1021/acs.jctc.5c00535)<br>
**arXiv/SI:** [arXiv:2504.04652](https://arxiv.org/abs/2504.04652)<br>
**GitHub:** [abelcarreras/VQEmulti](https://github.com/abelcarreras/VQEmulti)<br>
**pruning実装branch:** [`final_distribution_func`](https://github.com/abelcarreras/VQEmulti/tree/final_distribution_func)<br>
**主要実装:** [`vqemulti/prune_adapt.py`](https://github.com/abelcarreras/VQEmulti/blob/final_distribution_func/vqemulti/prune_adapt.py)

論文の中心式は、operator位置 $i$、ansatz長 $N$、parameter $\theta_i$ に対して

\[
f_i = \frac{1}{|\theta_i|^2}\exp\left(-\alpha\frac{i}{N}\right)
\]

を用い、最も大きい $f_i$ のoperatorについて、

\[
|\theta_i| < 0.1\times
\operatorname{mean}\left(|\theta_{N-3}|,\ldots,|\theta_N|\right)
\]

なら削除する、というものである。公開branchのdefaultは `alpha=11`、paperでは主に $\alpha\approx10$ を議論する。

報告された代表的傾向:

- linear H4 3 Åでchemical accuracy到達operator数が約35→26（約26%）。
- H2O 3 Åで約25%、N2 2 Åで約11%程度のoperator削減（図からの概算）。
- H6では同程度errorで約40%程度のoperator削減例。
- BeH2ではthresholdを緩めた条件で約26%程度の削減例。
- 小さいSTO-3G caseでは利益が小さい場合がある。
- 論文本文では削除後にfull reoptimizationを行わず、追加costは小さいとする。
- 一方でlate-stage delete/re-add cycleや、thresholdが強すぎる場合のpremature convergenceが報告される。

コード監査上の注意:

- pruning codeはdefault branchではなく`final_distribution_func` branchにある。
- `prune_adapt.py`は最大factorを1件選び、parameterを削除後にenergyを計算するが、削除後full reoptimizationは行わない。
- zero coefficientに対する除算保護、pruning専用CI/test、論文release tag、fully pinned environmentは確認できない。
- したがって、同repositoryをそのままproduction dependencyにはせず、論文式を独立実装・単体試験する。

本計画への導出:

- parameter magnitudeだけでなくpositionを使うことは、ADAPT growth後に古いoperatorがfadeするという仮説に対応する。
- しかしCEO blockでは1 parameter削除が回路削減につながらない場合があるため、parameter/position scoreは候補生成にしか使わない。
- thresholdを分子ごとに結果を見て調整しない。calibration caseでfreezeし、validationでは固定する。
- delete/re-add cycleを避けるため、post-growth compressionではre-addを原則禁止し、却下時はrollbackする。

### 4.6 Mafalda Ramôa MSc thesisのterm removal

**thesis:** [“Ansätze for Noisy Variational Quantum Eigensolvers,” arXiv:2212.04323](https://arxiv.org/abs/2212.04323)<br>
**GitHub:** [mafaldaramoa/VQE](https://github.com/mafaldaramoa/VQE)

Chapter 6では、過去operatorのenergy contributionを後のoperatorと比較し、削除後にfull reoptimizationを行い、energy増加が元のbenefitの150%以内なら削除を受理する。10-operator ansatzで、LiH/OH−では精度改善を伴う削除が得られた一方、H4では削除利益が得られなかった。optimizer回数はoriginal 10に対し、removalで約22–26となり、おおむね2.2–2.6倍だった。

本計画への導出:

- full reoptimizationは精度guardとして有効だが、全候補へ行うと測定costが大きい。
- candidate energy/optimizerを段階化し、full reoptimizationへ進む候補を少数に制限する必要がある。
- H4で失敗したことは、現在のH4 matched-work全compression rejectionと整合し、圧縮可能性はcase-dependentである。

### 4.7 Optimal Brain Surgeon（OBS）

**原論文:** [Hassibi and Stork, “Second Order Derivatives for Network Pruning: Optimal Brain Surgeon,” NeurIPS 1992](https://mlanthology.org/neurips/1992/hassibi1992neurips-second/)

OBSは単なるweight magnitudeではなく、1つのweightを固定して他のweightを再調整したときのloss増加をinverse Hessianから予測する。

VQE parameter $\boldsymbol\theta$ がstationary pointにあり、Hessianを $H$、近似逆Hessianを $M\approx H^{-1}$ とする。単一coordinate $\theta_i$ を0へ固定する局所二次近似では、

\[
\Delta E_i^{\mathrm{OBS}}
\approx
\frac{\theta_i^2}{2M_{ii}}
\]

である。一般の線形constraint $A\delta=r$ では、

\[
\Delta E_{A}^{\mathrm{OBS}}
\approx
\frac{1}{2}
r^\mathsf{T}
\left(A M A^\mathsf{T}\right)^{-1}
r.
\]

本計画への導出:

- CEO transformationは単純なcoordinate deleteだけでなく、複数parameterの線形constraint/reparameterizationを含むため、一般式を使う。
- $M$のqualityが不十分なら予測を無効とする。
- exact VQE energyとfull reoptimizationのみがacceptance evidenceであり、OBS値だけで削除しない。

### 4.8 measurement-data reuse

**関連研究:** [Nykänen et al., “Mitigating the measurement overhead of ADAPT-VQE with optimised informationally complete generalised measurements,” arXiv:2212.09719](https://arxiv.org/abs/2212.09719)

この研究はIC measurement dataからenergyだけでなくpool commutatorsをclassical post-processingし、同一stateの測定dataを再利用する。CEO*のOGMと同一手法ではないが、「同一stateで得たobservable dataを複数の推定に使う」という原理を支持する。

本projectの実装は [`measurement_reuse.py`](../provenance/dvg-obs-ceo/src/dvg_obs_ceo/measurement_reuse.py) にあり、現在はexact noiseless Pauli expectationだけを対象とする。これはshot-based reuseの性能を証明しない。

本計画への導出:

- exact simulatorではsemantic cacheとして重複計算を除く。
- finite-shot研究ではraw measurement record、basis、shots、estimator、backend contextまで一致するときだけreuseする。
- 異なるoptimized coefficientは異なるStatePreparationIDであり、energy測定を流用しない。

---

## 5. 現在の結果から次期設計を導く論理

### 5.1 Observation → inference → decision → falsification

| Observation | 推論 | 設計判断 | 反証条件 |
|---|---|---|---|
| V4.1 LiHはCNOT 45.79%削減 | 大きなredundancy自体は存在する | 大削減候補を表現できるtransformation familyを保持 | frozen prospective runで同familyが常に拒否される |
| matched LiH V5はCNOT 10.28% | best-foundの大削減はsearch/work/protocol依存 | historical resultとprospective resultを分離し、再現をsuccess条件にしない | 同一candidateが低costで再発見されるならranking/cap仮説を更新 |
| BeH2 V4.1は15.85%、matched HIGH V5は6.34% | budget増加は削減を増やすがhistorical endpointまでは届かない | progressive screeningで高価なattemptを有望候補へ集中 | measurement costを増やしてもresource gainが飽和する |
| H6 matched reductionは小さい | MVP-heavy topologyではordinary deletionがCNOTへ結びつきにくい | exact fusion/rank-demotionを優先 | exact candidate censusが空ならH6大幅削減仮説を棄却 |
| H4 compressionは全budget reject | 圧縮不能またはguardが正しく保護 | `NO_SAFE_COMPRESSION`を正式結果にする | threshold緩和でしか成功しない場合は一般methodに採用しない |
| One-Shotは0/15 completed | 同時joint compressionはrisk/costが高い | exact-compatible joint以外はsequential single commit | 小規模exact jointが低costで繰返し成功するなら限定復活 |
| FixedとSequentialは15/15同一結果 | rebuildが候補集合を変えないcaseが多い | catalog digest変化時のみrebuild | child catalogが変わり、追加のaccepted pointが得られるcaseが複数出る |
| magnitude平均CNOT 1.08% | small parameterは弱いproxy | magnitude-onlyをcontrolとし、主法はOBS+resource Pareto | OBSがmagnitudeよりcandidate efficiencyを改善しない |
| V5は追加optimizer/gradientが多い | compression overheadが主要risk | measurement budgetをprimary constraintにする | paper-compatible costでoverheadが小さいと判明すればcapを再評価 |
| V5.1 exact fusionはzero optimizerで追加削減 | exact algebraは最もcost-efficient | exact-first passを常時最初に実行 | prospective censusでcandidateが稀すぎる/0ならsecondary contributionに下げる |

### 5.2 なぜHamiltonian-aware ADAPT growthを同時に入れないか

Hamiltonian-aware operator selectionは有望でも、source growthそのものを変更する。これをpost-compressionと同時に導入すると、

- source ansatzが異なる、
- CEO* construction costが異なる、
- redundancy発生原因が異なる、
- Measurement Costの差がgrowthとcompressionのどちらから来たか分からない、

というconfoundingが生じる。

したがって本計画のcore studyでは採用しない。CEO-MESCが固定CEO* sourceで成立した後に、独立factorial studyとして検討する。

### 5.3 なぜbarrier-free full-ansatz Qiskit compilationを入れないか

resource reductionをalgorithmic rewriteではなくcompiler差で作る恐れがあるため、paper-era QASM counterを固定する。compiler studyは別ablationに分離する。

---

## 6. 研究質問と仮説

### RQ1: Mechanism

**なぜADAPT growth時には有用だったCEO blockが、後続operator追加とfull-ansatz reoptimization後に冗長になるのか。**

仮説:

- H1a: fadingはsmall coefficientだけでなく、近接blockとのcurvature couplingで説明できる。
- H1b: exact generator relationを持つMVP/OVP combinationは、同一state family内で低rank representationへ変換できる。
- H1c: TETRIS selection iteration、block adjacency、qubit support overlapがredundancyの発生率に関連する。

### RQ2: Compression performance

**同一CEO* checkpoint、同一accuracy guardの下で、magnitude pruningより大きいphysical resource reductionを得られるか。**

仮説:

- H2a: OBS+resource Pareto rankingは、同じcandidate-energy/optimizer budgetでmagnitude controlより大きなCNOT/total-depth削減を得る。
- H2b: exact-first passはenergy loss 0（numerical tolerance内）で追加resource reductionを得るcaseがある。

### RQ3: Measurement efficiency

**圧縮探索の追加measurement-equivalent costを制限しても、有意な回路削減を得られるか。**

仮説:

- H3a: exact-first、progressive rejection、conditional rebuildにより、full V5より少ないoptimizer/gradient workで同等以上のaccepted resource pointを得る。
- H3b: compression overheadを含めたend-to-end Measurement CostはCEO* constructionの25%以内をmedian targetとして設計可能である。

H3bの25%は現時点の結果ではなく**設計target**である。S1でpaper-compatible costを再構築した後、outcomeを見る前に最終freezeする。

### RQ4: Generalization

**developmentで固定したruleが、未使用geometryおよび未使用moleculeでもthreshold retuningなしに動くか。**

仮説:

- H4a: exact rewrite applicabilityはmolecule-specificでも、certificateのcorrectnessは一般的である。
- H4b: heuristic pruningの成功率はsystem-dependentであり、`NO_SAFE_COMPRESSION`を含むcalibrated methodとして報告すべきである。

---

## 7. CEO-MESCアルゴリズム仕様

### 7.1 入力

- immutable CEO* source checkpoint
- HamiltonianとProblemID
- StatePreparationID
- source energy $E_s$
- source gradient $g_s$
- source inverse-Hessian approximation $M_s$
- source circuit resources $\mathbf R_s$
- componentwise work cap
- energy budget $\varepsilon_E$
- exact/numerical validation tolerances

### 7.2 Stage A: source audit

次を全て満たさなければ実行しない。

1. source coefficientsとindicesの長さが一致。
2. recovered blocksをflattenしたindicesがsource orderと一致。
3. gradient dimensionとinverse-Hessian dimensionがparameter数と一致。
4. $\|g_s\|_\infty$がstationarity threshold以下。
5. source energyがindependent direct Hamiltonian expectationと一致。
6. source circuit resource digestがpaper-era counterで再現。
7. identity bundleとenvironment digestがqueueに一致。

### 7.3 Stage B: typed candidate censusとexact-first分類

候補familyを列挙した後、**exact class**と**approximate class**を明確に分離する。

Exact class:

1. exact coordinate fusion
2. exact generator relationが証明されたMVP constituent removal
3. registered exact MVP-to-single-QE reduction
4. registered exact MVP-to-OVP reduction
5. registered exact native rank demotion

Approximate class:

6. whole CEO-block deletion
7. exact relationを持たないMVP constituent removal
8. single-coordinate physical deletion

whole-block deletionや一般のconstituent removalを「exact」と仮定しない。exact classだけがcandidate energy/optimizerなしのcommit候補になり、approximate classは必ずOBS screeningとprogressive energy certificateへ進む。

各候補は次を持つ。

- source block IDs
- source/target pool indices
- exact generator relation
- constraint matrixとrhs
- source→target Jacobian
- expected physical circuit change
- candidate intent ID
- proposed physical state ID

exact候補ではgenerator matrix equality、native target circuit unitary equality、statevector equalityを独立経路で検証する。

### 7.4 Stage C: physical-resource prefilter

候補をtarget structureへmaterializeし、optimizer前にpaper-era circuitをrecountする。

次を満たさない候補はenergyを測定せず拒否する。

- circuit QASM digestがsourceから変化。
- logical structure digestがsourceから変化。
- CNOT/CNOT depth/total depthの少なくとも1つが減少。
- preregistered componentwise non-regression policyを満たす。

これにより「parameter削除だがCEO blockが残り、回路が減らない」候補へ測定を使わない。

### 7.5 Stage D: curvature quality gate

inverse Hessian $M_s$について次を検査する。

- finite、symmetric、dimension一致
- eigenvalue/condition number
- secant residual
- gradient/Hessian coordinate identity
- source constraint consistency
- target map後のpositive-definitenessまたはregularized solvability

品質区分:

- `GOOD`: OBS rankingをprimaryに使用。
- `USABLE_WITH_MARGIN`: uncertainty marginを加えたupper boundで使用。
- `UNUSABLE`: OBS scoreを無効とし、exact/resource-only候補以外を実行しない。

### 7.6 Stage E: candidate ranking

候補 $c$ について、次のvectorを作る。

\[
\mathbf q(c)=
\left(
\widehat{\Delta E}_{\mathrm{OBS}}(c)+u(c),
-\Delta N_{\mathrm{CNOT}},
-\Delta D_{\mathrm{CNOT}},
-\Delta D_{\mathrm{total}},
-\Delta N_{\mathrm{param}},
\widehat M_{\mathrm{validate}}(c)
\right)
\]

ここで $u(c)$ はHessian-quality由来のuncertainty margin、$\widehat M_{\mathrm{validate}}$ は予測validation costである。

単一の恣意的weight sumはprimary selectorにしない。非劣Pareto setを作り、各registered endpointから最大1件、合計最大 $K$ 件を選ぶ。初期値は現在の実装と同じ $K\le4$ とするが、S1/S4でoutcome-freeに再freezeする。

Pruned score $f_i$ はmagnitude controlおよびsecondary tie-breakとして記録するが、CEO-MESC primary rankingには単独使用しない。

### 7.7 Stage F: progressive certificate ladder

候補ごとに次を順番に行う。各段階でfailなら次へ進めない。

#### F0: exact algebra certificate

- generator relation
- constraint consistency
- native circuit semantics
- resource reduction

exact equivalenceが証明でき、target coefficientsを厳密にmapできる場合はF1/F2を省略してF3 independent validationへ進める。

#### F1: warm-start single-point probe

- OBS-mapped target coordinatesでcandidate energyを1回評価。
- $E_{probe}-E_s > \varepsilon_{probe}$ ならfull optimizerを起動しない。
- $\varepsilon_{probe}$ は $\varepsilon_E$ より厳しくし、calibration後にfreezeする。

#### F2: bounded full-ansatz reoptimization

- target-native coordinatesでBFGSを実行。
- mapped inverse Hessianをinitial Hessianとして使う。
- energy/gradient evaluationとiterationにhard capを置く。
- optimizer failure、NaN、cap overrunはcandidate rejectionまたはformal cap rejectionとする。

#### F3: independent acceptance certificate

- primary optimizer energy
- direct Hamiltonian expectationによるindependent energy
- parent statevectorとQiskit circuit statevectorのfidelity
- constraint residual
- KKT/gradient infinity norm
- physical/structural resource recount parity

既存の基準を初期contractとする。

\[
E_c-E_{budget\ reference}\le10^{-4}\ \mathrm{Ha}
\]

\[
|E_c-E_c^{ind}|\le10^{-10}\ \mathrm{Ha}
\]

\[
F(\psi_c,\psi_c^{ind})\ge1-10^{-10}
\]

\[
\|r_{constraint}\|_\infty\le10^{-10},\qquad
\|g_c\|_\infty\le10^{-8}.
\]

さらにresource policyを満たすことを要求する。

### 7.8 Stage G: commit / rollback

accepted候補だけをatomic commitする。transaction snapshotは次を含む。

- ansatz structure
- coefficients
- energy
- gradient
- inverse Hessian
- statevector
- resources
- work ledger
- RNG state
- metadata/identity digests

例外、cap rejection、validation failureでは全component digest一致を確認してrollbackする。partial artifactは消さず、append-only incident evidenceとして保存する。

### 7.9 Stage H: conditional rebuild

accepted childに対してcatalogを再構築し、次を比較する。

- block topology digest
- candidate equivalence-class set
- proposed physical-state set
- resource-Pareto representatives

次の場合だけ新roundを許可する。

1. 新しいsemantic candidateが1件以上生じた。
2. 新しいphysical stateが1件以上生じた。
3. 前roundの全rejected candidateだけに戻っていない。
4. remaining measurement/work capが十分。

catalogが不変なら即停止する。これがmatched-workで観測されたfixed/sequential同一性から導いた主要改善である。

### 7.10 擬似コード

```text
CEO_MESC(source, problem, caps, tolerances):
    audit_source_or_fail_closed(source, problem)
    runtime <- immutable snapshot(source)
    measured_state_cache <- empty three-ID cache

    exact_catalog <- enumerate_registered_exact_rewrites(runtime)
    exact_catalog <- verify_semantics_and_physical_resources(exact_catalog)
    for candidate in deterministic_exact_order(exact_catalog):
        if exact_certificate(candidate):
            commit_exact(candidate)

    previous_catalog_digest <- null
    while remaining_caps_are_sufficient():
        catalog <- enumerate_current_structural_candidates(runtime)
        catalog <- remove_nonphysical_resource_candidates(catalog)
        catalog <- semantic_and_physical_state_deduplicate(catalog)

        if digest(catalog) == previous_catalog_digest:
            return runtime, STOP_CATALOG_UNCHANGED

        ranked <- pareto_rank(
            OBS_loss_with_quality_margin,
            physical_resource_gain,
            predicted_validation_cost
        )
        attempts <- frozen_top_k(ranked)

        committed <- false
        for candidate in attempts:
            if not warm_start_probe_passes(candidate):
                record_rejection(candidate)
                continue
            result <- bounded_full_ansatz_reoptimization(candidate)
            if independent_acceptance_certificate(result):
                atomic_commit(result)
                committed <- true
                break
            exact_rollback_and_record(result)

        if not committed:
            return runtime, STOP_NO_SAFE_COMPRESSION

        previous_catalog_digest <- digest(catalog)
        if not child_catalog_materially_changes(runtime):
            return runtime, STOP_NO_NEW_CANDIDATE

    return runtime, STOP_WORK_CAP
```

---

## 8. Measurement Costの再定義と低overhead設計

### 8.1 絶対に分ける3種類のcost

1. **Physical circuit resources**
   - CNOT、CNOT depth、total depth、parameters、blocks。
2. **Quantum measurement work**
   - energy expectation、ansatz gradient、pool gradient、HVP、shots、measurement groups。
3. **Classical/software work**
   - candidate generation、matrix verification、resource recount、serialization、wall time。

これらを1つの`total_registered_work`へ単純加算してMeasurement Costと呼ばない。

### 8.2 CEO paper-compatible lower-bound cost

paper-compatible reportでは、少なくとも次を別々に記録する。

- $N_E$: direct energy-evaluation equivalents
- $N_{g,d}$: dimension $d$ のfull ansatz gradient evaluations
- $N_{pool}$: pool-gradient rounds
- $C_{OGM}(P,H,n)$: OGM groupingによるpool-gradient cost
- $N_{opt}$: optimizer starts/iterations
- Hamiltonian grouping factor $\hat R$

CEO論文とHessian recycling論文に合わせ、parameter-shift modelでは長さ $d$ のgradientを概念的に $2d$ energy-evaluation equivalentsとして扱う。ただしanalytic statevector gradientを実行したからといって量子hardware costが0とはしない。

暫定式は

\[
M_{eq} = N_E
       + 2\sum_{j\in\mathrm{ansatz\ gradients}} d_j
       + \sum_{r\in\mathrm{pool\ rounds}} C_{OGM,r}
\]

とし、CEO論文のexact definitionとsupplementをS1で再実装・validationする。

### 8.3 end-to-end cost

圧縮だけを安く見せないため、

\[
M_{total}=M_{CEO*\ growth}+M_{compression}
\]

をprimaryとする。compression overhead ratioは

\[
\rho_M = \frac{M_{compression}}{M_{CEO*\ growth}}
\]

である。

targetは暫定的に、

- LOW: $\rho_M\le0.10$
- MEDIUM: $\rho_M\le0.25$
- HIGH: $\rho_M\le0.50$

とする。最終値はS1でsource Measurement Costを再構築してから、candidate outcomeを見る前にfreezeする。

### 8.4 shotsを含むcost

finite-shot extensionでは、各measurement group $g$ のshots $S_g$ を保存し、

\[
M_{shots}=\sum_g S_g
\]

を直接報告する。variance-aware allocationとgrouping strategyを固定する。noiseless exact結果からshotsを推定してperformance claimを作らない。

### 8.5 measurement reuse

reuse keyは最低でも次を含む。

- StatePreparationID
- ProblemID
- canonical Pauli observable
- estimator version
- backend context
- shots/noise context

MeasurementContextIDが異なっても、上記semantic keyが完全一致する同一Pauli expectationなら、source contextをledgerに残して再利用できる。ただし、coefficient再最適化後のstateは別StatePreparationIDなので再利用不可である。

### 8.6 compressionで回路が短くなってもshot数が自動で減らない理由

CNOT/depth削減はstate preparation errorや実行可能性を改善し得るが、同じHamiltonian expectationを同じ統計誤差で推定するshot数を直接減らすとは限らない。したがって本研究は、

- circuit resource reduction
- compression measurement overhead
- finite-shot variance/noise benefit

を別claimとして検証する。

### 8.7 amortization

同一optimized stateを何度も測定する用途では、圧縮costを償却できる可能性がある。

\[
M_s(K)=M_{build,s}+K M_{eval,s}
\]

\[
M_c(K)=M_{build,s}+M_{compress}+K M_{eval,c}
\]

break-even回数は、$M_{eval,s}>M_{eval,c}$ の場合だけ

\[
K^*=\frac{M_{compress}}{M_{eval,s}-M_{eval,c}}
\]

である。noiseless計算で $M_{eval,s}=M_{eval,c}$ なら、回路短縮だけから測定回数の償却を主張しない。

---

## 9. 比較設計

### 9.1 primary comparators

次期studyでは比較手法を必要最小限にする。

1. **Immutable CEO***
   - 同一checkpoint。compression work 0のbaseline。
2. **Physical magnitude control**
   - 最小 $\theta_i^2$ をphysical deletionし、full reoptimization/recount。
3. **Pruned-inspired position–magnitude control**
   - paper式を独立実装。CEO block-aware physical reductionを必須化。
4. **CEO-MESC exact-only**
   - exact algebraic rewriteだけ。quantum measurement overhead 0を狙う。
5. **CEO-MESC fixed-catalog**
   - progressive certificate、accepted child後もsource whitelist内だけ。
6. **CEO-MESC conditional-rebuild**
   - catalog digestが変化したときだけrebuild。

既存V4.1 One-Shotは0/15 completedだったため、primary methodから外し、exact-compatible jointだけsecondary ablationとして残す。

### 9.2 matched-work contract

全methodで固定するもの:

- source checkpoint
- chemistry/problem identity
- energy budget
- optimizerとtolerances
- source Hessian
- paper-era resource counter
- candidate-energy cap
- gradient-component cap
- optimizer-start/iteration cap
- statevector/recount cap
- random seed/thread environment

method固有の仕事を隠すため、単一scalar capだけを使わない。componentwise capを維持する。

### 9.3 development/calibration/validationの分離

#### Calibration

- H2: identity、exact rewrite、measurement reuse、rollbackのsmoke test。
- H4: known hard/no-compression case。false acceptanceを検出する。

#### Development

- LiH 3.0 Å
- H6 1.5 Å
- H6 3.0 Å
- BeH2 3.0 Å

これらは既にoutcomeを観測しているため、confirmatory/generalization evidenceには使わない。

#### Geometry-held-out validation

- LiH 1.5 Å
- BeH2 1.3 Å

CEO/Hessian papersと整合するgeometryを優先し、thresholdはdevelopment後に変更しない。これはmolecule-held-outではなくgeometry-held-outであると明記する。

#### Molecule-held-out validation

- H2O 3.0 Å（Pruned-ADAPT benchmarkとの接続）
- N2 2.0 Å（Pruned-ADAPT benchmarkとの接続）

active space、basis、frozen orbitalsはPruned paper条件とCEO source生成の実行可能性を照合して事前登録する。異なるbasis/active-spaceの数値を直接同じtableで優劣比較しない。

### 9.4 FCI使用規則

FCIは次にしか使わない。

- 全frozen candidate execution終了後のoffline reporting
- chemical accuracy判定
- absolute error figure

FCIをranking、threshold、budget、retry、method choice、winner selectionに使わない。

---

## 10. 成功条件

### 10.1 correctness gate

1件でも次があればperformance studyを停止する。

- source/target identity mismatch
- noncanonical coefficient bytes
- physical/structural resource recount mismatch
- independent energy disagreement
- state fidelity failure
- KKT/constraint failure
- ledger/counter reconciliation failure
- incomplete rollback
- queue substitution
- post-outcome protocol mutation

### 10.2 scientific non-inferiority

accepted candidateは、primaryに

\[
E_c-E_s\le10^{-4}\ \mathrm{Ha}
\]

を満たす。さらにoffline reportingでchemical accuracy

\[
|E_c-E_{FCI}|<1.5936\times10^{-3}\ \mathrm{Ha}
\]

を保存したかを報告する。

### 10.3 resource target

現行matched-work V5平均（CNOT 3.952%、total depth 4.490%）を超えることを最低目標とする。

- **Minimum progress target:** valid paired medianでCNOTまたはtotal depth 5%以上。
- **Primary practical target:** valid paired medianでCNOT 10%以上かつtotal depth 10%以上。
- **Strong target:** preregistered development 4 cases中2件以上でCNOTまたはtotal depth 20%以上、かつ少なくとも1件はH6。

これらはalgorithmを採択するためのtargetであり、達成しなかった結果も保存・公表する。

### 10.4 measurement-efficiency target

- exact-only pass: candidate quantum measurement 0、optimizer start 0。
- full CEO-MESC: median $\rho_M\le0.25$ をprimary design target。
- same resource pointに対し、現行V5よりenergy/gradient/optimizer primitivesを減らす。
- conditional rebuildはfixed-catalogよりaccepted resource pointが改善しない限り、追加workを正当化しない。

### 10.5 generalization target

- geometry-held-out 2 casesをthreshold変更なしで実行。
- molecule-held-out 2 casesをthreshold変更なしで実行。
- success caseだけでなく`NO_SAFE_COMPRESSION`もdenominatorに含める。
- 少なくとも1 molecule-held-out caseでverified physical reductionが得られなければ、一般性claimを行わない。

---

## 11. 実装ステップ

### S0 — 現状archiveと文書整合性修正

**目的:** 完了済みmatched-work結果を不変化し、次期studyと混同しない。

作業:

- current HEAD、90-item queue digest、S12 report digest、figures digestをrelease manifestへ固定。
- current READMEが古いpre-calibration No-Goを表示しているdocumentation driftを修正する。
- historical V4.1/V5/V5.1を`development-best-found` namespaceに固定。
- new branch `research/ceo-mesc-v1`を作る。
- existing artifactを書換えないCI testを追加。

成果物:

- `docs/CEO_MESC_RESEARCH_PLAN.md`
- `artifacts/ceo-mesc/s0-baseline-freeze-v1.json`
- annotated tag for matched-work final baseline

GO条件:

- clean cloneでS12 artifact hashが一致。
- README/claim boundary/current release statusが一致。

### S1 — paper-compatible Measurement Cost再構築

**目的:** registered workをCEO論文のMeasurement Costと混同しない比較基盤を作る。

作業:

- CEO paper Methods/SIからenergy-equivalent formulaをspec化。
- OGM pool-gradient cost、ansatz gradient cost、HR optimizer costを分離。
- $\hat R$ grouping metricを実装。
- LiHの論文値GSD 50,468、CEO* 560を直接再現できるか監査。
- 完全再現できなければ、再現可能部分とmissing paper-era telemetryを明記し、tiered metricへ移行。

成果物:

- `measurement-cost-contract-v1.json`
- primitive-to-paper crosswalk
- LiH reproduction/refusal report

GO条件:

- 全primitiveに二重計上がない。
- analytic simulator callをmeasurement 0にしない。
- registered workとMeasurement Costを別fieldで出力。

### S2 — redundancy mechanism census

**目的:** 結果を見ずに、各sourceにどの変換が構造的に存在するかを調べる。

作業:

- LiH/H6/BeH2/H4の全CEO blockをfamily、rank、selection iteration、support、adjacencyで分類。
- exact generator relation、fusion、rank demotion候補を全列挙。
- historical accepted candidateがcatalog内に存在するか確認。
- matched-workで選ばれなかった理由を、absence/ranking/cap/acceptanceに分解。

成果物:

- per-case candidate census
- mechanism confusion matrix
- historical-to-current candidate identity map

GO条件:

- candidate countが決定論的。
- duplicate semantic/physical statesが分離。
- energy/FCIをcensusに使わない。

### S3 — exact-first transformation registry

**目的:** 量子測定なしに受理可能な変換familyを確立する。

作業:

- exact fusion、MVP→QE、MVP→OVP、constituent removalをtyped registry化。
- generator matrix equality、native circuit equality、random-state/property tests。
- orientation、normalization、qubit orderingの差をcanonicalize。
- exact変換後resource recount。

GO条件:

- exact certificateのfalse positive 0。
- sourceとtarget unitary/stateのtolerance contractを満たす。
- circuit metricが減らない候補をsuccessにしない。

### S4 — Hessian qualityとOBS predictor

**目的:** magnitudeより良いoutcome-blind rankingを作る。

作業:

- single-coordinate OBS formulaとgeneral constraint formulaを独立実装。
- direct quadratic calculationとのparity test。
- Hessian symmetrization、regularization、condition-number gate。
- prediction uncertainty margin。
- historical dataではcalibrationのみ行い、validation thresholdはfreeze。

評価:

- Spearman ranking correlation
- top-K recall of accepted candidates
- false-safe rate
- calibration curve of predicted vs actual ΔE

GO条件:

- OBS品質不良時にfail-openしない。
- actual outcomeをcandidate ID生成やtie-breakに入れない。

### S5 — progressive certificate ladder

**目的:** full optimizerへ送るcandidate数を減らす。

作業:

- F0 exact check
- F1 one-energy warm-start probe
- F2 bounded BFGS
- F3 independent validation
- 各段階のcounter/ledger integration
- fail/cap/interrupt/resume test

GO条件:

- rejected F1 candidateでoptimizer start 0。
- optimizer `nfev/njev/nit`とledger parity。
- interruption後にsame-item deterministic resume。

### S6 — conditional rebuild

**目的:** fixedとsequentialが同じ時の無駄を除く。

作業:

- child catalog digest比較。
- new semantic/physical state count。
- stale candidate invalidation。
- unchanged catalog early stop。
- exact-only post-pass。

primary ablation:

- fixed-catalog
- always-rebuild（historical control）
- conditional-rebuild

GO条件:

- catalog不変ならalways-rebuildより少ないwork。
- catalog変化時のみnew candidateをadmit。
- method semanticsの差がcatalog policyだけ。

### S7 — measurement reuse

**目的:** 同一state・observableの重複測定を安全に除く。

作業:

- three-layer identityをproduction ledgerへ接続。
- exact Pauli cache OFF/ON parity。
- energy/gradient observable overlap census。
- shot-based record schema設計。
- cross-state/cross-Hamiltonian/cross-backend reuse拒否test。

GO条件:

- reuse ON/OFFでenergy/gradient/decisionが一致。
- cache hitは新しいmeasurementとしてcountしないが、request eventは残す。
- paper Measurement Costのsavingをactual hitからだけ算出。

### S8 — H2/H4 calibration

**目的:** 低costでcorrectnessとfalse acceptanceを確認する。

作業:

- H2 exact rewrite positive control。
- H4 no-safe-compression negative control。
- LOW/MEDIUM/HIGH cap。
- repeated deterministic execution。

GO条件:

- H2でknown exact caseを受理。
- H4をthreshold緩和で無理に成功させない。
- 全transaction/identity/counter test green。

### S9 — development matched-work

**対象:** LiH 3.0、H6 1.5、H6 3.0、BeH2 3.0。

作業:

- pre-outcome queue freeze。
- 6 comparator × 3 budgets。
- fixed order、componentwise caps。
- candidate outcome完了前にFCI reportingしない。

主要分析:

- historical best-foundとのgap decomposition。
- current V5に対するresource/work差。
- exact-only寄与。
- conditional rebuild寄与。

### S10 — geometry-held-out validation

**対象:** LiH 1.5、BeH2 1.3。

条件:

- S9後にalgorithm/threshold変更禁止。
- source生成条件をCEO paperと揃える。
- development resultを見てbudgetを選ばず、3 budget全てを事前固定。

### S11 — molecule-held-out validation

**対象:** H2O 3.0、N2 2.0。

条件:

- chemistry specificationを事前固定。
- Pruned paperとbasis/active spaceが違う場合は直接数値比較しない。
- HPC runtime/capを事前見積りし、途中で科学条件を変更しない。

### S12 — aggregation、figures、release

必須table:

1. Energy/FCI error
2. Parameters/blocks
3. CNOT/CNOT depth/total depth
4. primitive work counters
5. paper-compatible Measurement Cost
6. exact-only vs heuristic contribution
7. terminal statusを含む全denominator

必須figure:

- energy error vs CNOT
- energy error vs total depth
- energy error vs paper Measurement Cost
- CNOT reduction vs compression overhead
- candidate funnel（generated→exact→prefilter→probe→optimizer→accepted）
- predicted ΔE vs actual ΔE calibration
- per-case Pareto front
- fixed/always/conditional rebuildのwork trajectory

release条件:

- clean recursive clone
- all tests greenまたはstrictly documented immutable xfail
- artifact hash manifest
- exact command/environment
- negative resultsを削除しない
- claim boundaryをmachine-readableに固定

---

## 12. 学術的透明性

### 12.1 preregistration

次をoutcome前にhash固定する。

- source list
- method list
- candidate families
- ranking rule
- tie-break
- energy/resource tolerances
- work caps
- stopping rule
- statistical summaries
- figures
- success criteria

### 12.2 status-aware reporting

各queue itemは次のどれかにする。

- `COMPLETED`
- `ALGORITHM_REJECTED`
- `CAP_REJECTED`
- `FAILED_ENGINEERING_PRESERVED`

missing/rejectedを0 reductionとして補完せず、completed-only summaryには必ずpaired nを付ける。terminal-rate tableを同時掲載する。

### 12.3 developmentとconfirmation

- LiH/H6/BeH2/H4は既知development。
- 新geometryはgeometry-held-out。
- H2O/N2はmolecule-held-out。
- validation後にalgorithmを変更した場合、その結果は新versionのdevelopmentへ戻す。

### 12.4 negative result

次も価値ある正式結果とする。

- safe compressionなし
- exact rewrite applicabilityなし
- OBSがmagnitudeを上回らない
- measurement overheadがresource gainを上回る
- conditional rebuildがalways-rebuildと同じ

---

## 13. システムエンジニアリング設計

### 13.1 immutable provenance

- upstream CEO* commit pin
- parent provenance submodule pin
- environment lock digest
- queue digest
- source checkpoint digest
- executor source digest
- measurement contract digest

### 13.2 append-only semantic ledger

各eventに次を保存する。

- global sequence
- previous digest
- queue item ID
- method ID
- candidate intent ID
- proposed physical state ID
- StatePreparationID/ProblemID/MeasurementContextID
- operation
- units
- success/failure
- evidence digest

### 13.3 componentwise cap

- candidate generations
- unique semantic candidates
- unique physical states
- symbolic checks
- sparse/dense exponential operations
- rewrite verifications
- resource recounts
- energy evaluations
- gradient vectors/components
- HVP
- optimizer starts/iterations
- statevector recomputations

unknown operationは0扱いせず拒否する。

### 13.4 transaction safety

- atomic artifact creation
- single terminal record
- failed attemptのpartial evidence保存
- exact rollback digest
- retry authorizationをsame-item/same-sourceへbinding
- SIGTERM/interruption recovery
- cap rejection前のstate expansion禁止

### 13.5 CI

test layers:

1. pure unit tests
2. property-based algebra tests
3. H2/H4 integration
4. frozen artifact verification
5. clean recursive clone
6. exact-tag CI
7. live GitHub checksは科学suiteと分離

外部GitHub 503でscientific regressionと誤判定しない一方、final release gateではrepository verification statusを明示する。

---

## 14. リスクとmitigation

| Risk | 影響 | 早期検出 | Mitigation |
|---|---|---|---|
| inverse Hessianがstale/indefinite | OBS誤順位 | quality gate | uncertainty margin、fallback、acceptance独立化 |
| exact relationの実装誤り | false lossless claim | matrix/circuit/state parity | two-route verification、property tests |
| parameter削除が回路削減にならない | fake compression | full QASM recount | resource prefilter |
| aggressive threshold | premature failure | H4/BeH2 calibration | outcome-free freeze、no retune |
| delete/re-add loop | work explosion | candidate identity history | post-growth no-readd、rollback |
| always rebuildが無駄 | measurement/classical overhead | catalog digest | conditional rebuild |
| cache contamination | incorrect energy/gradient | three-layer identity | exact semantic key、cross-context rejection |
| best-found cherry-picking | inflated performance | frozen queue/status table | all denominators、no retrospective winner |
| FCI leakage | selection bias | execution chronology audit | offline only |
| basis/active-space mismatch | invalid literature comparison | ProblemID | separate table/claim |
| compiler confounding | fake CNOT/depth gain | backend digest | paper-era counter固定 |
| GPU/CPU numerical ordering | nondeterminism | thread/environment digest | deterministic BLAS/thread policy |
| storage/interruption | evidence loss | preflight/capacity gate | durable checkpoint、append-only ledger |

---

## 15. なぜこの計画は現実的か

### 15.1 新しいVQEをゼロから作る計画ではない

すでに次が実装済みである。

- official CEO* source reconstruction
- DVG block recovery/candidate enumeration
- exact candidate composition
- OBS warm start
- parent BFGS optimizer
- independent energy/state/gradient checks
- paper-era full circuit recount
- atomic transaction/rollback
- three-layer identity
- semantic/physical deduplication
- componentwise caps
- persistent execution/resume
- 90-item queue completionとS12 aggregation/figures

主要コード:

- [`parent_native_candidate_adapter.py`](../src/v5_final/parent_native_candidate_adapter.py)
- [`parent_native_rewrite.py`](../src/v5_final/parent_native_rewrite.py)
- [`parent_native_executors.py`](../src/v5_final/parent_native_executors.py)
- [`parent_native_execution_services.py`](../src/v5_final/parent_native_execution_services.py)
- [`parent_native_work_accounting.py`](../src/v5_final/parent_native_work_accounting.py)
- [`measurement_reuse.py`](../provenance/dvg-obs-ceo/src/dvg_obs_ceo/measurement_reuse.py)

次期実装の中心は、これらを作り直すことではなく、exact-first pass、progressive probe、conditional rebuild、paper-compatible measurement ledgerを追加することである。

### 15.2 large-reductionの存在証拠とmatched-workの限界証拠が両方ある

- LiH/BeH2 historical resultは、研究対象が空ではないことを示す。
- 90-item resultは、現在のmethodをそのまま増やすだけでは大幅改善しないことを示す。

この2つがあるため、blindなmethod追加ではなく「large reductionが低budgetで再発見されない理由」を分解できる。

### 15.3 quantum-costを増やさない部分が明確

- exact generator/circuit verificationはclassical simulator側で行う。
- source inverse Hessianは既存HR artifactを再利用する。
- resource prefilterはcandidate energy前に行う。
- rejected warm-start probeはfull optimizerを起動しない。
- unchanged catalogではrebuildしない。
- same-state Pauli expectationだけをreuseする。

したがって「追加costが必ず小さい」とはまだ言えないが、**どの処理が量子測定を増やし、どの処理が増やさないかを設計時点で分離できる**。

### 15.4 先行研究との位置づけが明確

- Pruned-ADAPT: inexpensive magnitude/position pruning during growth。
- thesis term removal: energy-contribution removal with full reoptimization。
- Hessian recycling: already-paid curvature information。
- CEO-MESC: CEO algebra、physical resource change、curvature ranking、strict certificate、measurement capを統合したpost-growth compression。

単なるPruned-ADAPTの再実装でも、CEO*のparameter pruningでもない。

### 15.5 PRA-level contributionへつながる問いがある

主張の中心を「LiHで46%減った」だけにせず、

> When and why does a CEO block that was useful during adaptive growth become structurally redundant after later operators are added and the full ansatz is reoptimized?

とする。

この問いなら、positive case、negative H4 case、topology、curvature、measurement overheadを1つの科学的物語にできる。

---

## 16. 予想される論文構成

1. Introduction: CEO*の成果とpost-growth redundancy問題
2. CEO structural representation and exact rewrite algebra
3. Curvature-aware measurement-efficient compression
4. Three-layer identity、certificate、matched-work protocol
5. Mechanism census on LiH/H6/BeH2/H4
6. Matched-work resource/accuracy/measurement results
7. Held-out geometry/molecule validation
8. Negative results and applicability boundary
9. Discussion: break-even、hardware/noiseへの未検証範囲

primary figures:

- Fig. 1: CEO-MESC algorithm and certificate ladder
- Fig. 2: CEO block redundancy mechanism
- Fig. 3: candidate funnel and work accounting
- Fig. 4: energy–CNOT–Measurement Cost Pareto
- Fig. 5: per-system reduction and terminal rates
- Fig. 6: predictor calibration
- Fig. 7: held-out validation

---

## 17. 実行優先順位

### 最優先

1. S0 documentation/release alignment
2. S1 paper Measurement Cost reconstruction
3. S2 candidate/mechanism census
4. S3 exact-first registry

### 次点

5. S4 OBS quality/ranking
6. S5 progressive certificate
7. S6 conditional rebuild
8. S7 measurement reuse

### 性能実験

9. S8 H2/H4 calibration
10. S9 known development matched-work
11. S10/S11 held-out validation
12. S12 final aggregation/release

S1–S7がgreenになる前に大規模molecular performance executionへ進まない。ただし、以前のように無期限のinfrastructure workへ脱線しないため、各stageには「このstageが答える科学的問い」と「終了条件」を必ず置く。新しい安全機能は、identified riskまたはrelease requirementに直接対応するものだけ追加する。

---

## 18. 参考文献・GitHub

### 査読論文

1. M. Ramôa et al., [Reducing the resources required by ADAPT-VQE using coupled exchange operators and improved subroutines](https://www.nature.com/articles/s41534-025-01039-4), npj Quantum Information 11, 86 (2025).
2. M. Ramôa et al., [Reducing measurement costs by recycling the Hessian in adaptive variational quantum algorithms](https://doi.org/10.1088/2058-9565/ad904e), Quantum Science and Technology 10, 015031 (2025).
3. P. G. Anastasiou et al., [TETRIS-ADAPT-VQE](https://journals.aps.org/prresearch/abstract/10.1103/PhysRevResearch.6.013254), Physical Review Research 6, 013254 (2024).
4. N. Vaquero-Sabater, A. Carreras, D. Casanova, [Pruned-ADAPT-VQE](https://pubs.acs.org/doi/10.1021/acs.jctc.5c00535), Journal of Chemical Theory and Computation 21, 8720–8728 (2025).
5. H. R. Grimsley et al., [An adaptive variational algorithm for exact molecular simulations on a quantum computer](https://www.nature.com/articles/s41467-019-10988-2), Nature Communications 10, 3007 (2019).
6. B. Hassibi and D. G. Stork, [Second Order Derivatives for Network Pruning: Optimal Brain Surgeon](https://mlanthology.org/neurips/1992/hassibi1992neurips-second/), NeurIPS 1992.

### arXiv・学位論文

7. P. G. Anastasiou et al., [How to really measure operator gradients in ADAPT-VQE](https://arxiv.org/abs/2306.03227), arXiv:2306.03227.
8. A. Nykänen et al., [Mitigating the measurement overhead of ADAPT-VQE with optimised informationally complete generalised measurements](https://arxiv.org/abs/2212.09719), arXiv:2212.09719.
9. M. Ramôa, [Ansätze for Noisy Variational Quantum Eigensolvers](https://arxiv.org/abs/2212.04323), MSc thesis, arXiv:2212.04323.
10. N. Vaquero-Sabater et al., [Pruned-ADAPT-VQE preprint and Supporting Information](https://arxiv.org/abs/2504.04652), arXiv:2504.04652.

### 公開コード

11. [mafaldaramoa/ceo-adapt-vqe](https://github.com/mafaldaramoa/ceo-adapt-vqe) — CEO*、Hessian recycling、TETRISを含む公式simulation code。
12. [mafaldaramoa/ceo-adapt-vqe at pinned commit a3f89d0](https://github.com/mafaldaramoa/ceo-adapt-vqe/commit/a3f89d03e6a03c89767d3cf8ee7657a57653dda0) — 本研究の上流固定点。
13. [abelcarreras/VQEmulti](https://github.com/abelcarreras/VQEmulti) — VQE/ADAPT codebase。
14. [VQEmulti pruning branch](https://github.com/abelcarreras/VQEmulti/tree/final_distribution_func) — Pruned-ADAPT実装を含むbranch。
15. [VQEmulti `prune_adapt.py`](https://github.com/abelcarreras/VQEmulti/blob/final_distribution_func/vqemulti/prune_adapt.py) — decision factor、dynamic threshold、delete処理。
16. [mafaldaramoa/VQE](https://github.com/mafaldaramoa/VQE) — MSc thesisのoperator removal/conservative growth notebook code。
17. [Reimangod/v5-matched-work-study](https://github.com/Reimangod/v5-matched-work-study) — 本projectのmatched-work、identity、ledger、executor、S12 evidence。

---

## 19. 最終判断

この計画は現実的である。ただし、現実的である理由は「必ずLiHで再び約50%削減できる」からではない。

現実的な理由は次である。

1. 大幅削減が存在したdevelopment evidenceがある。
2. 現行matched-workの限界が定量化されている。
3. 先行研究はsmall/position-aware pruningが低追加costで働く場合を示している。
4. CEO*は逆Hessianをすでに持ち、追加測定なしのranking情報に使える。
5. exact rewriteは量子測定を増やさずに回路を変えられる。
6. current repositoryには、候補生成、再最適化、独立validation、resource recount、identity、rollback、matched-work executionの大部分がすでにある。

一方で、次は未証明である。

- 大幅削減の一般性
- measurement overhead 25%以内
- exact fusionの十分な出現頻度
- OBS rankingのmagnitudeに対する優位性
- held-out moleculeでの有効性
- finite-shot/noisy hardware上のbenefit

したがってCEO-MESCの研究価値は、結果を保証することではなく、**CEO特有のpost-growth redundancyを、回路resource、energy accuracy、measurement overheadの3軸で初めて因果的・再現可能に評価すること**にある。

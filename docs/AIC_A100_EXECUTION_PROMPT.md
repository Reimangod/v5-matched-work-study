# Codex prompt — Execute the AIC A100 pilot autonomously

以下を新しいCodexチャットへ、そのまま貼り付けて使用する。

---

```text
次のrepositoryで、AIC A100 pilotを計画の最後までステップごとに実装・検証してください。

Repository:
/Users/rei/Documents/ceo-adapt-vqe/v5-matched-work-study

Primary execution plan:
/Users/rei/Documents/ceo-adapt-vqe/v5-matched-work-study/docs/AIC_A100_PILOT_PLAN.md

Related scientific plan:
/Users/rei/Documents/ceo-adapt-vqe/v5-matched-work-study/docs/CEO_MESC_RESEARCH_PLAN.md

Current CPU implementation references:
/Users/rei/Documents/ceo-adapt-vqe/v5-matched-work-study/src/v5_final/parent_native_execution_services.py
/Users/rei/Documents/ceo-adapt-vqe/v5-matched-work-study/src/v5_final/verifier_v2.py
/Users/rei/Documents/ceo-adapt-vqe/v5-matched-work-study/provenance/dvg-obs-ceo/pyproject.toml

Official AIC manual:
https://docs.keioaic.dev/slurm_user_manual

目的は「A100を使うこと」ではありません。次を順番に証明することです。

1. AIC上でQiskit GPU backendが本当にA100を使用している。
2. 現行CPU referenceと科学的に同じstate、energy、gradient、candidate ordering、accept/reject、resourceを返す。
3. GPU初期化、data transfer、Python/BFGSを含むend-to-end wall timeが実際に短くなる。
4. 条件を満たす場合だけ、将来のCEO structural-compression計算へA100を採用する。

重要な前提:

- 現行コードはQiskit Statevector、SciPy expm_multiply、OpenFermion、NumPy、PySCFを使うCPU実装です。
- SlurmでA100を確保するだけではGPU化したことになりません。
- 現行対象はH4 8 qubit、LiH/H6 12 qubit、BeH2 14 qubit程度なので、A100がend-to-endで速くならない可能性があります。
- speedupがなければ正式なengineering negative resultとして終了してください。
- A100によるwall-time短縮と、quantum Measurement Cost削減を混同しないでください。

作業開始時の必須監査:

1. `/Users/rei/.codex/RTK.md`を最初に読み、shell commandはその指示に従ってください。
2. repositoryのbranch、HEAD、worktree、submodule、untracked fileを確認してください。
3. userの既存変更と、次の計画文書を削除・上書きしないでください。
   - `docs/AIC_A100_PILOT_PLAN.md`
   - `docs/CEO_MESC_RESEARCH_PLAN.md`
4. 既存S11/S12、90-item queue、raw ledger、release、tag、historical artifactを変更しないでください。
5. repository visibilityを変更しないでください。
6. destructive Git command、force push、history rewriteを行わないでください。
7. 公式AIC manualは実行時点でもう一度確認してください。manual内には「1ユーザー最大2 GPU」と`--gres=gpu:4`のexampleが共存するため、exampleを信頼せずAIC上の`scontrol show partition`と`sinfo`をactual authorityにしてください。

Git方針:

- 作業branchは`infra/aic-a100-pilot-v1`としてください。
- 既存branchを直接改変しないでください。
- unrelated dirty changesがあれば保存し、混ぜないでください。
- P0、P2、P3、P4、P6の意味のある境界で小さくcommitしてください。
- test失敗中の状態をmainへmergeしないでください。
- remote pushが利用可能ならbranchをpushしてください。
- repository visibility、branch protection、既存tag/releaseは変更しないでください。

Artifact分離:

新しいartifactだけを次に保存してください。

artifacts/aic-a100-pilot-v1/
  p0-baseline/
  p1-aic-preflight/
  p2-gpu-smoke/
  p3-parity/
  p4-microbenchmark/
  p5-scientific-pilot/
  p6-decision/

予定コード:

src/aic_a100_pilot/
  environment.py
  aer_gpu_backend.py
  parity.py
  benchmark.py
  decision_gate.py

scripts/aic/
  a100_interactive_preflight.sh
  a100_smoke.sbatch
  a100_parity.sbatch
  a100_benchmark.sbatch

既存production executorからpilot codeをimportさせないでください。pilot側から既存CPU implementationをread-only referenceとして呼び出してください。

自律実行ルール:

- P0が終わったら監査し、GOならP1へ進んでください。
- P1が終わったらP2、P2が終わったらP3という順序で、P6の正式終端まで自動で進めてください。
- 各phaseで実装、unit test、integration test、artifact audit、Git差分監査を行ってください。
- 安全に修正可能なengineering blockerは修正して再検証してください。
- 同じblockerで無限にframeworkを追加しないでください。
- scientific semantics、tolerance、Qiskit generation、optimizer、candidate rule、queue、Measurement Cost contractの変更が必要なら、推測で変更せずformal No-Goで停止してください。
- userへ細かな実装判断を逐次質問せず、計画内の安全な判断は自律的に行ってください。
- SSH秘密鍵、GitHub token、usernameをlog/artifactへ出力しないでください。

P0 — Local CPU reference freeze:

- current commit/submodule/environmentを固定してください。
- H2、H4、LiH、H6、BeH2のうち、計画にある最小reference bundleを作ってください。
- state、energy、gradient、resource、candidate order、terminal decisionを保存してください。
- CPU reference結果を見た後にparity toleranceを恣意的に変えないでください。
- existing scientific artifactへのdiffがないことを証明してください。

P1 — AIC preflight:

- 既存SSH設定があれば`ssh nadeko`経由で接続を確認してください。
- 秘密鍵やSSH config内容を表示しないでください。
- 計算ノードへ直接常駐せず、Slurmの`srun`または`sbatch`を使ってください。
- 最初は`gpu-interactive`、A100 1枚、短時間でpreflightしてください。
- `scontrol show partition`、`sinfo`、`nvidia-smi`、Python、disk、memory、CUDA/driverを確認してください。
- A100が認識されない、allocationが不明、storage不足ならformal No-Goにしてください。
- 1 jobにつきGPUは1枚だけ要求してください。2 GPUまたはmulti-nodeは、このpilotでは使用しないでください。

P2 — GPU environment and real-GPU smoke:

- CPU reference venvとGPU pilot venvを分けてください。
- Python 3.10と現行Qiskit generationを維持してください。
- 現行Qiskit 0.43.3/Qiskit Aer 0.12.2相当と互換なGPU packageを試してください。
- GPU packageがAIC CUDA/driverと互換でない場合、Qiskitを勝手に最新版へupgradeしないでください。
- その場合は`NO_GO_A100_PINNED_ENVIRONMENT_INCOMPATIBLE`で停止してください。
- `AerSimulator(method="statevector", device="GPU", precision="double")`を明示してください。
- `available_devices()`、result metadata、`nvidia-smi`利用変化の3経路でreal GPU useを検証してください。
- CPU fallbackを成功扱いしないでください。

primitive route accountingを実装してください。

- N_gpu_statevector
- N_gpu_energy
- N_gpu_gradient_component
- N_cpu_statevector
- N_cpu_energy
- N_cpu_gradient_component
- N_cpu_fallback

独立validationだけがGPUで、optimizer objectiveがCPUのままなら、production GPU backendとは判定しないでください。P4へ進むにはoptimizerが実際に呼ぶenergy objectiveのGPU bindingが必要です。

P3 — CPU/GPU scientific parity:

次の順序で進めてください。

1. deterministic 4-qubit synthetic circuit
2. H2 exact positive control
3. H4 no-safe-compression negative control
4. LiH 3.0 Å representative candidate
5. H6 representative MVP-heavy candidate
6. BeH2 3.0 Å largest current state

前段がgreenになるまで次へ進まないでください。

比較対象:

- phase-aligned state
- energy
- gradient vector
- independent Hamiltonian expectation
- candidate semantic IDs
- candidate ordering/tie-break
- accepted/rejected decision
- optimizer terminal status
- rollback
- parameters/blocks/CNOT/CNOT depth/total depth

resource recountはCPU paper-era counterを共通使用してください。GPU simulator固有のtranspilationでresourceを数え直さないでください。

parity toleranceはP0でfreezeしたものを使ってください。初期目安は、既存contractがより厳しくない場合に限り、state aligned errorはcurrent verifier tolerance以下、energy absolute differenceは1e-10 Ha以下、max gradient differenceは1e-8以下、resource/terminal decision/candidate semantic orderingはexact equalityです。GPU結果を見てtoleranceを緩和しないでください。

fixed-coordinate parityが失敗したらoptimizerを実行しないでください。

P4 — Same-node microbenchmark:

- Mac CPU対A100だけを比較せず、同じAIC node上のCPU routeとGPU routeを比較してください。
- H4 8 qubit、LiH/H6 12 qubit、BeH2 14 qubitを測ってください。
- future break-even推定用にsynthetic 16/18/20 qubitを使って構いませんが、molecular performance evidenceに含めないでください。
- warm-upを分離し、各測定を最低5回繰り返してください。
- median、min、max、MADを保存してください。
- initialization、circuit construction、transfer、statevector、energy、gradient、candidate verification、optimizer、complete itemを分離してください。
- CPU core-hours、GPU-hours、peak CPU RSS、peak GPU memory、GPU utilizationを保存してください。

速度指標:

kernel_speedup = median_CPU_kernel / median_GPU_kernel
end_to_end_speedup = median_CPU_total / median_GPU_total

current 12--14 qubit productionへA100を採用するengineering gateは、全parity greenかつtarget molecular caseのmedian end-to-end speedupが1.20x以上です。1.20x未満なら小分子はCPUを維持してください。16--20 qubitだけ速い場合は`GO_A100_LARGE_SYSTEM_ONLY`候補にしてください。

P5 — Limited scientific pilot:

P0--P4が全てgreenの場合だけ実行してください。full 90-item studyは再実行しないでください。最大6 itemsに限定します。

- H2 exact positive
- H4 negative
- LiH exact-only
- LiH approximate
- H6 candidate-heavy
- BeH2 largest-state

CPU/GPU paired、同じsource、candidate list、caps、optimizer、counter、fixed orderで実行してください。GPUで速かったmethodだけ追加したり、CPU/GPUのbest resultを選んだりしないでください。pilot結果を既存molecular performance tableへ混ぜないでください。

P6 — Final decision:

最終statusは必ず次のいずれか一つにしてください。

- GO_A100_CURRENT_SYSTEM_BACKEND
- GO_A100_LARGE_SYSTEM_ONLY
- NO_GO_A100_NO_END_TO_END_SPEEDUP
- NO_GO_A100_NUMERICAL_NONPARITY
- NO_GO_A100_DECISION_NONPARITY
- NO_GO_A100_ENVIRONMENT_INCOMPATIBLE
- NO_GO_A100_OPERATIONAL_INSTABILITY

No-Goでも全attempt、failure、raw timingを削除しないでください。成功subsetだけを残さないでください。

Slurm safety:

- `gpu-interactive`はpreflightだけに使ってください。
- smokeは`gpu-short`、parity/benchmarkは`gpu-standard`を基本にしてください。
- actual partition limitが異なればofficial runtime stateへ合わせ、artifactへ記録してください。
- 1 caseごとにatomic artifactを作ってください。
- multiple jobsが同じledgerへ同時appendしないようにしてください。
- parallel化する場合はper-item ledgerとdeterministic aggregationを使ってください。
- SIGTERM、timeout、OOM、CUDA errorでpartial resultをsuccessにしないでください。
- stale jobを放置せず、終了時に`squeue`を監査してください。

Testing:

- unit tests
- CPU fallback detection
- H2/H4 integration
- LiH/BeH2 parity
- single-precision accidental-use rejection
- CUDA mismatch
- timeout/SIGTERM
- corrupted checkpoint
- backend-context mixing
- clean clone or reproducible environment audit
- existing S11/S12 artifact immutability

重要なシステム境界:

- StatePreparationIDとProblemIDが同じでも、CPUとGPUは異なるExecutionEnvironmentID/backend contextです。
- numerical outputのbyte identityをCPU/GPU間で必須にせず、preregistered scientific toleranceとdecision identityを使ってください。
- resource countはGPU hardware resourceではなく、既存paper-era logical circuit resourceです。
- A100 wall time、GPU-hours、Measurement Costを別fieldで報告してください。

作業中は各phase終了時に簡潔な監査結果を報告しながら、そのまま次phaseへ進んでください。60秒以上の長い処理では途中状況を知らせてください。Slurm job待機中もjob ID、state、elapsed time、GPU use、最新checkpointを定期確認してください。

最終報告に必ず含めるもの:

- 最終GO/NO-GO status
- branch、HEAD、remote sync、worktree
- AIC partition、Slurm job IDs
- A100 model、CUDA、driver、Qiskit/Aer versions
- CPU/GPU route counters
- parity table
- kernel/end-to-end speedup table
- raw artifact pathsとdigests
- tests
- failure/rollback
- existing 90-item artifactが不変である証拠
- 許可できるclaimと禁止されるclaim
- 次にA100を使うべきproblem size/workload

性能が上がらなくても、thresholdやprotocolを緩めず、正しいnegative resultとして完了してください。
```


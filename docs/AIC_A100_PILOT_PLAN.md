# AIC A100 Pilot Plan

## CPU/GPU parity and acceleration study for CEO structural compression

**Document status:** planning draft; no GPU scientific outcome has been generated  
**Scope:** engineering qualification of an A100 execution backend  
**Out of scope:** changing CEO*, changing the frozen 90-item matched-work result, or claiming measurement-cost reduction  
**Target repository:** `v5-matched-work-study`  
**Proposed branch:** `infra/aic-a100-pilot-v1`

---

## 1. 結論

このpilotの目的は、A100を使うこと自体ではなく、次の3点を順番に証明することである。

1. AIC上でGPU対応simulatorが本当にA100を使用している。
2. 現行CPU referenceと科学的に同じenergy、state、gradient、候補順位、accept/rejectを返す。
3. 初期化・転送・Python orchestrationを含むend-to-end wall timeが実際に短くなる。

いずれかを満たさなければ、A100をCEO-MBSCのprimary execution backendへ採用しない。

現行研究の12--14 qubit statevectorは小さいため、A100が速くならない可能性は高い。その場合も、

> A100は現行小分子には不適合であり、より大きなheld-out系またはbatched evaluationまで採用を延期する

という正式なengineering negative resultとして終了できる計画にする。

---

## 2. 学術的境界

### 2.1 A100が変えてよいもの

- classical simulation wall time
- candidate throughput
- statevector/expectation kernel runtime
- usable problem size
- CPU core-hoursとGPU-hoursの配分

### 2.2 A100が変えてはいけないもの

- Hamiltonian
- molecule/geometry/basis/active space
- ansatz structure
- operator pool
- coefficient bytes
- optimizer specification
- candidate generation rule
- ranking rule
- energy guard
- resource counter
- Measurement Cost accounting contract
- queue order
- success criterion

### 2.3 claim boundary

A100 pilotの結果から直接主張してよいのは次だけである。

- CPU/GPU parityの成否
- kernel別およびend-to-endのwall-time差
- GPU memory使用量
- GPU利用が確認できたか
- A100 backendを将来の実験へ採用できるか

次は主張しない。

- CEO-MBSCがCEO*より高性能
- A100によってMeasurement Costが減った
- A100によって量子hardwareのshotsが減った
- A100結果がCPU結果より正確
- pilot subsetだけに基づくmolecular generalization

GPU-hoursはMeasurement Costに加算せず、classical execution costとして別に報告する。

---

## 3. 現状監査

### 3.1 現行実装はCPU backendである

現行経路は主に次を使用する。

- `qiskit.quantum_info.Statevector`
- `scipy.sparse.linalg.expm_multiply`
- OpenFermion sparse operators
- NumPy/SciPy
- standard PySCF
- CPU版BFGSとPython orchestration

したがって、SlurmでA100を割り当てるだけではGPUは使用されない。

### 3.2 現行problem size

既存matched-work sourceの代表値は次である。

| Case | Qubits | State dimension | Complex128 statevector size |
|---|---:|---:|---:|
| H4 | 8 | 256 | 4 KiB |
| LiH | 12 | 4,096 | 64 KiB |
| H6 | 12 | 4,096 | 64 KiB |
| BeH2 | 14 | 16,384 | 256 KiB |

この規模では、GPU転送・kernel launch・Aer初期化のoverheadが計算本体より大きくなる可能性がある。

### 3.3 AICの利用条件

[AIC Slurmユーザマニュアル](https://docs.keioaic.dev/slurm_user_manual)では、計算ノードにA100が6枚あり、1ユーザーは全partition合計で最大2枚までとされている。

一方、同ページのexampleは`--gres=gpu:4`となっているため、exampleを上限の根拠にしない。実行直前に次でactual configurationを確認する。

```bash
scontrol show partition
sinfo
```

pilotでは常に1 jobあたり1 GPUだけを要求する。2 GPUを1 statevectorへ使用する試験は、1 GPUで明確なmemoryまたはruntime不足が確認されるまで行わない。

---

## 4. Backend設計

### 4.1 既存CPU referenceを変更しない

次の2経路を分離する。

```text
CPUReferenceBackend
  - current Qiskit Statevector
  - current SciPy/OpenFermion path
  - immutable reference semantics

A100ExperimentalBackend
  - Qiskit Aer GPU
  - device="GPU"
  - precision="double"
  - initially used only for independent statevector/energy parity
```

GPU backendを既存classへ直接埋め込まず、新しいadapterとして追加する。

### 4.2 環境version

現行research environmentは概ね次に固定されている。

- Python 3.10
- Qiskit 0.43.3
- Qiskit Aer 0.12.2相当
- NumPy 1.23.5
- SciPy 1.10.1
- PySCF 2.2.0

GPU pilotでは、CPU referenceと同じQiskit generationに対応するGPU packageを使う。GPU packageがAICのCUDA/driverと互換でない場合、Qiskitを無断でupgradeしない。

その場合のterminal statusは、

```text
NO_GO_A100_PINNED_ENVIRONMENT_INCOMPATIBLE
```

とする。modern Qiskitへのmigrationは別studyとして扱う。

### 4.3 ExecutionEnvironmentID

各結果へ最低限次を保存する。

- Git commit
- dirty/clean status
- Python version
- package lock digest
- Qiskit/Qiskit Aer version
- CUDA runtime
- NVIDIA driver
- GPU name/UUID
- simulator method
- precision
- CPU model
- allocated CPUs/memory
- thread environment
- Slurm job ID/partition/node
- random seed

CPUとGPUは同じ`StatePreparationID`と`ProblemID`を持ち得るが、異なる`ExecutionEnvironmentID`およびbackend contextを持つ。

---

## 5. Artifactとrepository分離

既存のS11/S12 artifact、queue、release、tagを変更しない。

新規artifact rootは次とする。

```text
artifacts/aic-a100-pilot-v1/
  p0-baseline/
  p1-aic-preflight/
  p2-gpu-smoke/
  p3-parity/
  p4-microbenchmark/
  p5-scientific-pilot/
  p6-decision/
```

予定する新規コードは次である。

```text
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
```

既存production executorからA100 pilot moduleをimportしない。pilotから既存CPU referenceをread-onlyで呼び出す。

---

## 6. P0 — Local baseline freeze

### 目的

AICへ移動する前に、比較対象となるCPU referenceを固定する。

### 作業

1. 新branch `infra/aic-a100-pilot-v1`を作る。
2. current commitとsubmodule commitを保存する。
3. worktreeの既存未追跡fileを混同しない。
4. H2/H4/LiH/BeH2の小さなreference bundleを生成する。
5. package/environment digestを保存する。

### Reference bundle

各caseで保存する。

- statevector norm
- canonical aligned-state digestまたはnumerical summary
- energy
- gradient
- resource vector
- one exact candidate result
- one approximate candidate result
- candidate order
- terminal decision

### GO条件

- reference testがlocalでgreen
- source digestが完全
- candidate outcomeを見てparity toleranceを変更していない
- existing scientific artifactへのdiffがない

---

## 7. P1 — AIC preflight

### 目的

AIC上のactual allocation、software、storageを結果取得前に確認する。

### 対話job

```bash
srun \
  --partition=gpu-interactive \
  --gres=gpu:1 \
  --cpus-per-task=8 \
  --time=00:30:00 \
  --pty bash
```

上記optionがsite policyで拒否された場合、値を勝手に推測せず` scontrol show partition `のactual configurationへ合わせる。

### 保存するpreflight

```bash
hostname
date -u
scontrol show job "$SLURM_JOB_ID"
nvidia-smi
nvidia-smi --query-gpu=name,uuid,driver_version,memory.total --format=csv
python3 --version
df -h
```

### GO条件

- allocated deviceがNVIDIA A100
- jobからGPUが1枚だけvisible
- Python 3.10 environmentを作成可能
- projectとartifact用容量が十分
- CPU/memory/time limitが記録済み
- shared accountやroot操作を使用していない

### NO-GO

```text
NO_GO_AIC_ACCESS
NO_GO_AIC_GPU_NOT_A100
NO_GO_AIC_RESOURCE_CONFIGURATION_UNKNOWN
NO_GO_AIC_STORAGE
```

---

## 8. P2 — GPU environment and smoke test

### 8.1 environment

CPU referenceとGPU pilotを別venvにする。

```text
venv-cpu-reference/
venv-aer-gpu-pilot/
```

research source、raw artifact、existing environmentを削除しない。

### 8.2 GPU smoke test

Qiskit Aerについて最低限次を確認する。

```python
from qiskit_aer import AerSimulator

backend = AerSimulator(
    method="statevector",
    device="GPU",
    precision="double",
)

assert "GPU" in backend.available_devices()
```

さらに4-qubit deterministic circuitを実行し、result metadataと`nvidia-smi`の両方からGPU利用を確認する。

### 8.3 false GPU successを防ぐ

次はsuccessと認めない。

- SlurmでA100を確保しただけ
- `CUDA_VISIBLE_DEVICES`が存在するだけ
- CPU fallbackで結果が得られただけ
- importだけ成功した
- GPU memory/utilization evidenceがない

### 8.4 GPU path coverage

独立statevector validationだけがGPUで、optimizer objectiveがCPUのままなら、A100 execution backendとは呼ばない。primitiveごとにrouteを記録する。

| Primitive | Initial pilot route | Production adoption requirement |
|---|---|---|
| circuit construction | CPU | CPUのままでよい |
| statevector evolution | GPU candidate | GPU bindingとparityが必要 |
| Hamiltonian expectation | GPU candidate | optimizerで使うactual routeのGPU bindingが必要 |
| gradient | CPUまたはGPU candidate | actual registered ruleとcounter parityが必要 |
| sparse generator verification | CPU | CPUのままでよい |
| resource recount | CPU | paper-era counterを維持 |
| PySCF/source generation | CPU | pilot対象外 |
| BFGS orchestration | CPU | objective/gradient kernelだけGPU化可能 |

最低限次のcounterを保存する。

```text
N_gpu_statevector
N_gpu_energy
N_gpu_gradient_component
N_cpu_statevector
N_cpu_energy
N_cpu_gradient_component
N_cpu_fallback
```

registered GPU operationが暗黙にCPUへfallbackした場合、そのitemを速度successに含めない。unknown routeもGPU successとして扱わない。

P4のend-to-end benchmarkへ進むには、測定対象となるoptimizerのactual energy objectiveがGPU routeへ結合されていなければならない。独立validation routeだけのGPU化はP3 parity evidenceには使えるが、production acceleration evidenceには使えない。

### GO条件

- `available_devices()`がGPUを返す
- result metadataがGPU routeを示す
- A100のmemory/utilization changeが観測される
- double precisionを使用
- deterministic circuitがCPU referenceと一致
- primitive route counterがreconcileする

### NO-GO

```text
NO_GO_A100_GPU_NOT_USED
NO_GO_A100_CPU_FALLBACK
NO_GO_A100_DOUBLE_PRECISION_UNAVAILABLE
NO_GO_A100_PACKAGE_INCOMPATIBLE
```

---

## 9. P3 — CPU/GPU scientific parity

### 9.1 test順序

1. synthetic 4-qubit circuit
2. H2 positive exact-rewrite control
3. H4 negative/no-safe-compression control
4. LiH 3.0 Å representative candidate
5. H6 representative MVP-heavy candidate
6. BeH2 3.0 Å largest current state

各段階がgreenになるまで次へ進まない。

### 9.2 parity対象

#### Numerical

- normalized state
- phase-aligned state error
- energy
- gradient vector
- gradient norm
- independent Hamiltonian expectation

#### Algorithmic

- candidate semantic IDs
- candidate ranking
- tie-break
- accepted/rejected decision
- energy guard decision
- optimizer terminal status
- rollback behavior

#### Structural

- parameters
- blocks
- CNOT
- CNOT depth
- total depth

resource recountはCPU paper-era counterを共通利用し、GPU simulatorで数え直さない。

### 9.3 tolerance

parity toleranceはP0で、candidate outcome取得前にfreezeする。初期案は次である。

- phase-aligned state error: current verifier tolerance以下
- absolute energy difference: `1e-10 Ha`以下
- max gradient-component difference: `1e-8`以下
- resource vector: exact integer equality
- terminal decision: exact equality
- candidate semantic ordering: exact equality。ただし真のfloating tieはfrozen canonical tie-breakで解決

既存contractがこれより厳しい場合は既存値を優先する。GPU結果を見て緩和しない。

### 9.4 optimizer

GPU kernelとCPU BFGSを組み合わせた場合、floating differencesでiteration数が変わり得る。そのため、次を分離する。

1. fixed-coordinate state/energy parity
2. one-step gradient parity
3. bounded optimizer terminal parity

fixed-coordinate parityが失敗した場合はoptimizerを実行しない。

### GO条件

- 全positive/negative controlでdecision parity
- resource vector完全一致
- tolerance内のstate/energy/gradient
- GPU固有のcandidate脱落なし
- NaN/Inf/warningなし

### NO-GO

```text
NO_GO_A100_STATE_PARITY
NO_GO_A100_ENERGY_PARITY
NO_GO_A100_GRADIENT_PARITY
NO_GO_A100_DECISION_PARITY
NO_GO_A100_RESOURCE_PARITY
```

---

## 10. P4 — Microbenchmark

### 10.1 原則

速度比較は同じAIC node上のCPU routeとGPU routeで行う。Mac CPU対A100だけを比較しない。

### 10.2 benchmark matrix

| Test | Qubits | Purpose |
|---|---:|---|
| synthetic small | 8 | launch overhead |
| H4 | 8 | scientific small case |
| LiH/H6 | 12 | current common size |
| BeH2 | 14 | current largest size |
| synthetic scaling | 16, 18, 20 | future break-even estimate |

synthetic scalingは速度評価専用であり、molecular performance evidenceにしない。

### 10.3 測定項目

- environment initialization
- circuit construction
- host-to-device transfer
- statevector evolution
- Hamiltonian expectation
- gradient component
- one candidate verification
- one optimizer run
- complete queue-item wall time
- peak CPU RSS
- peak GPU memory
- GPU utilization
- CPU core-hours
- GPU-hours

### 10.4 反復

- warm-upを1回以上行い、warm-up時間を別報告
- measured repetitionは最低5回
- median、minimum、maximum、MADを保存
- timeout/failureを最速値へ置換しない
- CPU/GPU両方を同じSlurm allocation内で実行可能なら、node variationを抑える

### 10.5 指標

```text
kernel_speedup = median_CPU_kernel / median_GPU_kernel
end_to_end_speedup = median_CPU_total / median_GPU_total
```

### 採用基準

A100を現行12--14 qubit productionへ採用するには、少なくとも次を満たす。

- parity gateが全てgreen
- target molecular caseのmedian end-to-end speedupが`1.20x`以上
- GPU routeに追加engineering failureがない
- artifact sizeとtransfer overheadが管理可能

`1.20x`未満なら、現行小分子にはCPUを維持する。16--20 qubitでのみ速い場合は、A100をfuture-large-system backendに限定する。

この`1.20x`は科学的効果量ではなく、移植・運用complexityを正当化するengineering thresholdである。

---

## 11. P5 — Limited scientific pilot

### 前提

P0--P4が全てgreenの場合だけ実行する。

### pilot対象

full 90-item studyを再実行しない。次の最大6 work itemsへ限定する。

- H2 exact positive control
- H4 negative control
- LiH one exact-only item
- LiH one approximate item
- H6 one candidate-heavy item
- BeH2 one largest-state item

### 方法

- frozen source
- frozen candidate list
- frozen caps
- same optimizer
- same resource counter
- CPU/GPU paired execution
- output-blind fixed order

### 禁止

- GPUで速かったmethodだけ追加実行
- GPU結果を見てthreshold変更
- CPU/GPUのbest result選択
- CPUで失敗したitemだけGPU retry
- pilot結果をmolecular performance tableへ混入

### GO条件

- 6 itemでpaired terminal decisionが一致
- end-to-end speedup criterionを満たす
- resume/timeout/rollbackが正常
- GPU artifactがindependent audit可能

---

## 12. P6 — Final decision

最終statusは次のいずれか一つにする。

### GO

```text
GO_A100_CURRENT_SYSTEM_BACKEND
```

12--14 qubitを含む今後のpilotへA100を使用できる。

```text
GO_A100_LARGE_SYSTEM_ONLY
```

現在の小分子にはCPUを維持し、16 qubit以上またはbatched workloadだけA100を使用する。

### NO-GO

```text
NO_GO_A100_NO_END_TO_END_SPEEDUP
NO_GO_A100_NUMERICAL_NONPARITY
NO_GO_A100_DECISION_NONPARITY
NO_GO_A100_ENVIRONMENT_INCOMPATIBLE
NO_GO_A100_OPERATIONAL_INSTABILITY
```

NO-GOでもGPUに都合のよいsubsetだけを残さず、全attemptを保存する。

---

## 13. Slurm運用計画

### 13.1 smoke job

```bash
#!/bin/bash
#SBATCH --job-name=ceo-a100-smoke
#SBATCH --partition=gpu-short
#SBATCH --ntasks=1
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --time=00:30:00
#SBATCH --output=logs/a100-smoke-%j.out

set -euo pipefail
python -m aic_a100_pilot.environment
python -m aic_a100_pilot.aer_gpu_backend --smoke
```

### 13.2 parity/benchmark job

```bash
#!/bin/bash
#SBATCH --job-name=ceo-a100-parity
#SBATCH --partition=gpu-standard
#SBATCH --ntasks=1
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=16
#SBATCH --time=12:00:00
#SBATCH --output=logs/a100-parity-%j.out

set -euo pipefail
python -m aic_a100_pilot.parity --protocol artifacts/aic-a100-pilot-v1/protocol.json
python -m aic_a100_pilot.benchmark --protocol artifacts/aic-a100-pilot-v1/protocol.json
```

memory値はactual partitionとpreflightを確認してから明示する。manualのdefaultへ暗黙依存せず、要求量を過大指定しない。

### 13.3 checkpoint

- 1 caseごとに独立atomic artifact
- temporary fileからrename
- previous digest chain
- SIGTERM時にincomplete statusを保存
- resumeはsame protocol/source/backendだけ許可
- 複数jobが同じledgerへ同時appendしない

parallel化する場合はper-item ledgerへ分け、終了後にdeterministic aggregationする。

---

## 14. Securityとdata protection

- SSH private keyをprojectへコピーしない
- GitHub tokenをbatch scriptへ直書きしない
- AIC node上のcredentialをartifactへ保存しない
- `nvidia-smi`等のhardware metadataにはusername/home pathを不要に含めない
- AICは試験環境のため、重要artifactはlocalとGit repositoryへbackupする
- raw research dataを容量確保のため自動削除しない
- shared accountを使用しない

repositoryがprivateの場合、deploy keyまたは短寿命credentialの扱いを別途確認し、credentialをrelease artifactへ含めない。

---

## 15. Test plan

### Unit

- GPU option schema
- environment digest
- backend context separation
- tolerance comparison
- CPU/GPU result canonicalization
- unknown device rejection

### Integration

- A100 smoke
- CPU fallback detection
- H2 exact parity
- H4 negative parity
- LiH state/energy/gradient parity
- BeH2 maximum current dimension

### Failure injection

- GPU unavailable
- CUDA mismatch
- OOM
- Slurm timeout
- SIGTERM
- corrupted checkpoint
- CPU/GPU backend mix
- single precision accidental use
- partial artifact

### Release audit

- clean clone
- exact commit
- environment manifest
- Slurm scripts
- all raw timings
- decision gate
- no modification of matched-work artifact

---

## 16. 実行順と停止条件

```text
P0 CPU baseline freeze
  -> P1 AIC preflight
    -> P2 real-GPU smoke
      -> P3 CPU/GPU scientific parity
        -> P4 end-to-end benchmark
          -> P5 limited scientific pilot
            -> P6 GO/NO-GO release
```

各phaseのgateを満たさない限り次へ進まない。

ただし、No-Goのたびに大規模release infrastructureを作らない。各phaseは小さなJSON artifactとtestで閉じ、P6で初めて統合decision manifestを作る。

---

## 17. 現実的な予測

### 現行12--14 qubit

最も可能性が高い結果は、statevector kernelの一部はGPUで動くが、end-to-endでは初期化、転送、circuit construction、Python/BFGSが支配し、十分なspeedupを得られないことである。

### 将来のlarge system

A100が有望になるのは次である。

- 16--20 qubit以上
- H2O/N2など大きいheld-out source
- 多trajectory
- candidate/stateのbatch化
- GPU上でHamiltonian expectationまで完結
- host/device transferを反復ごとに行わない設計

### 最重要判断

A100を利用できることと、A100を利用すべきことは異なる。

本pilotは、GPU採用を前提にせず、

> correctnessを維持したまま、対象workloadでend-to-end benefitが実測された場合だけ採用する

ことを保証する。

---

## 18. 参考資料

- [AIC Slurmユーザマニュアル](https://docs.keioaic.dev/slurm_user_manual)
- [Qiskit AerSimulator documentation](https://qiskit.github.io/qiskit-aer/stubs/qiskit_aer.AerSimulator.html)
- [qiskit-aer-gpu package](https://pypi.org/project/qiskit-aer-gpu/)
- [`CEO_MESC_RESEARCH_PLAN.md`](./CEO_MESC_RESEARCH_PLAN.md)
- [`parent_native_execution_services.py`](../src/v5_final/parent_native_execution_services.py)
- [`verifier_v2.py`](../src/v5_final/verifier_v2.py)
- [`provenance/dvg-obs-ceo/pyproject.toml`](../provenance/dvg-obs-ceo/pyproject.toml)

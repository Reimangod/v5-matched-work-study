#!/usr/bin/env bash
#SBATCH --partition=gpu-short
#SBATCH --gres=gpu:1
#SBATCH --array=0-2%2
#SBATCH --cpus-per-task=4
#SBATCH --mem=32000M
#SBATCH --time=01:00:00
#SBATCH --job-name=a100-dual-vqe

set -euo pipefail
: "${A100_EXPECTED_HEAD:?A100_EXPECTED_HEAD must be set}"
root="/share/${USER}/aic-a100-dual-optimizer-v1"
repo="${root}/repo"
environment_root="/share/${USER}/aic-a100-pilot-v1"
site="${environment_root}/gpu-venv/lib/python3.10/site-packages"
libs="$(find "${site}" -type d -path '*/lib' -print | sort | paste -sd: -)"
export LD_LIBRARY_PATH="${libs}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
export PYTHONPATH="${repo}/src:${repo}/provenance/dvg-obs-ceo/src:${repo}/provenance/dvg-obs-ceo/vendor/ceo-adapt-vqe"
cases=(h2 h6 beh2)
case_alias="${cases[${SLURM_ARRAY_TASK_ID}]}"
if [[ "${case_alias}" == "h2" ]]; then
  frozen_threads=2
else
  frozen_threads=1
fi
export OMP_NUM_THREADS="${frozen_threads}"
export MKL_NUM_THREADS="${frozen_threads}"
export OPENBLAS_NUM_THREADS="${frozen_threads}"
export NUMEXPR_NUM_THREADS="${frozen_threads}"
export VECLIB_MAXIMUM_THREADS="${frozen_threads}"
output_root="${root}/dual-optimizer-v3/${A100_EXPECTED_HEAD}"

cd "${repo}"
test "$(git rev-parse HEAD)" = "${A100_EXPECTED_HEAD}"
test "$(git status --porcelain --untracked-files=no)" = ""
"${environment_root}/gpu-venv/bin/python" -m aic_a100_pilot.dual_optimizer_execution \
  run --case "${case_alias}" --output-root "${output_root}"

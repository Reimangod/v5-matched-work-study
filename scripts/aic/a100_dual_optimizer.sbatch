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
root="/share/${USER}/aic-a100-pilot-v1"
repo="${root}/repo"
site="${root}/gpu-venv/lib/python3.10/site-packages"
libs="$(find "${site}" -type d -path '*/lib' -print | sort | paste -sd: -)"
export LD_LIBRARY_PATH="${libs}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
export PYTHONPATH="${repo}/src:${repo}/provenance/dvg-obs-ceo/src:${repo}/provenance/dvg-obs-ceo/vendor/ceo-adapt-vqe"
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1

cases=(h2 h6 beh2)
case_alias="${cases[${SLURM_ARRAY_TASK_ID}]}"
output_root="${root}/dual-optimizer-v1/${A100_EXPECTED_HEAD}"

cd "${repo}"
test "$(git rev-parse HEAD)" = "${A100_EXPECTED_HEAD}"
test "$(git status --porcelain --untracked-files=no)" = ""
"${root}/gpu-venv/bin/python" -m aic_a100_pilot.dual_optimizer_execution \
  run --case "${case_alias}" --output-root "${output_root}"

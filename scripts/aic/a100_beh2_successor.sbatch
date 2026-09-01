#!/usr/bin/env bash
#SBATCH --partition=gpu-standard
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32000M
#SBATCH --time=04:00:00
#SBATCH --job-name=a100-beh2-v1

set -euo pipefail
: "${A100_EXPECTED_HEAD:?A100_EXPECTED_HEAD must be set}"
root="/share/${USER}/aic-a100-dual-optimizer-v1"
repo="${root}/repo"
environment_root="/share/${USER}/aic-a100-pilot-v1"
site="${environment_root}/gpu-venv/lib/python3.10/site-packages"
libs="$(find "${site}" -type d -path '*/lib' -print | sort | paste -sd: -)"
export LD_LIBRARY_PATH="${libs}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
export PYTHONPATH="${repo}/src:${repo}/provenance/dvg-obs-ceo/src:${repo}/provenance/dvg-obs-ceo/vendor/ceo-adapt-vqe"
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1
export A100_SCHEDULER_PARTITION=gpu-standard
export A100_SCHEDULER_TIME_LIMIT=04:00:00
export A100_SCHEDULER_GPU_PER_TASK=1
output_root="${root}/beh2-successor-v1/${A100_EXPECTED_HEAD}"

cd "${repo}"
test "$(git rev-parse HEAD)" = "${A100_EXPECTED_HEAD}"
test "$(git status --porcelain --untracked-files=no)" = ""
"${environment_root}/gpu-venv/bin/python" -m aic_a100_pilot.beh2_successor_execution \
  run --output-root "${output_root}"

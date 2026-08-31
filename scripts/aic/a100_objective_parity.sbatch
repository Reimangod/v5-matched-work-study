#!/usr/bin/env bash
#SBATCH --partition=gpu-standard
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64000M
#SBATCH --time=04:00:00
#SBATCH --job-name=a100-p3-objective

set -euo pipefail
: "${A100_CASE:?A100_CASE must be set}"
: "${A100_EXPECTED_HEAD:?A100_EXPECTED_HEAD must be set}"
root="/share/${USER}/aic-a100-pilot-v1"
repo="${root}/repo"
site="${root}/gpu-venv/lib/python3.10/site-packages"
libs="$(find "${site}" -type d -path '*/lib' -print | sort | paste -sd: -)"
export LD_LIBRARY_PATH="${libs}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
export PYTHONPATH="${repo}/src:${repo}/provenance/dvg-obs-ceo/src:${repo}/provenance/dvg-obs-ceo/vendor/ceo-adapt-vqe"
if [[ "${A100_CASE}" == "h2" ]]; then frozen_threads=2; else frozen_threads=1; fi
export OMP_NUM_THREADS="${frozen_threads}"
export MKL_NUM_THREADS="${frozen_threads}"
export OPENBLAS_NUM_THREADS="${frozen_threads}"
output="${root}/p3-objective/${A100_CASE}.json"
mkdir -p "$(dirname "${output}")"
export A100_OBJECTIVE_PARITY_OUTPUT="${output}"

cd "${repo}"
test "$(git rev-parse HEAD)" = "${A100_EXPECTED_HEAD}"
"${root}/gpu-venv/bin/python" -m aic_a100_pilot.objective_parity --case "${A100_CASE}"

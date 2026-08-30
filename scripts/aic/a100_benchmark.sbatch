#!/usr/bin/env bash
#SBATCH --partition=gpu-standard
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64000M
#SBATCH --time=02:00:00
#SBATCH --job-name=a100-p4-benchmark

set -euo pipefail
: "${A100_BENCHMARK_KIND:?A100_BENCHMARK_KIND must be set}"
: "${A100_BENCHMARK_VALUE:?A100_BENCHMARK_VALUE must be set}"
: "${A100_EXPECTED_HEAD:?A100_EXPECTED_HEAD must be set}"
root="/share/${USER}/aic-a100-pilot-v1"
repo="${root}/repo"
site="${root}/gpu-venv/lib/python3.10/site-packages"
libs="$(find "${site}" -type d -path '*/lib' -print | sort | paste -sd: -)"
export LD_LIBRARY_PATH="${libs}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
export PYTHONPATH="${repo}/src:${repo}/provenance/dvg-obs-ceo/src:${repo}/provenance/dvg-obs-ceo/vendor/ceo-adapt-vqe"

if [[ "${A100_BENCHMARK_KIND}" == "current" ]]; then
  if [[ "${A100_BENCHMARK_VALUE}" == "h2" ]]; then
    frozen_threads=2
  else
    frozen_threads=1
  fi
  arguments=(--case "${A100_BENCHMARK_VALUE}")
elif [[ "${A100_BENCHMARK_KIND}" == "synthetic" ]]; then
  frozen_threads=1
  arguments=(--synthetic-qubits "${A100_BENCHMARK_VALUE}")
else
  echo "unregistered benchmark kind" >&2
  exit 2
fi
export OMP_NUM_THREADS="${frozen_threads}"
export MKL_NUM_THREADS="${frozen_threads}"
export OPENBLAS_NUM_THREADS="${frozen_threads}"
output="${root}/p4/${A100_BENCHMARK_KIND}-${A100_BENCHMARK_VALUE}.json"
mkdir -p "$(dirname "${output}")"
export A100_BENCHMARK_OUTPUT="${output}"

cd "${repo}"
test "$(git rev-parse HEAD)" = "${A100_EXPECTED_HEAD}"
"${root}/gpu-venv/bin/python" -m aic_a100_pilot.benchmark "${arguments[@]}"

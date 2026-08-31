#!/usr/bin/env bash
#SBATCH --partition=gpu-standard
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64000M
#SBATCH --time=08:00:00
#SBATCH --job-name=a100-unified-v4

set -euo pipefail
: "${A100_CASE:?A100_CASE must be set}"
: "${A100_EXPECTED_HEAD:?A100_EXPECTED_HEAD must be set}"
root="/share/${USER}/aic-a100-pilot-v1"
repo="${root}/repo"
site="${root}/gpu-venv/lib/python3.10/site-packages"
libs="$(find "${site}" -type d -path '*/lib' -print | sort | paste -sd: -)"
export LD_LIBRARY_PATH="${libs}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
export PYTHONPATH="${repo}/src:${repo}/provenance/dvg-obs-ceo/src:${repo}/provenance/dvg-obs-ceo/vendor/ceo-adapt-vqe"
output="${root}/p3-unified-route-v4/${A100_CASE}.json"
preparation="${root}/p3-unified-route-v4/preparation"
bundle="${preparation}/${A100_CASE}.pickle"
manifest="${preparation}/${A100_CASE}.json"
mkdir -p "$(dirname "${output}")"

cd "${repo}"
test "$(git rev-parse HEAD)" = "${A100_EXPECTED_HEAD}"
if [[ "${A100_CASE}" == "h2" ]]; then source_threads=2; else source_threads=1; fi
env \
  OMP_NUM_THREADS="${source_threads}" OMP_DYNAMIC=FALSE \
  MKL_NUM_THREADS="${source_threads}" MKL_DYNAMIC=FALSE \
  OPENBLAS_NUM_THREADS="${source_threads}" \
  NUMEXPR_NUM_THREADS="${source_threads}" \
  VECLIB_MAXIMUM_THREADS="${source_threads}" \
  "${root}/gpu-venv/bin/python" -m aic_a100_pilot.unified_route_prepare \
  --case "${A100_CASE}" \
  --bundle "${bundle}" \
  --manifest "${manifest}"
env \
  OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE \
  MKL_NUM_THREADS=1 MKL_DYNAMIC=FALSE \
  OPENBLAS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  VECLIB_MAXIMUM_THREADS=1 A100_NUMERICAL_THREADS=1 \
  "${root}/gpu-venv/bin/python" -m aic_a100_pilot.unified_route \
  --case "${A100_CASE}" \
  --prepared-bundle "${bundle}" \
  --prepared-manifest "${manifest}" \
  --output "${output}"

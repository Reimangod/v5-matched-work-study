#!/usr/bin/env bash
#SBATCH --partition=gpu-standard
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64000M
#SBATCH --time=12:00:00
#SBATCH --job-name=a100-v2-beh2-diagnostic

set -euo pipefail
: "${A100_EXPECTED_HEAD:?A100_EXPECTED_HEAD must be set}"
root="/share/${USER}/aic-a100-pilot-v1"
repo="${root}/repo"
site="${root}/gpu-venv/lib/python3.10/site-packages"
libs="$(find "${site}" -type d -path '*/lib' -print | sort | paste -sd: -)"
export LD_LIBRARY_PATH="${libs}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
export PYTHONPATH="${repo}/src:${repo}/provenance/dvg-obs-ceo/src:${repo}/provenance/dvg-obs-ceo/vendor/ceo-adapt-vqe"
namespace="${root}/p9-stable-control-v2-postfailure-diagnostic"
source_results="${root}/p8-unified-stable-v2/results"
preparation="${namespace}/preparation"
bundle="${preparation}/beh2.pickle"
manifest="${preparation}/beh2.json"
start_record="${namespace}/attempt-start/beh2.json"
incident="${namespace}/incidents/beh2.json"
output="${namespace}/results/beh2.json"

cd "${repo}"
test "$(git rev-parse HEAD)" = "${A100_EXPECTED_HEAD}"
env \
  OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE \
  MKL_NUM_THREADS=1 MKL_DYNAMIC=FALSE \
  OPENBLAS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  VECLIB_MAXIMUM_THREADS=1 \
  "${root}/gpu-venv/bin/python" -m aic_a100_pilot.stable_control_v2_prepare \
  --case beh2 \
  --bundle "${bundle}" \
  --manifest "${manifest}"
env \
  OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE \
  MKL_NUM_THREADS=1 MKL_DYNAMIC=FALSE \
  OPENBLAS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  VECLIB_MAXIMUM_THREADS=1 A100_NUMERICAL_THREADS=1 \
  "${root}/gpu-venv/bin/python" -m aic_a100_pilot.stable_control_v2_postfailure_route \
  --prepared-bundle "${bundle}" \
  --prepared-manifest "${manifest}" \
  --source-results "${source_results}" \
  --start-record "${start_record}" \
  --incident "${incident}" \
  --output "${output}"

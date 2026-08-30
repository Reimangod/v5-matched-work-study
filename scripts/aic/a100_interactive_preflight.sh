#!/usr/bin/env bash
set -euo pipefail

# Run from the AIC login node. This requests exactly one GPU and emits no user
# identity or credential material. Site state remains authoritative.
srun \
  --partition=gpu-interactive \
  --gres=gpu:1 \
  --cpus-per-task=8 \
  --mem=32000M \
  --time=00:10:00 \
  --job-name=a100-p1-preflight \
  bash -lc '
    set -euo pipefail
    echo "JOB_ID=${SLURM_JOB_ID}"
    echo "PARTITION=${SLURM_JOB_PARTITION}"
    echo "NODE=$(hostname)"
    scontrol show job "${SLURM_JOB_ID}" -o \
      | sed -E "s/UserId=[^ ]+/UserId=<REDACTED>/; s/WorkDir=[^ ]+/WorkDir=<REDACTED>/"
    nvidia-smi --query-gpu=name,uuid,driver_version,memory.total \
      --format=csv,noheader
    echo "VISIBLE_GPU_COUNT=$(nvidia-smi --query-gpu=uuid --format=csv,noheader | wc -l | tr -d " ")"
    python3 --version
  '

#!/usr/bin/env bash
#SBATCH --partition=gpu-standard
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32000M
#SBATCH --time=00:10:00
#SBATCH --job-name=a100-p2-smoke

set -euo pipefail
root="/share/${USER}/aic-a100-pilot-v1"
site="${root}/gpu-venv/lib/python3.10/site-packages"
libs="$(find "${site}" -type d -path '*/lib' -print | sort | paste -sd: -)"
export LD_LIBRARY_PATH="${libs}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"

"${root}/gpu-venv/bin/python" - <<'PY'
import ctypes
import json
import numpy as np
from qiskit import QuantumCircuit
from qiskit_aer import AerSimulator

cuda = ctypes.CDLL("libcuda.so.1")
count = ctypes.c_int()
if cuda.cuInit(0) != 0 or cuda.cuDeviceGetCount(ctypes.byref(count)) != 0:
    raise RuntimeError("CUDA driver initialization failed")
if count.value != 1:
    raise RuntimeError(f"expected exactly one CUDA device, got {count.value}")

backend = AerSimulator(method="statevector", device="GPU", precision="double")
qc = QuantumCircuit(4)
qc.h(0)
for target in range(1, 4):
    qc.cx(0, target)
qc.save_statevector()
result = backend.run(qc).result()
metadata = result.results[0].metadata
if str(metadata.get("device", "")).upper() != "GPU":
    raise RuntimeError(f"CPU fallback detected: {metadata}")
state = np.asarray(result.get_statevector(qc), dtype=np.complex128)
expected = np.zeros(16, dtype=np.complex128)
expected[[0, 15]] = 1 / np.sqrt(2)
print(json.dumps({
    "cuda_driver_device_count": count.value,
    "aer_available_devices": list(backend.available_devices()),
    "metadata_device": metadata.get("device"),
    "metadata_method": metadata.get("method"),
    "state_max_abs_error": float(np.max(np.abs(state - expected))),
}, sort_keys=True))
PY

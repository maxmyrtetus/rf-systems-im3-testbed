#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   ./scripts/run_im3_case.sh <tag>
# Example:
#   ./scripts/run_im3_case.sh cfg0_pre19

TAG=${1:?tag required}

FC=${FC:-915000000}
FS=${FS:-2000000}
N=${N:-16000000}
GAIN=${GAIN:-20}
NAVG=${NAVG:-40}

BIN="data/${TAG}.bin"

echo "=== CAPTURE ${BIN} ==="
GAIN=${GAIN} FS=${FS} N=${N} ./capture/capture_rtlsdr.sh "${BIN}"

echo "=== ANALYZE ${TAG} ==="
MPLBACKEND=Agg python analysis/analyze_im3.py "${BIN}" \
  --format rtlsdr --fc ${FC} --fs ${FS} --tag "${TAG}" --navg ${NAVG}

echo "=== CLIP CHECK ${TAG} ==="
python -c "import numpy as np; fn='${BIN}'; raw=np.fromfile(fn,dtype=np.uint8); print(fn,'bytes:',raw.size,'frac(0 or 255):',np.mean((raw==0)|(raw==255)))"

echo "DONE: ${TAG}"

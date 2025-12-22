#!/usr/bin/env bash
set -euo pipefail

FC=${FC:-915000000}
FS=${FS:-2400000}
N=${N:-24000000}
GAIN=${GAIN:-0}

OUT=${1:-data/capture_u8iq.bin}
mkdir -p "$(dirname "$OUT")"

echo "rtl_sdr: fc=$FC fs=$FS gain=$GAIN n=$N out=$OUT"
rtl_sdr -f "$FC" -s "$FS" -g "$GAIN" -n "$N" "$OUT"
echo "Wrote $OUT"

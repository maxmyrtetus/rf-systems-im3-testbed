import numpy as np
from pathlib import Path

# Generates two-tone complex baseband waveform for HackRF TX
# Output format: interleaved int8 IQ: I0,Q0,I1,Q1,...

fs = 2_000_000        # HackRF supports 2–20 MHz sample rates; 2 MHz matching RTL-SDR
duration_s = 2.0
f_off1 = -250_000     # -250 kHz
f_off2 = +250_000     # +250 kHz

# Keep amplitude low to avoid clipping
amp = 0.30

t = np.arange(int(fs * duration_s)) / fs
x = (np.exp(1j*2*np.pi*f_off1*t) + np.exp(1j*2*np.pi*f_off2*t)) / 2.0
x = amp * x

i = np.clip(np.real(x) * 127, -128, 127).astype(np.int8)
q = np.clip(np.imag(x) * 127, -128, 127).astype(np.int8)

iq = np.empty(2 * len(i), dtype=np.int8)
iq[0::2] = i
iq[1::2] = q

out = Path("waveforms") / f"twotone_fs{fs}_off250k_i8iq.bin"
out.parent.mkdir(parents=True, exist_ok=True)
iq.tofile(out)

print("Wrote:", out, "bytes:", out.stat().st_size)

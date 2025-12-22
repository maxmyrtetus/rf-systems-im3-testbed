import numpy as np
from pathlib import Path
from scipy.signal import lfilter

def rrc_taps(beta: float, sps: int, span: int):
    """
    Root-Raised-Cosine filter taps.
    beta: roll-off (0..1)
    sps: samples per symbol
    span: filter span in symbols (e.g., 10)
    """
    N = span * sps
    t = np.arange(-N/2, N/2 + 1) / sps  # in symbol periods
    taps = np.zeros_like(t, dtype=np.float64)

    for i, ti in enumerate(t):
        if abs(ti) < 1e-12:
            taps[i] = 1.0 - beta + (4 * beta / np.pi)
        elif abs(abs(ti) - 1/(4*beta)) < 1e-12:
            # special-case singularity at t = +-T/(4β)
            taps[i] = (beta / np.sqrt(2)) * (
                (1 + 2/np.pi) * np.sin(np.pi/(4*beta)) +
                (1 - 2/np.pi) * np.cos(np.pi/(4*beta))
            )
        else:
            num = np.sin(np.pi * ti * (1 - beta)) + 4 * beta * ti * np.cos(np.pi * ti * (1 + beta))
            den = np.pi * ti * (1 - (4 * beta * ti)**2)
            taps[i] = num / den

    # Normalize energy
    taps /= np.sqrt(np.sum(taps**2))
    return taps

def bits_to_qpsk(bits: np.ndarray):
    """
    Gray-coded QPSK mapping:
      00 -> +1 + j
      01 -> -1 + j
      11 -> -1 - j
      10 -> +1 - j
    """
    bits = bits.reshape(-1, 2)
    b0 = bits[:, 0]
    b1 = bits[:, 1]

    i = np.where((b0 == 0) & (b1 == 0),  +1,
        np.where((b0 == 0) & (b1 == 1),  -1,
        np.where((b0 == 1) & (b1 == 1),  -1,  +1)))
    q = np.where((b0 == 0) & (b1 == 0),  +1,
        np.where((b0 == 0) & (b1 == 1),  +1,
        np.where((b0 == 1) & (b1 == 1),  -1,  -1)))
    return (i + 1j*q) / np.sqrt(2)

def main():
    # --- sample rate agreeing with RTL-SDR
    fs = 2_000_000          # 2.0 Msps
    sym_rate = 250_000      # 250 ksps QPSK symbols
    sps = fs // sym_rate    # samples per symbol (must be int)
    assert sps * sym_rate == fs, "fs must be an integer multiple of sym_rate"

    # Burst parameters
    n_payload_syms = 4000
    beta = 0.35
    span = 10               # RRC span in symbols
    guard_syms = 200        # zeros before/after burst (in symbols)

    # fixed bits for correlation/sync later
    rng = np.random.default_rng(1234)
    pre_bits = rng.integers(0, 2, size=256, dtype=np.int8)   # 128 QPSK symbols
    pre_syms = bits_to_qpsk(pre_bits)

    # random bits
    payload_bits = rng.integers(0, 2, size=2*n_payload_syms, dtype=np.int8)
    payload_syms = bits_to_qpsk(payload_bits)

    # Assemble burst in symbol domain
    guards = np.zeros(guard_syms, dtype=np.complex64)
    sym_stream = np.concatenate([guards, pre_syms, payload_syms, guards]).astype(np.complex64)

    # Upsample 
    up = np.zeros(len(sym_stream) * sps, dtype=np.complex64)
    up[::sps] = sym_stream

    # Pulse shape with RRC
    h = rrc_taps(beta=beta, sps=sps, span=span).astype(np.float32)
    x = lfilter(h, [1.0], up)

    # Scale amplitude to avoid clipping 
    # (HackRF uses interleaved int8 IQ)
    amp = 0.25
    x = amp * x / (np.max(np.abs(x)) + 1e-12)

    i = np.clip(np.real(x) * 127, -128, 127).astype(np.int8)
    q = np.clip(np.imag(x) * 127, -128, 127).astype(np.int8)

    iq = np.empty(2 * len(i), dtype=np.int8)
    iq[0::2] = i
    iq[1::2] = q

    out = Path("waveforms") / f"qpsk_fs{fs}_sym{sym_rate}_rrc{beta}_i8iq.bin"
    out.parent.mkdir(parents=True, exist_ok=True)
    iq.tofile(out)
    print("Wrote:", out, "bytes:", out.stat().st_size)

    # metadata text file 
    meta = out.with_suffix(".txt")
    meta.write_text(
        f"fs={fs}\n"
        f"sym_rate={sym_rate}\n"
        f"sps={sps}\n"
        f"beta={beta}\n"
        f"span_syms={span}\n"
        f"guard_syms={guard_syms}\n"
        f"preamble_bits=256 (128 syms)\n"
        f"payload_syms={n_payload_syms}\n"
        f"note=int8 interleaved IQ for HackRF-style TX\n"
    )
    print("Wrote:", meta)

if __name__ == "__main__":
    main()

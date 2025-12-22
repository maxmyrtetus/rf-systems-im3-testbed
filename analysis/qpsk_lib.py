import re
import numpy as np
from scipy.signal import lfilter, fftconvolve


def rrc_taps(beta: float, sps: int, span_syms: int) -> np.ndarray:
    """
    root raised cos filter taps.
    beta: rolloff (0..1)
    sps: samples per symbol
    span_syms: filter span in symbols (ie 10)
    """
    N = span_syms * sps
    t = np.arange(-N / 2, N / 2 + 1) / sps
    taps = np.zeros_like(t, dtype=np.float64)

    for i, ti in enumerate(t):
        if abs(ti) < 1e-12:
            taps[i] = 1.0 - beta + (4 * beta / np.pi)
        elif beta > 0 and abs(abs(ti) - 1 / (4 * beta)) < 1e-12:
            taps[i] = (beta / np.sqrt(2)) * (
                (1 + 2 / np.pi) * np.sin(np.pi / (4 * beta))
                + (1 - 2 / np.pi) * np.cos(np.pi / (4 * beta))
            )
        else:
            num = np.sin(np.pi * ti * (1 - beta)) + 4 * beta * ti * np.cos(
                np.pi * ti * (1 + beta)
            )
            den = np.pi * ti * (1 - (4 * beta * ti) ** 2)
            taps[i] = num / den

    taps /= np.sqrt(np.sum(taps**2))
    return taps.astype(np.float32)


def bits_to_qpsk(bits: np.ndarray) -> np.ndarray:
    """
    Mapping consistent with generator:
      b0 controls Q sign, b1 controls I sign
      00 -> +1 + j
      01 -> -1 + j
      11 -> -1 - j
      10 -> +1 - j
    """
    bits = bits.reshape(-1, 2).astype(np.int8)
    b0 = bits[:, 0]
    b1 = bits[:, 1]
    I = np.where(b1 == 0, 1.0, -1.0)
    Q = np.where(b0 == 0, 1.0, -1.0)
    return (I + 1j * Q) / np.sqrt(2.0)


def qpsk_to_bits(syms: np.ndarray) -> np.ndarray:
    # Hard decision demapper, works w/ bits_to_qpsk()
    b0 = (np.imag(syms) < 0).astype(np.int8)
    b1 = (np.real(syms) < 0).astype(np.int8)
    bits = np.empty(2 * len(syms), dtype=np.int8) 
    bits[0::2] = b0
    bits[1::2] = b1
    return bits


def _first_number(s: str):
    m = re.search(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", s)
    return m.group(0) if m else None


def parse_meta(meta_path: str | None) -> dict:
    """
    Parse waveform metadata txt that generator writes.
    Returns defaults if meta file missing.
    """
    params = dict(
        fs=2_000_000,
        sym_rate=250_000,
        sps=8,
        beta=0.35,
        span_syms=10,
        guard_syms=200,
        payload_syms=4000,
        preamble_bits=256,  # 128 symbols
        seed=1234,
        amp=0.25,
    )
    if meta_path is None:
        return params

    try:
        text = open(meta_path, "r").read().splitlines()
    except FileNotFoundError:
        return params

    for line in text:
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()

        if k in ("fs", "sym_rate", "sps", "span_syms", "guard_syms", "payload_syms"):
            num = _first_number(v)
            if num is not None:
                params[k] = int(float(num))
        elif k in ("beta", "amp"):
            num = _first_number(v)
            if num is not None:
                params[k] = float(num)

    return params


def generate_reference(params: dict):
    """
    Regenerate:
      - tx_ref: sample-rate shaped, int8-quantized reference waveform (complex64)
      - sym_stream: symbol-rate stream (complex64)
      - pre_syms: preamble symbols (complex64)
      - payload_bits: payload bits (int8)
      - h: RRC taps (float32)
    This matches generator logic (seed=1234).
    """
    fs = params["fs"]
    sym_rate = params["sym_rate"]
    sps = params["sps"]
    beta = params["beta"]
    span = params["span_syms"]
    guard_syms = params["guard_syms"]
    payload_syms = params["payload_syms"]
    seed = params.get("seed", 1234)
    amp = params.get("amp", 0.25)

    assert sps * sym_rate == fs, "fs must be integer multiple of sym_rate"

    rng = np.random.default_rng(seed)

    pre_bits = rng.integers(0, 2, size=256, dtype=np.int8)  # 128 symbols
    pre_syms = bits_to_qpsk(pre_bits).astype(np.complex64)

    payload_bits = rng.integers(0, 2, size=2 * payload_syms, dtype=np.int8)
    payload_syms_c = bits_to_qpsk(payload_bits).astype(np.complex64)

    guards = np.zeros(guard_syms, dtype=np.complex64)
    sym_stream = np.concatenate([guards, pre_syms, payload_syms_c, guards]).astype(
        np.complex64
    )

    # Upsample and pulse shape
    up = np.zeros(len(sym_stream) * sps, dtype=np.complex64)
    up[::sps] = sym_stream

    h = rrc_taps(beta=beta, sps=sps, span_syms=span)
    x = lfilter(h, [1.0], up)

    # Match generator: scale then int8 quantize
    x = amp * x / (np.max(np.abs(x)) + 1e-12)
    i8 = np.clip(np.real(x) * 127, -128, 127).astype(np.int8)
    q8 = np.clip(np.imag(x) * 127, -128, 127).astype(np.int8)
    tx_ref = (i8.astype(np.float32) + 1j * q8.astype(np.float32)) / 127.0

    return tx_ref.astype(np.complex64), sym_stream, pre_syms, payload_bits, h


def mix_down(x: np.ndarray, fs: float, f_hz: float) -> np.ndarray:
    n = np.arange(len(x), dtype=np.float64)
    return x * np.exp(-1j * 2 * np.pi * f_hz * n / fs)


def coarse_cfo_qpsk4(rx: np.ndarray, fs: float) -> float:
    """
    CFO estimate using 4th-power phase increment:
      CFO ≈ angle(mean(rx4[n]*conj(rx4[n-1]))) * fs/(2pi) / 4
    good when QPSK energy present 
    """
    if len(rx) < 1000:
        return 0.0
    rx4 = rx**4
    z = rx4[1:] * np.conj(rx4[:-1])
    m = np.mean(z)
    if not np.isfinite(m):
        return 0.0
    ang = np.angle(m)
    return float((fs * ang) / (2 * np.pi) / 4.0)


def correlate_find_peak(rx: np.ndarray, ref: np.ndarray) -> tuple[int, np.ndarray]:
    """
    Return (k0, corr) where corr[k] = sum rx[k:k+L] * conj(ref)
    Implemented via fftconvolve with reversed conj reference.
    """
    corr = fftconvolve(rx, np.conj(ref[::-1]), mode="valid")
    k0 = int(np.argmax(np.abs(corr)))
    return k0, corr


def fine_cfo_and_channel(rx_seg: np.ndarray, ref: np.ndarray, fs: float, mask_frac=0.05):
    """
    Fine CFO estimate via phase-slope fit of rx_seg * conj(ref) on high-energy samples,
    plus single-tap complex channel estimate.
    Returns (cfo_hz, h_hat, rx_cfo_corrected, mask)
    """
    mag = np.abs(ref)
    mask = mag > (mask_frac * np.max(mag))

    z = rx_seg[mask] * np.conj(ref[mask])
    phi = np.unwrap(np.angle(z))
    n = np.nonzero(mask)[0].astype(np.float64)
    if len(n) < 10:
        return 0.0, 1.0 + 0j, rx_seg, mask

    slope, _ = np.polyfit(n, phi, 1)
    cfo_hz = float(slope * fs / (2 * np.pi))

    n_all = np.arange(len(rx_seg), dtype=np.float64)
    rx_cfo = rx_seg * np.exp(-1j * 2 * np.pi * cfo_hz * n_all / fs)

    h_hat = np.vdot(ref[mask], rx_cfo[mask]) / np.vdot(ref[mask], ref[mask])
    return cfo_hz, complex(h_hat), rx_cfo, mask

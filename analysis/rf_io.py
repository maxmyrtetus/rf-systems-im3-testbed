import numpy as np

def read_rtlsdr_u8iq(filename: str) -> np.ndarray:
    """Read rtl_sdr raw IQ file: interleaved uint8 I,Q (0..255). """
    raw = np.fromfile(filename, dtype=np.uint8)
    if raw.size % 2 != 0:
        raw = raw[:-1]
    i = raw[0::2].astype(np.float32)
    q = raw[1::2].astype(np.float32)
    # Center around 0 and scale to ~[-1,1]
    i = (i - 127.5) / 128.0
    q = (q - 127.5) / 128.0
    return i + 1j*q

def read_hackrf_i8iq(filename: str) -> np.ndarray:
    """Read HackRF raw IQ file: interleaved int8 I,Q. """
    raw = np.fromfile(filename, dtype=np.int8).astype(np.float32)
    if raw.size % 2 != 0:
        raw = raw[:-1]
    i = raw[0::2] / 128.0
    q = raw[1::2] / 128.0
    return i + 1j*q





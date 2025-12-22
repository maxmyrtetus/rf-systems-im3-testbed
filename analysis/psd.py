import numpy as np

def psd_db(x: np.ndarray, fs: float, fc: float, nfft: int = 262144):
    """Return freq axis (Hz) and PSD-like magnitude in dB (relative)."""
    x = x[:nfft]
    w = np.hanning(len(x))
    X = np.fft.fftshift(np.fft.fft(x * w))
    p = 20*np.log10(np.abs(X) + 1e-12)
    f = fc + np.fft.fftshift(np.fft.fftfreq(len(x), d=1/fs))
    return f, p

def psd_db_avg(x: np.ndarray, fs: float, fc: float, nfft: int = 262144, navg: int = 10):
    """
    Averaged PSD (more stable noise floor; better for seeing IM3).
    Returns f_hz, p_db (relative).
    """
    x = x.astype(np.complex64)
    x = x - np.mean(x)  # remove DC offset spike

    need = nfft * navg
    if len(x) < need:
        x = np.pad(x, (0, need - len(x)), mode="constant")
    else:
        x = x[:need]

    frames = x.reshape(navg, nfft)

    w = np.hanning(nfft).astype(np.float32)
    X = np.fft.fft(frames * w, axis=1)
    P = np.mean(np.abs(X)**2, axis=0) + 1e-30

    f = fc + np.fft.fftfreq(nfft, d=1/fs)
    f = np.fft.fftshift(f)
    p_db = 10*np.log10(np.fft.fftshift(P))
    return f, p_db

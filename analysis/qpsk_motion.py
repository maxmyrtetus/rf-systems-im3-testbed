import argparse
import json
from pathlib import Path
import numpy as np
from scipy.signal import fftconvolve

from analysis.rf_io import read_rtlsdr_u8iq
from analysis.qpsk_hw_rx import parse_meta, generate_reference, estimate_cfo_and_channel  

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iq", required=True)
    ap.add_argument("--meta", default=None)
    ap.add_argument("--fc", type=float, default=915e6)
    ap.add_argument("--fs", type=float, default=2_000_000.0)
    ap.add_argument("--seconds", type=float, default=2.0, help="how much IQ to analyze")
    ap.add_argument("--out", type=str, default="motion")
    ap.add_argument("--mask_frac", type=float, default=0.05)
    ap.add_argument("--peak_thresh", type=float, default=0.6, help="fraction of max corr magnitude")
    ap.add_argument("--min_sep_ms", type=float, default=5.0, help="minimum separation between bursts (ms)")
    args = ap.parse_args()

    params = parse_meta(args.meta)
    params["fs"] = int(args.fs)

    tx_ref, _, _, _, _ = generate_reference(params)

    rx = read_rtlsdr_u8iq(args.iq)
    rx = rx - np.mean(rx)

    L = min(len(rx), int(args.seconds * args.fs))
    rx = rx[:L]

    corr = fftconvolve(rx, np.conj(tx_ref[::-1]), mode="valid")
    mag = np.abs(corr)

    thr = args.peak_thresh * np.max(mag)
    min_sep = int((args.min_sep_ms / 1000.0) * args.fs)

    # Greedy peak picking
    candidates = np.where(mag > thr)[0]
    peaks = []
    last = -10**18
    for k in candidates:
        if k - last >= min_sep:
            # local max in a small window
            w = mag[max(0, k-50):min(len(mag), k+51)]
            kk = int(np.argmax(w) + max(0, k-50))
            if len(peaks) == 0 or kk - peaks[-1] >= min_sep:
                peaks.append(kk)
                last = kk

    phases = []
    mags = []
    cfos = []

    for k0 in peaks:
        rx_seg = rx[k0:k0+len(tx_ref)]
        if len(rx_seg) < len(tx_ref):
            continue
        cfo_hz, h_hat, _, _ = estimate_cfo_and_channel(rx_seg, tx_ref, fs=args.fs, mask_frac=args.mask_frac)
        phases.append(float(np.angle(h_hat)))
        mags.append(float(np.abs(h_hat)))
        cfos.append(float(cfo_hz))

    phases = np.unwrap(np.array(phases))
    mags = np.array(mags)
    cfos = np.array(cfos)

    metrics = {
        "iq_file": args.iq,
        "bursts_used": int(len(phases)),
        "phase_var": float(np.var(phases)) if len(phases) else None,
        "mag_var": float(np.var(mags)) if len(mags) else None,
        "cfo_mean_hz": float(np.mean(cfos)) if len(cfos) else None,
        "cfo_std_hz": float(np.std(cfos)) if len(cfos) else None,
    }

    Path("results").mkdir(exist_ok=True)
    Path("plots").mkdir(exist_ok=True)

    out_json = Path("results") / f"{args.out}_motion_metrics.json"
    out_json.write_text(json.dumps(metrics, indent=2))
    print(json.dumps(metrics, indent=2))
    print("Saved:", out_json)

    import matplotlib.pyplot as plt
    if len(phases) > 0:
        plt.figure(figsize=(8, 3))
        plt.plot(phases)
        plt.title("Estimated channel phase per burst (unwrap)")
        plt.xlabel("Burst index")
        plt.ylabel("Phase (rad)")
        plt.grid(True)
        out_png = Path("plots") / f"{args.out}_phase.png"
        plt.tight_layout()
        plt.savefig(out_png, dpi=200)
        print("Saved:", out_png)

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt

from rf_io import read_rtlsdr_u8iq, read_hackrf_i8iq
from psd import psd_db_avg
from im3 import im3_metrics


def peak_candidates(f_hz, p_db, f_min, f_max, k=6, min_sep_hz=5_000,
                    exclude_center_hz=None, exclude_halfwidth_hz=0.0):
    """
    Returns up to k candidate peaks (freq_hz, power_db) in [f_min, f_max],
    enforces min_sep_hz separation between the chosen peaks.
    excludes anything within +-exclude_halfwidth_hz of exclude_center_hz.
    """
    idx = np.where((f_hz >= f_min) & (f_hz <= f_max))[0]
    if exclude_center_hz is not None and exclude_halfwidth_hz > 0:
        idx = idx[np.abs(f_hz[idx] - exclude_center_hz) > exclude_halfwidth_hz]

    if idx.size == 0:
        return []

    # sort by descending power
    idx_sorted = idx[np.argsort(p_db[idx])[::-1]]

    chosen = []
    for i in idx_sorted:
        fi = float(f_hz[i])
        if all(abs(fi - fj) > min_sep_hz for fj, _ in chosen):
            chosen.append((fi, float(p_db[i])))
            if len(chosen) >= k:
                break
    return chosen


def choose_tone_pair(c1, c2, expected_sep_hz, fc_hz, enforce_straddle_fc=True):
    """
    Choose (f1,f2) from candidate lists c1 and c2 by:
      1) min |(f2-f1) - expected_sep|
      2) max (p1+p2)
      3) min |center - fc|
    """
    best = None
    best_sep_err = 1e99
    best_sum_p = -1e99
    best_center_err = 1e99

    for f1, p1 in c1:
        for f2, p2 in c2:
            if f2 <= f1:
                continue
            if enforce_straddle_fc and not (f1 < fc_hz < f2):
                continue

            sep = f2 - f1
            sep_err = abs(sep - expected_sep_hz)
            center = 0.5 * (f1 + f2)
            center_err = abs(center - fc_hz)
            sum_p = p1 + p2

            # sep_err, then -sum_p, then center_err
            better = False
            if sep_err < best_sep_err - 1e-9:
                better = True
            elif abs(sep_err - best_sep_err) < 1e-9 and sum_p > best_sum_p + 1e-9:
                better = True
            elif abs(sep_err - best_sep_err) < 1e-9 and abs(sum_p - best_sum_p) < 1e-9 and center_err < best_center_err:
                better = True

            if better:
                best = (f1, p1, f2, p2, sep, sep_err, center, center_err)
                best_sep_err = sep_err
                best_sum_p = sum_p
                best_center_err = center_err

    return best


def main():
    ap = argparse.ArgumentParser(description="IM3 analyzer with robust two-tone locking.")
    ap.add_argument("iq_file", help="IQ file path")
    ap.add_argument("--format", choices=["rtlsdr", "hackrf"], default="rtlsdr")
    ap.add_argument("--fc", type=float, default=915e6)
    ap.add_argument("--fs", type=float, default=2_000_000.0)
    ap.add_argument("--f1", type=float, default=914.75e6)
    ap.add_argument("--f2", type=float, default=915.25e6)

    ap.add_argument("--nfft", type=int, default=262144)
    ap.add_argument("--navg", type=int, default=10)

    ap.add_argument("--search_window_hz", type=float, default=250_000.0,
                    help="Search window around nominal f1/f2 to collect candidates")
    ap.add_argument("--exclude_fc_hz", type=float, default=150_000.0,
                    help="Exclude peaks within +-this of fc to avoid LO/carrier leakage being picked as a tone")
    ap.add_argument("--cand_k", type=int, default=6)
    ap.add_argument("--cand_minsep_hz", type=float, default=10_000.0)

    ap.add_argument("--peak_window_hz", type=float, default=30_000.0,
                    help="Peak window for measuring fundamentals/IM3 once tones are locked")

    ap.add_argument("--span_mhz", type=float, default=2.4)
    ap.add_argument("--tag", type=str, default="capture")

    args = ap.parse_args()

    iq_path = Path(args.iq_file)
    if not iq_path.exists():
        raise FileNotFoundError(f"IQ file not found: {iq_path}")

    # Read IQ
    if args.format == "rtlsdr":
        x = read_rtlsdr_u8iq(str(iq_path))
    else:
        x = read_hackrf_i8iq(str(iq_path))

    # PSD
    f_hz, p_db = psd_db_avg(x, fs=args.fs, fc=args.fc, nfft=args.nfft, navg=args.navg)

    # Candidate lists
    w = args.search_window_hz
    c1 = peak_candidates(
        f_hz, p_db, args.f1 - w, args.f1 + w,
        k=args.cand_k, min_sep_hz=args.cand_minsep_hz,
        exclude_center_hz=args.fc, exclude_halfwidth_hz=args.exclude_fc_hz
    )
    c2 = peak_candidates(
        f_hz, p_db, args.f2 - w, args.f2 + w,
        k=args.cand_k, min_sep_hz=args.cand_minsep_hz,
        exclude_center_hz=args.fc, exclude_halfwidth_hz=args.exclude_fc_hz
    )

    if len(c1) == 0 or len(c2) == 0:
        raise RuntimeError(f"Could not find candidates (c1={len(c1)}, c2={len(c2)}). "
                           f"Try increasing --search_window_hz or reducing --exclude_fc_hz.")

    expected_sep = args.f2 - args.f1  # ~500 kHz
    best = choose_tone_pair(c1, c2, expected_sep, args.fc, enforce_straddle_fc=True)

    if best is None:
        # relax straddle constraint if needed
        best = choose_tone_pair(c1, c2, expected_sep, args.fc, enforce_straddle_fc=False)

    if best is None:
        raise RuntimeError("Failed to lock onto a valid tone pair. Try adjusting candidate settings.")

    f1_meas, p1_meas, f2_meas, p2_meas, sep, sep_err, f_center, center_err = best

    # Compute IM3 metrics using measured tones
    metrics = im3_metrics(f_hz, p_db, f1_meas, f2_meas, window_hz=args.peak_window_hz)
    metrics.update({
        "fc_hz": float(args.fc),
        "fs_hz": float(args.fs),
        "f1_nom_hz": float(args.f1),
        "f2_nom_hz": float(args.f2),
        "f1_meas_hz": float(f1_meas),
        "f2_meas_hz": float(f2_meas),
        "p1_meas_db": float(p1_meas),
        "p2_meas_db": float(p2_meas),
        "expected_sep_hz": float(expected_sep),
        "measured_sep_hz": float(sep),
        "sep_err_hz": float(sep_err),
        "tone_center_hz": float(f_center),
        "center_err_hz": float(center_err),
        "exclude_fc_hz": float(args.exclude_fc_hz),
        "search_window_hz": float(args.search_window_hz),
    })

    print("=== Tone lock (fixed) ===")
    print(f"f1_meas offset from center: {(f1_meas - f_center)/1e3:+.1f} kHz   p1={p1_meas:.2f} dB")
    print(f"f2_meas offset from center: {(f2_meas - f_center)/1e3:+.1f} kHz   p2={p2_meas:.2f} dB")
    print(f"measured separation: {sep/1e3:.1f} kHz  (err {sep_err/1e3:.1f} kHz)")
    print(f"tone_center shift from fc: {(f_center - args.fc)/1e3:+.1f} kHz")
    print("\n=== IM3 metrics ===")
    for k in ["pfund_db", "pim3_db", "delta_db", "oip3_rel_db"]:
        print(f"{k}: {metrics[k]}")

    # Save JSON
    Path("data").mkdir(exist_ok=True)
    Path("plots").mkdir(exist_ok=True)

    json_path = Path("data") / f"{args.tag}_im3.json"
    json_path.write_text(json.dumps(metrics, indent=2))
    print("Saved:", json_path)

    # Plot relative to tone center (this makes expected locations show at +-0.25 and +-0.75 MHz)
    x_mhz = (f_hz - f_center) / 1e6

    plt.figure(figsize=(10, 4))
    plt.plot(x_mhz, p_db)
    plt.xlabel("Frequency offset from tone_center (MHz)")
    plt.ylabel("PSD (dB, relative)")
    plt.title(f"IM3 PSD ({args.tag})")
    plt.grid(True)

    # Mark tones and IM3
    for ff, label in [
        (f1_meas, "f1"),
        (f2_meas, "f2"),
        (metrics["fim3_low_hz"], "IM3-"),
        (metrics["fim3_high_hz"], "IM3+"),
    ]:
        plt.axvline((ff - f_center)/1e6, linestyle="--")
        plt.text((ff - f_center)/1e6, np.max(p_db)-5, label, rotation=90, va="top")

    half = args.span_mhz / 2.0
    plt.xlim(-half, +half)

    png_path = Path("plots") / f"{args.tag}_im3_psd_locked.png"
    plt.tight_layout()
    plt.savefig(png_path, dpi=200)
    plt.show()
    print("Saved:", png_path)


if __name__ == "__main__":
    main()

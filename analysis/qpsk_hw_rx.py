import argparse
import json
from pathlib import Path
import numpy as np
from scipy.signal import lfilter

from rf_io import read_rtlsdr_u8iq
from qpsk_lib import (
    parse_meta, generate_reference, mix_down,
    coarse_cfo_qpsk4, correlate_find_peak, fine_cfo_and_channel,
    qpsk_to_bits
)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iq", required=True, help="RTL-SDR u8 IQ capture file")
    ap.add_argument("--meta", default=None, help="waveforms/qpsk_...txt")
    ap.add_argument("--fc", type=float, default=915e6, help="RF center freq for CFO ppm")
    ap.add_argument("--fs", type=float, default=2_000_000.0)
    ap.add_argument("--search_s", type=float, default=1.0, help="seconds of IQ to search")
    ap.add_argument("--out", type=str, default="qpsk_hw")
    ap.add_argument("--mask_frac", type=float, default=0.05)
    ap.add_argument("--coarse", choices=["qpsk4", "none"], default="qpsk4")
    args = ap.parse_args()

    params = parse_meta(args.meta)
    params["fs"] = int(args.fs)

    tx_ref, sym_stream, pre_syms, payload_bits, h = generate_reference(params)

    # Load RX
    rx = read_rtlsdr_u8iq(args.iq).astype(np.complex64)
    rx = rx - np.mean(rx)

    search_len = min(len(rx), int(args.search_s * args.fs))
    rx_search = rx[:search_len]

    # Coarse CFO (since we saw ~+57 kHz LO offset in the IM3 tests)
    cfo_coarse = 0.0
    if args.coarse == "qpsk4":
        cfo_coarse = coarse_cfo_qpsk4(rx_search, fs=args.fs)

    rx_search_c = mix_down(rx_search, fs=args.fs, f_hz=cfo_coarse)
    rx_c = mix_down(rx, fs=args.fs, f_hz=cfo_coarse)

    # Burst detect by correlation with known sample-rate reference
    k0, corr = correlate_find_peak(rx_search_c, tx_ref)

    # Extract one burst-length segment
    L = len(tx_ref)
    rx_seg = rx_c[k0:k0+L]
    if len(rx_seg) < L:
        raise RuntimeError("Not enough samples in search window. Increase --search_s.")

    # Fine CFO + channel estimate
    cfo_fine, h_hat, rx_cfo, mask = fine_cfo_and_channel(rx_seg, tx_ref, fs=args.fs, mask_frac=args.mask_frac)
    cfo_total = cfo_coarse + cfo_fine

    # Equalize to roughly match tx_ref
    rx_eq = rx_cfo / (h_hat + 1e-12)

    # Sample EVM vs tx_ref on masked samples
    evm_samp = np.sqrt(np.mean(np.abs(rx_eq[mask] - tx_ref[mask])**2) / np.mean(np.abs(tx_ref[mask])**2))
    evm_samp_pct = float(100.0 * evm_samp)

    # Matched filter (RRC)
    y = lfilter(h, [1.0], rx_eq)

    sps = params["sps"]
    g = (len(h) - 1) // 2
    n_syms = len(sym_stream)
    guard_syms = params["guard_syms"]
    n_pre = len(pre_syms)
    n_pay = params["payload_syms"]

    # Search symbol timing phase (0..sps-1) using preamble EVM
    best = dict(evm=1e9, tau=0, g2=1+0j, sym_rx=None)
    for tau in range(sps):
        idxs = tau + 2*g + np.arange(n_syms) * sps
        idxs = idxs[idxs < len(y)]
        sym_rx = y[idxs]
        if len(sym_rx) < guard_syms + n_pre + 10:
            continue

        pre_start = guard_syms
        pre_stop = guard_syms + n_pre
        sym_tx_pre = sym_stream[pre_start:pre_stop]
        sym_rx_pre = sym_rx[pre_start:pre_stop]

        g2 = np.vdot(sym_tx_pre, sym_rx_pre) / np.vdot(sym_tx_pre, sym_tx_pre)
        sym_rx_al = sym_rx_pre / (g2 + 1e-12)

        evm_pre = np.sqrt(np.mean(np.abs(sym_rx_al - sym_tx_pre)**2) / np.mean(np.abs(sym_tx_pre)**2))

        if evm_pre < best["evm"]:
            best = dict(evm=float(evm_pre), tau=tau, g2=complex(g2), sym_rx=sym_rx)

    if best["sym_rx"] is None:
        raise RuntimeError("Symbol timing search failed. Try higher TX power or less attenuation, and ensure fs matches.")

    sym_rx = best["sym_rx"]
    tau_best = best["tau"]
    g2_best = best["g2"]

    # Use preamble+payload region
    start = guard_syms
    end = min(len(sym_rx), guard_syms + n_pre + n_pay)

    sym_tx_use = sym_stream[start:end]
    sym_rx_use = sym_rx[start:end] / (g2_best + 1e-12)

    # Symbol EVM (%)
    evm_sym = np.sqrt(np.mean(np.abs(sym_rx_use - sym_tx_use)**2) / np.mean(np.abs(sym_tx_use)**2))
    evm_sym_pct = float(100.0 * evm_sym)

    # Payload BER (after preamble)
    sym_rx_payload = sym_rx_use[n_pre:n_pre + n_pay]
    bits_hat = qpsk_to_bits(sym_rx_payload)
    bits_true = payload_bits[:len(bits_hat)]
    ber = float(np.mean(bits_hat != bits_true)) if len(bits_true) else float("nan")

    # CFO ppm
    cfo_ppm = float(cfo_total / args.fc * 1e6)

    metrics = {
        "iq_file": args.iq,
        "fc_hz": float(args.fc),
        "fs_hz": float(args.fs),
        "burst_start_sample": int(k0),
        "coarse_cfo_hz": float(cfo_coarse),
        "fine_cfo_hz": float(cfo_fine),
        "cfo_total_hz": float(cfo_total),
        "cfo_ppm": float(cfo_ppm),
        "h_hat_mag": float(np.abs(h_hat)),
        "h_hat_phase_deg": float(np.angle(h_hat, deg=True)),
        "timing_tau_samples": int(tau_best),
        "evm_preamble_pct": float(100.0 * best["evm"]),
        "evm_sample_pct": float(evm_samp_pct),
        "evm_symbol_pct": float(evm_sym_pct),
        "payload_ber": float(ber),
        "payload_bits_used": int(len(bits_true)),
        "notes": "Correlation sync + coarse CFO(QPSK^4) + fine CFO slope + single-tap channel + matched filter + timing search + hard-decision BER",
    }

    Path("results").mkdir(exist_ok=True)
    Path("plots").mkdir(exist_ok=True)

    out_json = Path("results") / f"{args.out}_metrics.json"
    out_json.write_text(json.dumps(metrics, indent=2))
    print(json.dumps(metrics, indent=2))
    print("Saved:", out_json)

    # Plots
    import matplotlib.pyplot as plt

    # Correlation around peak
    win = 4000
    lo = max(0, k0 - win)
    hi = min(len(corr), k0 + win)
    plt.figure(figsize=(8, 3))
    plt.plot(np.abs(corr[lo:hi]))
    plt.title("Burst detection via correlation |corr| around peak")
    plt.xlabel("Index (samples)")
    plt.ylabel("|corr| (arb)")
    plt.grid(True)
    p_corr = Path("plots") / f"{args.out}_corr.png"
    plt.tight_layout()
    plt.savefig(p_corr, dpi=200)
    print("Saved:", p_corr)

    # Constellation (payload)
    plt.figure(figsize=(4, 4))
    plt.scatter(np.real(sym_rx_payload), np.imag(sym_rx_payload), s=2)
    plt.title("RX QPSK constellation (payload, equalized)")
    plt.xlabel("I")
    plt.ylabel("Q")
    plt.grid(True)
    plt.axis("equal")
    p_const = Path("plots") / f"{args.out}_constellation.png"
    plt.tight_layout()
    plt.savefig(p_const, dpi=200)
    print("Saved:", p_const)


if __name__ == "__main__":
    main()

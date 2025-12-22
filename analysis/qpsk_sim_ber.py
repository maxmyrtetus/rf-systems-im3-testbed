import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
import csv

from qpsk_lib import bits_to_qpsk, qpsk_to_bits

def main():
    rng = np.random.default_rng(0)
    snr_db_list = np.arange(0, 13, 1)   # 0..12 dB
    n_bits = 400_000

    ber_list = []
    for snr_db in snr_db_list:
        bits = rng.integers(0, 2, size=n_bits, dtype=np.int8)
        syms = bits_to_qpsk(bits)

        snr_lin = 10 ** (snr_db / 10.0)   # Es/N0
        N0 = 1.0 / snr_lin
        sigma = np.sqrt(N0 / 2.0)
        noise = sigma * (rng.standard_normal(len(syms)) + 1j * rng.standard_normal(len(syms)))

        r = syms + noise
        bits_hat = qpsk_to_bits(r)
        ber = float(np.mean(bits_hat != bits))
        ber_list.append(ber)
        print(f"SNR={snr_db:2d} dB  BER={ber:.3e}")

    Path("plots").mkdir(exist_ok=True)
    Path("results").mkdir(exist_ok=True)

    # CSV
    csv_path = Path("results/qpsk_ber_vs_snr.csv")
    with csv_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["snr_db", "ber"])
        for snr_db, ber in zip(snr_db_list, ber_list):
            w.writerow([snr_db, ber])
    print("Saved:", csv_path)

    # Plot
    plt.figure(figsize=(6, 4))
    plt.semilogy(snr_db_list, ber_list, marker="o")
    plt.xlabel("SNR (dB), Es/N0")
    plt.ylabel("BER")
    plt.title("QPSK BER vs SNR (AWGN simulation)")
    plt.grid(True, which="both")
    out_png = Path("plots/qpsk_ber_vs_snr.png")
    plt.tight_layout()
    plt.savefig(out_png, dpi=200)
    print("Saved:", out_png)

if __name__ == "__main__":
    main()

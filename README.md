# RF Systems IM3 Testbed @ 915 MHz + SDR Comms Metrics (QPSK)

I put together this inexpensive RF, SDR measuring project at 915MHz to gain practical experience in:
- examining RF front-end tradeoffs and linearity (IM3 distortions)
- and create repeatable IQ recordings to gauge receiver performance (using metrics like sync/CFO/channel/EVM/BER)

**Hardware:** includes fixed attenuators, Nooelec LaNA LNA, a HackRF clone (our transmitter - TX), RTL-SDR Blog V4 (receiver - RX), a 915 MHz bandpass SAW filter, and NanoVNA to find S-parameters.  
**Band:** 915 MHz ISM.  
The purpose of the repository is to create a small SDR setup that can test RF linearity (IM3s) and report communications and sensing data.

---

## Measured results (IM3, two-tone @ +-.250 MHz)
I put up two tones: f1 = 914.750 MHz and f2 = 915.250 MHz. Where there are IM3s at +/-750 MHz respectively, in relation to the tone center (915MHz).

**Settings used for all these comparisons:** navg=80, nfft=131072

### IM3 (dBc) across front-end configurations
- **Baseline (HackRF -> pads -> RTL), pre0:**  
  delta_db = **40.2929 dB**  (IM3 ≈ −40.29 dBc)  
  Plot: `plots/base_pre0_navg80_im3_psd_locked.png`

- **SAW only (HackRF -> SAW -> pads -> RTL), pre0:**  
  delta_db = **39.6334 dB**  
  Plot: `plots/saw_pre0_navg80_im3_psd_locked.png`

- **SAW + LaNA (HackRF -> SAW -> LaNA -> pads -> RTL), pre0:**  
  delta_db = **45.2724 dB** (IM3 ≈ −45.27 dBc)  
  Plot: `plots/saw_lna_pre0_navg80_im3_psd_locked.png`

With navg=80, we can observe that the IM3 peaks are easily detectable because they are located around 18dB above the noise floor.

## QPSK comms metrics (simulation)
- QPSK BER vs SNR (AWGN): `plots/qpsk_ber_vs_snr.png` (which was generated with `analysis/qpsk_sim_ber.py`)

## QPSK comms metrics (hardware status)
- The Burst correlation lock + CFO estimate seem to be working.
- However, the EVM/BER is not reliable yet.
- The scripts for burst sync, coarse+fine CFO, single-tap channel estimation, matched filtering, timing search, EVM, and BER have all been implemented/
- Yet, Hardware validation in progress (capturing `data/qpsk_rx.bin` as well as iterating SNR/levels). I got some faulty number and it is most likely due to a problem in the script: `analysis/qpsk_hw_rx.py`

---

## requirements:
```bash
pip install -r requirements.txt

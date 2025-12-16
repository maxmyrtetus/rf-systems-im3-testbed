Frequencies 
Center: fc = 915.000e6
Tone 1: f1 = 914.750e6
Tone 2: f2 = 915.250e6
IM3: f_im3_low = 914.250e6, f_im3_high = 915.750e6

This keeps everything in a ~1.5 MHz span that the RTL-SDR can handle.

Data naming:
Use:
data/chain0_txgainXX_attYY_u8iq.bin
data/chain1_txgainXX_attYY_u8iq.bin
data/chain2_txgainXX_attYY_u8iq.bin

Where:
XX = TX SDR gain setting (or generator level)
YY = total attenuation into the RTL-SDR
import numpy as np

def peak_near(f, p_db, f0_hz, window_hz=30_000):
    m = (f > f0_hz - window_hz) & (f < f0_hz + window_hz)
    if not np.any(m):
        return float("nan")
    return float(np.max(p_db[m]))

def im3_metrics(f, p_db, f1, f2, window_hz=30_000):
    fim3_low = 2*f1 - f2
    fim3_high = 2*f2 - f1

    p1 = peak_near(f, p_db, f1, window_hz)
    p2 = peak_near(f, p_db, f2, window_hz)
    pim3l = peak_near(f, p_db, fim3_low, window_hz)
    pim3h = peak_near(f, p_db, fim3_high, window_hz)

    pfund = float(np.nanmean([p1, p2]))
    pim3  = float(np.nanmean([pim3l, pim3h]))
    delta = float(pfund - pim3)

    # Relative OIP3 estimate 
    oip3_rel = float(pfund + delta/2.0)

    return {
        "f1_hz": float(f1),
        "f2_hz": float(f2),
        "fim3_low_hz": float(fim3_low),
        "fim3_high_hz": float(fim3_high),
        "p1_db": p1,
        "p2_db": p2,
        "pim3l_db": pim3l,
        "pim3h_db": pim3h,
        "pfund_db": pfund,
        "pim3_db": pim3,
        "delta_db": delta,
        "oip3_rel_db": oip3_rel,
    }

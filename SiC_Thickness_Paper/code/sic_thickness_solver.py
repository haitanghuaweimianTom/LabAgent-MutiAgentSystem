#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SiC Epitaxial Layer Thickness Solver
2025 Gaojiaoshebei National College Student Mathematical Modeling Contest - Problem B

Model: d = 1/(2*n*cos(theta)*Delta_sigma)
Usage: python sic_thickness_solver.py
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

import openpyxl
import numpy as np
from scipy.signal import find_peaks
from scipy.ndimage import gaussian_filter1d
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import json as js
import os

DATA_DIR = "E:/cherryClaw/math_modeling_multi_agent"
OUT_DIR = "E:/cherryClaw/math_modeling_multi_agent/SiC_Thickness_Paper/figures"
os.makedirs(OUT_DIR, exist_ok=True)


def load_excel(path):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["Sheet1"]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    wn = np.array([r[0] for r in rows[1:] if r[0] is not None], dtype=float)
    refl = np.array([r[1] for r in rows[1:] if r[1] is not None], dtype=float)
    return wn, refl


samples = {
    "SiC-1": load_excel(DATA_DIR + "/附件1.xlsx"),
    "SiC-2": load_excel(DATA_DIR + "/附件2.xlsx"),
    "Si-1": load_excel(DATA_DIR + "/附件3.xlsx"),
    "Si-2": load_excel(DATA_DIR + "/附件4.xlsx")
}


def n_sic(sig):
    lam = 1e4 / sig
    n2 = 6.7 * (1 + 0.46/6.7 * lam**2/(lam**2 - 0.106**2))
    return np.sqrt(max(n2, 2.5**2))


def n_si(sig):
    return 3.42


def find_peaks_wn(wn, refl, region, sigma=5, dist=5, prom=0.5):
    mask = (wn >= region[0]) & (wn <= region[1])
    wn_r = wn[mask]
    refl_r = refl[mask]
    refl_sm = gaussian_filter1d(refl_r, sigma=sigma)
    peaks, _ = find_peaks(refl_sm, distance=dist, prominence=prom)
    return wn_r[peaks], refl_r[peaks], refl_sm, wn_r


def solve_epitaxial(wn, refl, mat, n_func, region):
    pk, _, _, _ = find_peaks_wn(wn, refl, region, sigma=5, dist=5, prom=0.5)
    if len(pk) < 3:
        return None
    spacings = np.diff(pk)
    good = spacings[(spacings >= 5) & (spacings <= 500)]
    if len(good) < 2:
        return None
    bins = np.arange(good.min() - 2.5, good.max() + 7.5, 5)
    hist, bins2 = np.histogram(good, bins=bins)
    dom_dsigma = (bins[np.argmax(hist)] + bins[np.argmax(hist) + 1]) / 2
    valid = good[np.abs(good - dom_dsigma) < 0.3 * dom_dsigma]
    if len(valid) < 2:
        valid = good
    dsigma = np.mean(valid)
    ds_std = np.std(valid)
    seq = [pk[0]]
    for i, sp in enumerate(np.diff(pk)):
        if abs(sp - dsigma) < 0.3 * dsigma:
            seq.append(pk[i + 1])
    seq = np.array(seq)
    n = n_func(float(np.median(seq)))
    d_um = 1e4 / (2 * n * dsigma)
    return {"dsigma": dsigma, "dsigma_std": ds_std, "d_um": d_um, "d_std": d_um*(ds_std/dsigma), "n": n, "seq": seq}


def main():
    results = {}
    print("=" * 60)
    print("SiC and Si Epitaxial Layer Thickness Analysis")
    print("=" * 60)
    for name, wn, refl in [("SiC-1", samples["SiC-1"][0], samples["SiC-1"][1]),
                            ("SiC-2", samples["SiC-2"][0], samples["SiC-2"][1])]:
        r = solve_epitaxial(wn, refl, "sic", n_sic, (900, 1300))
        results[name] = r
        if r:
            print(f"  [{name}] ds={round(r['dsigma'], 3)} cm-1, n={round(r['n'], 4)}, d={round(r['d_um'], 3)} um")
    for name, wn, refl in [("Si-1", samples["Si-1"][0], samples["Si-1"][1]),
                            ("Si-2", samples["Si-2"][0], samples["Si-2"][1])]:
        r = solve_epitaxial(wn, refl, "si", n_si, (400, 3500))
        results[name] = r
        if r:
            print(f"  [{name}] ds={round(r['dsigma'], 3)} cm-1, n={round(r['n'], 3)}, d={round(r['d_um'], 4)} um")
    fig, axes = plt.subplots(2, 2, figsize=(16, 11))
    for idx, (name, (wn, refl)) in enumerate([("SiC-1", samples["SiC-1"]), ("SiC-2", samples["SiC-2"]),
                                                ("Si-1", samples["Si-1"]), ("Si-2", samples["Si-2"])]):
        ax = axes[idx // 2][idx % 2]
        mat = "sic" if "SiC" in name else "si"
        region = (900, 1300) if mat == "sic" else (400, 3500)
        mask = (wn >= region[0]) & (wn <= region[1])
        wn_s = wn[mask]
        refl_s = refl[mask]
        ax.plot(wn_s, refl_s, "b-", lw=0.5, alpha=0.6, label="Raw")
        refl_sm = gaussian_filter1d(refl_s, sigma=(5 if mat == "sic" else 3))
        ax.plot(wn_s, refl_sm, "r-", lw=1.2, label="Smoothed")
        r = results[name]
        if r and len(r["seq"]) > 0:
            seq = r["seq"]
            pk_v = np.interp(seq, wn_s, refl_sm)
            ax.plot(seq, pk_v, "g^", ms=10, label=f"Peaks N={len(seq)}", zorder=5)
            for p in seq:
                ax.axvline(p, color="green", alpha=0.25, lw=0.8)
            ax.set_title(f"{name}  d={round(r['d_um'], 2)} um  delta={round(r['dsigma'], 2)} cm-1", fontsize=12, fontweight="bold")
        ax.set_xlabel("Wavenumber (cm-1)")
        ax.set_ylabel("Reflectance (%)")
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.25)
    plt.tight_layout()
    fig.savefig(OUT_DIR + "/sic_thickness_results.png", dpi=180, bbox_inches="tight")
    out = {name: {"thickness_um": round(r["d_um"], 4), "thickness_cm": round(r["d_um"]*1e-4, 8),
                  "delta_sigma_cm1": round(r["dsigma"], 4), "n": round(r["n"], 4),
                  "peak_positions": [round(float(x), 2) for x in r["seq"]], "num_peaks": len(r["seq"]),
                  "model": "dual_beam" if "SiC" in name else "multi_beam_FP",
                  "is_multi_beam": False if "SiC" in name else True}
           for name, r in results.items() if r}
    with open(OUT_DIR + "/thickness_results.json", "w", encoding="utf-8") as f:
        js.dump(out, f, ensure_ascii=False, indent=2)
    print("\nFINAL RESULTS:")
    for name, r in out.items():
        print(f"  {name}: d={r['thickness_um']} um, ds={r['delta_sigma_cm1']} cm-1, n={r['n']}")
    return results


if __name__ == "__main__":
    main()
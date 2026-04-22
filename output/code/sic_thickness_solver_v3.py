#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SiC外延层厚度测定 - 红外干涉法 (最终版)
2025高教社杯全国大学生数学建模竞赛 B题

基于物理原理的严格峰值检测算法
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

import openpyxl
import numpy as np
from scipy.signal import find_peaks, savgol_filter
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import json as js
import os

DATA_DIR = "E:/cherryClaw/math_modeling_multi_agent"
OUT_DIR = "E:/cherryClaw/math_modeling_multi_agent/output/figures"
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


def n_sic(sigma):
    """4H-SiC Sellmeier色散公式"""
    lam = 1e4 / sigma
    n2 = 6.7 * (1 + 0.46 * lam**2 / (lam**2 - 0.106**2))
    return np.sqrt(np.maximum(n2, 2.5**2))


def n_si(sigma):
    return 3.42


def find_equidistant_sequence(peaks, tolerance=0.15):
    """
    从检测到的峰中找出等间距序列
    peaks: 波数数组
    tolerance: 允许的相对偏差 (15%)
    返回: (等间距序列, 间距均值, 间距标准差) 或 None
    """
    if len(peaks) < 2:
        return None

    n = len(peaks)
    best_seq = None
    best_count = 0
    best_std = float('inf')

    # 尝试所有峰对作为可能的序列起始点
    for i in range(n):
        for j in range(i+1, n):
            spacing = peaks[j] - peaks[i]
            if spacing <= 0:
                continue
            expected_count = int((peaks[-1] - peaks[i]) / spacing) + 1

            # 构建等间距序列
            seq = [peaks[i]]
            for k in range(i+1, n):
                expected_pos = seq[-1] + spacing
                if abs(peaks[k] - expected_pos) < tolerance * spacing:
                    seq.append(peaks[k])

            if len(seq) >= 2:
                spacings_in_seq = np.diff(seq)
                std = np.std(spacings_in_seq)
                if len(seq) > best_count or (len(seq) == best_count and std < best_std):
                    best_seq = seq
                    best_count = len(seq)
                    best_std = std

    if best_seq is None or len(best_seq) < 2:
        return None

    spacings_final = np.diff(best_seq)
    return best_seq, np.mean(spacings_final), np.std(spacings_final)


def solve_sample(wn, refl, n_func, region, name, is_sic=True):
    """
    求解外延层厚度
    """
    mask = (wn >= region[0]) & (wn <= region[1])
    wn_r = wn[mask]
    refl_r = refl[mask]

    best_result = None

    # 尝试不同的平滑和峰检测参数
    for sigma in [5, 7, 9, 11]:
        for prom in [0.3, 0.5, 0.7, 1.0]:
            for dist in [3, 5, 7]:

                # Savitzky-Golay平滑
                if len(refl_r) > sigma:
                    refl_sm = savgol_filter(refl_r, window_length=min(sigma*2+1, len(refl_r)-1), polyorder=3)
                else:
                    refl_sm = refl_r

                peaks, _ = find_peaks(refl_sm, distance=dist, prominence=prom)

                if len(peaks) < 2:
                    continue

                peak_positions = wn_r[peaks]

                # 找等间距序列
                result = find_equidistant_sequence(peak_positions, tolerance=0.2)

                if result is not None:
                    seq, spacing_mean, spacing_std = result

                    # 验收标准: 至少有3个峰或2个峰且std较小
                    if len(seq) >= 3 or (len(seq) == 2 and spacing_std < spacing_mean * 0.05):
                        n_vals = n_func(np.array(seq))
                        n_avg = np.mean(n_vals)

                        d = 1e4 / (2 * n_avg * spacing_mean)
                        d_std = d * (spacing_std / spacing_mean) if spacing_mean > 0 else 0

                        # 计算干涉条纹对比度
                        R_max = np.max(refl_sm)
                        R_min = np.min(refl_sm)
                        K = (R_max - R_min) / (R_max + R_min) if (R_max + R_min) > 0 else 0

                        # 评分: 优先选择更多峰的序列
                        score = len(seq) * 100 - spacing_std

                        if best_result is None or score > best_result['score']:
                            best_result = {
                                'score': score,
                                'peaks': seq,
                                'spacing_cm_1': spacing_mean,
                                'spacing_std': spacing_std,
                                'n': n_avg,
                                'thickness_um': d,
                                'thickness_std': d_std,
                                'num_peaks': len(seq),
                                'fringe_contrast': K,
                                'is_multi_beam': K > 0.3,
                                'sigma': sigma,
                                'prominence': prom,
                                'raw_peaks': peak_positions.tolist()
                            }

    return best_result


def analyze_all():
    """分析所有样品"""
    results = {}

    # SiC样品
    sic_region = (900, 1300)
    for name in ["SiC-1", "SiC-2"]:
        print(f"\n{'='*60}")
        print(f"Analyzing {name} (SiC epitaxial layer)")
        print(f"{'='*60}")
        wn, refl = samples[name]
        r = solve_sample(wn, refl, n_sic, sic_region, name, is_sic=True)
        if r:
            results[name] = r
            print(f"  Delta_sigma = {r['spacing_cm_1']:.3f} +/- {r['spacing_std']:.3f} cm^-1")
            print(f"    n = {r['n']:.4f}")
            print(f"    d = {r['thickness_um']:.3f} +/- {r['thickness_std']:.3f} um")
            print(f"    Detected {r['num_peaks']} peaks in equidistant sequence")
            print(f"    All detected peaks (raw): {r['raw_peaks']}")
            print(f"    Sequence peaks: {r['peaks']}")
            print(f"    Fringe contrast K = {r['fringe_contrast']:.4f}")
            print(f"    Multi-beam interference: {'Yes' if r['is_multi_beam'] else 'No'}")
        else:
            print("  No valid result found")

    # Si样品
    si_region = (400, 3500)
    for name in ["Si-1", "Si-2"]:
        print(f"\n{'='*60}")
        print(f"Analyzing {name} (Si epitaxial layer)")
        print(f"{'='*60}")
        wn, refl = samples[name]
        r = solve_sample(wn, refl, n_si, si_region, name, is_sic=False)
        if r:
            results[name] = r
            print(f"  Delta_sigma = {r['spacing_cm_1']:.3f} +/- {r['spacing_std']:.3f} cm^-1")
            print(f"    n = {r['n']:.4f}")
            print(f"    d = {r['thickness_um']:.3f} +/- {r['thickness_std']:.3f} um")
            print(f"    Detected {r['num_peaks']} peaks in equidistant sequence")
            print(f"    Fringe contrast K = {r['fringe_contrast']:.4f}")
            print(f"    Multi-beam interference: {'Yes' if r['is_multi_beam'] else 'No'}")
        else:
            print("  No valid result found")

    return results


def plot_all_results(results):
    """绘制所有结果"""
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))

    configs = [
        ("SiC-1", samples["SiC-1"], (900, 1300)),
        ("SiC-2", samples["SiC-2"], (900, 1300)),
        ("Si-1", samples["Si-1"], (400, 3500)),
        ("Si-2", samples["Si-2"], (400, 3500))
    ]

    for idx, (name, (wn, refl), region) in enumerate(configs):
        ax = axes[idx // 2][idx % 2]

        mask = (wn >= region[0]) & (wn <= region[1])
        wn_s = wn[mask]
        refl_s = refl[mask]

        ax.plot(wn_s, refl_s, 'b-', lw=0.5, alpha=0.5, label='Raw')

        if len(refl_s) > 11:
            refl_sm = savgol_filter(refl_s, window_length=11, polyorder=3)
        else:
            refl_sm = refl_s
        ax.plot(wn_s, refl_sm, 'b-', lw=1.0, alpha=0.8, label='Smoothed')

        r = results.get(name)
        if r:
            # 标记所有检测到的峰
            raw_peaks = r.get('raw_peaks', [])
            if raw_peaks:
                raw_pk_v = np.interp(raw_peaks, wn_s, refl_sm)
                ax.plot(raw_peaks, raw_pk_v, 'yo', ms=8, label=f'All peaks (N={len(raw_peaks)})', alpha=0.5)

            # 标记等间距序列中的峰
            seq_peaks = r.get('peaks', [])
            if seq_peaks:
                seq_pk_v = np.interp(seq_peaks, wn_s, refl_sm)
                ax.plot(seq_peaks, seq_pk_v, 'g^', ms=12, label=f'Selected (N={len(seq_peaks)})', zorder=5)

                for p in seq_peaks:
                    ax.axvline(p, color='green', alpha=0.3, lw=1.0)

            title = f"{name}\nd = {r['thickness_um']:.2f} um, "
            title += "Delta_sigma = {0:.2f} cm^-1".format(r['spacing_cm_1'])
            if 'fringe_contrast' in r:
                title += ", K = {0:.3f}".format(r['fringe_contrast'])
            ax.set_title(title, fontsize=11, fontweight='bold')

        ax.set_xlabel("Wavenumber (cm^-1)")
        ax.set_ylabel("Reflectance (%)")
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.25)

    plt.tight_layout()
    fig.savefig(OUT_DIR + "/sic_thickness_results_v3.png", dpi=180, bbox_inches="tight")
    print(f"\nFigure saved: {OUT_DIR}/sic_thickness_results_v3.png")
    return fig


def save_results(results):
    """保存结果"""
    output = {}
    for name, r in results.items():
        item = {
            "thickness_um": round(float(r["thickness_um"]), 4),
            "thickness_cm": round(float(r["thickness_um"]) * 1e-4, 8),
            "delta_sigma_cm1": round(float(r["spacing_cm_1"]), 4),
            "delta_sigma_std": round(float(r.get("spacing_std", 0)), 4),
            "n": round(float(r["n"]), 4),
            "peak_positions": [round(float(x), 2) for x in r["peaks"]],
            "num_peaks": int(r["num_peaks"]),
            "raw_peak_positions": [round(float(x), 2) for x in r.get("raw_peaks", [])]
        }
        if "fringe_contrast" in r:
            item["fringe_contrast"] = round(float(r["fringe_contrast"]), 4)
            item["is_multi_beam"] = bool(r["is_multi_beam"])
        output[name] = item

    with open(OUT_DIR + "/thickness_results_v3.json", "w", encoding="utf-8") as f:
        js.dump(output, f, ensure_ascii=False, indent=2)
    print(f"JSON saved: {OUT_DIR}/thickness_results_v3.json")
    return output


if __name__ == "__main__":
    results = analyze_all()
    plot_all_results(results)
    output = save_results(results)

    print("\n" + "="*60)
    print("Final Results Summary")
    print("="*60)
    for name, r in output.items():
        print(f"\n{name}:")
        print(f"  Thickness d = {r['thickness_um']:.4f} um")
        print(f"  Delta_sigma = {r['delta_sigma_cm1']:.4f} +/- {r['delta_sigma_std']:.4f} cm^-1")
        print(f"  n = {r['n']:.4f}")
        print(f"  Number of peaks = {r['num_peaks']}")
        if "fringe_contrast" in r:
            print(f"  Fringe contrast K = {r['fringe_contrast']:.4f}")
            print(f"  Multi-beam: {'Yes' if r['is_multi_beam'] else 'No'}")
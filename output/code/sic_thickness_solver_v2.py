#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SiC外延层厚度测定 - 红外干涉法 (改进版)
2025高教社杯全国大学生数学建模竞赛 B题

问题1: 双光束干涉模型 d = 1/(2*n*cos(theta)*Delta_sigma)
问题3: 多光束Fabry-Perot干涉分析
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')
import openpyxl
import numpy as np
from scipy.signal import find_peaks, savgol_filter
from scipy.optimize import curve_fit
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import json as js
import os

DATA_DIR = "E:/cherryClaw/math_modeling_multi_agent"
OUT_DIR = "E:/cherryClaw/math_modeling_multi_agent/output/figures"
os.makedirs(OUT_DIR, exist_ok=True)


def load_excel(path):
    """加载Excel光谱数据"""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["Sheet1"]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    wn = np.array([r[0] for r in rows[1:] if r[0] is not None], dtype=float)
    refl = np.array([r[1] for r in rows[1:] if r[1] is not None], dtype=float)
    return wn, refl


# 加载所有数据
samples = {
    "SiC-1": load_excel(DATA_DIR + "/附件1.xlsx"),
    "SiC-2": load_excel(DATA_DIR + "/附件2.xlsx"),
    "Si-1": load_excel(DATA_DIR + "/附件3.xlsx"),
    "Si-2": load_excel(DATA_DIR + "/附件4.xlsx")
}


def n_sic(sigma):
    """4H-SiC Sellmeier色散公式
    n^2(lambda) = 6.7 * (1 + 0.46*lambda^2/(lambda^2 - 0.106^2))
    lambda in micrometers
    """
    lam = 1e4 / sigma  # convert wavenumber (cm^-1) to wavelength (μm)
    n2 = 6.7 * (1 + 0.46 * lam**2 / (lam**2 - 0.106**2))
    return np.sqrt(np.maximum(n2, 2.5**2))


def n_si(sigma):
    """Si折射率 (红外波段近似常数)"""
    return 3.42


def finesse(R):
    """Fabry-Perot腔的精细度
    F = pi * sqrt(R) / (1 - R)
    """
    if R >= 1:
        return float('inf')
    return np.pi * np.sqrt(R) / (1 - R) if R > 0 else float('inf')


def fringe_contrast(R_max, R_min):
    """干涉条纹对比度 (fringe contrast)
    K = (I_max - I_min) / (I_max + I_min)
    """
    return (R_max - R_min) / (R_max + R_min)


def multi_beam_condition(R1, R2, threshold=0.3):
    """判断是否产生多光束干涉的必要条件
    当对比度 K > threshold 时，认为多光束效应显著
    多光束干涉条件: R1 * R2 > 0.01 (即双方反射率足够高)
    """
    K_max = 2 * np.sqrt(R1 * R2) / (1 + R1 * R2)
    return K_max > threshold, K_max


def find_interference_peaks(wn, refl, region, sigma_smooth=5, min_dist=5, min_prom=0.3):
    """寻找干涉峰"""
    mask = (wn >= region[0]) & (wn <= region[1])
    wn_r = wn[mask]
    refl_r = refl[mask]

    # 平滑
    refl_sm = savgol_filter(refl_r, window_length=11, polyorder=3)

    # 找峰
    peaks, properties = find_peaks(refl_sm, distance=min_dist, prominence=min_prom)

    return wn_r[peaks], refl_r[peaks], refl_sm, wn_r


def analyze_peak_spacing(peaks):
    """分析峰间距分布"""
    if len(peaks) < 2:
        return None, None, None

    spacings = np.diff(peaks)

    # 直方图分析
    if len(spacings) > 0:
        bins = np.arange(spacings.min() - 5, spacings.max() + 10, 5)
        hist, bin_edges = np.histogram(spacings, bins=bins)
        dominant_bin = np.argmax(hist)
        dom_spacing = (bin_edges[dominant_bin] + bin_edges[dominant_bin + 1]) / 2

        # 筛选符合的间距
        valid = spacings[np.abs(spacings - dom_spacing) < 0.3 * dom_spacing]

        if len(valid) >= 2:
            mean_spacing = np.mean(valid)
            std_spacing = np.std(valid)
            return mean_spacing, std_spacing, valid

    return np.mean(spacings), np.std(spacings), spacings


def dual_beam_thickness(wn, refl, n_func, region, sample_name):
    """双光束干涉模型计算厚度"""
    peaks, _, refl_sm, wn_r = find_interference_peaks(wn, refl, region)

    if len(peaks) < 2:
        return None

    spacing, spacing_std, valid_spacings = analyze_peak_spacing(peaks)
    if spacing is None:
        return None

    # 计算折射率 (取峰位对应的折射率)
    n_values = n_func(peaks)
    n_avg = np.mean(n_values)

    # 厚度公式: d = 1/(2*n*Delta_sigma)
    d = 1e4 / (2 * n_avg * spacing)  # convert to μm

    # 误差传递
    d_std = d * (spacing_std / spacing) if spacing_std > 0 else 0

    return {
        "spacing_cm_1": spacing,
        "spacing_std": spacing_std,
        "n": n_avg,
        "thickness_um": d,
        "thickness_std": d_std,
        "peaks": peaks.tolist(),
        "num_peaks": len(peaks),
        "valid_spacings": valid_spacings.tolist() if valid_spacings is not None else []
    }


def multi_beam_analysis(wn, refl, n_func, region, sample_name):
    """多光束Fabry-Perot干涉分析"""
    result = dual_beam_thickness(wn, refl, n_func, region, sample_name)
    if result is None:
        return None

    # 计算干涉条纹对比度
    _, _, refl_sm, wn_r = find_interference_peaks(wn, refl, region)

    # 使用所有峰计算对比度
    R_max = np.max(refl_sm)
    R_min = np.min(refl_sm)
    K = fringe_contrast(R_max, R_min)

    result["fringe_contrast"] = K
    result["is_multi_beam"] = K > 0.3  # 阈值

    # 计算Fabry-Perot精细度估计
    # 对于理想FP腔: K = 2*sqrt(R1*R2)/(1+R1*R2)
    # 反解R: R = (sqrt(1-K^2) - (1-K)) / (sqrt(1-K^2) + (1-K))
    if K > 0 and K < 1:
        R_geo = np.sqrt(((1+K)**2 - (1-K)**2) / ((1+K)**2 + (1-K)**2))
        result["geometric_reflectivity"] = R_geo
    else:
        result["geometric_reflectivity"] = None

    return result


def enhanced_peak_detection(wn, refl, region, sample_type):
    """增强的峰检测算法 - 用于多峰分析"""
    mask = (wn >= region[0]) & (wn <= region[1])
    wn_r = wn[mask]
    refl_r = refl[mask]

    # 使用不同平滑参数找到最稳定的峰序列
    best_peaks = None
    best_spacing_std = float('inf')

    for sigma in [3, 5, 7, 9, 11]:
        for prom in [0.2, 0.3, 0.5, 0.7]:
            for dist in [3, 5, 7]:
                peaks, _ = find_peaks(refl_r, distance=dist, prominence=prom)

                if len(peaks) < 3:
                    continue

                spacings = np.diff(wn_r[peaks])
                spacing_std = np.std(spacings)
                spacing_mean = np.mean(spacings)

                # 寻找等间距序列
                if spacing_mean > 0:
                    relative_std = spacing_std / spacing_mean
                    if relative_std < best_spacing_std and relative_std < 0.15:
                        best_spacing_std = relative_std
                        best_peaks = (peaks.copy(), sigma, prom, dist, spacing_mean, spacing_std)

    if best_peaks is None:
        return None

    peaks, sigma, prom, dist, spacing_mean, spacing_std = best_peaks

    return {
        "peaks": wn_r[peaks].tolist(),
        "sigma": sigma,
        "prominence": prom,
        "spacing_mean": spacing_mean,
        "spacing_std": spacing_std,
        "relative_std": best_spacing_std
    }


def solve_all():
    """求解所有样品"""
    results = {}

    # SiC样品分析 (双光束干涉模型)
    sic_region = (900, 1300)
    for name in ["SiC-1", "SiC-2"]:
        wn, refl = samples[name]
        print(f"\n{'='*60}")
        print(f"分析 {name} (SiC外延层)")
        print(f"{'='*60}")

        # 基础分析
        r = dual_beam_thickness(wn, refl, n_sic, sic_region, name)
        if r:
            results[name] = r
            print(f"  双光束干涉模型:")
            print(f"    Δσ = {r['spacing_cm_1']:.3f} ± {r['spacing_std']:.3f} cm⁻¹")
            print(f"    n = {r['n']:.4f}")
            print(f"    d = {r['thickness_um']:.3f} ± {r['thickness_std']:.3f} μm")
            print(f"    检测到 {r['num_peaks']} 个干涉峰")

        # 增强分析
        r_enhanced = enhanced_peak_detection(wn, refl, sic_region, "SiC")
        if r_enhanced:
            print(f"  增强峰检测:")
            print(f"    Δσ = {r_enhanced['spacing_mean']:.3f} ± {r_enhanced['spacing_std']:.3f} cm⁻¹")
            print(f"    相对标准差 = {r_enhanced['relative_std']*100:.2f}%")
            print(f"    最优平滑参数: σ={r_enhanced['sigma']}, prom={r_enhanced['prominence']}")

            # 使用增强结果更新
            if r:
                r["enhanced_spacing"] = r_enhanced["spacing_mean"]
                r["enhanced_spacing_std"] = r_enhanced["spacing_std"]

    # Si样品分析 (多光束干涉)
    si_region = (400, 3500)
    for name in ["Si-1", "Si-2"]:
        wn, refl = samples[name]
        print(f"\n{'='*60}")
        print(f"分析 {name} (Si外延层)")
        print(f"{'='*60}")

        r = multi_beam_analysis(wn, refl, n_si, si_region, name)
        if r:
            results[name] = r
            print(f"  Δσ = {r['spacing_cm_1']:.3f} ± {r['spacing_std']:.3f} cm⁻¹")
            print(f"    n = {r['n']:.4f}")
            print(f"    d = {r['thickness_um']:.3f} ± {r['thickness_std']:.3f} μm")
            print(f"    干涉条纹对比度 K = {r['fringe_contrast']:.4f}")
            print(f"    多光束干涉: {'是' if r['is_multi_beam'] else '否'}")
            print(f"    检测到 {r['num_peaks']} 个干涉峰")

    return results


def plot_results(results):
    """绘制所有结果"""
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))

    plot_configs = [
        ("SiC-1", samples["SiC-1"], (900, 1300), "SiC"),
        ("SiC-2", samples["SiC-2"], (900, 1300), "SiC"),
        ("Si-1", samples["Si-1"], (400, 3500), "Si"),
        ("Si-2", samples["Si-2"], (400, 3500), "Si")
    ]

    for idx, (name, (wn, refl), region, mat) in enumerate(plot_configs):
        ax = axes[idx // 2][idx % 2]

        mask = (wn >= region[0]) & (wn <= region[1])
        wn_s = wn[mask]
        refl_s = refl[mask]

        ax.plot(wn_s, refl_s, 'b-', lw=0.5, alpha=0.5, label='Raw')

        # 平滑
        refl_sm = savgol_filter(refl_s, window_length=11, polyorder=3)
        ax.plot(wn_s, refl_sm, 'b-', lw=1.0, alpha=0.8, label='Smoothed')

        r = results.get(name)
        if r:
            peaks = r.get('peaks', [])
            if peaks:
                pk_v = np.interp(peaks, wn_s, refl_sm)
                ax.plot(peaks, pk_v, 'g^', ms=12, label=f'Peaks (N={len(peaks)})', zorder=5)

                # 标注峰间距
                for i, p in enumerate(peaks):
                    ax.axvline(p, color='green', alpha=0.2, lw=0.8)

                # 标题
                title = f"{name}\n"
                title += f"d = {r['thickness_um']:.2f} μm"
                title += f", Δσ = {r['spacing_cm_1']:.2f} cm⁻¹"
                if 'fringe_contrast' in r:
                    title += f", K = {r['fringe_contrast']:.3f}"
                ax.set_title(title, fontsize=11, fontweight='bold')
            else:
                ax.set_title(f"{name}", fontsize=11, fontweight='bold')

        ax.set_xlabel("Wavenumber (cm⁻¹)")
        ax.set_ylabel("Reflectance (%)")
        ax.legend(fontsize=9, loc='upper right')
        ax.grid(True, alpha=0.25)

    plt.tight_layout()
    fig.savefig(OUT_DIR + "/sic_thickness_results_v2.png", dpi=180, bbox_inches="tight")
    print(f"\nFigure saved: {OUT_DIR}/sic_thickness_results_v2.png")

    # 单独绘制SiC样品详细分析
    fig2, axes2 = plt.subplots(1, 2, figsize=(14, 5))

    for idx, name in enumerate(["SiC-1", "SiC-2"]):
        ax = axes2[idx]
        wn, refl = samples[name]

        # 900-1300 cm-1区域
        mask = (wn >= 900) & (wn <= 1300)
        wn_s = wn[mask]
        refl_s = refl[mask]

        ax.plot(wn_s, refl_s, 'b-', lw=1.0, alpha=0.7, label='Spectrum')
        refl_sm = savgol_filter(refl_s, window_length=11, polyorder=3)
        ax.plot(wn_s, refl_sm, 'r-', lw=1.5, label='Smoothed')

        r = results.get(name)
        if r and 'peaks' in r:
            for p in r['peaks']:
                ax.axvline(p, color='green', alpha=0.5, lw=1.5, linestyle='--')
                ax.annotate(f'{p:.1f}', (p, ax.get_ylim()[1]*0.95),
                           fontsize=9, ha='center', color='green')

        ax.set_xlabel("Wavenumber (cm⁻¹)")
        ax.set_ylabel("Reflectance (%)")
        ax.set_title(f"{name} - Interference Peaks Analysis")
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.25)

        # 插入表格数据
        if r:
            textstr = f"Δσ = {r['spacing_cm_1']:.2f} cm⁻¹\n"
            textstr += f"n = {r['n']:.4f}\n"
            textstr += f"d = {r['thickness_um']:.2f} μm"
            ax.text(0.02, 0.98, textstr, transform=ax.transAxes, fontsize=10,
                   verticalalignment='top', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

    plt.tight_layout()
    fig2.savefig(OUT_DIR + "/sic_detailed_analysis.png", dpi=180, bbox_inches="tight")
    print(f"Figure saved: {OUT_DIR}/sic_detailed_analysis.png")

    return fig, fig2


def save_results(results):
    """保存结果到JSON"""
    output = {}
    for name, r in results.items():
        item = {
            "thickness_um": round(float(r["thickness_um"]), 4),
            "thickness_cm": round(float(r["thickness_um"]) * 1e-4, 8),
            "delta_sigma_cm1": round(float(r["spacing_cm_1"]), 4),
            "delta_sigma_std": round(float(r.get("spacing_std", 0)), 4),
            "n": round(float(r["n"]), 4),
            "peak_positions": [round(float(x), 2) for x in r["peaks"]],
            "num_peaks": int(r["num_peaks"])
        }
        if "fringe_contrast" in r:
            item["fringe_contrast"] = round(float(r["fringe_contrast"]), 4)
            item["is_multi_beam"] = bool(r["is_multi_beam"])
        if "enhanced_spacing" in r:
            item["enhanced_delta_sigma"] = round(float(r["enhanced_spacing"]), 4)
        output[name] = item

    with open(OUT_DIR + "/thickness_results_v2.json", "w", encoding="utf-8") as f:
        js.dump(output, f, ensure_ascii=False, indent=2)
    print(f"JSON saved: {OUT_DIR}/thickness_results_v2.json")

    return output


if __name__ == "__main__":
    results = solve_all()
    plot_results(results)
    output = save_results(results)

    print("\n" + "="*60)
    print("最终结果汇总")
    print("="*60)
    for name, r in output.items():
        print(f"\n{name}:")
        print(f"  厚度 d = {r['thickness_um']:.4f} μm")
        print(f"  Δσ = {r['delta_sigma_cm1']:.4f} cm⁻¹")
        print(f"  n = {r['n']:.4f}")
        print(f"  干涉峰数 = {r['num_peaks']}")
        if "fringe_contrast" in r:
            print(f"  对比度 K = {r['fringe_contrast']:.4f}")
            print(f"  多光束干涉: {'是' if r['is_multi_beam'] else '否'}")
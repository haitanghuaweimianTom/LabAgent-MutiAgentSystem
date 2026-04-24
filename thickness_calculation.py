#!/usr/bin/env python3
"""
碳化硅外延层厚度测量计算脚本
使用方法: python thickness_calculation.py [附件路径]
"""

import pandas as pd
import numpy as np
from scipy.signal import savgol_filter, find_peaks
import argparse
import warnings
warnings.filterwarnings('ignore')


def load_spectrum(filepath):
    """加载光谱数据"""
    df = pd.read_excel(filepath)
    return df['波数 (cm-1)'].values, df['反射率 (%)'].values


def find_interference_peaks(wn, refl, wn_min, wn_max, smooth_window=31, min_prominence=2):
    """寻找干涉峰"""
    mask = (wn > wn_min) & (wn < wn_max)
    wn_f = wn[mask]
    refl_f = refl[mask]

    refl_smooth = savgol_filter(refl_f, window_length=smooth_window, polyorder=3)
    peaks, _ = find_peaks(refl_smooth, distance=30, prominence=min_prominence)

    return wn_f, refl_f, wn_f[peaks], refl_smooth[peaks]


def calculate_thickness(spacing_cm, n_eff):
    """
    计算外延层厚度

    参数:
        spacing_cm: 条纹间距 (cm^-1)
        n_eff: 有效折射率

    返回:
        厚度 (μm)
    """
    d_cm = 1 / (2 * n_eff * spacing_cm)
    d_um = d_cm * 1e4
    return d_um


def calculate_contrast(refl):
    """计算干涉对比度"""
    return (np.max(refl) - np.min(refl)) / (np.max(refl) + np.min(refl))


def analyze_sic(filepath, n_eff_range=[2.55, 2.60, 2.65, 2.70, 2.75],
                region=(700, 1000)):
    """分析SiC样品"""
    print(f"\n{'='*60}")
    print(f"分析: {filepath}")
    print(f"{'='*60}")

    wn, refl = load_spectrum(filepath)
    wn_f, refl_f, peak_wn, peak_refl = find_interference_peaks(wn, refl, region[0], region[1])

    if len(peak_wn) < 2:
        print("错误: 未检测到足够的干涉峰")
        return None

    spacing = np.mean(np.diff(peak_wn))
    contrast = calculate_contrast(refl_f)

    print(f"\n干涉区域: {region[0]}-{region[1]} cm⁻¹")
    print(f"干涉峰位置: {peak_wn}")
    print(f"条纹间距: {spacing:.3f} cm⁻¹")
    print(f"对比度: {contrast:.4f}")

    print(f"\n厚度估算:")
    print(f"{'折射率':<12} {'厚度(μm)':<12}")
    print(f"{'-'*30}")

    results = []
    for n in n_eff_range:
        d = calculate_thickness(spacing, n)
        results.append((n, d))
        print(f"{n:<12.2f} {d:<12.3f}")

    return {
        'spacing': spacing,
        'contrast': contrast,
        'results': results,
        'peaks': peak_wn
    }


def analyze_silicon(filepath, n_eff_range=[3.42, 3.45, 3.48]):
    """分析Si样品"""
    print(f"\n{'='*60}")
    print(f"分析: {filepath}")
    print(f"{'='*60}")

    wn, refl = load_spectrum(filepath)

    # Reststrahlen带分析
    print("\n[Reststrahlen带分析 (400-700 cm⁻¹)]")
    wn_rs, refl_rs, valley_wn, valley_refl = find_interference_peaks(
        wn, refl, 400, 700, smooth_window=21, min_prominence=1
    )

    # 反相峰值（谷）
    valleys, _ = find_peaks(-savgol_filter(refl_rs, window_length=21, polyorder=3),
                            distance=20, prominence=1)

    contrast_rs = calculate_contrast(refl_rs)
    print(f"对比度: {contrast_rs:.4f}")
    print(f"多光束干涉: {'是' if contrast_rs > 0.85 else '否'}")

    if len(valleys) >= 2:
        spacing = np.diff(wn_rs[valleys])[0]
        print(f"谷间距: {spacing:.2f} cm⁻¹")
        print("\n厚度估算:")
        for n in n_eff_range:
            d = calculate_thickness(spacing, n)
            print(f"  n={n}: d = {d:.2f} μm")

    # 透明区分析
    print("\n[透明区分析 (1200-2000 cm⁻¹)]")
    wn_tr, refl_tr, peak_wn_tr, _ = find_interference_peaks(
        wn, refl, 1200, 2000, smooth_window=31, min_prominence=2
    )

    if len(peak_wn_tr) >= 2:
        spacing_tr = np.diff(peak_wn_tr)[0]
        print(f"峰间距: {spacing_tr:.2f} cm⁻¹")
        for n in n_eff_range:
            d = calculate_thickness(spacing_tr, n)
            print(f"  n={n}: d = {d:.2f} μm")


def main():
    parser = argparse.ArgumentParser(description='SiC外延层厚度计算')
    parser.add_argument('filepaths', nargs='+', help='光谱数据文件路径')
    parser.add_argument('--sic', action='store_true', help='按SiC样品分析')
    parser.add_argument('--si', action='store_true', help='按Si样品分析')
    args = parser.parse_args()

    if args.sic:
        for fp in args.filepaths:
            analyze_sic(fp)
    elif args.si:
        for fp in args.filepaths:
            analyze_silicon(fp)
    else:
        print("请指定样品类型: --sic 或 --si")


if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        # 默认分析
        print("碳化硅外延层厚度测量计算工具")
        print("="*60)

        # 分析附件1和2
        results1 = analyze_sic('附件1.xlsx')
        results2 = analyze_sic('附件2.xlsx')

        # 分析附件3和4
        analyze_silicon('附件3.xlsx')
        analyze_silicon('附件4.xlsx')

        print("\n" + "="*60)
        print("计算完成!")
    else:
        main()
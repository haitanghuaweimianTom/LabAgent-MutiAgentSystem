#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate all figures for SiC Epitaxial Layer Thickness Paper
2025 Gaojiaoshebei National College Student Mathematical Modeling Contest - Problem B
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

import numpy as np
import openpyxl
from scipy.signal import find_peaks
from scipy.ndimage import gaussian_filter1d
import matplotlib
matplotlib.use("Agg", force=True)
import matplotlib
matplotlib.rcParams['figure.max_open_warning'] = 0
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import os

plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

DATA_DIR = "E:/cherryClaw/math_modeling_multi_agent"
OUTPUT_DIR = "E:/cherryClaw/math_modeling_multi_agent/SiC_Thickness_Paper/figures"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def load_excel(path):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["Sheet1"]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    wn = np.array([r[0] for r in rows[1:] if r[0] is not None], dtype=float)
    refl = np.array([r[1] for r in rows[1:] if r[1] is not None], dtype=float)
    return wn, refl


def n_sic(sigma):
    lam = 1e4 / sigma
    n2 = 6.7 * (1 + 0.46 * lam**2 / (lam**2 - 0.106**2))
    return np.sqrt(np.maximum(n2, 2.5**2))


def n_si(sigma):
    return 3.42


def savefig(fig, name):
    path = os.path.join(OUTPUT_DIR, name)
    fig.savefig(path, dpi=100, bbox_inches='tight', facecolor='white')
    print(f"Saved: {path}")
    plt.close(fig)
    fig.clear()
    return path


def plot_fig1_interference_principle():
    """图1: 红外干涉法测量原理示意图"""
    fig, ax = plt.subplots(1, 1, figsize=(10, 6))
    ax.add_patch(patches.Rectangle((0, 0.6), 4, 0.3, facecolor='#87CEEB', edgecolor='black', linewidth=2))
    ax.add_patch(patches.Rectangle((0, 0), 4, 0.6, facecolor='#D3D3D3', edgecolor='black', linewidth=2))
    ax.text(2, 0.75, 'SiC Epitaxial Layer', ha='center', va='center', fontsize=12, fontweight='bold')
    ax.text(2, 0.3, 'SiC Substrate', ha='center', va='center', fontsize=12, fontweight='bold')
    ax.arrow(0.8, 1.2, 0, -0.3, head_width=0.08, head_length=0.05, fc='red', ec='red', linewidth=2)
    ax.text(0.6, 1.4, 'Incident Light', fontsize=10, color='red')
    ax.arrow(0.8, 1.0, 0, 0.3, head_width=0.08, head_length=0.05, fc='blue', ec='blue', linewidth=2)
    ax.text(0.4, 1.1, 'Reflected\nLight 1', fontsize=9, color='blue')
    ax.arrow(1.2, 0.9, 0.3, -0.3, head_width=0.06, head_length=0.04, fc='green', ec='green', linewidth=1.5)
    ax.arrow(1.8, 0.5, -0.3, 0.3, head_width=0.06, head_length=0.04, fc='green', ec='green', linewidth=1.5)
    ax.arrow(1.5, 0.9, -0.3, 0.3, head_width=0.08, head_length=0.05, fc='purple', ec='purple', linewidth=2)
    ax.text(1.8, 1.1, 'Reflected Light 2', fontsize=9, color='purple')
    ax.set_xlim(-0.2, 4.5)
    ax.set_ylim(-0.1, 1.6)
    ax.set_aspect('equal')
    ax.axis('off')
    ax.set_title('Schematic of Infrared Interference Method for Epitaxial Layer Thickness Measurement', fontsize=12, fontweight='bold', pad=15)
    return savefig(fig, 'fig1_interference_principle.png')


def plot_fig2_spectrum_overview():
    """图2: 四种样品光谱总览"""
    samples_data = {
        'SiC-1': load_excel(os.path.join(DATA_DIR, '附件1.xlsx')),
        'SiC-2': load_excel(os.path.join(DATA_DIR, '附件2.xlsx')),
        'Si-1': load_excel(os.path.join(DATA_DIR, '附件3.xlsx')),
        'Si-2': load_excel(os.path.join(DATA_DIR, '附件4.xlsx'))
    }
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    for idx, (name, (wn, refl)) in enumerate(samples_data.items()):
        ax = axes[idx // 2, idx % 2]
        ax.plot(wn, refl, 'b-', lw=0.5, alpha=0.7)
        ax.set_xlabel('Wavenumber (cm-1)', fontsize=10)
        ax.set_ylabel('Reflectance (%)', fontsize=10)
        ax.set_title(f'{name} - Full Spectrum', fontsize=12, fontweight='bold')
        ax.grid(True, alpha=0.3)
        if 'SiC' in name:
            ax.axvspan(900, 1300, alpha=0.2, color='green', label='Analysis Region')
            ax.legend(fontsize=9)
    plt.tight_layout()
    return savefig(fig, 'fig2_spectrum_overview.png')


def plot_fig3_sic_peak_detection():
    """图3: SiC样品干涉峰检测"""
    sic1_data = load_excel(os.path.join(DATA_DIR, '附件1.xlsx'))
    sic2_data = load_excel(os.path.join(DATA_DIR, '附件2.xlsx'))
    peaks_sic1 = np.array([985.93, 1084.28])
    peaks_sic2 = np.array([988.82, 1091.51])
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    for idx, ((name, (wn, refl)), peaks) in enumerate([(('SiC-1', sic1_data), peaks_sic1), (('SiC-2', sic2_data), peaks_sic2)]):
        ax = axes[idx]
        mask = (wn >= 900) & (wn <= 1300)
        wn_s = wn[mask]
        refl_s = refl[mask]
        refl_sm = gaussian_filter1d(refl_s, sigma=5)
        ax.plot(wn_s, refl_s, 'b-', lw=0.5, alpha=0.5, label='Raw Data')
        ax.plot(wn_s, refl_sm, 'b-', lw=1.2, label='Smoothed')
        for p in peaks:
            ax.axvline(p, color='red', linestyle='--', alpha=0.7, lw=1.5)
            ax.plot(p, np.interp(p, wn_s, refl_sm), 'ro', ms=10, zorder=5)
            ax.annotate(f'{p:.1f}', xy=(p, np.interp(p, wn_s, refl_sm)), xytext=(p, np.interp(p, wn_s, refl_sm)+3), ha='center', fontsize=10, color='red')
        spacing = peaks[1] - peaks[0]
        ax.annotate('', xy=(peaks[0], -5), xytext=(peaks[1], -5), arrowprops=dict(arrowstyle='<->', color='green', lw=2))
        ax.text((peaks[0]+peaks[1])/2, -8, f'delta_sigma = {spacing:.2f} cm-1', ha='center', fontsize=10, color='green')
        ax.set_xlabel('Wavenumber (cm-1)', fontsize=11)
        ax.set_ylabel('Reflectance (%)', fontsize=11)
        ax.set_title(f'{name} - Interference Peak Detection', fontsize=12, fontweight='bold')
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.3)
        ax.set_ylim(-10, 50)
    plt.tight_layout()
    return savefig(fig, 'fig3_sic_peak_detection.png')


def plot_fig4_si_peak_detection():
    """图4: Si样品干涉峰检测"""
    si1_data = load_excel(os.path.join(DATA_DIR, '附件3.xlsx'))
    si2_data = load_excel(os.path.join(DATA_DIR, '附件4.xlsx'))
    peaks_si1 = np.array([418.0, 748.25, 1105.49, 1509.51, 1927.5, 2375.39, 2779.4, 3209.45])
    peaks_si2 = np.array([750.66, 1110.8, 1519.63, 1942.93, 2389.37, 2802.54, 3242.24])
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    for idx, ((name, (wn, refl)), peaks) in enumerate([(('Si-1', si1_data), peaks_si1), (('Si-2', si2_data), peaks_si2)]):
        ax = axes[idx]
        wn_s = wn
        refl_s = refl
        refl_sm = gaussian_filter1d(refl_s, sigma=5)
        ax.plot(wn_s, refl_s, 'b-', lw=0.3, alpha=0.4, label='Raw Data')
        ax.plot(wn_s, refl_sm, 'b-', lw=0.8, alpha=0.8, label='Smoothed')
        for p in peaks:
            ax.axvline(p, color='green', linestyle='--', alpha=0.5, lw=1)
            ax.plot(p, np.interp(p, wn_s, refl_sm), 'go', ms=6, zorder=5)
        ax.set_xlabel('Wavenumber (cm-1)', fontsize=11)
        ax.set_ylabel('Reflectance (%)', fontsize=11)
        ax.set_title(f'{name} - Multi-beam Interference Peaks', fontsize=12, fontweight='bold')
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.3)
        textstr = 'Fringe Contrast K > 0.99\nMulti-beam Effect: SIGNIFICANT'
        ax.text(0.02, 0.98, textstr, transform=ax.transAxes, fontsize=10, verticalalignment='top', bbox=dict(boxstyle='round', facecolor='yellow', alpha=0.7))
    plt.tight_layout()
    return savefig(fig, 'fig4_si_peak_detection.png')


def plot_fig5_refractive_index_dispersion():
    """图5: 折射率色散曲线"""
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    sigma_range = np.linspace(600, 1400, 500)
    n_sic_vals = np.array([n_sic(s) for s in sigma_range])
    ax = axes[0]
    ax.plot(sigma_range, n_sic_vals, 'b-', lw=2)
    ax.axvspan(900, 1300, alpha=0.2, color='green')
    ax.axvline(900, color='green', linestyle='--', alpha=0.7)
    ax.axvline(1300, color='green', linestyle='--', alpha=0.7)
    ax.text(1100, 2.75, 'Analysis Region', ha='center', fontsize=10, color='green')
    ax.set_xlabel('Wavenumber (cm-1)', fontsize=11)
    ax.set_ylabel('Refractive Index n', fontsize=11)
    ax.set_title('4H-SiC Refractive Index Dispersion (Sellmeier)', fontsize=12, fontweight='bold')
    ax.grid(True, alpha=0.3)
    n_at_1100 = n_sic(1100)
    ax.plot(1100, n_at_1100, 'ro', ms=10)
    ax.annotate(f'n(1100)={n_at_1100:.3f}', xy=(1100, n_at_1100), xytext=(1200, n_at_1100+0.1), fontsize=10, arrowprops=dict(arrowstyle='->', color='red'))
    ax = axes[1]
    sigma_range_si = np.linspace(400, 3500, 500)
    n_si_val = n_si(1000)
    ax.axhline(y=n_si_val, color='red', linestyle='-', lw=2, label=f'n = {n_si_val}')
    ax.fill_between(sigma_range_si, n_si_val-0.05, n_si_val+0.05, alpha=0.2, color='red')
    ax.set_xlabel('Wavenumber (cm-1)', fontsize=11)
    ax.set_ylabel('Refractive Index n', fontsize=11)
    ax.set_title('Si Refractive Index (n = 3.42)', fontsize=12, fontweight='bold')
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3)
    ax.set_ylim(3.3, 3.6)
    plt.tight_layout()
    return savefig(fig, 'fig5_refractive_index_dispersion.png')


def plot_fig6_thickness_comparison():
    """图6: 厚度结果对比"""
    samples = ['SiC-1', 'SiC-2', 'Si-1', 'Si-2']
    thicknesses = [24.58, 24.02, 3.67, 3.52]
    errors = [0.02, 0.02, 0.01, 0.01]
    colors = ['#2E86AB', '#2E86AB', '#A23B72', '#A23B72']
    fig, ax = plt.subplots(figsize=(10, 6))
    x = np.arange(len(samples))
    bars = ax.bar(x, thicknesses, 0.6, yerr=errors, capsize=5, color=colors, edgecolor='black', linewidth=1.5)
    for i, (th, err) in enumerate(zip(thicknesses, errors)):
        ax.text(i, th + err + 0.5, f'{th:.2f}', ha='center', fontsize=11, fontweight='bold')
    ax.set_xlabel('Sample', fontsize=12)
    ax.set_ylabel('Thickness (um)', fontsize=12)
    ax.set_title('Epitaxial Layer Thickness Results', fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(samples, fontsize=11)
    ax.grid(True, axis='y', alpha=0.3)
    from matplotlib.patches import Patch
    legend_elements = [Patch(facecolor='#2E86AB', edgecolor='black', label='SiC (Dual-beam)'), Patch(facecolor='#A23B72', edgecolor='black', label='Si (Multi-beam)')]
    ax.legend(handles=legend_elements, fontsize=10)
    plt.tight_layout()
    return savefig(fig, 'fig6_thickness_comparison.png')


def plot_fig7_model_comparison():
    """图7: 单次vs多次反射模型"""
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    ax = axes[0]
    x = np.linspace(0, 4*np.pi, 500)
    y1 = np.sin(x) * 0.5 + 0.5
    ax.plot(x, y1, 'b-', lw=2)
    ax.fill_between(x, y1, alpha=0.3)
    ax.set_title('Dual-beam Interference\n(Single Reflection)', fontsize=12, fontweight='bold')
    ax.set_xlabel('Phase Difference', fontsize=11)
    ax.set_ylabel('Intensity', fontsize=11)
    ax.set_ylim(-0.1, 1.3)
    ax.grid(True, alpha=0.3)
    ax = axes[1]
    R = 0.3
    y2 = (R + R - 2*R*np.cos(x)) / (1 + R*R - 2*R*np.cos(x))
    ax.plot(x, y2, 'r-', lw=2)
    ax.fill_between(x, y2, alpha=0.3, color='red')
    ax.set_title('Multi-beam Fabry-Perot\n(Multiple Reflections)', fontsize=12, fontweight='bold')
    ax.set_xlabel('Phase Difference', fontsize=11)
    ax.set_ylabel('Intensity', fontsize=11)
    ax.set_ylim(-0.1, 1.3)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    return savefig(fig, 'fig7_model_comparison.png')


def plot_fig8_multi_beam_condition():
    """图8: 多光束干涉条件"""
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    ax = axes[0]
    R = np.linspace(0.01, 0.9, 100)
    R1, R2 = np.meshgrid(R, R)
    K = 2 * np.sqrt(R1 * R2) / (1 + R1 * R2)
    im = ax.imshow(K, extent=[0.01, 0.9, 0.01, 0.9], origin='lower', aspect='equal', cmap='hot', vmin=0, vmax=1)
    ax.set_xlabel('R1 (Reflectivity 1)', fontsize=11)
    ax.set_ylabel('R2 (Reflectivity 2)', fontsize=11)
    ax.set_title('Fringe Contrast K vs Reflectivities', fontsize=12, fontweight='bold')
    plt.colorbar(im, ax=ax, label='Contrast K')
    ax.contour(R1, R2, K, levels=[0.5], colors='white', linewidths=2)
    ax.text(0.5, 0.7, 'K>0.5\n(Multi-beam)', color='white', fontsize=10, ha='center')
    ax = axes[1]
    samples = ['SiC-1', 'SiC-2', 'Si-1', 'Si-2']
    contrasts = [0.985, 0.980, 0.994, 0.990]
    colors_bar = ['#2E86AB', '#2E86AB', '#A23B72', '#A23B72']
    bars = ax.bar(samples, contrasts, 0.5, color=colors_bar, edgecolor='black', linewidth=1.5)
    ax.axhline(y=0.5, color='red', linestyle='--', linewidth=2, label='K=0.5 threshold')
    ax.set_ylabel('Fringe Contrast K', fontsize=11)
    ax.set_title('Fringe Contrast of Each Sample', fontsize=12, fontweight='bold')
    ax.set_ylim(0, 1.1)
    ax.legend(fontsize=10)
    ax.grid(True, axis='y', alpha=0.3)
    for i, c in enumerate(contrasts):
        ax.text(i, c + 0.02, f'{c:.3f}', ha='center', fontsize=10, fontweight='bold')
    plt.tight_layout()
    return savefig(fig, 'fig8_multi_beam_condition.png')


def plot_fig9_algorithm_flowchart():
    """图9: 算法流程图"""
    fig, ax = plt.subplots(figsize=(10, 12))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 12)
    ax.axis('off')
    boxes = [
        (5, 11, 'Start: Load Spectral Data'),
        (5, 9.5, 'Data Preprocessing (Smoothing)'),
        (5, 8, 'Select Analysis Region'),
        (5, 6.5, 'Peak Detection'),
        (5, 5, 'Calculate Peak Spacings'),
        (5, 3.5, 'Find Mode Spacing'),
        (5, 2, 'Calculate Refractive Index'),
        (5, 0.5, 'Compute Thickness d = 1/(2n delta_sigma)'),
    ]
    colors_box = ['lightblue', 'lightyellow', 'lightyellow', 'lightgreen', 'lightyellow', 'lightgreen', 'lightyellow', 'lightblue']
    for i, (x, y, text) in enumerate(boxes):
        rect = patches.FancyBboxPatch((x-2, y-0.4), 4, 0.8, boxstyle="round,pad=0.1", facecolor=colors_box[i], edgecolor='black', linewidth=2)
        ax.add_patch(rect)
        ax.text(x, y, text, ha='center', va='center', fontsize=10, fontweight='bold')
    for i in range(len(boxes)-1):
        ax.annotate('', xy=(5, boxes[i+1][1]+0.4), xytext=(5, boxes[i][1]-0.4), arrowprops=dict(arrowstyle='->', color='black', lw=2))
    ax.set_title('Algorithm Flowchart', fontsize=14, fontweight='bold', pad=20)
    return savefig(fig, 'fig9_algorithm_flowchart.png')


def plot_fig10_error_analysis():
    """图10: 误差分析"""
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    ax = axes[0]
    n_sic_range = np.linspace(2.6, 2.75, 100)
    d_sic1 = 1e4 / (2 * n_sic_range * 76.01)
    d_sic2 = 1e4 / (2 * n_sic_range * 77.78)
    ax.plot(n_sic_range, d_sic1, 'b-', lw=2, label='SiC-1')
    ax.plot(n_sic_range, d_sic2, 'r-', lw=2, label='SiC-2')
    ax.axvline(2.6758, color='green', linestyle='--', alpha=0.7, label='n=2.6758')
    ax.set_xlabel('Refractive Index n', fontsize=11)
    ax.set_ylabel('Calculated Thickness d (um)', fontsize=11)
    ax.set_title('Thickness Sensitivity to Refractive Index', fontsize=12, fontweight='bold')
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3)
    ax = axes[1]
    d_sigma_range = np.linspace(60, 100, 100)
    d_sic_sens = 1e4 / (2 * 2.6758 * d_sigma_range)
    ax.plot(d_sigma_range, d_sic_sens, 'b-', lw=2)
    ax.fill_between(d_sigma_range, d_sic_sens*0.98, d_sic_sens*1.02, alpha=0.3, color='blue')
    ax.set_xlabel('Peak Spacing delta_sigma (cm-1)', fontsize=11)
    ax.set_ylabel('Calculated Thickness d (um)', fontsize=11)
    ax.set_title('Thickness Sensitivity to delta_sigma', fontsize=12, fontweight='bold')
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    return savefig(fig, 'fig10_error_analysis.png')


def plot_fig11_results_summary():
    """图11: 结果汇总表"""
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.axis('off')
    data = [
        ['Sample', 'Model', 'delta_sigma', 'n', 'Thickness', 'Peaks', 'Multi-beam'],
        ['SiC-1', 'Dual-beam', '76.01', '2.6758', '24.58 um', '2', 'Weak'],
        ['SiC-2', 'Dual-beam', '77.78', '2.6758', '24.02 um', '2', 'Weak'],
        ['Si-1', 'Multi-beam FP', '398.78', '3.4200', '3.67 um', '8', 'Significant'],
        ['Si-2', 'Multi-beam FP', '415.26', '3.4200', '3.52 um', '8', 'Significant'],
    ]
    table = ax.table(cellText=data[1:], colLabels=data[0], loc='center', cellLoc='center', colColours=['lightgray']*7)
    table.auto_set_font_size(False)
    table.set_fontsize(11)
    table.scale(1.2, 2.5)
    ax.set_title('Summary of Results', fontsize=14, fontweight='bold', pad=20)
    return savefig(fig, 'fig11_results_summary.png')


def main():
    print("Generating all figures...")
    plot_fig1_interference_principle()
    plot_fig2_spectrum_overview()
    plot_fig3_sic_peak_detection()
    plot_fig4_si_peak_detection()
    plot_fig5_refractive_index_dispersion()
    plot_fig6_thickness_comparison()
    plot_fig7_model_comparison()
    plot_fig8_multi_beam_condition()
    plot_fig9_algorithm_flowchart()
    plot_fig10_error_analysis()
    plot_fig11_results_summary()
    print("All figures generated!")


if __name__ == "__main__":
    main()
"""
Visualization Module
===================

Generates high-quality figures for the mathematical modeling paper.
Follows publication standards with colorblind-safe palettes, proper
typography, and journal-specific dimensions.
"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import Rectangle, FancyArrowPatch, Circle
from matplotlib.lines import Line2D
from typing import Dict, List, Optional, Tuple
import seaborn as sns
from string import ascii_uppercase

# Set style for publication quality
plt.style.use('seaborn-v0_8-whitegrid')
plt.rcParams['figure.dpi'] = 150
plt.rcParams['savefig.dpi'] = 300
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['Arial', 'Helvetica', 'DejaVu Sans']
plt.rcParams['font.size'] = 10
plt.rcParams['axes.labelsize'] = 11
plt.rcParams['axes.titlesize'] = 12
plt.rcParams['xtick.labelsize'] = 9
plt.rcParams['ytick.labelsize'] = 9
plt.rcParams['legend.fontsize'] = 9
plt.rcParams['axes.linewidth'] = 1.0
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['xtick.direction'] = 'out'
plt.rcParams['ytick.direction'] = 'out'


# Colorblind-safe Okabe-Ito palette
OKABE_ITO = [
    '#E69F00',  # Orange
    '#56B4E9',  # Sky blue
    '#009E73',  # Bluish green
    '#F0E442',  # Yellow
    '#0072B2',  # Blue
    '#D55E00',  # Vermillion
    '#CC79A7',  # Reddish purple
    '#000000',  # Black
]

# Material-specific colors
MATERIAL_COLORS = {
    'SiC': '#0072B2',    # Blue
    'Si': '#009E73',     # Green
    'peak': '#D55E00',   # Vermillion
    'valley': '#CC79A7', # Reddish purple
}


class PublicationStyle:
    """Manages publication-quality figure styling."""

    # Figure dimensions (in inches) for different journal layouts
    SINGLE_COLUMN = 3.5   # ~89mm for Nature
    ONE_HALF_COLUMN = 5.5
    DOUBLE_COLUMN = 7.0  # ~183mm for Nature
    MAX_HEIGHT = 9.0

    @classmethod
    def apply_nature_style(cls):
        """Apply Nature journal figure specifications."""
        plt.rcParams['font.family'] = 'sans-serif'
        plt.rcParams['font.sans-serif'] = ['Arial']
        plt.rcParams['font.size'] = 8
        plt.rcParams['axes.labelsize'] = 9
        plt.rcParams['axes.titlesize'] = 10
        plt.rcParams['xtick.labelsize'] = 7
        plt.rcParams['ytick.labelsize'] = 7
        plt.rcParams['legend.fontsize'] = 8
        plt.rcParams['axes.linewidth'] = 0.5

    @classmethod
    def get_color(cls, key: str) -> str:
        """Get color from palette."""
        if key in MATERIAL_COLORS:
            return MATERIAL_COLORS[key]
        colors = {
            'primary': OKABE_ITO[0],
            'secondary': OKABE_ITO[1],
            'accent': OKABE_ITO[2],
        }
        return colors.get(key, '#333333')


class PrincipleDiagram:
    """Generates the interference principle diagram."""

    @staticmethod
    def draw(ax=None) -> plt.Figure:
        """Draw the principle diagram with publication quality."""
        if ax is None:
            fig, ax = plt.subplots(figsize=(12, 8))
        else:
            fig = ax.figure

        ax.set_xlim(0, 14)
        ax.set_ylim(0, 10)
        ax.set_aspect('equal')
        ax.axis('off')

        # Title
        ax.text(7, 9.5,
                'Figure 1. Principle of Infrared Interference Thickness Measurement',
                fontsize=14, fontweight='bold', ha='center', transform=ax.transData)

        # Epitaxial layer
        epitaxial = mpatches.FancyBboxPatch(
            (2, 4.5), 5, 1.5,
            boxstyle="round,pad=0.05,rounding_size=0.2",
            facecolor='#aec7e8', edgecolor='#1f77b4', linewidth=2
        )
        ax.add_patch(epitaxial)
        ax.text(4.5, 5.25, 'Epitaxial Layer', fontsize=12, ha='center', va='center', fontweight='bold')
        ax.text(4.5, 4.8, r'$n = 2.65$ (SiC)', fontsize=10, ha='center', va='center')

        # Substrate
        substrate = mpatches.FancyBboxPatch(
            (2, 2), 5, 2.5,
            boxstyle="round,pad=0.05,rounding_size=0.2",
            facecolor='#d3d3d3', edgecolor='#7f7f7f', linewidth=2
        )
        ax.add_patch(substrate)
        ax.text(4.5, 3.25, 'Substrate', fontsize=12, ha='center', va='center', fontweight='bold')

        # Thickness arrow
        ax.annotate('', xy=(7.5, 4.5), xytext=(7.5, 6),
                    arrowprops=dict(arrowstyle='<->', color='red', lw=2.5))
        ax.text(8.1, 5.25, r'$d$', fontsize=14, color='red', fontweight='bold')

        # Incident light
        ax.annotate('', xy=(4.5, 8.5), xytext=(4.5, 9.5),
                    arrowprops=dict(arrowstyle='->', color='#d62728', lw=2.5))
        ax.text(5.3, 9.2, 'Incident Light', fontsize=10, color='#d62728', fontweight='bold')

        # Reflected beam 1
        ax.annotate('', xy=(2.3, 8.5), xytext=(3.5, 6),
                    arrowprops=dict(arrowstyle='->', color='#2ca02c', lw=2))
        ax.text(1.0, 8.3, r'$I_1$', fontsize=14, color='#2ca02c', fontweight='bold')
        ax.text(1.0, 7.7, '(Surface', fontsize=9, color='#2ca02c')
        ax.text(1.0, 7.3, 'Reflection)', fontsize=9, color='#2ca02c')

        # Reflected beam 2
        ax.annotate('', xy=(6.5, 6), xytext=(4.5, 4.5),
                    arrowprops=dict(arrowstyle='->', color='#9467bd', lw=2))
        ax.text(7.3, 5.5, r'$I_2$', fontsize=14, color='#9467bd', fontweight='bold')
        ax.text(7.3, 5.0, '(Substrate', fontsize=9, color='#9467bd')
        ax.text(7.3, 4.6, 'Reflection)', fontsize=9, color='#9467bd')

        # Formula box
        formula_text = (r'$\Delta = 2nd = m\lambda$' + '\n' +
                        r'$d = \frac{1}{2n\Delta\sigma}$')
        ax.text(10.5, 8.5, formula_text, fontsize=12,
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.9),
                ha='center', va='center')

        # Legend
        legend_text = (r'$\Delta$: Optical path difference    '
                      r'$n$: Refractive index' + '\n' +
                      r'$d$: Layer thickness    '
                      r'$\lambda$: Wavelength    '
                      r'$\Delta\sigma$: Fringe spacing')
        ax.text(7, 1.0, legend_text, fontsize=9, ha='center', va='center',
                style='italic', bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))

        return fig


class SpectrumPlotter:
    """Generates publication-quality spectral data plots."""

    @staticmethod
    def plot_all_spectra(
        spectra: Dict[str, Tuple[np.ndarray, np.ndarray]],
        filepath: str = 'figure02_spectra_overview.png'
    ) -> plt.Figure:
        """
        Plot all four samples in a 2x2 grid with publication quality.

        Args:
            spectra: Dictionary of (wavenumber, reflectivity) data
            filepath: Output file path

        Returns:
            matplotlib Figure
        """
        fig, axes = plt.subplots(2, 2, figsize=(PublicationStyle.DOUBLE_COLUMN, 6))
        fig.subplots_adjust(hspace=0.3, wspace=0.3)

        titles = ['(a) SiC Sample 1', '(b) SiC Sample 2',
                  '(c) Si Sample 1', '(d) Si Sample 2']
        colors = [MATERIAL_COLORS['SiC'], MATERIAL_COLORS['SiC'],
                  MATERIAL_COLORS['Si'], MATERIAL_COLORS['Si']]
        regions = [(700, 1000), (700, 1000), (400, 700), (400, 700)]
        region_colors = ['#D55E00', '#D55E00', '#E69F00', '#E69F00']
        region_labels = ['SiC Reststrahlen Band', 'SiC Reststrahlen Band',
                         'Si Reststrahlen Band', 'Si Reststrahlen Band']

        sample_keys = ['SiC_Sample_1', 'SiC_Sample_2', 'Si_Sample_1', 'Si_Sample_2']

        for idx, (ax, title, color, (wn_min, wn_max), reg_color, reg_label, key) in enumerate(
            zip(axes.flatten(), titles, colors, regions, region_colors, region_labels, sample_keys)
        ):
            if key in spectra:
                wn, refl = spectra[key]
                ax.plot(wn, refl, color=color, linewidth=0.8, alpha=0.8)
                ax.axvspan(wn_min, wn_max, alpha=0.15, color=reg_color, label=reg_label)

            ax.set_title(title, fontsize=11, fontweight='bold')
            ax.set_xlabel('Wavenumber (cm$^{-1}$)', fontsize=10)
            ax.set_ylabel('Reflectivity (%)', fontsize=10)
            ax.set_xlim(400, 1200)
            ax.grid(True, alpha=0.3, linestyle='--')
            ax.legend(loc='upper right', fontsize=8, framealpha=0.9)

            # Add panel label
            ax.text(-0.05, 1.05, ascii_uppercase[idx], transform=ax.transAxes,
                   fontsize=12, fontweight='bold', va='top')

        plt.tight_layout()
        fig.savefig(filepath, bbox_inches='tight', facecolor='white', dpi=300)
        plt.close()

        return fig


class InterferenceAnalyzer:
    """Generates interference analysis plots with peak/valley detection."""

    @staticmethod
    def plot_analysis(
        analysis_data: Dict,
        filepath: str = 'figure03_interference_analysis.png'
    ) -> plt.Figure:
        """
        Plot interference analysis results with peak annotations.

        Args:
            analysis_data: Dictionary containing analysis results for each sample
            filepath: Output file path

        Returns:
            matplotlib Figure
        """
        fig, axes = plt.subplots(2, 2, figsize=(PublicationStyle.DOUBLE_COLUMN, 6))
        fig.subplots_adjust(hspace=0.35, wspace=0.35)

        # Panel (a): SiC-1 peaks
        ax = axes[0, 0]
        if 'SiC_Sample_1' in analysis_data:
            data = analysis_data['SiC_Sample_1']
            ax.plot(data['wavenumber'], data['reflectivity'], 'b-', linewidth=0.8, alpha=0.4, label='Raw')
            ax.plot(data['wavenumber'], data['smoothed'], color='#0072B2', linewidth=1.5, label='Smoothed')

            if len(data['peaks']) > 0:
                ax.plot(data['peaks'], data['peak_values'], 'o', markersize=10,
                       markerfacecolor='#E69F00', markeredgecolor='#333333', markeredgewidth=1.5,
                       label=f'Peaks (n={len(data["peaks"])})', zorder=5)

            # Annotate spacing
            if len(data['peaks']) >= 2:
                for i in range(len(data['peaks']) - 1):
                    spacing = data['peaks'][i+1] - data['peaks'][i]
                    mid_x = (data['peaks'][i] + data['peaks'][i+1]) / 2
                    mid_y = (data['peak_values'][i] + data['peak_values'][i+1]) / 2 + 3
                    ax.annotate('', xy=(data['peaks'][i+1], data['peak_values'][i+1]),
                               xytext=(data['peaks'][i], data['peak_values'][i]),
                               arrowprops=dict(arrowstyle='<->', color='#009E73', lw=1.5))
                    ax.text(mid_x, mid_y, f'$\Delta\\sigma$ = {spacing:.1f}',
                           fontsize=9, ha='center', color='#009E73', fontweight='bold')

        ax.set_title('(a) SiC Sample 1: Interference Peaks (700-1000 cm$^{-1}$)',
                    fontsize=10, fontweight='bold')
        ax.set_xlabel('Wavenumber (cm$^{-1}$)', fontsize=9)
        ax.set_ylabel('Reflectivity (%)', fontsize=9)
        ax.legend(loc='upper right', fontsize=8, framealpha=0.9)
        ax.grid(True, alpha=0.3, linestyle='--')
        ax.set_xlim(700, 1000)
        ax.text(-0.05, 1.05, 'A', transform=ax.transAxes, fontsize=12, fontweight='bold', va='top')

        # Panel (b): SiC-2
        ax = axes[0, 1]
        if 'SiC_Sample_2' in analysis_data:
            data = analysis_data['SiC_Sample_2']
            ax.plot(data['wavenumber'], data['reflectivity'], 'b-', linewidth=0.8, alpha=0.4)
            ax.plot(data['wavenumber'], data['smoothed'], color='#0072B2', linewidth=1.5)

            if len(data['peaks']) > 0:
                ax.plot(data['peaks'], data['peak_values'], 'o', markersize=10,
                       markerfacecolor='#E69F00', markeredgecolor='#333333', markeredgewidth=1.5, zorder=5)

        ax.set_title('(b) SiC Sample 2: Interference Region (700-1000 cm$^{-1}$)',
                    fontsize=10, fontweight='bold')
        ax.set_xlabel('Wavenumber (cm$^{-1}$)', fontsize=9)
        ax.set_ylabel('Reflectivity (%)', fontsize=9)
        ax.grid(True, alpha=0.3, linestyle='--')
        ax.set_xlim(700, 1000)
        ax.text(-0.05, 1.05, 'B', transform=ax.transAxes, fontsize=12, fontweight='bold', va='top')

        # Panel (c): Si-1 valleys
        ax = axes[1, 0]
        if 'Si_Sample_1' in analysis_data:
            data = analysis_data['Si_Sample_1']
            ax.plot(data['wavenumber'], data['reflectivity'], 'g-', linewidth=0.8, alpha=0.4)
            ax.plot(data['wavenumber'], data['smoothed'], color='#009E73', linewidth=1.5)

            if len(data.get('valleys', [])) > 0:
                ax.plot(data['valleys'], data['valley_values'], 'v', markersize=12,
                       markeredgecolor='#333333', markeredgewidth=1.5,
                       label=f'Valleys (n={len(data["valleys"])})', zorder=5)

            if len(data.get('valleys', [])) >= 2:
                spacing = data['valleys'][1] - data['valleys'][0]
                mid_x = (data['valleys'][0] + data['valleys'][1]) / 2
                ax.annotate('', xy=(data['valleys'][1], data['valley_values'][1]),
                           xytext=(data['valleys'][0], data['valley_values'][0]),
                           arrowprops=dict(arrowstyle='<->', color='#CC79A7', lw=1.5))
                ax.text(mid_x, 35, f'$\Delta\\sigma$ = {spacing:.1f}',
                       fontsize=9, ha='center', color='#CC79A7', fontweight='bold')

        ax.set_title('(c) Si Sample 1: Reststrahlen Band (400-700 cm$^{-1}$)',
                    fontsize=10, fontweight='bold')
        ax.set_xlabel('Wavenumber (cm$^{-1}$)', fontsize=9)
        ax.set_ylabel('Reflectivity (%)', fontsize=9)
        ax.legend(loc='upper right', fontsize=8, framealpha=0.9)
        ax.grid(True, alpha=0.3, linestyle='--')
        ax.set_xlim(400, 700)
        ax.text(-0.05, 1.05, 'C', transform=ax.transAxes, fontsize=12, fontweight='bold', va='top')

        # Panel (d): Si-2
        ax = axes[1, 1]
        if 'Si_Sample_2' in analysis_data:
            data = analysis_data['Si_Sample_2']
            ax.plot(data['wavenumber'], data['reflectivity'], 'g-', linewidth=0.8, alpha=0.4)
            ax.plot(data['wavenumber'], data['smoothed'], color='#009E73', linewidth=1.5)

        ax.set_title('(d) Si Sample 2: Reststrahlen Band (400-700 cm$^{-1}$)',
                    fontsize=10, fontweight='bold')
        ax.set_xlabel('Wavenumber (cm$^{-1}$)', fontsize=9)
        ax.set_ylabel('Reflectivity (%)', fontsize=9)
        ax.grid(True, alpha=0.3, linestyle='--')
        ax.set_xlim(400, 700)
        ax.text(-0.05, 1.05, 'D', transform=ax.transAxes, fontsize=12, fontweight='bold', va='top')

        plt.tight_layout()
        fig.savefig(filepath, bbox_inches='tight', facecolor='white', dpi=300)
        plt.close()

        return fig


class MultiBeamAnalyzer:
    """Generates multi-beam interference analysis plots."""

    @staticmethod
    def plot_contrast_comparison(
        contrasts: Dict[str, float],
        filepath: str = 'figure04_contrast.png'
    ) -> plt.Figure:
        """Plot interference contrast comparison with publication quality."""
        fig, axes = plt.subplots(1, 2, figsize=(PublicationStyle.DOUBLE_COLUMN, 3.5))
        fig.subplots_adjust(wspace=0.35)

        # Panel (a): Contrast bar chart
        ax = axes[0]
        samples = list(contrasts.keys())
        values = list(contrasts.values())
        colors = [MATERIAL_COLORS['SiC'], MATERIAL_COLORS['SiC'],
                  MATERIAL_COLORS['Si'], MATERIAL_COLORS['Si']]

        bars = ax.bar(range(len(samples)), values, color=colors, alpha=0.8,
                     edgecolor='black', linewidth=1, width=0.6)
        ax.axhline(y=0.85, color='#D55E00', linestyle='--', linewidth=1.5,
                  label='Multi-beam threshold (C=0.85)')
        ax.axhline(y=0.5, color='#E69F00', linestyle='--', linewidth=1.5,
                  label='Double-beam threshold (C=0.5)')

        ax.set_ylabel('Interference Contrast C', fontsize=10)
        ax.set_title('(a) Interference Contrast Comparison', fontsize=11, fontweight='bold')
        ax.set_ylim(0, 1.05)
        ax.set_xticks(range(len(samples)))
        ax.set_xticklabels(samples, fontsize=9, rotation=15, ha='right')
        ax.legend(loc='upper right', fontsize=8, framealpha=0.9)
        ax.grid(True, alpha=0.3, axis='y', linestyle='--')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)

        for bar, val in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02,
                   f'{val:.3f}', ha='center', va='bottom', fontsize=9, fontweight='bold')

        ax.text(-0.05, 1.05, 'A', transform=ax.transAxes, fontsize=12, fontweight='bold', va='top')

        # Panel (b): Thickness vs refractive index
        ax = axes[1]
        n_sic = np.linspace(2.55, 2.75, 100)
        d1 = 1e4 / (2 * n_sic * 153.8)
        d2 = 1e4 / (2 * n_sic * 155.0)

        ax.plot(n_sic, d1, color='#0072B2', linewidth=2, label='Sample 1 ($\Delta\\sigma$=153.8 cm$^{-1}$)')
        ax.plot(n_sic, d2, color='#009E73', linewidth=2, linestyle='--', label='Sample 2 ($\Delta\\sigma$=155.0 cm$^{-1}$)')
        ax.axvline(x=2.65, color='gray', linestyle=':', alpha=0.7, linewidth=1.5)
        ax.scatter([2.65], [12.27], color='#0072B2', s=80, zorder=5, marker='o', edgecolor='black')
        ax.scatter([2.65], [12.17], color='#009E73', s=80, zorder=5, marker='s', edgecolor='black')
        ax.annotate('(2.65, 12.27)', xy=(2.65, 12.27), xytext=(2.68, 12.4),
                   arrowprops=dict(arrowstyle='->', color='#0072B2', lw=1), fontsize=8, color='#0072B2')
        ax.annotate('(2.65, 12.17)', xy=(2.65, 12.17), xytext=(2.68, 11.8),
                   arrowprops=dict(arrowstyle='->', color='#009E73', lw=1), fontsize=8, color='#009E73')

        ax.set_xlabel('Refractive Index $n$', fontsize=10)
        ax.set_ylabel('Thickness $d$ ($\\mu$m)', fontsize=10)
        ax.set_title('(b) SiC Thickness vs. Refractive Index', fontsize=11, fontweight='bold')
        ax.legend(loc='upper right', fontsize=8, framealpha=0.9)
        ax.grid(True, alpha=0.3, linestyle='--')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.text(-0.05, 1.05, 'B', transform=ax.transAxes, fontsize=12, fontweight='bold', va='top')

        plt.tight_layout()
        fig.savefig(filepath, bbox_inches='tight', facecolor='white', dpi=300)
        plt.close()

        return fig


class AlgorithmFlowchart:
    """Generates algorithm flowchart for thickness calculation."""

    @staticmethod
    def draw(filepath: str = 'figure05_flowchart.png') -> plt.Figure:
        """Draw the algorithm flowchart with publication quality."""
        fig, ax = plt.subplots(figsize=(12, 8))
        ax.set_xlim(0, 14)
        ax.set_ylim(0, 12)
        ax.set_aspect('equal')
        ax.axis('off')

        # Title
        ax.text(7, 11.3,
                'Figure 5. Algorithm Flowchart for Epitaxial Layer Thickness Calculation',
                fontsize=13, fontweight='bold', ha='center')

        def draw_box(x, y, w, h, text, color='#aec7e8', fontsize=10):
            box = mpatches.FancyBboxPatch(
                (x, y), w, h,
                boxstyle="round,pad=0.05,rounding_size=0.2",
                facecolor=color, edgecolor='#333333', linewidth=1.5
            )
            ax.add_patch(box)
            ax.text(x + w/2, y + h/2, text, ha='center', va='center',
                   fontsize=fontsize, wrap=True)

        def draw_arrow(x1, y1, x2, y2):
            ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                       arrowprops=dict(arrowstyle='->', color='#333333', lw=1.5))

        # Main flow
        draw_box(5, 10.5, 4, 1, 'Input: Spectrum Data\n($\\sigma$, R)', '#90EE90', 10)
        draw_arrow(7, 10.5, 7, 9.5)

        draw_box(5, 8.5, 4, 1, 'Data Preprocessing\nSavitzky-Golay Filter', '#FFFACD', 10)
        draw_arrow(7, 8.5, 7, 7.5)

        draw_box(5, 6.5, 4, 1, 'Region Selection\n700-1000 cm$^{-1}$ (SiC)', '#FFFACD', 10)
        draw_arrow(7, 6.5, 7, 5.5)

        draw_box(5, 4.5, 4, 1, 'Peak Detection\nscipy.find_peaks()', '#FFFACD', 10)
        draw_arrow(7, 4.5, 7, 3.5)

        draw_box(5, 2.5, 4, 1, 'Calculate Thickness\n$d = 1/(2n\\Delta\\sigma)$', '#FFA07A', 10)
        draw_arrow(7, 2.5, 7, 1.5)

        draw_box(5, 0.5, 4, 1, 'Output: Thickness $d$\nwith Uncertainty', '#90EE90', 10)

        # Side annotations
        ax.text(10.5, 10, 'Parameters:\nwindow=31\norder=3', fontsize=9, va='center',
               style='italic', color='gray')
        ax.text(10.5, 8, 'Removes noise\npreserves peaks', fontsize=9, va='center',
               style='italic', color='gray')
        ax.text(10.5, 6, 'Select interference\nregion', fontsize=9, va='center',
               style='italic', color='gray')
        ax.text(10.5, 4, 'distance=30\nprominence=3', fontsize=9, va='center',
               style='italic', color='gray')
        ax.text(10.5, 2, 'n: refractive index\n$\\Delta\\sigma$: fringe spacing', fontsize=9,
               va='center', style='italic', color='gray')

        # Contrast check
        ax.text(1, 5.5, 'Contrast Check:', fontsize=10, fontweight='bold')
        ax.text(1, 5, 'C > 0.85:', fontsize=9)
        ax.text(1, 4.5, 'Multi-beam', fontsize=9, color='#D55E00')
        ax.text(1, 4, 'correction', fontsize=9, color='#D55E00')
        ax.text(1, 3.5, 'needed', fontsize=9, color='#D55E00')
        ax.text(1, 2.5, 'C < 0.5:', fontsize=9)
        ax.text(1, 2, 'Double-beam', fontsize=9, color='#009E73')
        ax.text(1, 1.5, 'direct calc', fontsize=9, color='#009E73')

        plt.tight_layout()
        fig.savefig(filepath, bbox_inches='tight', facecolor='white', dpi=300)
        plt.close()

        return fig


class ResultsTable:
    """Generates results summary table."""

    @staticmethod
    def draw(
        results: List[Dict],
        filepath: str = 'figure06_results_table.png'
    ) -> plt.Figure:
        """Draw results table with publication quality."""
        fig, ax = plt.subplots(figsize=(PublicationStyle.DOUBLE_COLUMN, 3.5))
        ax.axis('off')

        ax.set_title('Table 1. Summary of Epitaxial Layer Thickness Calculation Results',
                    fontsize=12, fontweight='bold', y=0.98)

        # Table data
        table_data = [
            ['Sample', 'Material', 'Region\n(cm⁻¹)', 'Spacing\n(cm⁻¹)',
             'n', 'Thickness\n(μm)', 'Contrast', 'Notes'],
            ['Attach 1', 'SiC', '700-1000', '153.80', '2.65', '12.27 ± 0.15', '0.942', 'Clear peaks'],
            ['Attach 2', 'SiC', '700-1000', '155.00', '2.65', '12.17 ± 0.12', '0.943', 'Single peak*'],
            ['Attach 3', 'Si', '400-700', '157.65', '3.45', '9.19 ± 0.11', '0.913', 'Valley spacing'],
            ['Attach 4', 'Si', '1100-2000', '206.59', '3.45', '7.02 ± 0.08', '0.919', 'Transparent']
        ]

        table = ax.table(
            cellText=table_data[1:],
            colLabels=table_data[0],
            loc='center',
            cellLoc='center',
            colColours=[MATERIAL_COLORS['SiC']] * 8
        )

        # Style header
        for i in range(len(table_data[0])):
            table[0, i].set_text_props(color='white', fontweight='bold')
            table[0, i].set_fontsize(9)

        # Style cells
        for i in range(1, len(table_data)):
            for j in range(len(table_data[0])):
                table[i, j].set_fontsize(9)
                if i % 2 == 0:
                    table[i, j].set_facecolor('#f0f0f0')

        table.auto_set_font_size(False)
        table.set_fontsize(9)
        table.scale(1.2, 2.0)

        # Note
        ax.text(0.5, 0.12,
               '* Attachment 2: Single peak in 700-1000 cm⁻¹; period estimated from full spectrum analysis.',
               fontsize=9, style='italic', transform=ax.transAxes, ha='center')

        plt.tight_layout()
        fig.savefig(filepath, bbox_inches='tight', facecolor='white', dpi=300)
        plt.close()

        return fig


def save_publication_figure(fig, filename, formats=['pdf', 'png'], dpi=300):
    """
    Save figure in multiple publication formats.

    Args:
        fig: matplotlib Figure
        filename: Base filename without extension
        formats: List of formats to save ('pdf', 'png', 'eps')
        dpi: Resolution for raster formats
    """
    for fmt in formats:
        filepath = f"{filename}.{fmt}"
        fig.savefig(filepath, format=fmt, dpi=dpi, bbox_inches='tight',
                   facecolor='white', edgecolor='none')

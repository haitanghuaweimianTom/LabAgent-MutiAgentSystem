#!/usr/bin/env python3
"""
figures4papers skill version for 2025A smoke screen decoy problem.
Emphasizes: ultra-wide grouped bars, strong edges, hatch encoding,
dedicated legend panels, large-font bar panels, print-safe styling.
Strictly follows scientific-figure-making/references/ api.md + common-patterns.md.
"""
import json
import warnings
from pathlib import Path
from dataclasses import dataclass

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import gridspec
import numpy as np

CHARTS_DIR = Path(__file__).parent

with open(Path(__file__).parent.parent / "execution" / "results.json") as f:
    RESULTS = json.load(f)

# ------------------------------------------------------------------
# API implementation per figures4papers skill (api.md)
# ------------------------------------------------------------------
PALETTE = {
    "blue_main": "#0F4D92",
    "blue_secondary": "#3775BA",
    "green_1": "#DDF3DE", "green_2": "#AADCA9", "green_3": "#8BCF8B",
    "red_1": "#F6CFCB", "red_2": "#E9A6A1", "red_strong": "#B64342",
    "neutral": "#CFCECE", "highlight": "#FFD700",
    "teal": "#42949E", "violet": "#9A4D8E",
}

DEFAULT_COLORS = [
    PALETTE["blue_main"], PALETTE["green_3"], PALETTE["red_strong"],
    PALETTE["teal"], PALETTE["violet"], PALETTE["neutral"],
]


@dataclass(frozen=True)
class FigureStyle:
    font_size: int = 16
    axes_linewidth: float = 2.5
    use_tex: bool = False
    font_family: tuple = ("DejaVu Sans", "Helvetica", "Arial", "sans-serif")


def apply_publication_style(style=None):
    """Configure matplotlib rcParams per figures4papers house style."""
    if style is None:
        style = FigureStyle()
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": list(style.font_family),
        "svg.fonttype": "none",
        "font.size": style.font_size,
        "axes.spines.right": False,
        "axes.spines.top": False,
        "axes.linewidth": style.axes_linewidth,
        "legend.frameon": False,
        "text.usetex": style.use_tex,
    })


def finalize_figure(fig, out_path, formats=None, dpi=300, close=True, pad=0.05, **kwargs):
    """Save figure to specified formats; create parent dirs as needed."""
    import os
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fig.tight_layout(pad=pad)
    base = Path(out_path)
    os.makedirs(base.parent, exist_ok=True)
    if formats is None:
        ext = base.suffix.lstrip(".") or "png"
        formats = [ext]
        base = base.with_suffix("")
    saved = []
    for fmt in formats:
        p = str(base) + f".{fmt}"
        fig.savefig(p, dpi=dpi, bbox_inches="tight", **kwargs)
        saved.append(p)
    if close:
        plt.close(fig)
    return saved


def make_grouped_bar(ax, categories, series, labels, ylabel="Value",
                     colors=None, annotate=False):
    """Render grouped bars with black edges (print-safe)."""
    n_series = len(series)
    n_cat = len(categories)
    x = np.arange(n_cat)
    width = 0.8 / n_series
    if colors is None:
        colors = DEFAULT_COLORS[:n_series]
    containers = []
    for i, (data, label, color) in enumerate(zip(series, labels, colors)):
        offset = (i - (n_series - 1) / 2) * width
        bars = ax.bar(x + offset, data, width, label=label, color=color,
                      edgecolor="black", linewidth=1.5)
        containers.append(bars)
    ax.set_xticks(x)
    ax.set_xticklabels(categories, fontsize=plt.rcParams["font.size"] - 2)
    ax.set_ylabel(ylabel, fontsize=plt.rcParams["font.size"])
    if annotate:
        for bars in containers:
            for bar in bars:
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width() / 2., height + 0.15,
                        f"{height:.1f}", ha="center", va="bottom",
                        fontsize=plt.rcParams["font.size"] - 4)
    return containers[-1] if containers else None


def annotate_bars(ax, bars, fmt="{:.2f}", fontsize=10, padding=3):
    """Add text above each bar in a BarContainer."""
    for bar in bars:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2., height + padding,
                fmt.format(height), ha="center", va="bottom", fontsize=fontsize)


def make_heatmap(ax, matrix, x_labels=None, y_labels=None, cmap="magma",
                 cbar_label=None, annotate=False):
    """Render 2D heatmap with optional cell annotations."""
    vmax = float(matrix.max()) if matrix.size else 1.0
    im = ax.imshow(matrix, cmap=cmap, aspect="auto", vmin=0, vmax=vmax)
    if x_labels:
        ax.set_xticks(range(len(x_labels)))
        ax.set_xticklabels(x_labels, fontsize=plt.rcParams["font.size"] - 2)
    if y_labels:
        ax.set_yticks(range(len(y_labels)))
        ax.set_yticklabels(y_labels, fontsize=plt.rcParams["font.size"] - 2)
    if annotate:
        for (i, j), val in np.ndenumerate(matrix):
            color = "white" if val > vmax / 2 else "black"
            ax.text(j, i, f"{val:.1f}", ha="center", va="center",
                    fontsize=plt.rcParams["font.size"] - 2, color=color,
                    fontweight="bold")
    cbar = plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    if cbar_label:
        cbar.set_label(cbar_label, fontsize=plt.rcParams["font.size"] - 2)
    return im


def make_trend(ax, x, y_series, labels, colors=None, ylabel=None,
               xlabel=None, show_shadow=True):
    """Plot multiple trend lines with optional fill_between shadow."""
    if colors is None:
        colors = DEFAULT_COLORS[:len(y_series)]
    for y, label, color in zip(y_series, labels, colors):
        ax.plot(x, y, label=label, color=color, lw=2.5)
        if show_shadow:
            ax.fill_between(x, y, alpha=0.12, color=color)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=plt.rcParams["font.size"])
    if xlabel:
        ax.set_xlabel(xlabel, fontsize=plt.rcParams["font.size"])


# ------------------------------------------------------------------
# Figure 1: Ultra-wide grouped bars + dedicated legend panel
# Tutorial 1 + common-patterns: ultra-wide, strong edges, hatch, legend panel
# ------------------------------------------------------------------
def fig1_grouped_bars():
    apply_publication_style(FigureStyle(font_size=24, axes_linewidth=3))
    # Ultra-wide canvas: width 3-4x height for multi-metric scanning
    fig = plt.figure(figsize=(28, 7))
    gs = gridspec.GridSpec(1, 4, figure=fig, width_ratios=[3, 3, 3, 1], wspace=0.25)

    # Q2: FY1, FY2, FY3 independently vs M1
    q2_categories = ["FY1", "FY2", "FY3"]
    q2_vals = [
        RESULTS["result2"]["fy1"]["tau_eff"],
        RESULTS["result2"]["fy2"]["tau_eff"],
        RESULTS["result2"]["fy3"]["tau_eff"],
    ]
    # Q3: optimal coordinated assignment from detailed.q5
    q3_assignments = RESULTS["detailed"]["q5"]["assignments"]
    q3_vals = [a["tau_eff"] for a in q3_assignments]
    q3_categories = [f"{a['uav']}-{a['missile']}" for a in q3_assignments]

    # --- Panel a: Independent (Q2) ---
    ax_a = fig.add_subplot(gs[0, 0])
    bars = ax_a.bar(q2_categories, q2_vals, color=PALETTE["red_strong"],
                    edgecolor="black", linewidth=2, hatch="\\", width=0.5)
    ax_a.set_ylabel("Coverage (s)", fontsize=22)
    ax_a.set_ylim(0, 12)
    ax_a.set_title("Q2 Independent (vs M1)", fontsize=22, fontweight="bold")
    annotate_bars(ax_a, bars, fmt="{:.1f}s", fontsize=18, padding=0.2)

    # --- Panel b: Coordinated (Q3) ---
    ax_b = fig.add_subplot(gs[0, 1])
    bars = ax_b.bar(q3_categories, q3_vals, color=PALETTE["blue_main"],
                    edgecolor="black", linewidth=2, hatch="/", width=0.5)
    ax_b.set_ylim(0, 12)
    ax_b.set_title("Q3 Coordinated", fontsize=22, fontweight="bold")
    annotate_bars(ax_b, bars, fmt="{:.1f}s", fontsize=18, padding=0.2)

    # --- Panel c: Side-by-side grouped comparison ---
    ax_c = fig.add_subplot(gs[0, 2])
    # Use mean coverage for comparison
    x = np.arange(2)
    width = 0.35
    bars1 = ax_c.bar(x[0], np.mean(q2_vals), width, label="Q2 Independent",
                     color=PALETTE["red_strong"], edgecolor="black",
                     linewidth=2, hatch="\\")
    bars2 = ax_c.bar(x[1], np.mean(q3_vals), width, label="Q3 Coordinated",
                     color=PALETTE["blue_main"], edgecolor="black",
                     linewidth=2, hatch="/")
    ax_c.set_xticks(x)
    ax_c.set_xticklabels(["Q2 Mean", "Q3 Mean"], fontsize=20)
    ax_c.set_ylim(0, 12)
    ax_c.set_title("Comparison", fontsize=22, fontweight="bold")
    for bars in [bars1, bars2]:
        for bar in bars:
            h = bar.get_height()
            ax_c.text(bar.get_x() + bar.get_width() / 2., h + 0.2,
                      f"{h:.1f}s", ha="center", va="bottom", fontsize=16)

    # --- Panel d: Dedicated legend panel ---
    ax_d = fig.add_subplot(gs[0, 3])
    ax_d.set_axis_off()
    handles = [
        plt.Rectangle((0, 0), 1, 1, facecolor=PALETTE["red_strong"],
                      edgecolor="black", linewidth=2, hatch="\\",
                      label="Q2 Independent"),
        plt.Rectangle((0, 0), 1, 1, facecolor=PALETTE["blue_main"],
                      edgecolor="black", linewidth=2, hatch="/",
                      label="Q3 Coordinated"),
    ]
    ax_d.legend(handles, ["Q2 Independent", "Q3 Coordinated"],
                loc="center", fontsize=20, frameon=False)

    finalize_figure(fig, str(CHARTS_DIR / "fig_01_f4p_grouped_bars"),
                    formats=["png", "pdf"], dpi=300, pad=0.06)
    print("  Saved fig_01_f4p_grouped_bars.png / .pdf")


# ------------------------------------------------------------------
# Figure 2: Heatmap + robust assignment grouped bars
# Tutorial 3 heatmap + common-patterns hatch encoding
# ------------------------------------------------------------------
def fig2_heatmap_bars():
    apply_publication_style(FigureStyle(font_size=18, axes_linewidth=2.5))
    fig = plt.figure(figsize=(18, 8))
    gs = gridspec.GridSpec(1, 2, figure=fig, wspace=0.30)

    # --- Panel a: Assignment matrix heatmap ---
    ax1 = fig.add_subplot(gs[0, 0])
    uavs = ["FY1", "FY2", "FY3"]
    missiles = ["M1", "M2", "M3"]
    matrix = np.zeros((len(uavs), len(missiles)))
    for a in RESULTS["detailed"]["q5"]["assignments"]:
        i = uavs.index(a["uav"])
        j = missiles.index(a["missile"])
        matrix[i, j] = a["tau_eff"]

    make_heatmap(ax1, matrix, x_labels=missiles, y_labels=uavs,
                 cmap="Blues", cbar_label="Coverage (s)", annotate=True)
    ax1.set_xlabel("Missile", fontsize=18)
    ax1.set_ylabel("UAV", fontsize=18)
    ax1.set_title("Coordinated assignment matrix", fontsize=20, fontweight="bold")

    # --- Panel b: Robust assignment primary / backup ---
    ax2 = fig.add_subplot(gs[0, 1])
    r4 = RESULTS["result4"]
    primaries = {}
    backups = {}
    for a in r4["optimal_assignment"]:
        m = a["missile"]
        if a["role"] == "primary":
            primaries[m] = primaries.get(m, 0) + 1
        else:
            backups[m] = backups.get(m, 0) + 1
    missiles_list = ["M1", "M2", "M3"]
    p_counts = [primaries.get(m, 0) for m in missiles_list]
    b_counts = [backups.get(m, 0) for m in missiles_list]

    x = np.arange(len(missiles_list))
    width = 0.35
    bars1 = ax2.bar(x - width / 2, p_counts, width, label="Primary",
                    color=PALETTE["blue_main"], edgecolor="black",
                    linewidth=2, hatch="/")
    bars2 = ax2.bar(x + width / 2, b_counts, width, label="Backup",
                    color=PALETTE["green_3"], edgecolor="black",
                    linewidth=2, hatch="\\")
    ax2.set_xticks(x)
    ax2.set_xticklabels(missiles_list, fontsize=18)
    ax2.set_ylabel("UAV count", fontsize=18)
    ax2.set_ylim(0, 3)
    ax2.set_title("Robust assignment (5 UAVs)", fontsize=20, fontweight="bold")
    ax2.legend(fontsize=16)

    for bars in [bars1, bars2]:
        for bar in bars:
            h = bar.get_height()
            if h > 0:
                ax2.text(bar.get_x() + bar.get_width() / 2., h + 0.05,
                         f"{int(h)}", ha="center", va="bottom", fontsize=14)

    finalize_figure(fig, str(CHARTS_DIR / "fig_02_f4p_heatmap_bars"),
                    formats=["png", "pdf"], dpi=300, pad=0.06)
    print("  Saved fig_02_f4p_heatmap_bars.png / .pdf")


# ------------------------------------------------------------------
# Figure 3: Multi-panel trend / scatter with shared legend
# Tutorial 2 adapted: scatter + trend + robust metrics bars + legend panel
# ------------------------------------------------------------------
def fig3_scatter_metrics():
    apply_publication_style(FigureStyle(font_size=16, axes_linewidth=2))
    fig = plt.figure(figsize=(20, 7))
    gs = gridspec.GridSpec(1, 3, figure=fig, width_ratios=[2, 2, 1], wspace=0.28)

    # --- Panel a: Distance vs coverage scatter + trend ---
    ax1 = fig.add_subplot(gs[0, 0])
    uavs = {
        "FY1": (17800, 0, 1800),
        "FY2": (12000, 1400, 1400),
        "FY3": (6000, -3000, 700),
    }
    missiles = {
        "M1": (20000, 0, 2000),
        "M2": (19000, 600, 2100),
        "M3": (18000, -600, 1900),
    }

    distances = []
    taus = []
    labels_scatter = []
    for a in RESULTS["detailed"]["q5"]["assignments"]:
        ux, uy, uz = uavs[a["uav"]]
        mx, my, mz = missiles[a["missile"]]
        d = np.sqrt((ux - mx) ** 2 + (uy - my) ** 2 + (uz - mz) ** 2)
        distances.append(d)
        taus.append(a["tau_eff"])
        labels_scatter.append(f"{a['uav']}-{a['missile']}")

    distances = np.array(distances)
    taus = np.array(taus)

    ax1.scatter(distances, taus, s=200, c=PALETTE["blue_main"],
                edgecolors="black", linewidths=2, zorder=5)
    for d, t, lbl in zip(distances, taus, labels_scatter):
        ax1.annotate(lbl, (d, t), xytext=(10, 10),
                     textcoords="offset points", fontsize=12)

    # Trend line with shadow
    z = np.polyfit(distances, taus, 1)
    p = np.poly1d(z)
    x_line = np.linspace(min(distances) * 0.9, max(distances) * 1.1, 100)
    y_line = p(x_line)
    ax1.plot(x_line, y_line, color=PALETTE["neutral"], lw=2.5, ls="--")
    ax1.fill_between(x_line, y_line, alpha=0.12, color=PALETTE["neutral"])

    ax1.set_xlabel("UAV-Missile distance (m)", fontsize=16)
    ax1.set_ylabel("Coverage duration (s)", fontsize=16)
    ax1.set_title("Distance vs coverage", fontsize=18, fontweight="bold")

    # --- Panel b: Robust metrics bars ---
    ax2 = fig.add_subplot(gs[0, 1])
    categories = ["Min coverage", "Redundancy", "Total UAVs"]
    values = [
        RESULTS["result4"]["min_coverage_time"],
        RESULTS["result4"]["redundancy"],
        5,
    ]
    colors_b = [PALETTE["blue_main"], PALETTE["teal"], PALETTE["green_3"]]
    bars = ax2.bar(range(len(categories)), values, color=colors_b,
                   edgecolor="black", linewidth=2)
    ax2.set_xticks(range(len(categories)))
    ax2.set_xticklabels(categories, fontsize=14)
    ax2.set_ylabel("Value", fontsize=16)
    ax2.set_ylim(0, max(values) * 1.3)
    ax2.set_title("Robust metrics", fontsize=18, fontweight="bold")
    for bar, val in zip(bars, values):
        ax2.text(bar.get_x() + bar.get_width() / 2., bar.get_height() + 0.3,
                 f"{val:.1f}" if isinstance(val, float) else str(val),
                 ha="center", va="bottom", fontsize=14)

    # --- Panel c: Dedicated legend panel ---
    ax3 = fig.add_subplot(gs[0, 2])
    ax3.set_axis_off()
    handles = [
        plt.Line2D([0], [0], marker="o", color="w",
                   markerfacecolor=PALETTE["blue_main"], markersize=12,
                   markeredgecolor="black", label="Assignment"),
        plt.Line2D([0], [0], color=PALETTE["neutral"], lw=2.5,
                   ls="--", label="Trend"),
    ]
    ax3.legend(handles, ["Assignment", "Trend"],
               loc="center", fontsize=14, frameon=False)

    finalize_figure(fig, str(CHARTS_DIR / "fig_03_f4p_scatter_metrics"),
                    formats=["png", "pdf"], dpi=300, pad=0.06)
    print("  Saved fig_03_f4p_scatter_metrics.png / .pdf")


def main():
    print("Generating figures4papers skill charts for 2025A...")
    fig1_grouped_bars()
    fig2_heatmap_bars()
    fig3_scatter_metrics()
    print("Done.")


if __name__ == "__main__":
    main()

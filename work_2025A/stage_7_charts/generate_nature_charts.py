#!/usr/bin/env python3
"""
Nature Figure Skill version for 2025A smoke screen decoy problem.
Emphasizes: schematic-led composite, NMI pastel palette, asymmetric hero layout,
information architecture (overview -> deviation -> relationship).
"""
import json
import warnings
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
from matplotlib import gridspec
from matplotlib.patches import Circle, FancyBboxPatch
from matplotlib.lines import Line2D

CHARTS_DIR = Path(__file__).parent

# Load results
with open(Path(__file__).parent.parent / "execution" / "results.json") as f:
    RESULTS = json.load(f)

# ------------------------------------------------------------------
# Nature Figure Skill: api.md + design-theory.md
# ------------------------------------------------------------------
PALETTE = {
    "blue_main": "#0F4D92", "blue_secondary": "#3775BA",
    "green_1": "#DDF3DE", "green_2": "#AADCA9", "green_3": "#8BCF8B",
    "red_1": "#F6CFCB", "red_2": "#E9A6A1", "red_strong": "#B64342",
    "neutral_light": "#CFCECE", "neutral_mid": "#767676",
    "neutral_dark": "#4D4D4D", "neutral_black": "#272727",
    "teal": "#42949E", "violet": "#9A4D8E",
}

PALETTE_NMI_PASTEL = {
    "baseline_dark": "#484878", "baseline_mid": "#7884B4",
    "baseline_soft": "#B4C0E4", "ours_tiny": "#E4E4F0",
    "ours_base": "#E4CCD8", "ours_large": "#F0C0CC",
    "bg_lilac": "#E0E0F0", "bg_aqua": "#E0F0F0",
    "delta_up": "#2E9E44", "delta_down": "#E53935",
}


def apply_publication_style(font_size=14, axes_linewidth=2.5):
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "DejaVu Sans", "Liberation Sans"],
        "svg.fonttype": "none",
        "font.size": font_size,
        "axes.spines.right": False,
        "axes.spines.top": False,
        "axes.linewidth": axes_linewidth,
        "legend.frameon": False,
    })


def add_panel_label(ax, label, x=-0.06, y=1.02, fontsize=14, color="black", fontweight="bold"):
    ax.text(x, y, label, transform=ax.transAxes, fontsize=fontsize,
            fontweight=fontweight, color=color, ha="left", va="bottom")


def finalize_figure(fig, out_path, formats=None, dpi=300, pad=2, close=True):
    import os
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fig.tight_layout(pad=pad)
    base = Path(out_path)
    os.makedirs(base.parent, exist_ok=True)
    if formats is None:
        formats = [base.suffix.lstrip(".") or "png"]
        base = base.with_suffix("")
    saved = []
    for fmt in formats:
        p = str(base) + f".{fmt}"
        fig.savefig(p, dpi=dpi, bbox_inches="tight")
        saved.append(p)
    if close:
        plt.close(fig)
    return saved


# ------------------------------------------------------------------
# Figure 1: Schematic-led composite (Pattern 12)
# Hero: 2D battlefield top-down
# Supporting: coverage bars, timeline, total coverage donut
# ------------------------------------------------------------------
def fig1_schematic_composite():
    apply_publication_style(font_size=13, axes_linewidth=2)
    fig = plt.figure(figsize=(14, 9))
    gs = fig.add_gridspec(2, 3, height_ratios=[2.2, 1.0], hspace=0.32, wspace=0.28)

    # Data
    uavs = {
        "FY1": (17800, 0, 1800), "FY2": (12000, 1400, 1400),
        "FY3": (6000, -3000, 700), "FY4": (11000, 2000, 1800),
        "FY5": (13000, -2000, 1300),
    }
    missiles = {
        "M1": (20000, 0, 2000), "M2": (19000, 600, 2100), "M3": (18000, -600, 1900),
    }
    target = (0, 200)
    decoy = (0, 0)

    # --- Hero panel a: top-down battlefield ---
    ax_a = fig.add_subplot(gs[0, :])
    ax_a.set_aspect("equal", adjustable="box")

    # Draw smoke effective radius circles for result3 assignments
    r3 = RESULTS["result3"]["assignments"]
    colors_uav = [PALETTE_NMI_PASTEL["baseline_dark"], PALETTE_NMI_PASTEL["baseline_mid"],
                  PALETTE_NMI_PASTEL["ours_base"]]
    for i, assign in enumerate(r3):
        uav_name = assign["uav"]
        mx, my, _ = missiles[assign["missile"]]
        # Approximate smoke cloud center between UAV and missile
        ux, uy, _ = uavs[uav_name]
        cx, cy = (ux + mx) / 2, (uy + my) / 2
        circle = Circle((cx, cy), 600, color=colors_uav[i], alpha=0.15, zorder=1)
        ax_a.add_patch(circle)
        ax_a.plot([ux, cx], [uy, cy], color=colors_uav[i], lw=1.5, ls="--", alpha=0.6)

    # Missiles
    for name, (x, y, z) in missiles.items():
        ax_a.scatter(x, y, c=PALETTE["red_strong"], s=100, marker="v", zorder=5, edgecolors="white", linewidths=0.8)
        ax_a.annotate(name, (x, y), xytext=(8, 8), textcoords="offset points", fontsize=10, color=PALETTE["red_strong"])

    # UAVs
    for name, (x, y, z) in uavs.items():
        color = PALETTE["blue_main"] if name in ["FY1", "FY2", "FY3"] else PALETTE["neutral_mid"]
        ax_a.scatter(x, y, c=color, s=80, marker="o", zorder=5, edgecolors="white", linewidths=0.8)
        ax_a.annotate(name, (x, y), xytext=(8, -12), textcoords="offset points", fontsize=9, color=color)

    # Target and decoy
    ax_a.scatter(*target, c=PALETTE["green_3"], s=200, marker="*", zorder=6, edgecolors="white", linewidths=1)
    ax_a.annotate("Target", target, xytext=(10, 10), textcoords="offset points", fontsize=10, color=PALETTE["green_3"], fontweight="bold")
    ax_a.scatter(*decoy, c=PALETTE["neutral_black"], s=60, marker="s", zorder=5)
    ax_a.annotate("Decoy", decoy, xytext=(10, -15), textcoords="offset points", fontsize=10, color=PALETTE["neutral_black"])

    ax_a.set_xlim(-2500, 22500)
    ax_a.set_ylim(-5500, 4500)
    ax_a.set_xlabel("x (m)", fontsize=13)
    ax_a.set_ylabel("y (m)", fontsize=13)
    ax_a.set_title("Battlefield deployment (top-down)", fontsize=15, fontweight="bold")
    add_panel_label(ax_a, "a", x=-0.02, y=1.01, fontsize=14)

    # Legend strip above hero
    legend_elements = [
        Line2D([0], [0], marker="v", color="w", markerfacecolor=PALETTE["red_strong"], markersize=10, label="Missile"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=PALETTE["blue_main"], markersize=9, label="UAV (active)"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=PALETTE["neutral_mid"], markersize=9, label="UAV (reserve)"),
        Line2D([0], [0], marker="*", color="w", markerfacecolor=PALETTE["green_3"], markersize=12, label="Target"),
    ]
    ax_a.legend(handles=legend_elements, loc="upper right", frameon=False, fontsize=10, ncol=4)

    # --- Panel b: coverage duration comparison ---
    ax_b = fig.add_subplot(gs[1, 0])
    assignments = RESULTS["detailed"]["q5"]["assignments"]
    names = [f"{a['uav']}-{a['missile']}" for a in assignments]
    taus = [a["tau_eff"] for a in assignments]
    colors_b = [PALETTE_NMI_PASTEL["baseline_dark"], PALETTE_NMI_PASTEL["baseline_mid"], PALETTE_NMI_PASTEL["ours_base"]]
    bars = ax_b.bar(range(len(names)), taus, color=colors_b, edgecolor="black", linewidth=1.2)
    ax_b.set_xticks(range(len(names)))
    ax_b.set_xticklabels(names, fontsize=11)
    ax_b.set_ylabel("Coverage (s)", fontsize=12)
    ax_b.set_ylim(0, max(taus) * 1.25)
    for bar, val in zip(bars, taus):
        ax_b.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.15,
                  f"{val:.1f}s", ha="center", va="bottom", fontsize=10)
    add_panel_label(ax_b, "b", x=-0.08, y=1.02, fontsize=14)

    # --- Panel c: timeline ---
    ax_c = fig.add_subplot(gs[1, 1])
    # Use actual coverage intervals from optimal assignment (detailed.q5)
    q5_assignments = RESULTS["detailed"]["q5"]["assignments"]
    colors_timeline = [PALETTE_NMI_PASTEL["baseline_dark"], PALETTE_NMI_PASTEL["baseline_mid"], PALETTE_NMI_PASTEL["ours_base"]]
    for i, assign in enumerate(q5_assignments):
        name = f"{assign['uav']}-{assign['missile']}"
        intervals = assign["params"].get("intervals", [])
        for t0, t1 in intervals:
            ax_c.barh(i, t1 - t0, left=t0, color=colors_timeline[i], height=0.5, edgecolor="black", linewidth=1)
    ax_c.set_yticks(range(len(q5_assignments)))
    ax_c.set_yticklabels([f"{a['uav']}-{a['missile']}" for a in q5_assignments], fontsize=10)
    ax_c.set_xlabel("Time (s)", fontsize=12)
    ax_c.set_xlim(0, 28)
    ax_c.set_ylim(-0.5, len(q5_assignments) - 0.5)
    add_panel_label(ax_c, "c", x=-0.08, y=1.02, fontsize=14)

    # --- Panel d: robust assignment (result4) ---
    ax_d = fig.add_subplot(gs[1, 2])
    r4 = RESULTS["result4"]
    # Count primary vs backup per missile
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
    w = 0.35
    ax_d.bar(x - w / 2, p_counts, w, label="Primary", color=PALETTE["blue_main"], edgecolor="black", linewidth=1)
    ax_d.bar(x + w / 2, b_counts, w, label="Backup", color=PALETTE_NMI_PASTEL["ours_base"], edgecolor="black", linewidth=1)
    ax_d.set_xticks(x)
    ax_d.set_xticklabels(missiles_list, fontsize=11)
    ax_d.set_ylabel("UAV count", fontsize=12)
    ax_d.set_ylim(0, 3)
    ax_d.legend(fontsize=10)
    add_panel_label(ax_d, "d", x=-0.08, y=1.02, fontsize=14)

    finalize_figure(fig, str(CHARTS_DIR / "fig_01_nature_schematic"), formats=["svg", "png"], dpi=300, pad=2)
    print("  Saved fig_01_nature_schematic.svg / .png")


# ------------------------------------------------------------------
# Figure 2: Assignment matrix + coverage breakdown
# ------------------------------------------------------------------
def fig2_assignment_analysis():
    apply_publication_style(font_size=13, axes_linewidth=2)
    fig = plt.figure(figsize=(14, 5))
    gs = fig.add_gridspec(1, 3, wspace=0.35)

    # --- Panel a: assignment matrix heatmap ---
    ax1 = fig.add_subplot(gs[0, 0])
    uavs = ["FY1", "FY2", "FY3"]
    missiles = ["M1", "M2", "M3"]
    matrix = np.zeros((len(uavs), len(missiles)))
    for a in RESULTS["result3"]["assignments"]:
        i = uavs.index(a["uav"])
        j = missiles.index(a["missile"])
        matrix[i, j] = a["tau_eff"]

    im = ax1.imshow(matrix, cmap="Blues", aspect="auto", vmin=0, vmax=12)
    ax1.set_xticks(range(len(missiles)))
    ax1.set_xticklabels(missiles, fontsize=12)
    ax1.set_yticks(range(len(uavs)))
    ax1.set_yticklabels(uavs, fontsize=12)
    ax1.set_xlabel("Missile", fontsize=13)
    ax1.set_ylabel("UAV", fontsize=13)
    for (i, j), val in np.ndenumerate(matrix):
        color = "white" if val > 6 else "black"
        ax1.text(j, i, f"{val:.1f}s", ha="center", va="center", fontsize=11, color=color, fontweight="bold")
    cbar = fig.colorbar(im, ax=ax1, fraction=0.046, pad=0.04)
    cbar.set_label("Coverage (s)", fontsize=11)
    cbar.outline.set_linewidth(0.8)
    add_panel_label(ax1, "a", x=-0.08, y=1.02, fontsize=14)

    # --- Panel b: scenario comparison (result2 vs result3) ---
    ax2 = fig.add_subplot(gs[0, 1])
    scenarios = ["Q2\n(Indep.)", "Q3\n(Coord.)"]
    # Q2: result2 fy1, fy2, fy3 all vs M1
    q2_vals = [RESULTS["result2"]["fy1"]["tau_eff"],
               RESULTS["result2"]["fy2"]["tau_eff"],
               RESULTS["result2"]["fy3"]["tau_eff"]]
    # Q3: use optimal assignment from detailed.q5
    q3_vals = [a["tau_eff"] for a in RESULTS["detailed"]["q5"]["assignments"]]
    # Average per scenario
    q2_avg = np.mean(q2_vals)
    q3_avg = np.mean(q3_vals)
    x = np.arange(len(scenarios))
    bars = ax2.bar(x, [q2_avg, q3_avg], color=[PALETTE_NMI_PASTEL["baseline_soft"], PALETTE_NMI_PASTEL["ours_base"]],
                   edgecolor="black", linewidth=1.5, width=0.5)
    ax2.set_xticks(x)
    ax2.set_xticklabels(scenarios, fontsize=11)
    ax2.set_ylabel("Mean coverage (s)", fontsize=12)
    ax2.set_ylim(0, max(q2_avg, q3_avg) * 1.4)
    for bar, val in zip(bars, [q2_avg, q3_avg]):
        ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.1,
                 f"{val:.1f}s", ha="center", va="bottom", fontsize=10)
    add_panel_label(ax2, "b", x=-0.08, y=1.02, fontsize=14)

    # --- Panel c: result4 robust coverage ---
    ax3 = fig.add_subplot(gs[0, 2])
    categories = ["Min\ncoverage", "Redundancy", "Total\nUAVs"]
    values = [RESULTS["result4"]["min_coverage_time"], RESULTS["result4"]["redundancy"], 5]
    colors_c = [PALETTE["blue_main"], PALETTE["teal"], PALETTE["green_3"]]
    bars = ax3.bar(range(len(categories)), values, color=colors_c, edgecolor="black", linewidth=1.2)
    ax3.set_xticks(range(len(categories)))
    ax3.set_xticklabels(categories, fontsize=10)
    ax3.set_ylabel("Value", fontsize=12)
    ax3.set_ylim(0, max(values) * 1.3)
    for bar, val in zip(bars, values):
        ax3.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.2,
                 f"{val:.1f}" if isinstance(val, float) else str(val),
                 ha="center", va="bottom", fontsize=10)
    add_panel_label(ax3, "c", x=-0.08, y=1.02, fontsize=14)

    finalize_figure(fig, str(CHARTS_DIR / "fig_02_nature_assignment"), formats=["svg", "png"], dpi=300, pad=2)
    print("  Saved fig_02_nature_assignment.svg / .png")


# ------------------------------------------------------------------
# Figure 3: Relationship analysis (distance vs coverage)
# ------------------------------------------------------------------
def fig3_relationship():
    apply_publication_style(font_size=13, axes_linewidth=2)
    fig = plt.figure(figsize=(12, 5))
    gs = fig.add_gridspec(1, 2, wspace=0.30)

    # --- Panel a: distance vs coverage scatter ---
    ax1 = fig.add_subplot(gs[0, 0])
    uavs = {"FY1": (17800, 0, 1800), "FY2": (12000, 1400, 1400), "FY3": (6000, -3000, 700)}
    missiles = {"M1": (20000, 0, 2000), "M2": (19000, 600, 2100), "M3": (18000, -600, 1900)}

    distances = []
    taus = []
    colors = []
    labels = []
    for a in RESULTS["result3"]["assignments"]:
        ux, uy, uz = uavs[a["uav"]]
        mx, my, mz = missiles[a["missile"]]
        d = np.sqrt((ux - mx) ** 2 + (uy - my) ** 2 + (uz - mz) ** 2)
        distances.append(d)
        taus.append(a["tau_eff"])
        colors.append(PALETTE["blue_main"])
        labels.append(f"{a['uav']}-{a['missile']}")

    ax1.scatter(distances, taus, c=colors, s=120, edgecolors="white", linewidths=1.5, zorder=5)
    for d, t, lbl in zip(distances, taus, labels):
        ax1.annotate(lbl, (d, t), xytext=(8, 8), textcoords="offset points", fontsize=10)

    # Trend line
    z = np.polyfit(distances, taus, 1)
    p = np.poly1d(z)
    x_line = np.linspace(min(distances) * 0.9, max(distances) * 1.1, 100)
    ax1.plot(x_line, p(x_line), color=PALETTE["neutral_mid"], lw=1.5, ls="--", alpha=0.7)

    ax1.set_xlabel("UAV-Missile distance (m)", fontsize=13)
    ax1.set_ylabel("Coverage duration (s)", fontsize=13)
    add_panel_label(ax1, "a", x=-0.08, y=1.02, fontsize=14)

    # --- Panel b: total coverage composition ---
    ax2 = fig.add_subplot(gs[0, 1])
    assignments = RESULTS["detailed"]["q5"]["assignments"]
    names = [f"{a['uav']}-{a['missile']}" for a in assignments]
    taus = [a["tau_eff"] for a in assignments]
    total = sum(taus)
    colors_b = [PALETTE_NMI_PASTEL["baseline_dark"], PALETTE_NMI_PASTEL["baseline_mid"], PALETTE_NMI_PASTEL["ours_base"]]
    wedges, texts, autotexts = ax2.pie(taus, labels=names, colors=colors_b, autopct=lambda pct: f"{pct:.1f}%",
                                       startangle=90, wedgeprops={"edgecolor": "white", "linewidth": 2})
    for t in texts:
        t.set_fontsize(11)
    for t in autotexts:
        t.set_fontsize(10)
        t.set_color("white" if total > 0 else "black")
    ax2.set_title(f"Total coverage: {total:.1f} s", fontsize=13, fontweight="bold")
    add_panel_label(ax2, "b", x=-0.08, y=1.02, fontsize=14)

    finalize_figure(fig, str(CHARTS_DIR / "fig_03_nature_relationship"), formats=["svg", "png"], dpi=300, pad=2)
    print("  Saved fig_03_nature_relationship.svg / .png")


def main():
    print("Generating Nature Figure Skill charts for 2025A...")
    fig1_schematic_composite()
    fig2_assignment_analysis()
    fig3_relationship()
    print("Done.")


if __name__ == "__main__":
    main()

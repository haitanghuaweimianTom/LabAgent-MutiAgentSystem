#!/usr/bin/env python3
"""
Nature-level scientific visualization for 2024A 舞龙 spiral motion.
Strictly follows src/knowledge/nature_figure/ skill conventions.
"""
import sys
import warnings
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
from matplotlib import gridspec
from matplotlib.colors import LinearSegmentedColormap

sys.path.insert(0, str(Path(__file__).parent.parent / "execution"))
import solve

CHARTS_DIR = Path(__file__).parent

# ------------------------------------------------------------------
# Skill: api.md — Constants & Helpers
# ------------------------------------------------------------------
PALETTE = {
    "blue_main": "#0F4D92",
    "blue_secondary": "#3775BA",
    "green_1": "#DDF3DE",
    "green_2": "#AADCA9",
    "green_3": "#8BCF8B",
    "red_1": "#F6CFCB",
    "red_2": "#E9A6A1",
    "red_strong": "#B64342",
    "neutral_light": "#CFCECE",
    "neutral_mid": "#767676",
    "neutral_dark": "#4D4D4D",
    "neutral_black": "#272727",
    "gold": "#FFD700",
    "teal": "#42949E",
    "violet": "#9A4D8E",
    "magenta": "#EA84DD",
}

DEFAULT_COLORS = [
    PALETTE["blue_main"],
    PALETTE["green_3"],
    PALETTE["red_strong"],
    PALETTE["teal"],
    PALETTE["violet"],
    PALETTE["neutral_light"],
]


def apply_publication_style(font_size=16, axes_linewidth=2.5, use_tex=False):
    """Apply Nature-style rcParams. Call once before creating any figures."""
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.sans-serif"] = ["Arial", "DejaVu Sans", "Liberation Sans"]
    plt.rcParams["svg.fonttype"] = "none"
    plt.rcParams["font.size"] = font_size
    plt.rcParams["axes.spines.right"] = False
    plt.rcParams["axes.spines.top"] = False
    plt.rcParams["axes.linewidth"] = axes_linewidth
    plt.rcParams["legend.frameon"] = False
    if use_tex:
        plt.rcParams["text.usetex"] = True


def add_panel_label(ax, label, x=-0.06, y=1.02, fontsize=14, color="black", fontweight="bold"):
    """Place a Nature-style panel label near the top-left edge."""
    ax.text(x, y, label, transform=ax.transAxes, fontsize=fontsize,
            fontweight=fontweight, color=color, ha="left", va="bottom")


def finalize_figure(fig, out_path, formats=None, dpi=300, pad=2, bbox_inches=None, close=True):
    """Apply tight_layout and save figure."""
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
        kw = {}
        if bbox_inches is not None:
            kw["bbox_inches"] = bbox_inches
        fig.savefig(p, dpi=dpi, **kw)
        saved.append(p)
    if close:
        plt.close(fig)
    return saved


# ------------------------------------------------------------------
# Data precomputation
# ------------------------------------------------------------------
def compute_full_chain_at_time(t):
    """Return xs, ys, thetas, velocities for all 223 segments at time t."""
    s = solve.v0 * t
    th1 = solve.theta_from_s(s)
    xs, ys, ths = solve.solve_chain(th1, t)
    vs = [float(solve.v0)]
    for i in range(1, solve.n):
        d = solve.d_head if i == 1 else solve.d_body
        thi = ths[i]
        thim1 = ths[i - 1]
        xi, yi = solve.xy(thi)
        xim1, yim1 = solve.xy(thim1)
        dx = xi - xim1
        dy = yi - yim1
        dist = (dx ** 2 + dy ** 2) ** 0.5
        if dist < 1e-10:
            vs.append(0.0)
            continue
        ux, uy = dx / dist, dy / dist
        vim1_x = -solve.v0 * (np.cos(thim1) - thim1 * np.sin(thim1)) / np.sqrt(1 + thim1 ** 2)
        vim1_y = -solve.v0 * (np.sin(thim1) + thim1 * np.cos(thim1)) / np.sqrt(1 + thim1 ** 2)
        vi = vim1_x * ux + vim1_y * uy
        vs.append(float(vi))
    return xs, ys, ths, vs


def build_velocity_matrix():
    """Compute velocity for all segments across all times (223 x 301)."""
    T = solve.T_max + 1
    V = np.zeros((solve.n, T))
    radii = np.zeros(T)
    for t in range(T):
        s = solve.v0 * t
        th1 = solve.theta_from_s(s)
        radii[t] = solve.b * th1
        xs, ys, ths, vs = compute_full_chain_at_time(t)
        V[:, t] = vs
    return V, radii


def rolling_median(x, window=5):
    x = np.asarray(x, dtype=float)
    n = len(x)
    y = x.copy()
    half = window // 2
    for i in range(half, n - half):
        y[i] = np.median(x[i - half:i + half + 1])
    return y


# ------------------------------------------------------------------
# Figure 1: Schematic-led composite (Pattern 12 from common-patterns.md)
# Top: 3 large spiral snapshots
# Bottom: radius trend + tail velocity trend
# ------------------------------------------------------------------
def fig1_composite():
    apply_publication_style(font_size=14, axes_linewidth=2)
    fig = plt.figure(figsize=(14, 9))
    gs = fig.add_gridspec(2, 3, height_ratios=[2.2, 1.0], hspace=0.30, wspace=0.28)

    times = [0, 150, 300]
    theta_bg = np.linspace(0, solve.theta0, 2000)
    x_bg = solve.b * theta_bg * np.cos(theta_bg)
    y_bg = solve.b * theta_bg * np.sin(theta_bg)
    cmap = LinearSegmentedColormap.from_list("vel", ["#E8F4FD", PALETTE["blue_main"]])

    # --- Top row: hero schematic panels ---
    for idx, t in enumerate(times):
        ax = fig.add_subplot(gs[0, idx])
        ax.set_aspect("equal", adjustable="box")
        ax.plot(x_bg, y_bg, color="#D0D0D0", lw=0.8, zorder=1)

        xs, ys, ths, vs = compute_full_chain_at_time(t)
        xs_arr = np.array(xs)
        ys_arr = np.array(ys)
        vmax = max(vs) if max(vs) > 0 else 1.0

        sc = ax.scatter(xs_arr, ys_arr, c=vs, cmap=cmap, s=14, vmin=0, vmax=vmax,
                        edgecolors="none", zorder=3)
        ax.plot(xs_arr, ys_arr, color=PALETTE["neutral_mid"], lw=0.4, alpha=0.5, zorder=2)
        ax.scatter(xs_arr[0], ys_arr[0], c=PALETTE["red_strong"], s=100, marker="*",
                   edgecolors="white", linewidths=0.8, zorder=5)
        ax.scatter(xs_arr[-1], ys_arr[-1], c=PALETTE["green_3"], s=60, marker="^",
                   edgecolors="white", linewidths=0.8, zorder=5)

        if idx == 2:
            cbar = fig.colorbar(sc, ax=ax, fraction=0.046, pad=0.04)
            cbar.set_label("Velocity (m/s)", fontsize=12)
            cbar.outline.set_linewidth(0.8)

        ax.set_title(f"t = {t} s", fontsize=15, fontweight="bold")
        ax.set_xlabel("x (m)", fontsize=13)
        ax.set_ylabel("y (m)", fontsize=13)
        margin = 1.5
        ax.set_xlim(xs_arr.min() - margin, xs_arr.max() + margin)
        ax.set_ylim(ys_arr.min() - margin, ys_arr.max() + margin)
        add_panel_label(ax, chr(ord("a") + idx), x=-0.08, y=1.02, fontsize=14)

    # --- Bottom row: supporting quant ---
    # Precompute all radii and tail velocities
    V, radii = build_velocity_matrix()
    tail_v = rolling_median(V[-1, :], window=5)
    times_all = np.arange(solve.T_max + 1)

    # d) Head radius vs time
    ax_d = fig.add_subplot(gs[1, 0])
    ax_d.plot(times_all, radii, color=PALETTE["blue_main"], lw=2.5)
    ax_d.fill_between(times_all, 0, radii, color=PALETTE["blue_main"], alpha=0.08)
    ax_d.set_xlabel("Time (s)", fontsize=13)
    ax_d.set_ylabel("Head radius (m)", fontsize=13)
    ax_d.set_ylim(0, radii[0] * 1.1)
    add_panel_label(ax_d, "d", x=-0.08, y=1.02, fontsize=14)

    # e) Tail velocity vs time
    ax_e = fig.add_subplot(gs[1, 1])
    ax_e.plot(times_all, tail_v, color=PALETTE["teal"], lw=2.5)
    ax_e.axhline(1.0, color=PALETTE["neutral_light"], ls="--", lw=1.2)
    ax_e.set_xlabel("Time (s)", fontsize=13)
    ax_e.set_ylabel("Tail velocity (m/s)", fontsize=13)
    ax_e.set_ylim(-0.05, 1.15)
    add_panel_label(ax_e, "e", x=-0.08, y=1.02, fontsize=14)

    # f) Legend-only panel
    ax_f = fig.add_subplot(gs[1, 2])
    from matplotlib.lines import Line2D
    legend_elements = [
        Line2D([0], [0], marker="*", color="w", markerfacecolor=PALETTE["red_strong"],
               markersize=12, label="Head"),
        Line2D([0], [0], marker="^", color="w", markerfacecolor=PALETTE["green_3"],
               markersize=10, label="Tail"),
    ]
    ax_f.legend(handles=legend_elements, loc="center", frameon=False, fontsize=13)
    ax_f.set_axis_off()
    add_panel_label(ax_f, "f", x=-0.08, y=1.02, fontsize=14)

    finalize_figure(fig, str(CHARTS_DIR / "fig_01_composite"),
                    formats=["svg", "png"], dpi=300, pad=2)
    print("  Saved fig_01_composite.svg / .png")


# ------------------------------------------------------------------
# Figure 2: Multi-panel trend (Pattern 3 / Tutorial 3)
# 4 velocity-profile panels + 1 legend-only panel
# ------------------------------------------------------------------
def fig2_trends():
    apply_publication_style(font_size=13, axes_linewidth=2)
    fig = plt.figure(figsize=(18, 5))
    gs = gridspec.GridSpec(1, 5, figure=fig, wspace=0.30)

    V, _ = build_velocity_matrix()
    times_sel = [0, 75, 150, 225, 300]
    colors = [PALETTE["blue_main"], "#4A90A4", PALETTE["teal"],
              PALETTE["violet"], PALETTE["neutral_mid"]]
    labels = [f"t = {t} s" for t in times_sel]
    segs = np.arange(solve.n)

    handles, labels_out = [], []
    for col, (t, c, lbl) in enumerate(zip(times_sel, colors, labels)):
        ax = fig.add_subplot(gs[col])
        line, = ax.plot(segs, V[:, t], color=c, lw=2.2, label=lbl)
        handles.append(line)
        labels_out.append(lbl)

        ax.set_xlabel("Segment index", fontsize=13)
        ax.set_ylabel("Velocity (m/s)", fontsize=13)
        ax.set_xlim(0, solve.n - 1)
        ax.set_ylim(-0.05, 1.15)
        ax.axhline(1.0, color=PALETTE["neutral_light"], ls="--", lw=1)
        add_panel_label(ax, chr(ord("a") + col), x=-0.06, y=1.02, fontsize=14)

    # Legend-only panel (last)
    ax_leg = fig.add_subplot(gs[-1])
    ax_leg.legend(handles, labels_out, fontsize=12, loc="center", frameon=False)
    ax_leg.set_axis_off()
    add_panel_label(ax_leg, "e", x=-0.06, y=1.02, fontsize=14)

    finalize_figure(fig, str(CHARTS_DIR / "fig_02_trends"),
                    formats=["svg", "png"], dpi=300, pad=2)
    print("  Saved fig_02_trends.svg / .png")


# ------------------------------------------------------------------
# Figure 3: Geometry + Heatmap (make_heatmap style + trend line)
# ------------------------------------------------------------------
def fig3_geometry_heatmap():
    apply_publication_style(font_size=14, axes_linewidth=2)
    fig = plt.figure(figsize=(14, 6))
    gs = fig.add_gridspec(1, 2, wspace=0.30)

    V, _ = build_velocity_matrix()

    # --- Panel a: Spiral geometry r(theta) ---
    ax1 = fig.add_subplot(gs[0, 0])
    theta_vals = np.linspace(0, solve.theta0, 1000)
    r_vals = solve.b * theta_vals
    ax1.plot(theta_vals, r_vals, color=PALETTE["blue_main"], lw=2.5)
    ax1.fill_between(theta_vals, 0, r_vals, color=PALETTE["blue_main"], alpha=0.08)

    ax1.scatter([solve.theta0], [solve.r0], color=PALETTE["red_strong"], s=80, zorder=5, marker="*")
    ax1.scatter([0], [0], color=PALETTE["neutral_black"], s=40, zorder=5)
    ax1.annotate("Start (t=0)", xy=(solve.theta0, solve.r0),
                 xytext=(solve.theta0 - 15, solve.r0 + 1.5),
                 arrowprops=dict(arrowstyle="->", color=PALETTE["neutral_mid"]),
                 fontsize=11, color=PALETTE["neutral_mid"])
    ax1.annotate("Center", xy=(0, 0), xytext=(15, 1.2),
                 arrowprops=dict(arrowstyle="->", color=PALETTE["neutral_mid"]),
                 fontsize=11, color=PALETTE["neutral_mid"])

    # Pitch annotation
    th_m = solve.theta0 / 2
    r_m = solve.b * th_m
    ax1.annotate("", xy=(th_m + 2 * np.pi, r_m + solve.p), xytext=(th_m, r_m),
                 arrowprops=dict(arrowstyle="<->", color=PALETTE["neutral_mid"], lw=1.2))
    ax1.text(th_m + np.pi, r_m + solve.p + 0.4, f"Pitch p = {solve.p} m",
             fontsize=10, color=PALETTE["neutral_mid"], ha="center")

    ax1.set_xlabel("Polar angle θ (rad)", fontsize=13)
    ax1.set_ylabel("Polar radius r (m)", fontsize=13)
    ax1.set_xlim(0, solve.theta0 * 1.05)
    ax1.set_ylim(0, solve.r0 * 1.15)
    add_panel_label(ax1, "a", x=-0.06, y=1.02, fontsize=14)

    # --- Panel b: Velocity heatmap ---
    ax2 = fig.add_subplot(gs[0, 1])
    extent = [0, solve.T_max, 0, solve.n]
    im = ax2.imshow(V, aspect="auto", cmap="YlGnBu", origin="lower",
                    extent=extent, interpolation="nearest", vmin=0, vmax=1)

    ax2.set_xlabel("Time (s)", fontsize=13)
    ax2.set_ylabel("Segment index", fontsize=13)
    ax2.set_xlim(0, solve.T_max)
    ax2.set_ylim(0, solve.n)
    add_panel_label(ax2, "b", x=-0.06, y=1.02, fontsize=14)

    cbar = fig.colorbar(im, ax=ax2, fraction=0.046, pad=0.04)
    cbar.set_label("Velocity (m/s)", fontsize=12)
    cbar.outline.set_linewidth(0.8)

    # Contour for v = 0.5
    T_grid = np.arange(solve.T_max + 1)
    S_grid = np.arange(solve.n)
    ax2.contour(T_grid, S_grid, V, levels=[0.5], colors=PALETTE["red_strong"],
                linewidths=1.5, linestyles="--")
    ax2.text(250, 180, "v = 0.5 m/s", fontsize=10, color=PALETTE["red_strong"])

    finalize_figure(fig, str(CHARTS_DIR / "fig_03_geometry_heatmap"),
                    formats=["svg", "png"], dpi=300, pad=2)
    print("  Saved fig_03_geometry_heatmap.svg / .png")


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------
def main():
    print("Computing full velocity matrix (223 segments x 301 timesteps)...")
    print("Generating figures with strict nature_figure skill conventions...")

    fig1_composite()
    fig2_trends()
    fig3_geometry_heatmap()

    print("All skill-compliant charts generated in", CHARTS_DIR)


if __name__ == "__main__":
    main()

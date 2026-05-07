#!/usr/bin/env python3
"""
Nature-level scientific visualization for 2024A 舞龙 spiral motion.
Generates 3 multi-panel figures following Nature journal standards.
"""
import sys
import json
import warnings
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
from matplotlib.patches import Circle
from matplotlib.lines import Line2D
from matplotlib.colors import LinearSegmentedColormap

# Import solver from parent execution directory
sys.path.insert(0, str(Path(__file__).parent.parent / "execution"))
import solve

CHARTS_DIR = Path(__file__).parent

# ------------------------------------------------------------------
# Nature style palette & rcParams
# ------------------------------------------------------------------
PALETTE = {
    "hero": "#0F4D92",      # deep blue
    "accent1": "#8BCF8B",   # green
    "accent2": "#E8A87C",   # warm orange
    "accent3": "#C38D9E",   # mauve
    "baseline": "#7F7F7F",  # gray
    "background": "#F5F5F5",
    "head": "#C41E3A",      # red for head
    "tail": "#2E8B57",      # sea green for tail
}


def _style(font_size=14, lw=2):
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Noto Sans CJK JP", "Arial", "DejaVu Sans", "Liberation Sans"],
        "svg.fonttype": "none",
        "axes.spines.right": False,
        "axes.spines.top": False,
        "axes.linewidth": 1.2,
        "xtick.major.width": 1.0,
        "ytick.major.width": 1.0,
        "xtick.minor.width": 0.6,
        "ytick.minor.width": 0.6,
        "xtick.major.size": 5,
        "ytick.major.size": 5,
        "xtick.minor.size": 3,
        "ytick.minor.size": 3,
        "xtick.direction": "out",
        "ytick.direction": "out",
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "savefig.facecolor": "white",
        "figure.dpi": 150,
        "font.size": font_size,
        "axes.titlesize": font_size + 2,
        "axes.labelsize": font_size,
        "legend.fontsize": font_size - 2,
        "lines.linewidth": lw,
        "lines.markersize": 6,
        "patch.linewidth": 1.0,
    })


def rolling_median(x, window=5):
    """Simple rolling median filter to remove single-point outliers."""
    x = np.asarray(x, dtype=float)
    n = len(x)
    y = x.copy()
    half = window // 2
    for i in range(half, n - half):
        y[i] = np.median(x[i - half:i + half + 1])
    return y


def _save(fig, name, dpi=300, pad=2):
    base = CHARTS_DIR / name
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fig.tight_layout(pad=pad)
    fig.savefig(str(base) + ".svg", bbox_inches="tight")
    fig.savefig(str(base) + ".png", dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved {name}.png / .svg")


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


# ------------------------------------------------------------------
# Figure 1: Spiral trajectory snapshots
# ------------------------------------------------------------------
def fig1_snapshots():
    _style(font_size=13, lw=1.8)
    fig = plt.figure(figsize=(16, 10))
    gs = GridSpec(2, 3, figure=fig, wspace=0.25, hspace=0.35)

    times = [0, 60, 120, 180, 240, 300]
    # Precompute full spiral curve for background
    theta_bg = np.linspace(0, solve.theta0, 2000)
    x_bg = solve.b * theta_bg * np.cos(theta_bg)
    y_bg = solve.b * theta_bg * np.sin(theta_bg)

    # Color map for segment velocity
    cmap = LinearSegmentedColormap.from_list("vel", ["#E8F4FD", "#0F4D92"])

    for idx, t in enumerate(times):
        ax = fig.add_subplot(gs[idx // 3, idx % 3])
        ax.set_aspect("equal", adjustable="box")

        # Background spiral
        ax.plot(x_bg, y_bg, color="#D0D0D0", lw=0.8, zorder=1)

        xs, ys, ths, vs = compute_full_chain_at_time(t)
        xs_arr = np.array(xs)
        ys_arr = np.array(ys)

        # Chain as scatter colored by velocity
        vmax = max(vs) if max(vs) > 0 else 1.0
        sc = ax.scatter(xs_arr, ys_arr, c=vs, cmap=cmap, s=18, vmin=0, vmax=vmax,
                        edgecolors="none", zorder=3)

        # Connect segments with faint line
        ax.plot(xs_arr, ys_arr, color="#7F7F7F", lw=0.5, alpha=0.6, zorder=2)

        # Head and tail
        ax.scatter(xs_arr[0], ys_arr[0], c=PALETTE["head"], s=120, marker="*",
                   edgecolors="white", linewidths=0.8, zorder=5, label="龙头")
        ax.scatter(xs_arr[-1], ys_arr[-1], c=PALETTE["tail"], s=80, marker="^",
                   edgecolors="white", linewidths=0.8, zorder=5, label="龙尾")

        # Pitch annotation at t=0
        if t == 0:
            # Draw a small arrow indicating pitch
            th_annot = solve.theta0 - 2 * np.pi
            r_annot = solve.b * th_annot
            x1 = r_annot * np.cos(th_annot)
            y1 = r_annot * np.sin(th_annot)
            x2 = (r_annot + 0.55) * np.cos(th_annot)
            y2 = (r_annot + 0.55) * np.sin(th_annot)
            ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                        arrowprops=dict(arrowstyle="<->", color=PALETTE["baseline"], lw=1.5))
            ax.text((x1 + x2) / 2 + 0.4, (y1 + y2) / 2 + 0.5, f"螺距 p = {solve.p} m",
                    fontsize=11, color=PALETTE["baseline"], fontweight="bold")

        ax.set_title(f"t = {t} s", fontweight="bold")
        ax.set_xlabel("x (m)")
        ax.set_ylabel("y (m)")

        # Dynamic limits to center the interesting region
        margin = 1.5
        ax.set_xlim(xs_arr.min() - margin, xs_arr.max() + margin)
        ax.set_ylim(ys_arr.min() - margin, ys_arr.max() + margin)

        # Colorbar for last panel only
        if idx == 5:
            cbar = plt.colorbar(sc, ax=ax, fraction=0.046, pad=0.04)
            cbar.set_label("速度 (m/s)")
            cbar.outline.set_linewidth(0.8)
            cbar.ax.tick_params(width=0.8)

    # Shared legend
    legend_elements = [
        Line2D([0], [0], marker="*", color="w", markerfacecolor=PALETTE["head"],
               markersize=12, label="龙头 (Head)"),
        Line2D([0], [0], marker="^", color="w", markerfacecolor=PALETTE["tail"],
               markersize=10, label="龙尾 (Tail)"),
    ]
    fig.legend(handles=legend_elements, loc="lower center", ncol=2,
              frameon=False, bbox_to_anchor=(0.5, -0.01))

    fig.suptitle("Figure 1 | 板凳龙螺线运动轨迹快照 (Archimedean Spiral Kinematics)",
                 fontsize=16, fontweight="bold", y=1.02)
    _save(fig, "fig_01_trajectory_snapshots", dpi=300)


# ------------------------------------------------------------------
# Figure 2: Velocity analysis
# ------------------------------------------------------------------
def fig2_velocity_analysis(V, radii):
    _style(font_size=14, lw=2)
    fig = plt.figure(figsize=(14, 6))
    gs = GridSpec(1, 2, figure=fig, wspace=0.30)

    # --- Panel a: velocity profiles along chain ---
    ax1 = fig.add_subplot(gs[0, 0])
    times_sel = [0, 75, 150, 225, 300]
    colors = [PALETTE["hero"], "#4A90A4", PALETTE["accent2"], PALETTE["accent3"], PALETTE["baseline"]]
    for t, c in zip(times_sel, colors):
        segs = np.arange(solve.n)
        ax1.plot(segs, V[:, t], color=c, lw=2, label=f"t = {t} s", alpha=0.9)

    ax1.set_xlabel("板凳节段序号 (Segment index)")
    ax1.set_ylabel("速度 (m/s)")
    ax1.set_title("a  链上速度分布", fontweight="bold", loc="left")
    ax1.set_xlim(0, solve.n - 1)
    ax1.set_ylim(-0.05, 1.15)
    ax1.legend(loc="upper right", frameon=False)
    ax1.axhline(1.0, color="#D0D0D0", ls="--", lw=1)
    ax1.text(solve.n * 0.65, 1.03, "龙头速度 = 1.0 m/s", fontsize=10, color=PALETTE["baseline"])

    # --- Panel b: head radius & tail velocity vs time ---
    ax2 = fig.add_subplot(gs[0, 1])
    times_all = np.arange(solve.T_max + 1)

    # Head radius
    ax2.plot(times_all, radii, color=PALETTE["hero"], lw=2.5, label="龙头半径")
    ax2.set_xlabel("时间 (s)")
    ax2.set_ylabel("龙头到中心半径 (m)", color=PALETTE["hero"])
    ax2.tick_params(axis="y", labelcolor=PALETTE["hero"])
    ax2.set_ylim(0, radii[0] * 1.1)
    ax2.set_title("b  龙头半径与龙尾速度", fontweight="bold", loc="left")

    # Tail velocity on twin axis
    ax2b = ax2.twinx()
    tail_v = rolling_median(V[-1, :], window=5)
    ax2b.plot(times_all, tail_v, color=PALETTE["accent2"], lw=2.5, ls="--", label="龙尾速度")
    ax2b.set_ylabel("龙尾速度 (m/s)", color=PALETTE["accent2"])
    ax2b.tick_params(axis="y", labelcolor=PALETTE["accent2"])
    ax2b.set_ylim(-0.05, 1.15)
    ax2b.spines["top"].set_visible(False)

    # Combined legend
    lines1, labels1 = ax2.get_legend_handles_labels()
    lines2, labels2 = ax2b.get_legend_handles_labels()
    ax2.legend(lines1 + lines2, labels1 + labels2, loc="upper right", frameon=False)

    fig.suptitle("Figure 2 | 板凳龙速度传播分析 (Velocity Propagation Analysis)",
                 fontsize=16, fontweight="bold", y=1.02)
    _save(fig, "fig_02_velocity_analysis", dpi=300)


# ------------------------------------------------------------------
# Figure 3: Geometric & kinematic heatmap
# ------------------------------------------------------------------
def fig3_heatmap(V):
    _style(font_size=14, lw=2)
    fig = plt.figure(figsize=(14, 6))
    gs = GridSpec(1, 2, figure=fig, wspace=0.30)

    # --- Panel a: spiral geometry r(theta) ---
    ax1 = fig.add_subplot(gs[0, 0])
    theta_vals = np.linspace(0, solve.theta0, 1000)
    r_vals = solve.b * theta_vals
    ax1.plot(theta_vals, r_vals, color=PALETTE["hero"], lw=2.5)
    ax1.fill_between(theta_vals, 0, r_vals, color=PALETTE["hero"], alpha=0.08)

    # Mark start and end
    ax1.scatter([solve.theta0], [solve.r0], color=PALETTE["head"], s=100, zorder=5, marker="*")
    ax1.scatter([0], [0], color="black", s=50, zorder=5)
    ax1.annotate("起点 (t=0)", xy=(solve.theta0, solve.r0),
                 xytext=(solve.theta0 - 15, solve.r0 + 1.5),
                 arrowprops=dict(arrowstyle="->", color=PALETTE["baseline"]),
                 fontsize=11, color=PALETTE["baseline"])
    ax1.annotate("螺线中心", xy=(0, 0), xytext=(15, 1.5),
                 arrowprops=dict(arrowstyle="->", color=PALETTE["baseline"]),
                 fontsize=11, color=PALETTE["baseline"])

    # Pitch annotation
    th_m = solve.theta0 / 2
    r_m = solve.b * th_m
    ax1.annotate("", xy=(th_m + 2 * np.pi, r_m + solve.p), xytext=(th_m, r_m),
                 arrowprops=dict(arrowstyle="<->", color=PALETTE["baseline"], lw=1.2))
    ax1.text(th_m + np.pi, r_m + solve.p + 0.4, f"螺距 p = {solve.p} m",
             fontsize=10, color=PALETTE["baseline"], ha="center")

    ax1.set_xlabel("极角 θ (rad)")
    ax1.set_ylabel("极半径 r (m)")
    ax1.set_title("a  阿基米德螺线几何", fontweight="bold", loc="left")
    ax1.set_xlim(0, solve.theta0 * 1.05)
    ax1.set_ylim(0, solve.r0 * 1.15)

    # --- Panel b: velocity heatmap ---
    ax2 = fig.add_subplot(gs[0, 1])
    # Subsample for cleaner visualization: every 5th segment, every 5th second
    seg_step = 5
    t_step = 5
    V_sub = V[::seg_step, ::t_step]
    extent = [0, solve.T_max, 0, solve.n]

    im = ax2.imshow(V, aspect="auto", cmap="YlGnBu", origin="lower",
                    extent=extent, interpolation="nearest", vmin=0, vmax=1)

    ax2.set_xlabel("时间 (s)")
    ax2.set_ylabel("板凳节段序号")
    ax2.set_title("b  全链速度时空分布", fontweight="bold", loc="left")
    ax2.set_xlim(0, solve.T_max)
    ax2.set_ylim(0, solve.n)

    cbar = plt.colorbar(im, ax=ax2, fraction=0.046, pad=0.04)
    cbar.set_label("速度 (m/s)")
    cbar.outline.set_linewidth(0.8)
    cbar.ax.tick_params(width=0.8)

    # Overlay contour for v = 0.5
    T_grid = np.arange(solve.T_max + 1)
    S_grid = np.arange(solve.n)
    ax2.contour(T_grid, S_grid, V, levels=[0.5], colors=PALETTE["head"],
                linewidths=1.5, linestyles="--")
    ax2.text(250, 180, "v = 0.5 m/s", fontsize=10, color=PALETTE["head"])

    fig.suptitle("Figure 3 | 螺线几何与速度时空演化 (Geometry & Spatiotemporal Evolution)",
                 fontsize=16, fontweight="bold", y=1.02)
    _save(fig, "fig_03_geometry_heatmap", dpi=300)


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------
def main():
    print("Computing full velocity matrix (223 segments × 301 timesteps)...")
    V, radii = build_velocity_matrix()
    print("Done. Generating figures...")

    fig1_snapshots()
    fig2_velocity_analysis(V, radii)
    fig3_heatmap(V)

    print("All Nature-level charts generated in", CHARTS_DIR)


if __name__ == "__main__":
    main()

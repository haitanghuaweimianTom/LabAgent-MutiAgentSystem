"""
Generic chart style engine for publication-ready figures.
Supports Nature-style and figures4papers-style output.
"""

from pathlib import Path
from typing import Dict, Any

NATURE_PALETTE: Dict[str, str] = {
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
}

F4P_COLORS = [
    "#0F4D92", "#8BCF8B", "#B64342", "#42949E",
    "#9A4D8E", "#CFCECE", "#FFD700", "#3775BA",
]


def apply_nature_style(font_size: int = 14, lw: int = 2):
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.sans-serif"] = [
        "Noto Sans CJK JP", "Arial", "DejaVu Sans", "Liberation Sans"
    ]
    plt.rcParams["svg.fonttype"] = "none"
    plt.rcParams["font.size"] = font_size
    plt.rcParams["axes.spines.right"] = False
    plt.rcParams["axes.spines.top"] = False
    plt.rcParams["axes.linewidth"] = lw
    plt.rcParams["legend.frameon"] = False
    plt.rcParams["axes.unicode_minus"] = False


def save_figure(fig, name: str, out_dir: Path, dpi: int = 300, pad: float = 2.0):
    import warnings
    base = out_dir / name
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fig.tight_layout(pad=pad)
    fig.savefig(str(base) + ".svg", bbox_inches="tight")
    fig.savefig(str(base) + ".png", dpi=dpi, bbox_inches="tight")
    fig.clf()


def add_panel_label(ax, label: str, fs: int = 12):
    ax.text(
        -0.08, 1.02, label, transform=ax.transAxes, fontsize=fs,
        fontweight="bold", va="bottom", ha="left"
    )


def get_color(i: int) -> str:
    return F4P_COLORS[i % len(F4P_COLORS)]

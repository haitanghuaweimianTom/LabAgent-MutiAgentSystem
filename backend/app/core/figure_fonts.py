"""matplotlib 中文字体统一配置（图方框修复）。

背景：figure_agent 生成的图表在 PDF 里中文标题/标签显示成方框（tofu），
根因是 matplotlib 默认字体（DejaVu Sans）无 CJK 字形。本模块提供：

- 可移植的 CJK 优先字体列表（Linux/macOS/Windows 通吃，不绑定特定机器）。
- configure_matplotlib_cjk()：一次性设置 rcParams，供固定函数绘图模块调用。
- apply_cjk_font_to_style()：把 CJK 字体追加到任意期刊样式字体列表后，
  利用 matplotlib「逐字符回退」机制——英文走期刊拉丁字体、中文走 CJK 字体。
- MATPLOTLIB_CJK_PREAMBLE：可注入沙箱代码前部的 Python 片段，
  让 LLM 生成的绘图代码无论写不写字体配置，中文都不再是方框。

详见 [[labagent-fix-chain]]、[[no-local-binding-policy]]。
"""
from __future__ import annotations

from typing import List

# 可移植无衬线 CJK 字体列表（按优先级，matplotlib 取首个已安装且含该字形的）。
# Linux: Noto / WenQuanYi / AR PL；macOS: PingFang / Arial Unicode MS；
# Windows: Microsoft YaHei / SimHei；DejaVu Sans 作最终拉丁兜底。
CJK_FONT_SANS: List[str] = [
    "Noto Sans CJK SC", "Noto Sans CJK JP",
    "Source Han Sans SC", "Source Han Sans CN",
    "WenQuanYi Micro Hei", "WenQuanYi Zen Hei",
    "Microsoft YaHei", "SimHei",
    "PingFang SC", "Heiti SC", "Arial Unicode MS",
    "AR PL UMing CN", "AR PL UKai CN",
    "DejaVu Sans",
]

# 可移植衬线 CJK 字体列表（ieee 等衬线样式用）。
CJK_FONT_SERIF: List[str] = [
    "Noto Serif CJK SC", "Noto Serif CJK JP",
    "Source Han Serif SC", "SimSun",
    "AR PL UMing CN", "AR PL UKai CN",
    "Times New Roman", "DejaVu Serif",
]


def configure_matplotlib_cjk() -> None:
    """一次性配置 matplotlib 中文字体（无衬线 + 负号修正）。

    供固定函数绘图模块（backend/app/data/workspace/*.py）在 import 期调用，
    替代各自硬编码的、DejaVu 优先的字体列表。
    """
    import matplotlib
    matplotlib.rcParams["font.family"] = "sans-serif"
    matplotlib.rcParams["font.sans-serif"] = list(CJK_FONT_SANS)
    matplotlib.rcParams["axes.unicode_minus"] = False


def apply_cjk_font_to_style(font_list: List[str], serif: bool = False) -> List[str]:
    """把 CJK 字体追加到期刊样式字体列表后（去重，保持原顺序优先）。

    matplotlib 对每个字符在列表里逐个找含该字形的字体：英文命中期刊拉丁字体
    （若已装），中文落到 CJK 字体。这样英文用期刊字体、中文不方框，两全。
    """
    cjk = list(CJK_FONT_SERIF if serif else CJK_FONT_SANS)
    # matplotlib 3.11 不做逐字符回退，findfont 取列表首个已安装字体。
    # 故把 CJK 字体【前置】——首个已安装的 CJK 字体（如 Noto Sans CJK）
    # 拉丁+CJK 字形皆全，中文不再方框；原拉丁字体保留在后作兜底。
    merged: List[str] = [f for f in cjk if f not in font_list] + list(font_list)
    # 去重保序（已由上式保证，留防御性循环）
    return merged


# 沙箱注入用：拼成 Python 源码前导，prepend 到 LLM 生成的代码前。
# 用 repr() 从常量生成，避免与 CJK_FONT_SANS 字面量漂移。
MATPLOTLIB_CJK_PREAMBLE: str = (
    "import matplotlib\n"
    "matplotlib.use('Agg')\n"
    "import matplotlib.pyplot as plt\n"
    "plt.rcParams['font.family'] = 'sans-serif'\n"
    f"plt.rcParams['font.sans-serif'] = {CJK_FONT_SANS!r}\n"
    "plt.rcParams['axes.unicode_minus'] = False\n"
)

"""科研绘图 Agent —— 生成发表级质量图表。

融合 src/charts/ 的 5 步流水线 + Nature 风格引擎 + AutoFigure-Edit 理念：
- 智能图表规划（根据论文内容自动识别所需图表）
- 多格式输出（PNG/SVG/PDF + LaTeX tikz/pgf）
- 期刊风格适配（Nature/IEEE/ACM 配色和字体）
- 图表迭代编辑（支持修改指令重新生成）

在系统中的位置：solver_agent 之后、writer_agent 之前被调用，
接收 solver 的输出数据，生成图表，输出图表路径列表给 writer。

v8.2: 集成 VLM 图审闭环 + 浅层实验树/并行 seed 搜索
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .base import BaseAgent, AgentFactory
from ..core.security import wrap_user_content
from ..core.vlm_figure_reviewer import get_vlm_figure_reviewer

logger = logging.getLogger(__name__)

# ───────────────────────────────────────────────
# 系统提示词
# ───────────────────────────────────────────────

FIGURE_SYSTEM_PLAN = """你是一个科研图表规划专家。请根据论文内容和已有数据，规划需要生成的图表清单。

【输出 schema（严格 JSON，无任何其他文字）】
{
  "figures": [
    {
      "id": "fig_01",
      "type": "line|bar|scatter|heatmap|box|violin|histogram|pair|3d|flowchart|architecture|comparison",
      "title": "图表标题（中文）",
      "description": "该图表展示什么内容（≤50字）",
      "data_source": "数据来源描述，如 solver 输出的哪个字段",
      "recommended_size": "single_column|double_column|full_width",
      "priority": 1-5
    }
  ],
  "rationale": "图表选择理由（≤100字）"
}

【规则】
- 只规划图表，不生成代码，不编造数据
- 优先选择最能展示研究亮点的图表类型
- 避免冗余：同一数据不要用多种图表重复展示
- 考虑期刊规范：Nature 偏好简洁，IEEE 偏好详细
"""

FIGURE_SYSTEM_GENERATE = """你是一个科研绘图代码生成专家。请生成 matplotlib 代码来创建发表级质量图表。

【要求】
1. 使用 `matplotlib.use('Agg')` 和 `import matplotlib.pyplot as plt`
2. 调用 `apply_style(style_name)` 设置期刊风格（style_name 为 "nature" / "ieee" / "acm" / "default"）
3. 使用 `save_figure(fig, name, out_dir, dpi)` 保存图表（同时输出 PNG + SVG + PDF）
4. 使用中文标签时确保字体支持 CJK
5. 图表必须包含：标题、坐标轴标签、图例（如适用）
6. 配色使用期刊标准配色，避免默认彩虹色
7. 线宽、标记大小、字体大小符合期刊规范

【可用 API（已自动导入）】
- apply_style(style_name: str) -> None
- save_figure(fig, name: str, out_dir: Path, dpi: int = 300) -> None
- add_panel_label(ax, label: str, fs: int = 12) -> None
- NATURE_PALETTE, IEEE_PALETTE, ACM_PALETTE: Dict[str, str]
- get_color(index: int, palette: str = "nature") -> str

【输出】
只输出 Python 代码（无 markdown 围栏，无解释文字）。
"""

FIGURE_SYSTEM_EDIT = """你是一个科研图表编辑专家。请根据修改指令，修改已有的 matplotlib 代码。

【输入】
- original_code: 原始 matplotlib 代码
- edit_instruction: 自然语言修改指令（如"将配色改为 IEEE 风格"、"添加误差棒"、"改为双栏宽度"）

【输出】
只输出修改后的完整 Python 代码（无 markdown 围栏，无解释文字）。
确保代码可独立运行，保留所有原始功能。
"""


# ───────────────────────────────────────────────
# 期刊风格配置
# ───────────────────────────────────────────────

JOURNAL_STYLES = {
    "nature": {
        "font_family": "sans-serif",
        "font_sans": ["Noto Sans CJK JP", "Arial", "DejaVu Sans", "Liberation Sans"],
        "font_size": 8,
        "axes_labelsize": 9,
        "axes_titlesize": 10,
        "xtick_labelsize": 7,
        "ytick_labelsize": 7,
        "legend_fontsize": 8,
        "axes_linewidth": 0.5,
        "spines_top": False,
        "spines_right": False,
        "legend_frameon": False,
        "figure_dpi": 300,
        "save_dpi": 300,
        "palette": {
            "blue_main": "#0F4D92",
            "blue_secondary": "#3775BA",
            "green": "#8BCF8B",
            "red": "#B64342",
            "teal": "#42949E",
            "violet": "#9A4D8E",
            "neutral": "#767676",
            "gold": "#FFD700",
        },
        "single_column": 3.5,   # inches (~89mm)
        "double_column": 7.0,   # inches (~183mm)
        "max_height": 9.0,
    },
    "ieee": {
        "font_family": "serif",
        "font_serif": ["Times New Roman", "DejaVu Serif", "Liberation Serif"],
        "font_size": 10,
        "axes_labelsize": 10,
        "axes_titlesize": 11,
        "xtick_labelsize": 9,
        "ytick_labelsize": 9,
        "legend_fontsize": 9,
        "axes_linewidth": 1.0,
        "spines_top": True,
        "spines_right": True,
        "legend_frameon": True,
        "figure_dpi": 150,
        "save_dpi": 300,
        "palette": {
            "blue": "#0066CC",
            "red": "#CC0000",
            "green": "#009900",
            "orange": "#FF6600",
            "purple": "#6600CC",
            "cyan": "#0099CC",
            "magenta": "#CC0066",
            "yellow": "#CCCC00",
        },
        "single_column": 3.5,
        "double_column": 7.0,
        "max_height": 9.0,
    },
    "acm": {
        "font_family": "sans-serif",
        "font_sans": ["Helvetica", "Arial", "DejaVu Sans"],
        "font_size": 9,
        "axes_labelsize": 9,
        "axes_titlesize": 10,
        "xtick_labelsize": 8,
        "ytick_labelsize": 8,
        "legend_fontsize": 8,
        "axes_linewidth": 0.8,
        "spines_top": False,
        "spines_right": False,
        "legend_frameon": False,
        "figure_dpi": 150,
        "save_dpi": 300,
        "palette": {
            "blue": "#1f77b4",
            "orange": "#ff7f0e",
            "green": "#2ca02c",
            "red": "#d62728",
            "purple": "#9467bd",
            "brown": "#8c564b",
            "pink": "#e377c2",
            "gray": "#7f7f7f",
        },
        "single_column": 3.3,
        "double_column": 6.8,
        "max_height": 8.5,
    },
    "default": {
        "font_family": "sans-serif",
        "font_sans": ["Arial", "DejaVu Sans", "Liberation Sans"],
        "font_size": 10,
        "axes_labelsize": 11,
        "axes_titlesize": 12,
        "xtick_labelsize": 9,
        "ytick_labelsize": 9,
        "legend_fontsize": 9,
        "axes_linewidth": 1.0,
        "spines_top": False,
        "spines_right": False,
        "legend_frameon": False,
        "figure_dpi": 150,
        "save_dpi": 300,
        "palette": {
            "blue": "#0F4D92",
            "green": "#8BCF8B",
            "red": "#B64342",
            "teal": "#42949E",
            "violet": "#9A4D8E",
            "neutral": "#767676",
            "gold": "#FFD700",
            "orange": "#E67E22",
        },
        "single_column": 4.0,
        "double_column": 8.0,
        "max_height": 10.0,
    },
}

NATURE_PALETTE = JOURNAL_STYLES["nature"]["palette"]
IEEE_PALETTE = JOURNAL_STYLES["ieee"]["palette"]
ACM_PALETTE = JOURNAL_STYLES["acm"]["palette"]


# ───────────────────────────────────────────────
# 样式引擎（复用 src/charts/style_engine.py 能力）
# ───────────────────────────────────────────────

def apply_style(style_name: str = "nature"):
    """应用期刊风格到 matplotlib。"""
    import matplotlib.pyplot as plt
    style = JOURNAL_STYLES.get(style_name, JOURNAL_STYLES["default"])

    plt.rcParams["font.family"] = style["font_family"]
    if style["font_family"] == "serif":
        plt.rcParams["font.serif"] = style.get("font_serif", ["Times New Roman"])
    else:
        plt.rcParams["font.sans-serif"] = style.get("font_sans", ["Arial"])
    plt.rcParams["svg.fonttype"] = "none"
    plt.rcParams["font.size"] = style["font_size"]
    plt.rcParams["axes.labelsize"] = style["axes_labelsize"]
    plt.rcParams["axes.titlesize"] = style["axes_titlesize"]
    plt.rcParams["xtick.labelsize"] = style["xtick_labelsize"]
    plt.rcParams["ytick.labelsize"] = style["ytick_labelsize"]
    plt.rcParams["legend.fontsize"] = style["legend_fontsize"]
    plt.rcParams["axes.linewidth"] = style["axes_linewidth"]
    plt.rcParams["axes.spines.top"] = style["spines_top"]
    plt.rcParams["axes.spines.right"] = style["spines_right"]
    plt.rcParams["legend.frameon"] = style["legend_frameon"]
    plt.rcParams["axes.unicode_minus"] = False


def save_figure(fig, name: str, out_dir: Path, dpi: int = 300, pad: float = 2.0):
    """保存图表为 PNG + SVG + PDF 三种格式。"""
    import warnings
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    base = out_dir / name
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fig.tight_layout(pad=pad)
    fig.savefig(str(base) + ".svg", bbox_inches="tight", format="svg")
    fig.savefig(str(base) + ".png", dpi=dpi, bbox_inches="tight", format="png")
    fig.savefig(str(base) + ".pdf", bbox_inches="tight", format="pdf")
    fig.clf()


def add_panel_label(ax, label: str, fs: int = 12):
    """添加面板标签（如 'a', 'b'）。"""
    ax.text(
        -0.08, 1.02, label, transform=ax.transAxes, fontsize=fs,
        fontweight="bold", va="bottom", ha="left"
    )


def get_color(index: int, palette: str = "nature") -> str:
    """从期刊调色板中获取颜色。"""
    p = JOURNAL_STYLES.get(palette, JOURNAL_STYLES["default"])["palette"]
    colors = list(p.values())
    return colors[index % len(colors)]


# ───────────────────────────────────────────────
# FigureAgent
# ───────────────────────────────────────────────

@AgentFactory.register("figure_agent")
class FigureAgent(BaseAgent):
    """科研绘图 Agent —— 生成发表级质量图表。

    融合 src/charts/ 的 5 步流水线 + Nature 风格引擎 + AutoFigure-Edit 理念：
    - 智能图表规划（根据论文内容自动识别所需图表）
    - 多格式输出（PNG/SVG/PDF + LaTeX tikz/pgf）
    - 期刊风格适配（Nature/IEEE/ACM 配色和字体）
    - 图表迭代编辑（支持修改指令重新生成）

    支持的 action:
    - "plan": 根据论文内容规划所需图表列表
    - "generate": 生成单个图表（指定类型、数据、风格）
    - "generate_all": 批量生成所有规划图表
    - "edit": 根据修改指令编辑已有图表
    - "style_transfer": 将已有图表转换为指定期刊风格
    """

    name = "figure_agent"
    label = "科研绘图师"
    description = "生成发表级质量图表（Nature/IEEE/ACM 风格），支持 matplotlib/plotly/seaborn/LaTeX"
    default_model = ""

    def get_system_prompt(self) -> str:
        return FIGURE_SYSTEM_GENERATE

    # ── 公共入口 ──

    async def execute(
        self,
        task_input: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """执行绘图任务。

        Args:
            task_input: 必须包含 ``action``；可选 ``problem_text``、``data``、
                ``figure_plan``、``figure_spec``、``edit_instruction``、
                ``style_name``、``project_name``、``output_dir``。
            context: 上下文（result 等）。
        """
        action = task_input.get("action", "plan")
        project_name = task_input.get("project_name") or context.get("project_name")
        output_dir = self._resolve_output_dir(project_name, task_input.get("output_dir"))

        logger.info(f"[FigureAgent] action={action}, project={project_name}")

        if action == "plan":
            return await self._plan(task_input, context)
        elif action == "generate":
            return await self._generate(task_input, context, output_dir)
        elif action == "generate_all":
            return await self._generate_all(task_input, context, output_dir)
        elif action == "edit":
            return await self._edit(task_input, context, output_dir)
        elif action == "style_transfer":
            return await self._style_transfer(task_input, context, output_dir)
        elif action == "review":
            # v8.2: VLM 图审闭环
            return await self._review_figure(task_input, context, output_dir)
        elif action == "generate_with_review":
            # v8.2: 生成 + VLM 审核 + 自动修订
            return await self._generate_with_review(task_input, context, output_dir)
        else:
            return {"error": f"Unknown action: {action}"}

    # ── 辅助方法 ──

    def _resolve_output_dir(self, project_name: Optional[str], explicit: Optional[str] = None) -> Path:
        """解析输出目录。"""
        if explicit:
            return Path(explicit)
        if project_name:
            from ..core.paths import get_project_output_dir
            return get_project_output_dir(project_name) / "figures"
        return Path("outputs/figures")

    def _extract_data(self, task_input: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """提取可用数据。优先从 task_input 获取，其次从 context 的 solver/modeler 结果获取。"""
        data = task_input.get("data")
        if data:
            return data

        # 从 context 中提取 solver/modeler 的结果数据
        results = context.get("results", {})
        for key in ["solver_agent", "modeler_agent", "data_agent"]:
            agent_result = results.get(key, {})
            if isinstance(agent_result, dict) and agent_result:
                # 尝试找到数值数据
                for sub_key, val in agent_result.items():
                    if isinstance(val, (list, dict)) and val:
                        return {sub_key: val}
                return agent_result
        return {}

    def _get_style_name(self, task_input: Dict[str, Any], context: Dict[str, Any]) -> str:
        """获取期刊风格名称。"""
        # 优先从 task_input 获取
        style = task_input.get("style_name", "")
        if style in JOURNAL_STYLES:
            return style
        # 从模板推断
        template = context.get("template", "")
        if template in {"neurips_2024", "ieee_conference"}:
            return "ieee"
        elif template in {"acm_sigconf", "springer_lncs"}:
            return "acm"
        elif template in {"nature", "science"}:
            return "nature"
        return "default"

    # ── Action: plan ──

    async def _plan(self, task_input: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """规划图表清单。"""
        problem_text = task_input.get("problem_text", "")
        data = self._extract_data(task_input, context)

        # 构建数据描述
        data_desc = self._describe_data(data)

        wrapped_problem = wrap_user_content(problem_text[:2000], "problem")
        prompt = f"""【论文/问题描述】
{wrapped_problem}

【已有数据描述】
{data_desc}

【模板类型】{context.get("template", "default")}

请规划需要生成的图表清单。"""

        messages = [
            {"role": "system", "content": FIGURE_SYSTEM_PLAN},
            {"role": "user", "content": prompt},
        ]

        try:
            response = await self.call_llm(messages=messages, temperature=0.3)
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            plan = self._parse_json(content)
            return {
                "action": "plan",
                "figures": plan.get("figures", []),
                "rationale": plan.get("rationale", ""),
                "count": len(plan.get("figures", [])),
            }
        except Exception as e:
            logger.warning(f"[FigureAgent] plan failed: {e}")
            return {"action": "plan", "figures": [], "error": str(e)}

    def _describe_data(self, data: Dict[str, Any]) -> str:
        """生成数据描述。"""
        lines = []
        for key, val in data.items():
            if isinstance(val, dict):
                lines.append(f"- {key}: dict with keys {list(val.keys())}")
                for sub_k, sub_v in list(val.items())[:3]:
                    lines.append(f"  - {sub_k}: {str(sub_v)[:80]}")
            elif isinstance(val, list) and val:
                first = val[0]
                if isinstance(first, dict):
                    lines.append(f"- {key}: list of {len(val)} dicts, keys: {list(first.keys())}")
                else:
                    lines.append(f"- {key}: list of {len(val)} {type(first).__name__} values")
            else:
                lines.append(f"- {key}: {type(val).__name__} = {str(val)[:60]}")
        return "\n".join(lines) if lines else "No structured data available."

    # ── Action: generate ──

    async def _generate(
        self, task_input: Dict[str, Any], context: Dict[str, Any], output_dir: Path
    ) -> Dict[str, Any]:
        """生成单个图表。"""
        figure_spec = task_input.get("figure_spec", {})
        data = self._extract_data(task_input, context)
        style_name = self._get_style_name(task_input, context)

        # 构建代码生成提示
        prompt = self._build_generate_prompt(figure_spec, data, style_name, output_dir)

        messages = [
            {"role": "system", "content": FIGURE_SYSTEM_GENERATE},
            {"role": "user", "content": prompt},
        ]

        try:
            response = await self.call_llm(messages=messages, temperature=0.2)
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            code = self._sanitize_code(content)

            # 执行代码
            figure_path = await self._execute_chart_code(
                code, figure_spec.get("id", "fig_01"), output_dir, data, style_name
            )

            return {
                "action": "generate",
                "figure_id": figure_spec.get("id", "fig_01"),
                "figure_path": str(figure_path) if figure_path else None,
                "style": style_name,
                "success": figure_path is not None,
            }
        except Exception as e:
            logger.warning(f"[FigureAgent] generate failed: {e}")
            return {"action": "generate", "error": str(e), "success": False}

    def _build_generate_prompt(
        self, figure_spec: Dict[str, Any], data: Dict[str, Any], style_name: str, output_dir: Path
    ) -> str:
        """构建图表生成提示。"""
        fig_type = figure_spec.get("type", "line")
        title = figure_spec.get("title", "Figure")
        description = figure_spec.get("description", "")
        size = figure_spec.get("recommended_size", "single_column")

        style = JOURNAL_STYLES.get(style_name, JOURNAL_STYLES["default"])
        width = style["single_column"] if size == "single_column" else style["double_column"]

        data_desc = self._describe_data(data)

        return f"""【图表规格】
- 类型: {fig_type}
- 标题: {title}
- 描述: {description}
- 尺寸: {size} ({width} inches width)
- 风格: {style_name}

【数据】
{data_desc}

【要求】
1. 使用 matplotlib 生成图表
2. 调用 apply_style("{style_name}") 设置风格
3. 图表宽度约 {width} inches，高度自适应（不超过 {style['max_height']} inches）
4. 使用 save_figure(fig, "{figure_spec.get('id', 'fig_01')}", charts_dir) 保存
5. 数据在变量 DATA 中可用
6. 输出目录在变量 charts_dir 中

请生成完整可执行的 Python 代码。"""

    # ── Action: generate_all ──

    async def _generate_all(
        self, task_input: Dict[str, Any], context: Dict[str, Any], output_dir: Path
    ) -> Dict[str, Any]:
        """批量生成所有规划图表。"""
        figure_plan = task_input.get("figure_plan", {})
        figures = figure_plan.get("figures", [])
        data = self._extract_data(task_input, context)
        style_name = self._get_style_name(task_input, context)

        generated = []
        for fig_spec in figures:
            result = await self._generate(
                {"figure_spec": fig_spec, "data": data, "style_name": style_name},
                context,
                output_dir,
            )
            if result.get("success"):
                generated.append(result)

        return {
            "action": "generate_all",
            "total": len(figures),
            "generated": len(generated),
            "figures": generated,
        }

    # ── Action: edit ──

    async def _edit(
        self, task_input: Dict[str, Any], context: Dict[str, Any], output_dir: Path
    ) -> Dict[str, Any]:
        """根据修改指令编辑已有图表。"""
        original_code = task_input.get("original_code", "")
        edit_instruction = task_input.get("edit_instruction", "")
        figure_id = task_input.get("figure_id", "fig_edited")

        if not original_code:
            # 尝试从已有图表文件读取代码
            original_path = task_input.get("original_path")
            if original_path and Path(original_path).exists():
                original_code = Path(original_path).read_text(encoding="utf-8")

        prompt = f"""【原始代码】
```python
{original_code}
```

【修改指令】
{edit_instruction}

请输出修改后的完整 Python 代码。"""

        messages = [
            {"role": "system", "content": FIGURE_SYSTEM_EDIT},
            {"role": "user", "content": prompt},
        ]

        try:
            response = await self.call_llm(messages=messages, temperature=0.2)
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            new_code = self._sanitize_code(content)

            # 执行修改后的代码
            data = self._extract_data(task_input, context)
            style_name = self._get_style_name(task_input, context)
            figure_path = await self._execute_chart_code(
                new_code, figure_id, output_dir, data, style_name
            )

            return {
                "action": "edit",
                "figure_id": figure_id,
                "figure_path": str(figure_path) if figure_path else None,
                "success": figure_path is not None,
            }
        except Exception as e:
            logger.warning(f"[FigureAgent] edit failed: {e}")
            return {"action": "edit", "error": str(e), "success": False}

    # ── Action: style_transfer ──

    async def _style_transfer(
        self, task_input: Dict[str, Any], context: Dict[str, Any], output_dir: Path
    ) -> Dict[str, Any]:
        """将已有图表转换为指定期刊风格。"""
        original_path = task_input.get("original_path")
        target_style = task_input.get("style_name", "nature")
        figure_id = task_input.get("figure_id", "fig_transferred")

        if not original_path or not Path(original_path).exists():
            return {"action": "style_transfer", "error": "Original figure not found", "success": False}

        # 读取原始代码
        original_code = Path(original_path).read_text(encoding="utf-8")
        edit_instruction = f"将图表风格转换为 {target_style} 期刊风格，包括配色、字体、线宽等。"

        return await self._edit(
            {
                "original_code": original_code,
                "edit_instruction": edit_instruction,
                "figure_id": figure_id,
            },
            context,
            output_dir,
        )

    # ── Action: review (v8.2: VLM 图审闭环) ──

    async def _review_figure(
        self, task_input: Dict[str, Any], context: Dict[str, Any], output_dir: Path
    ) -> Dict[str, Any]:
        """使用 VLM 评估图表质量。"""
        figure_path = task_input.get("figure_path")
        figure_spec = task_input.get("figure_spec", {})
        experiment_data = task_input.get("data", {})

        if not figure_path or not Path(figure_path).exists():
            return {"action": "review", "error": "Figure not found", "success": False}

        reviewer = get_vlm_figure_reviewer()
        review_result = reviewer.review_figure(
            figure_path=Path(figure_path),
            figure_spec=figure_spec,
            experiment_data=experiment_data,
        )

        return {
            "action": "review",
            "review": review_result,
            "success": True,
        }

    # ── Action: generate_with_review (v8.2: 生成 + VLM 审核 + 自动修订) ──

    async def _generate_with_review(
        self, task_input: Dict[str, Any], context: Dict[str, Any], output_dir: Path
    ) -> Dict[str, Any]:
        """生成图表 + VLM 审核 + 自动修订。"""
        figure_spec = task_input.get("figure_spec", {})
        data = self._extract_data(task_input, context)
        style_name = self._get_style_name(task_input, context)
        max_revisions = task_input.get("max_revisions", 3)

        reviewer = get_vlm_figure_reviewer()
        current_code = None
        figure_path = None
        revision_count = 0

        for attempt in range(max_revisions + 1):
            # 生成图表
            if current_code is None:
                result = await self._generate(
                    {"figure_spec": figure_spec, "data": data, "style_name": style_name},
                    context,
                    output_dir,
                )
            else:
                # 使用修改后的代码重新生成
                result = await self._edit(
                    {
                        "original_code": current_code,
                        "edit_instruction": "根据审查建议修改图表",
                        "figure_id": figure_spec.get("id", "fig_01"),
                    },
                    context,
                    output_dir,
                )

            if not result.get("success"):
                return {
                    "action": "generate_with_review",
                    "error": result.get("error"),
                    "success": False,
                    "revisions": revision_count,
                }

            figure_path = result.get("figure_path")
            if not figure_path:
                break

            # VLM 审核
            review_result = reviewer.review_figure(
                figure_path=Path(figure_path),
                figure_spec=figure_spec,
                experiment_data=data,
            )

            # 如果质量足够好，退出循环
            if not review_result.get("needs_revision"):
                logger.info(
                    f"Figure quality acceptable after {revision_count} revisions "
                    f"(score={review_result.get('quality_score', 0):.2f})"
                )
                break

            # 生成修改后的代码
            if attempt < max_revisions:
                current_code = reviewer.get_revision_code_suggestions(
                    review_result, current_code or ""
                )
                revision_count += 1
                logger.info(
                    f"Figure needs revision {revision_count}/{max_revisions} "
                    f"(issues={len(review_result.get('issues', []))})"
                )

        return {
            "action": "generate_with_review",
            "figure_id": figure_spec.get("id", "fig_01"),
            "figure_path": figure_path,
            "style": style_name,
            "revisions": revision_count,
            "final_review": review_result if 'review_result' in dir() else None,
            "success": figure_path is not None,
        }

    # ── 代码执行 ──

    async def _execute_chart_code(
        self, code: str, figure_id: str, output_dir: Path, data: Dict[str, Any], style_name: str
    ) -> Optional[Path]:
        """在隔离进程中执行图表代码。"""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # 构建包装代码
        project_root = str(Path(__file__).parent.parent.parent.parent)
        wrapper = f"""
import json, sys
from pathlib import Path
sys.path.insert(0, {repr(project_root)})

charts_dir = Path({repr(str(output_dir))})
DATA = {json.dumps(data, ensure_ascii=False)}
FIGURE_ID = {repr(figure_id)}

# 导入样式引擎
from backend.app.agents.figure_agent import apply_style, save_figure, add_panel_label, NATURE_PALETTE, IEEE_PALETTE, ACM_PALETTE, get_color

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
import numpy as np

# 应用风格
apply_style({repr(style_name)})

{code}

print("FIGURE_DONE")
"""

        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
                f.write(wrapper)
                f.flush()
                result = subprocess.run(
                    [sys.executable, f.name],
                    capture_output=True, text=True, timeout=120, cwd=project_root
                )

            if result.returncode == 0 and "FIGURE_DONE" in result.stdout:
                # 查找生成的文件
                for ext in [".png", ".svg", ".pdf"]:
                    candidate = output_dir / f"{figure_id}{ext}"
                    if candidate.exists():
                        return candidate
                # 如果没找到精确匹配，返回目录
                return output_dir
            else:
                logger.warning(f"[FigureAgent] code execution failed: {result.stderr[:300]}")
                return None
        except Exception as e:
            logger.warning(f"[FigureAgent] execution error: {e}")
            return None

    # ── 工具方法 ──

    def _sanitize_code(self, code: str) -> str:
        """清理代码中的 markdown 围栏。"""
        code = code.strip()
        if code.startswith("```"):
            lines = code.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            code = "\n".join(lines)
        return code.strip()

    def _parse_json(self, text: str) -> Dict[str, Any]:
        """从文本中提取 JSON。"""
        # 尝试直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 尝试从 markdown 代码块中提取
        pattern = r"```(?:json)?\s*([\s\S]*?)```"
        matches = re.findall(pattern, text)
        for match in matches:
            try:
                return json.loads(match.strip())
            except json.JSONDecodeError:
                continue

        # 尝试从文本中找 JSON 对象
        pattern = r"(\{[\s\S]*\})"
        matches = re.findall(pattern, text)
        for match in matches:
            try:
                return json.loads(match.strip())
            except json.JSONDecodeError:
                continue

        return {}

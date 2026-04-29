"""
Mermaid 图表渲染模块
====================

借鉴 cherry-studio 的 Mermaid 支持，
为数学建模论文提供图表渲染能力。

支持从 Markdown 文本中提取 Mermaid 代码块并渲染为图片。

使用方法:
    from src.visualization.mermaid import MermaidRenderer

    renderer = MermaidRenderer()

    # 渲染单个 Mermaid 图表
    renderer.render(
        "graph TD; A-->B; B-->C;",
        output_path="flowchart.png"
    )

    # 从 Markdown 提取并渲染所有 Mermaid 图表
    renderer.render_from_markdown("paper.md", output_dir="charts/")

支持的输出格式:
- png (默认)
- svg
- pdf
"""

from .renderer import MermaidRenderer

__all__ = ["MermaidRenderer"]

"""
Mermaid 图表渲染器
==================

封装 mmdc (Mermaid CLI) 提供图表渲染功能。
支持从 Markdown 提取 Mermaid 代码块并批量渲染。
"""

import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass


@dataclass
class RenderResult:
    """渲染结果"""
    success: bool
    output_path: Optional[str] = None
    error: Optional[str] = None


class MermaidRenderer:
    """Mermaid 图表渲染器"""

    def __init__(self, mmdc_cmd: Optional[str] = None):
        self.mmdc_cmd = mmdc_cmd or self._find_mmdc()
        self.default_format = "png"
        self.default_width = 1200
        self.default_height = 800
        self.default_background = "white"

    def _find_mmdc(self) -> Optional[str]:
        """查找 mmdc 命令"""
        # 优先查找全局安装的 mmdc
        mmdc = shutil.which("mmdc")
        if mmdc:
            return mmdc
        # 检查 npx 是否可用
        if shutil.which("npx"):
            return "npx"
        return None

    def is_available(self) -> bool:
        """检查渲染器是否可用"""
        if not self.mmdc_cmd:
            return False
        try:
            if self.mmdc_cmd == "npx":
                result = subprocess.run(
                    ["npx", "-y", "@mermaid-js/mermaid-cli", "mmdc", "--version"],
                    capture_output=True, text=True, timeout=60
                )
            else:
                result = subprocess.run(
                    [self.mmdc_cmd, "--version"],
                    capture_output=True, text=True, timeout=10
                )
            return result.returncode == 0
        except Exception:
            return False

    def render(
        self,
        mermaid_code: str,
        output_path: str,
        output_format: Optional[str] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        background: Optional[str] = None,
        theme: str = "default",
        timeout: int = 120,
    ) -> RenderResult:
        """
        渲染 Mermaid 图表

        Args:
            mermaid_code: Mermaid 语法代码
            output_path: 输出图片路径
            output_format: 输出格式 (png/svg/pdf)
            width: 图片宽度
            height: 图片高度
            background: 背景颜色
            theme: Mermaid 主题
            timeout: 渲染超时时间

        Returns:
            RenderResult: 渲染结果
        """
        if not self.is_available():
            return RenderResult(
                success=False,
                error="Mermaid CLI (mmdc) 未找到，请运行: npm install -g @mermaid-js/mermaid-cli"
            )

        fmt = output_format or self.default_format
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # 确保输出路径有正确的扩展名
        if not output_path.suffix:
            output_path = output_path.with_suffix(f".{fmt}")

        # 创建临时输入文件
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".mmd", delete=False, encoding="utf-8"
        ) as f:
            f.write(mermaid_code.strip() + "\n")
            input_file = f.name

        try:
            cmd = self._build_command(
                input_file=input_file,
                output_path=str(output_path),
                fmt=fmt,
                width=width or self.default_width,
                height=height or self.default_height,
                background=background or self.default_background,
                theme=theme,
            )

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            if result.returncode != 0:
                error_msg = result.stderr or "未知错误"
                return RenderResult(
                    success=False,
                    error=f"Mermaid 渲染失败: {error_msg[:500]}"
                )

            if not output_path.exists():
                return RenderResult(
                    success=False,
                    error="渲染成功但输出文件未生成"
                )

            return RenderResult(
                success=True,
                output_path=str(output_path)
            )

        except subprocess.TimeoutExpired:
            return RenderResult(
                success=False,
                error=f"Mermaid 渲染超时 ({timeout}秒)"
            )
        except Exception as e:
            return RenderResult(
                success=False,
                error=f"渲染异常: {str(e)}"
            )
        finally:
            # 清理临时文件
            try:
                os.unlink(input_file)
            except Exception:
                pass

    def _build_command(
        self,
        input_file: str,
        output_path: str,
        fmt: str,
        width: int,
        height: int,
        background: str,
        theme: str,
    ) -> List[str]:
        """构建 mmdc 命令"""
        if self.mmdc_cmd == "npx":
            cmd = [
                "npx", "-y", "@mermaid-js/mermaid-cli",
                "mmdc",
                "-i", input_file,
                "-o", output_path,
                "-b", background,
                "-t", theme,
            ]
        else:
            cmd = [
                self.mmdc_cmd,
                "-i", input_file,
                "-o", output_path,
                "-b", background,
                "-t", theme,
            ]

        if fmt in ("svg", "pdf"):
            cmd.extend(["-e", fmt])

        return cmd

    def extract_from_markdown(self, markdown_text: str) -> List[Dict[str, str]]:
        """
        从 Markdown 文本中提取 Mermaid 代码块

        Returns:
            List[Dict]: 每个元素包含 {
                "code": mermaid代码,
                "caption": 标题(如果有),
                "index": 索引
            }
        """
        # 匹配 ```mermaid ... ``` 代码块
        pattern = r"```mermaid\n(.*?)```"
        matches = re.finditer(pattern, markdown_text, re.DOTALL)

        results = []
        for idx, match in enumerate(matches, 1):
            code = match.group(1).strip()

            # 尝试查找前面的标题
            start_pos = match.start()
            preceding_text = markdown_text[max(0, start_pos - 200):start_pos]
            caption_match = re.search(r"#{1,3}\s+(.+?)\n", preceding_text)
            caption = caption_match.group(1).strip() if caption_match else f"图{idx}"

            results.append({
                "code": code,
                "caption": caption,
                "index": idx,
            })

        return results

    def render_from_markdown(
        self,
        markdown_file: str,
        output_dir: str,
        output_format: Optional[str] = None,
        theme: str = "default",
    ) -> List[RenderResult]:
        """
        从 Markdown 文件提取并渲染所有 Mermaid 图表

        Args:
            markdown_file: Markdown 文件路径
            output_dir: 输出目录
            output_format: 输出格式
            theme: Mermaid 主题

        Returns:
            List[RenderResult]: 渲染结果列表
        """
        markdown_path = Path(markdown_file)
        if not markdown_path.exists():
            return [RenderResult(success=False, error=f"文件不存在: {markdown_file}")]

        text = markdown_path.read_text(encoding="utf-8")
        diagrams = self.extract_from_markdown(text)

        if not diagrams:
            return []

        output_dir_path = Path(output_dir)
        output_dir_path.mkdir(parents=True, exist_ok=True)

        results = []
        for diagram in diagrams:
            output_path = output_dir_path / f"mermaid_{diagram['index']:02d}.png"
            result = self.render(
                mermaid_code=diagram["code"],
                output_path=str(output_path),
                output_format=output_format,
                theme=theme,
            )
            if result.success:
                print(f"  [Mermaid] 渲染成功: {result.output_path} ({diagram['caption']})")
            else:
                print(f"  [Mermaid] 渲染失败: {result.error}")
            results.append(result)

        return results

    def render_text_with_placeholders(
        self,
        markdown_text: str,
        output_dir: str,
        output_format: Optional[str] = None,
        theme: str = "default",
    ) -> Tuple[str, List[RenderResult]]:
        """
        渲染 Markdown 文本中的所有 Mermaid 图表，
        并将代码块替换为图片引用

        Returns:
            Tuple[str, List[RenderResult]]: (替换后的文本, 渲染结果列表)
        """
        diagrams = self.extract_from_markdown(markdown_text)
        if not diagrams:
            return markdown_text, []

        output_dir_path = Path(output_dir)
        output_dir_path.mkdir(parents=True, exist_ok=True)

        results = []
        for diagram in diagrams:
            output_path = output_dir_path / f"mermaid_{diagram['index']:02d}.png"
            result = self.render(
                mermaid_code=diagram["code"],
                output_path=str(output_path),
                output_format=output_format,
                theme=theme,
            )
            results.append(result)

            # 替换代码块为图片引用
            if result.success:
                old_block = f"```mermaid\n{diagram['code']}\n```"
                rel_path = Path(result.output_path).name
                new_block = f"![{diagram['caption']}]({rel_path})"
                markdown_text = markdown_text.replace(old_block, new_block, 1)

        return markdown_text, results

    def __repr__(self) -> str:
        return f"MermaidRenderer(available={self.is_available()}, cmd={self.mmdc_cmd})"


import shutil

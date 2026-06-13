r"""
Markdown to LaTeX exporter (Phase 1E: paper_templates 接入)
============================================================

Converts system-generated Markdown papers into compilable .tex files.
默认输出 ``mcmthesis`` 兼容 .tex（向后兼容）；通过 ``template_id`` 参数
可切换为 [paper_templates](../backend/app/core/paper_templates/) 注册表
中的其他模板（IEEE / NeurIPS / ACM / Springer 等）。

**重要**：本转换器对 **mcmthesis** 路径做了深度调优（``\mcmsetup`` / 标题
页 / sheet 等）。对其他模板，仅做"基础兼容"输出（``\documentclass`` 切换 +
``cls_file`` 复制 + 通用结构）。**复杂 CCF-A 模板（IEEE 双栏 / NeurIPS）
建议走 Writer Agent 的章节级生成路径，不依赖本转换器**。

Features:
- Headings mapped to \section / \subsection / \subsubsection
- Markdown tables converted to LaTeX tabular with booktabs rules
- Math formulas preserved (inline $...$ and display $$...$$)
- Images converted to \includegraphics with figure environment
- Code blocks converted to lstlisting
- Lists converted to itemize / enumerate
"""

import re
import shutil
from pathlib import Path
from typing import List, Optional, Tuple

# Phase 1E 整改：从 [paper_templates](../backend/app/core/paper_templates/) 取
# documentclass/cls_file 而非硬编码 mcmthesis。
try:
    from backend.app.core.paper_templates import load_template as _load_template_from_registry
except Exception:  # noqa: BLE001
    _load_template_from_registry = None  # 兼容 src/ 目录独立运行


class MarkdownToTexConverter:
    """Converts Markdown text to paper-template-driven LaTeX.

    Args:
        template_dir: ``cls`` 文件所在目录（默认 ``config/latex_templates/``）。
        output_dir: 输出目录（.tex + figures/ + cls 都会落在这里）。
        template_id: paper_templates 注册表中的模板 ID，默认 ``math_modeling``。
            传入 ``None`` 或不存在的 ID 时，``documentclass`` 走 ``article`` 兜底。
    """

    def __init__(self, template_dir: Path, output_dir: Path, template_id: Optional[str] = None):
        self.template_dir = template_dir
        self.output_dir = output_dir
        self.figures_dir = output_dir / "figures"
        self.figures_dir.mkdir(parents=True, exist_ok=True)
        # 解析 template_id → (documentclass, cls_file)
        self.template_id = template_id or "math_modeling"
        self.documentclass, self.cls_file = self._resolve_template(self.template_id)

    def convert(self, md_text: str, title: str = "数学建模论文") -> str:
        """Convert full Markdown paper to LaTeX source."""
        # Pre-process: protect multi-line LaTeX environments
        md_text = self._protect_math_blocks(md_text)

        lines = md_text.splitlines()
        body_lines: List[str] = []
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            # Skip protected math block placeholders (they are already LaTeX)
            if stripped.startswith("<<MATHBLOCK"):
                body_lines.append(self._restore_math_block(stripped))
                i += 1
                continue

            if stripped.startswith("```"):
                i = self._process_code_block(lines, i, body_lines)
            elif stripped.startswith("|"):
                i = self._process_table(lines, i, body_lines)
            elif stripped.startswith("# "):
                body_lines.append(f"\\title{{{self._escape_latex(stripped[2:])}}}")
            elif stripped.startswith("## "):
                body_lines.append(self._process_heading(stripped[2:], level=1))
            elif stripped.startswith("### "):
                body_lines.append(self._process_heading(stripped[3:], level=2))
            elif stripped.startswith("#### "):
                body_lines.append(self._process_heading(stripped[4:], level=3))
            elif stripped.startswith("!"):
                body_lines.extend(self._process_image(stripped))
            elif stripped == "---":
                body_lines.append("%" + "-" * 40)
            elif stripped.startswith("-") and not stripped.startswith("- "):
                pass
            elif stripped.startswith("-"):
                i = self._process_list(lines, i, body_lines, ordered=False)
            elif re.match(r"^\d+\.", stripped):
                i = self._process_list(lines, i, body_lines, ordered=True)
            elif stripped:
                body_lines.append(self._process_inline(line))
            else:
                body_lines.append("")
            i += 1

        body = "\n".join(body_lines)
        return self._build_document(body, title)

    def _protect_math_blocks(self, text: str) -> str:
        """Protect multi-line LaTeX environments and display math."""
        self._math_block_cache: List[str] = []

        # Protect $$...$$
        def repl_display(m):
            self._math_block_cache.append(m.group(0))
            return f"<<MATHBLOCK{len(self._math_block_cache)-1}>>"
        text = re.sub(r"\$\$.*?\$\$", repl_display, text, flags=re.DOTALL)

        # Protect \begin{...}...\end{...}
        def repl_env(m):
            self._math_block_cache.append(m.group(0))
            return f"<<MATHBLOCK{len(self._math_block_cache)-1}>>"
        text = re.sub(r"\\begin\{.*?\}.*?\\end\{.*?\}", repl_env, text, flags=re.DOTALL)

        return text

    def _restore_math_block(self, stripped: str) -> str:
        """Restore a protected math block from placeholder."""
        m = re.match(r"<<MATHBLOCK(\d+)>>", stripped)
        if m:
            idx = int(m.group(1))
            if idx < len(self._math_block_cache):
                return self._math_block_cache[idx]
        return stripped

    def _process_heading(self, text: str, level: int) -> str:
        text = self._protect_math(text)
        text = self._escape_latex(text)
        text = self._restore_math(text)
        if level == 1:
            return f"\\section{{{text}}}"
        elif level == 2:
            return f"\\subsection{{{text}}}"
        else:
            return f"\\subsubsection{{{text}}}"

    def _process_inline(self, text: str) -> str:
        text = self._protect_math(text)
        text = self._escape_latex(text)
        text = self._restore_math(text)
        text = self._convert_bold(text)
        text = self._convert_italic(text)
        return text

    def _convert_bold(self, text: str) -> str:
        def repl(m):
            return f"\\textbf{{{m.group(1)}}}"
        return re.sub(r"\*\*(.+?)\*\*", repl, text)

    def _convert_italic(self, text: str) -> str:
        def repl(m):
            return f"\\textit{{{m.group(1)}}}"
        return re.sub(r"\*(.+?)\*", repl, text)

    def _protect_math(self, text: str) -> str:
        self._math_cache: List[str] = []
        def repl(m):
            self._math_cache.append(m.group(0))
            return f"<<MATH{len(self._math_cache)-1}>>"
        # Protect display math blocks $$...$$
        text = re.sub(r"\$\$.*?\$\$", repl, text, flags=re.DOTALL)
        # Protect LaTeX environments \begin{...}...\end{...}
        text = re.sub(r"\\begin\{.*?\}.*?\\end\{.*?\}", repl, text, flags=re.DOTALL)
        # Protect inline math $...$
        text = re.sub(r"\$.*?\$", repl, text)
        return text

    def _restore_math(self, text: str) -> str:
        for i, math in enumerate(self._math_cache):
            text = text.replace(f"<<MATH{i}>>", math)
        return text

    def _escape_latex(self, text: str) -> str:
        text = text.replace("\\", "\\textbackslash{}")
        text = text.replace("&", "\\&")
        text = text.replace("%", "\\%")
        text = text.replace("$", "\\$")
        text = text.replace("#", "\\#")
        text = text.replace("_", "\\_")
        text = text.replace("{", "\\{")
        text = text.replace("}", "\\}")
        text = text.replace("~", "\\textasciitilde{}")
        text = text.replace("^", "\\textasciicircum{}")
        return text

    def _process_code_block(self, lines: List[str], idx: int, out: List[str]) -> int:
        lang = ""
        header = lines[idx].strip()
        if len(header) > 3:
            lang = header[3:].strip()
        idx += 1
        code_lines = []
        while idx < len(lines) and not lines[idx].strip().startswith("```"):
            code_lines.append(lines[idx])
            idx += 1
        lang_map = {"python": "python", "matlab": "Matlab", "c++": "C++", "c": "C", "java": "Java"}
        lst_lang = lang_map.get(lang.lower(), "")
        lang_opt = f"[language={lst_lang}]" if lst_lang else ""
        out.append(f"\\begin{{lstlisting}}{lang_opt}")
        out.extend(code_lines)
        out.append("\\end{lstlisting}")
        return idx

    def _process_table(self, lines: List[str], idx: int, out: List[str]) -> int:
        table_lines = []
        while idx < len(lines) and lines[idx].strip().startswith("|"):
            table_lines.append(lines[idx].strip())
            idx += 1
        if len(table_lines) < 3:
            out.extend(table_lines)
            return idx - 1

        header_cells = [c.strip() for c in table_lines[0].split("|")[1:-1]]
        align = [self._guess_align(c) for c in header_cells]
        cols = " ".join(align)

        out.append("\\begin{table}[htbp]")
        out.append("\\centering")
        out.append("\\begin{tabular}{" + cols + "}")
        out.append("\\toprule")
        out.append(" & ".join(self._process_inline(c) for c in header_cells) + " \\\\")
        out.append("\\midrule")

        for row_line in table_lines[2:]:
            cells = [c.strip() for c in row_line.split("|")[1:-1]]
            if len(cells) == len(header_cells):
                out.append(" & ".join(self._process_inline(c) for c in cells) + " \\\\")

        out.append("\\bottomrule")
        out.append("\\end{tabular}")
        out.append("\\end{table}")
        return idx - 1

    def _guess_align(self, cell: str) -> str:
        if re.match(r"^\d+([.,]\d+)?$", cell.strip()):
            return "r"
        return "l"

    def _process_image(self, line: str) -> List[str]:
        m = re.search(r"!\[(.*?)\]\((.*?)\)", line)
        if not m:
            return [line]
        alt, src = m.group(1), m.group(2)
        src_path = Path(src)
        if src_path.exists():
            dst = self.figures_dir / src_path.name
            shutil.copy2(src_path, dst)
            src = f"figures/{src_path.name}"
        return [
            "\\begin{figure}[htbp]",
            "\\centering",
            f"\\includegraphics[width=0.8\\textwidth]{{{src}}}",
            f"\\caption{{{alt}}}",
            "\\end{figure}",
        ]

    def _process_list(self, lines: List[str], idx: int, out: List[str], ordered: bool) -> int:
        env = "enumerate" if ordered else "itemize"
        out.append(f"\\begin{{{env}}}")
        pattern = re.compile(r"^\d+\.\s*(.*)$") if ordered else re.compile(r"^-\s*(.*)$")
        while idx < len(lines):
            stripped = lines[idx].strip()
            m = pattern.match(stripped)
            if not m:
                if stripped == "" or stripped.startswith("#") or stripped.startswith("|") or stripped.startswith("!"):
                    break
                if not ordered and not stripped.startswith("-"):
                    break
                if ordered and not re.match(r"^\d+\.", stripped):
                    break
            if m:
                out.append(f"    \\item {self._process_inline(m.group(1))}")
            idx += 1
        out.append(f"\\end{{{env}}}")
        return idx - 1

    def _resolve_template(self, template_id: str) -> Tuple[str, str]:
        """从 paper_templates 注册表取 ``(documentclass, cls_file)``。

        找不到时返回 ``("article", "")`` 兜底（保证 .tex 一定可编译）。
        """
        if _load_template_from_registry is None:
            return ("article", "")
        try:
            tpl = _load_template_from_registry(template_id)
            if tpl:
                return (tpl.documentclass or "article", tpl.cls_file or "")
        except Exception:  # noqa: BLE001
            pass
        return ("article", "")

    def _build_document(self, body: str, title: str) -> str:
        r"""构造完整 LaTeX 文档。

        Phase 1E 改造：根据 ``self.documentclass`` 切换 preamble。
        - 当 documentclass == "cumcmthesis" 时：保留 \mcmsetup 完整结构。
        - 其他 documentclass：使用 paper_templates 提供的 preamble，
          退化为 ``\documentclass{X}`` + 标准包 + title + body + \end{document}``。
        """
        if self.documentclass == "cumcmthesis":
            # CUMCM 专属 \mcmsetup 结构（保留以兼容旧 4 套模板）
            return f"""\\documentclass{{mcmthesis}}
\\mcmsetup{{
    CTeX = true,
    tcn = 00000000,
    problem = A,
    sheet = true,
    titleinsheet = true,
    keywordsinsheet = true,
    titlepage = false,
    abstract = true
}}

\\usepackage{{palatino}}
\\usepackage{{ctex}}
\\usepackage{{booktabs}}
\\usepackage{{graphicx}}
\\usepackage{{hyperref}}
\\usepackage{{listings}}
\\usepackage{{xcolor}}

\\title{{{title}}}

\\begin{{document}}
\\maketitle

{body}

\\end{{document}}
"""
        # 通用 preamble：用于 IEEE / NeurIPS / ACM / Springer / article 等
        return f"""\\documentclass{{{self.documentclass}}}
\\usepackage{{ctex}}
\\usepackage{{amsmath,amssymb}}
\\usepackage{{graphicx}}
\\usepackage{{booktabs}}
\\usepackage{{hyperref}}
\\usepackage{{listings}}
\\usepackage{{xcolor}}
\\usepackage{{geometry}}
\\geometry{{margin=1in}}

\\title{{{title}}}

\\begin{{document}}
\\maketitle

{body}

\\end{{document}}
"""

    def export(self, md_path: Path, tex_path: Path) -> Path:
        """Export Markdown file to compilable TeX file.

        Phase 1E 改造：根据 ``self.cls_file``（从 paper_templates 注册表查得）
        复制对应 ``.cls`` 到 tex 同级目录，使 xelatex 编译能找到文档类。
        """
        md_text = md_path.read_text(encoding="utf-8")
        tex_text = self.convert(md_text)
        tex_path.parent.mkdir(parents=True, exist_ok=True)
        tex_path.write_text(tex_text, encoding="utf-8")

        # 优先用注册表声明的 cls_file，回退到 template_dir 下与 documentclass 同名
        cls_copied = False
        if self.cls_file:
            cls_path = Path(self.cls_file)
            if not cls_path.is_absolute():
                # 相对路径：相对项目根解析
                project_root = Path(__file__).resolve().parents[2]
                cls_path = project_root / cls_path
            if cls_path.exists():
                shutil.copy2(cls_path, tex_path.parent / cls_path.name)
                cls_copied = True
        if not cls_copied:
            # 兜底：尝试 self.template_dir 下的 ``<documentclass>.cls``
            cls_src = self.template_dir / f"{self.documentclass}.cls"
            if cls_src.exists():
                shutil.copy2(cls_src, tex_path.parent / f"{self.documentclass}.cls")

        return tex_path

r"""
Markdown to MCM/ICM LaTeX exporter
==================================

Converts system-generated Markdown papers into compilable mcmthesis .tex files.

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
from typing import List, Tuple


class MarkdownToTexConverter:
    """Converts Markdown text to mcmthesis-compatible LaTeX."""

    def __init__(self, template_dir: Path, output_dir: Path):
        self.template_dir = template_dir
        self.output_dir = output_dir
        self.figures_dir = output_dir / "figures"
        self.figures_dir.mkdir(parents=True, exist_ok=True)

    def convert(self, md_text: str, title: str = "数学建模论文") -> str:
        """Convert full Markdown paper to LaTeX source."""
        lines = md_text.splitlines()
        body_lines: List[str] = []
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

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
        text = re.sub(r"\$\$.*?\$\$", repl, text, flags=re.DOTALL)
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

    def _build_document(self, body: str, title: str) -> str:
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

    def export(self, md_path: Path, tex_path: Path) -> Path:
        """Export Markdown file to compilable TeX file."""
        md_text = md_path.read_text(encoding="utf-8")
        tex_text = self.convert(md_text)
        tex_path.parent.mkdir(parents=True, exist_ok=True)
        tex_path.write_text(tex_text, encoding="utf-8")

        cls_src = self.template_dir / "mcmthesis.cls"
        if cls_src.exists():
            shutil.copy2(cls_src, tex_path.parent / "mcmthesis.cls")

        return tex_path

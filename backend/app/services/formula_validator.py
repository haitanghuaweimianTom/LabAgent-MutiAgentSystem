"""LaTeX 公式有效性校验（Harness 扩展）。

确定性、可复现的 LaTeX 数学段校验，不依赖 LLM：
- Check A: 预处理剥离注释（保留 ``\\%`` 转义与行号映射）
- Check B: 抽取数学段（display 环境 / ``\\[ \\]`` / ``\\( \\)`` / ``$$ $$`` / ``$ $``）
- Check C: 环境配对（``\\begin{env}`` / ``\\end{env}`` 栈匹配）
- Check D: 定界符平衡（未转义 ``$`` 计数偶、``$$`` 偶、``\\[ \\]`` / ``\\( \\)`` 配对、
           全局 ``{}`` 栈平衡、``\\left`` / ``\\right`` 配对）
- Check E: 退化公式（空数学段 → warning）
- Check F: 错位对齐符（``&`` 出现在对齐/表格环境之外 → warning；
           ``\\\\`` 出现在单行数学段内 → warning）
- Check G: （可选，compile_check=True）最小 standalone 文档调用 xelatex/pdflatex 编译，
           解析 .log 中 ``! `` 行 → error finding

复用 ``services.symbolic_auditor`` 的 ``AuditReport`` / ``AuditFinding`` 作为结构化
finding 容器与打分（add(): error -15 / warning -5，floor 0）。

Check A–F 为确定性、可复现的核心（默认即"真实做事"）；Check G 为加强档，默认关闭。
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import tempfile
from typing import Any, Dict, List, Optional, Tuple

from .symbolic_auditor import AuditFinding, AuditReport

logger = logging.getLogger(__name__)


# 多行/单行数学环境名
_MATH_ENVS: Tuple[str, ...] = (
    "equation", "equation*", "align", "align*", "gather", "gather*",
    "multline", "multline*", "eqnarray", "eqnarray*", "math", "displaymath",
)
# 合法使用 & 与 \\ 的环境（align 族 + 表格/数组族）
_ALIGN_ENVS = {
    "align", "align*", "gather", "gather*", "multline", "multline*",
    "eqnarray", "eqnarray*", "tabular", "tabular*", "array", "matrix",
    "pmatrix", "bmatrix", "vmatrix", "Bmatrix", "Vmatrix", "smallmatrix",
    "cases", "aligned", "gathered",
}
# 多行数学环境（合法使用 \\）
_MULTILINE_ENVS = {
    "align", "align*", "gather", "gather*", "multline", "multline*",
    "eqnarray", "eqnarray*",
}

_ENV_TOKEN_RE = re.compile(r"\\(begin|end)\s*\{([^}]*)\}")
_ENV_BLOCK_RE = re.compile(
    r"\\begin\s*\{(" + "|".join(re.escape(e) for e in _MATH_ENVS) + r")\}(.*?)\\end\s*\{\1\}",
    re.DOTALL,
)
_ALL_ENV_BLOCK_RE = re.compile(r"\\begin\s*\{([^}]*)\}(.*?)\\end\s*\{\1\}", re.DOTALL)


def _line_of(text: str, offset: int) -> int:
    """字符偏移 → 1-indexed 行号（基于剥离注释后的文本，行号与原文一致）。"""
    return text.count("\n", 0, offset) + 1


class FormulaValidator:
    """LaTeX 公式有效性校验器（确定性，单例）。"""

    # ------------------------------------------------------------------ A
    def _strip_comments(self, text: str) -> str:
        """剥离 ``%`` 注释，保留 ``\\%`` 转义与行号（逐行处理，行数不变）。"""
        out: List[str] = []
        for line in text.split("\n"):
            kept: List[str] = []
            i, n = 0, len(line)
            while i < n:
                c = line[i]
                if c == "\\" and i + 1 < n:
                    kept.append(line[i:i + 2])  # 转义字符整体保留（含 \%）
                    i += 2
                    continue
                if c == "%":
                    break  # 注释至行尾
                kept.append(c)
                i += 1
            out.append("".join(kept))
        return "\n".join(out)

    # ------------------------------------------------------------------ 通用
    @staticmethod
    def _count_unescaped(text: str, char: str) -> Tuple[int, List[int]]:
        """统计未转义的 ``char`` 出现次数与位置（正确处理 ``\\$`` / ``\\\\$``）。"""
        count = 0
        positions: List[int] = []
        i, n = 0, len(text)
        while i < n:
            c = text[i]
            if c == "\\":
                i += 2  # 跳过转义序列（反斜杠 + 下一字符）
                continue
            if c == char:
                count += 1
                positions.append(i)
            i += 1
        return count, positions

    @staticmethod
    def _has_line_break(text: str) -> bool:
        """是否含未转义的 LaTeX 换行 ``\\\\``（行中断符）。"""
        i, n = 0, len(text)
        while i < n:
            if text[i] == "\\":
                if i + 1 < n and text[i + 1] == "\\":
                    return True
                i += 2
                continue
            i += 1
        return False

    # ------------------------------------------------------------------ B
    def _extract_math_segments(self, code: str) -> List[Dict[str, Any]]:
        """抽取所有数学段（带行号、类型、完整文本与内部文本）。

        顺序：display 环境 → ``$$`` → ``\\[ \\]`` → ``\\( \\)`` → ``$``，
        已抽取区域用空格遮蔽以避免重复计数。
        """
        segments: List[Dict[str, Any]] = []
        masked = list(code)

        def mask(start: int, end: int) -> None:
            for k in range(start, min(end, len(masked))):
                if masked[k] != "\n":
                    masked[k] = " "

        # B1. display 数学环境
        for m in _ENV_BLOCK_RE.finditer(code):
            line = _line_of(code, m.start())
            segments.append({
                "type": "env", "name": m.group(1),
                "content": m.group(0), "inner": m.group(2),
                "line": line, "start": m.start(), "end": m.end(),
            })
            mask(m.start(), m.end())

        masked_str = "".join(masked)

        # 在遮蔽后的文本上扫描其余定界符
        i, n = 0, len(masked_str)
        while i < n:
            c = masked_str[i]
            if c == "\\" and i + 1 < n:
                nxt = masked_str[i + 1]
                if nxt == "[":
                    end = masked_str.find("\\]", i + 2)
                    if end != -1:
                        seg = code[i:end + 2]
                        segments.append({"type": "bracket", "name": "bracket",
                                         "content": seg, "inner": seg[2:-2],
                                         "line": _line_of(code, i), "start": i, "end": end + 2})
                        for k in range(i, end + 2):
                            if masked[k] != "\n":
                                masked[k] = " "
                        i = end + 2
                        continue
                    segments.append({"type": "bracket_unpaired", "name": "bracket",
                                    "content": "\\[", "inner": "",
                                    "line": _line_of(code, i), "start": i, "end": i + 2})
                    i += 2
                    continue
                if nxt == "(":
                    end = masked_str.find("\\)", i + 2)
                    if end != -1:
                        seg = code[i:end + 2]
                        segments.append({"type": "paren", "name": "paren",
                                         "content": seg, "inner": seg[2:-2],
                                         "line": _line_of(code, i), "start": i, "end": end + 2})
                        for k in range(i, end + 2):
                            if masked[k] != "\n":
                                masked[k] = " "
                        i = end + 2
                        continue
                    segments.append({"type": "paren_unpaired", "name": "paren",
                                    "content": "\\(", "inner": "",
                                    "line": _line_of(code, i), "start": i, "end": i + 2})
                    i += 2
                    continue
                i += 2  # 其他转义序列
                continue
            if c == "$":
                if i + 1 < n and masked_str[i + 1] == "$":
                    end = masked_str.find("$$", i + 2)
                    if end != -1:
                        seg = code[i:end + 2]
                        segments.append({"type": "display", "name": "display",
                                         "content": seg, "inner": seg[2:-2],
                                         "line": _line_of(code, i), "start": i, "end": end + 2})
                        for k in range(i, end + 2):
                            if masked[k] != "\n":
                                masked[k] = " "
                        i = end + 2
                        continue
                    segments.append({"type": "display_unpaired", "name": "display",
                                    "content": "$$", "inner": "",
                                    "line": _line_of(code, i), "start": i, "end": i + 2})
                    i += 2
                    continue
                # 单 $ 行内数学
                j = i + 1
                while j < n:
                    if masked_str[j] == "\\":
                        j += 2
                        continue
                    if masked_str[j] == "$":
                        break
                    j += 1
                if j < n and masked_str[j] == "$":
                    seg = code[i:j + 1]
                    segments.append({"type": "inline", "name": "inline",
                                     "content": seg, "inner": seg[1:-1],
                                     "line": _line_of(code, i), "start": i, "end": j + 1})
                    for k in range(i, j + 1):
                        if masked[k] != "\n":
                            masked[k] = " "
                    i = j + 1
                    continue
                segments.append({"type": "inline_unpaired", "name": "inline",
                                "content": "$", "inner": "",
                                "line": _line_of(code, i), "start": i, "end": i + 1})
                i += 1
                continue
            i += 1

        segments.sort(key=lambda s: s["start"])
        return segments

    # ------------------------------------------------------------------ C
    def _check_env_pairing(self, code: str, report: AuditReport) -> None:
        """Check C: 所有 ``\\begin{env}`` 须有同名 ``\\end{env}``（栈匹配）。"""
        stack: List[Tuple[str, int]] = []
        for m in _ENV_TOKEN_RE.finditer(code):
            kind, env = m.group(1), m.group(2)
            line = _line_of(code, m.start())
            if kind == "begin":
                stack.append((env, line))
            else:  # end
                if not stack:
                    report.add(AuditFinding(
                        severity="error", category="env_pairing",
                        message=f"出现 \\end{{{env}}} 但无对应 \\begin{{...}}",
                        location=f"L{line}"))
                else:
                    top_env, top_line = stack.pop()
                    if top_env != env:
                        report.add(AuditFinding(
                            severity="error", category="env_pairing",
                            message=(f"环境嵌套不匹配：\\begin{{{top_env}}}(L{top_line}) "
                                     f"被 \\end{{{env}}}(L{line}) 关闭"),
                            location=f"L{line}"))
        for env, line in stack:
            report.add(AuditFinding(
                severity="error", category="env_pairing",
                message=f"环境 \\begin{{{env}}} 未关闭（缺少 \\end{{{env}}}）",
                location=f"L{line}"))

    # ------------------------------------------------------------------ D
    def _check_delimiter_balance(self, code: str, report: AuditReport) -> None:
        """Check D: 定界符与括号平衡。"""
        # D1. 未转义 $ 计数须偶
        dollars, _ = self._count_unescaped(code, "$")
        if dollars % 2 != 0:
            report.add(AuditFinding(
                severity="error", category="delimiter",
                message=f"未转义 $ 数量={dollars}（奇数），存在未配对的行内数学定界符",
                location="-"))
        # D2. $$ token 须偶（捕获 $ 计数为偶但 $$ 配对破损的情况）
        dd = len(re.findall(r"(?<!\\)\$\$", code))
        if dd % 2 != 0:
            report.add(AuditFinding(
                severity="warning", category="delimiter",
                message=f"$$ 显示数学定界符数量={dd}（奇数），存在未配对的 $$",
                location="-"))
        # D3. \[ 与 \] 配对
        ob, cb = len(re.findall(r"\\\[", code)), len(re.findall(r"\\\]", code))
        if ob != cb:
            report.add(AuditFinding(
                severity="error", category="delimiter",
                message=f"\\[ 与 \\] 数量不匹配：{ob} vs {cb}",
                location="-"))
        # D4. \( 与 \) 配对
        op, cp = len(re.findall(r"\\\(", code)), len(re.findall(r"\\\)", code))
        if op != cp:
            report.add(AuditFinding(
                severity="error", category="delimiter",
                message=f"\\( 与 \\) 数量不匹配：{op} vs {cp}",
                location="-"))
        # D5. 全局 {} 栈平衡
        stack: List[int] = []
        i, n = 0, len(code)
        while i < n:
            c = code[i]
            if c == "\\":
                i += 2
                continue
            if c == "{":
                stack.append(i)
            elif c == "}":
                if stack:
                    stack.pop()
                else:
                    report.add(AuditFinding(
                        severity="error", category="brace",
                        message="多余的 } （无对应 {）",
                        location=f"L{_line_of(code, i)}"))
            i += 1
        for pos in stack:
            report.add(AuditFinding(
                severity="error", category="brace",
                message="未闭合的 { （缺少 }）",
                location=f"L{_line_of(code, pos)}"))
        # D6. \left / \right 配对
        nl, nr = len(re.findall(r"\\left\b", code)), len(re.findall(r"\\right\b", code))
        if nl != nr:
            report.add(AuditFinding(
                severity="error", category="delimiter",
                message=f"\\left 与 \\right 数量不匹配：{nl} vs {nr}",
                location="-"))

    # ------------------------------------------------------------------ E
    def _check_degenerate(self, segments: List[Dict[str, Any]], report: AuditReport) -> None:
        """Check E: 退化（空）数学段。"""
        ok_types = {"env", "display", "bracket", "paren", "inline"}
        for seg in segments:
            if seg.get("type") not in ok_types:
                continue
            inner = (seg.get("inner") or "").strip()
            if not inner:
                report.add(AuditFinding(
                    severity="warning", category="degenerate",
                    message=f"空数学段（{seg.get('type')}/{seg.get('name')}），将渲染为空",
                    location=f"L{seg.get('line', '-')}"))

    # ------------------------------------------------------------------ F
    def _check_misplaced_alignment(
        self, code: str, env_spans: List[Tuple[str, int, int, int]],
        segments: List[Dict[str, Any]], report: AuditReport,
    ) -> None:
        """Check F: 错位对齐符。"""
        # F1. & 出现在 align 族/tabular/array 之外 → warning
        _, amp_positions = self._count_unescaped(code, "&")
        reported_amp = 0
        for p in amp_positions:
            env = self._env_at(env_spans, p)
            if env is None or env not in _ALIGN_ENVS:
                report.add(AuditFinding(
                    severity="warning", category="misplaced_align",
                    message=(f"& 出现在非对齐环境（{env or '正文'}），"
                             "可能导致 Misplaced alignment tab"),
                    location=f"L{_line_of(code, p)}"))
                reported_amp += 1
                if reported_amp >= 20:
                    break
        # F2. \\ 出现在单行数学段内 → warning（导致 Misplaced \cr）
        single_line_envs = set(_MATH_ENVS) - _MULTILINE_ENVS
        for seg in segments:
            typ = seg.get("type")
            name = seg.get("name", "")
            is_single_line = (
                typ in ("display", "bracket", "paren", "inline")
                or (typ == "env" and name in single_line_envs)
            )
            if is_single_line and self._has_line_break(seg.get("content", "")):
                report.add(AuditFinding(
                    severity="warning", category="misplaced_align",
                    message=(f"\\\\ 出现在单行数学段内（{typ}/{name}），"
                             "可能导致 Misplaced \\cr"),
                    location=f"L{seg.get('line', '-')}"))

    @staticmethod
    def _env_at(env_spans: List[Tuple[str, int, int, int]], pos: int) -> Optional[str]:
        for name, start, end, _line in env_spans:
            if start <= pos < end:
                return name
        return None

    # ------------------------------------------------------------------ G
    def _check_compile(
        self, latex_code: str, segments: List[Dict[str, Any]], report: AuditReport,
    ) -> None:
        """Check G: （可选）编译验证。失败/超时降级为 info，不阻断。"""
        compiles = []
        ok_types = {"env", "display", "bracket", "paren", "inline"}
        for seg in segments:
            if seg.get("type") in ok_types and seg.get("content"):
                compiles.append(seg["content"])
        if not compiles:
            return
        engine = shutil.which("xelatex") or shutil.which("pdflatex")
        if not engine:
            report.add(AuditFinding(
                severity="info", category="compile",
                message="未找到 xelatex/pdflatex，跳过编译验证",
                location="-"))
            return
        body = "\n\n".join(compiles)
        doc = (
            "\\documentclass{article}\n"
            "\\usepackage{amsmath,amssymb}\n"
            "\\begin{document}\n" + body + "\n\\end{document}\n"
        )
        try:
            with tempfile.TemporaryDirectory(prefix="formulacheck_") as td:
                tex_path = os.path.join(td, "formulacheck.tex")
                with open(tex_path, "w", encoding="utf-8") as f:
                    f.write(doc)
                try:
                    subprocess.run(
                        [engine, "-interaction=nonstopmode", "-halt-on-error", "formulacheck.tex"],
                        cwd=td, capture_output=True, text=True, timeout=30,
                    )
                except subprocess.TimeoutExpired:
                    report.add(AuditFinding(
                        severity="info", category="compile",
                        message="编译超时（>30s），跳过编译验证",
                        location="-"))
                    return
                except Exception as exc:  # noqa: BLE001
                    report.add(AuditFinding(
                        severity="info", category="compile",
                        message=f"编译异常，跳过编译验证：{exc}",
                        location="-"))
                    return
                log_path = os.path.join(td, "formulacheck.log")
                for err in self._parse_log_errors(log_path):
                    report.add(AuditFinding(
                        severity="error", category="compile",
                        message=f"LaTeX 编译错误：{err}",
                        location="-"))
        except Exception as exc:  # noqa: BLE001
            report.add(AuditFinding(
                severity="info", category="compile",
                message=f"编译流程异常，跳过编译验证：{exc}",
                location="-"))

    @staticmethod
    def _parse_log_errors(log_path: str) -> List[str]:
        errs: List[str] = []
        try:
            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                for raw in f:
                    line = raw.rstrip("\n")
                    if line.startswith("!"):
                        msg = line[1:].strip()
                        if msg and msg not in errs:
                            errs.append(msg)
        except Exception:  # noqa: BLE001
            pass
        return errs[:10]

    # ------------------------------------------------------------------ 入口
    def validate(self, latex_code: str, compile_check: bool = False) -> AuditReport:
        """校验 LaTeX 公式有效性，返回 AuditReport。"""
        report = AuditReport()
        if not latex_code or not isinstance(latex_code, str) or not latex_code.strip():
            report.add(AuditFinding(
                severity="warning", category="empty_input",
                message="无 LaTeX 源码可供校验", location="-"))
            report.segment_count = 0  # type: ignore[attr-defined]
            return report

        # A. 预处理（剥离注释，保留行号映射）
        code = self._strip_comments(latex_code)
        # B. 抽取数学段
        segments = self._extract_math_segments(code)
        # 所有环境 span（供 F1 判断 & 所属环境）
        env_spans: List[Tuple[str, int, int, int]] = [
            (m.group(1), m.start(), m.end(), _line_of(code, m.start()))
            for m in _ALL_ENV_BLOCK_RE.finditer(code)
        ]

        # C. 环境配对
        self._check_env_pairing(code, report)
        # D. 定界符平衡
        self._check_delimiter_balance(code, report)
        # E. 退化公式
        self._check_degenerate(segments, report)
        # F. 错位对齐符
        self._check_misplaced_alignment(code, env_spans, segments, report)
        # G. （可选）编译验证
        if compile_check:
            self._check_compile(latex_code, segments, report)

        report.segment_count = len(segments)  # type: ignore[attr-defined]
        report.score = max(0.0, float(report.score))
        return report


_formula_validator: Optional[FormulaValidator] = None


def get_formula_validator() -> FormulaValidator:
    """返回 FormulaValidator 单例（仿 get_fact_checker）。"""
    global _formula_validator
    if _formula_validator is None:
        _formula_validator = FormulaValidator()
    return _formula_validator

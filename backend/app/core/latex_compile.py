"""LaTeX 编译辅助：多趟编译以正确解析交叉引用。

背景：xelatex/pdflatex 单趟编译时，``\\ref{...}`` / ``\\cite{...}`` 因 ``.aux``
尚未写好而显示成 ``??``。必须至少编译两遍（第二遍读取第一遍写出的 ``.aux``），
交叉引用才能解析。``latexmk`` 会自动处理多趟，但系统常未安装 latexmk，需手动跑两遍。

详见 [[figure-cjk-font-listings-fix]] 等论文质量加固记录。
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Dict, Optional, Union

PathLike = Union[str, Path]


def compile_latex(
    tex_file: PathLike,
    cwd: Optional[PathLike] = None,
    engine: str = "xelatex",
    passes: int = 2,
    timeout: int = 120,
) -> Dict[str, object]:
    """多趟编译 ``.tex``，返回编译结果。

    Args:
        tex_file: ``.tex`` 文件名（相对 ``cwd``）或绝对路径。
        cwd: 编译工作目录，默认取 ``tex_file`` 所在目录。
        engine: ``"xelatex"`` | ``"pdflatex"`` | ``"latexmk"``。
        passes: 非 latexmk 引擎的编译趟数（默认 2 趟以解析交叉引用）。
        timeout: 单趟超时秒数。

    Returns:
        ``{success, engine, returncode, pdf_path, stderr_snippet}``
    """
    tex_path = Path(tex_file)
    work_dir = str(cwd or tex_path.parent)
    tex_name = tex_path.name

    if not shutil.which(engine):
        return {
            "success": False,
            "engine": engine,
            "returncode": -1,
            "pdf_path": None,
            "stderr_snippet": f"{engine} not found",
        }

    resolved = shutil.which(engine) or engine
    if engine == "latexmk":
        cmd = [resolved, "-pdf", "-interaction=nonstopmode", "-silent", tex_name]
        passes_to_run = 1
    else:
        cmd = [resolved, "-interaction=nonstopmode", tex_name]
        passes_to_run = max(1, int(passes))

    last_rc = -1
    last_stderr = ""
    for i in range(passes_to_run):
        try:
            proc = subprocess.run(
                cmd, cwd=work_dir, capture_output=True, text=True, timeout=timeout
            )
            last_rc = proc.returncode
            last_stderr = (proc.stderr or "")[:2000]
        except subprocess.TimeoutExpired:
            return {
                "success": False, "engine": engine, "returncode": -1,
                "pdf_path": None, "stderr_snippet": "compilation timeout",
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "success": False, "engine": engine, "returncode": -1,
                "pdf_path": None, "stderr_snippet": str(exc)[:2000],
            }
        # 首趟之后、下一趟之前运行 bibtex：\cite 需要 .aux 里的 \citation 记录
        # 生成 .bbl，第二趟才能解析为编号而非 "?"。仅当 main.bib 存在且 .aux
        # 声明了 \bibdata 时运行（无参考文献则跳过，避免无谓报错）。
        if i == 0 and passes_to_run > 1 and shutil.which("bibtex"):
            work = Path(work_dir)
            aux_path = work / f"{tex_path.stem}.aux"
            if aux_path.exists() and (work / f"{tex_path.stem}.bib").exists():
                aux_text = aux_path.read_text(encoding="utf-8", errors="replace")
                if "\\bibdata" in aux_text:
                    try:
                        subprocess.run(
                            ["bibtex", tex_path.stem], cwd=work_dir,
                            capture_output=True, text=True, timeout=60,
                        )
                    except (subprocess.TimeoutExpired, Exception):  # noqa: BLE001
                        pass

    pdf_path = tex_path.with_suffix(".pdf")
    success = pdf_path.exists()
    try:
        pdf_rel = str(pdf_path.relative_to(Path(work_dir).parent)) if success else None
    except ValueError:
        pdf_rel = str(pdf_path) if success else None
    return {
        "success": success,
        "engine": engine,
        "returncode": last_rc,
        "pdf_path": pdf_rel,
        "stderr_snippet": last_stderr if (not success or last_rc != 0) else "",
    }

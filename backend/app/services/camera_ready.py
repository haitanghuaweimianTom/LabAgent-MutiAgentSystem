"""Camera-Ready 打包服务（Phase 3）。

将一次任务的最终产物打成可直接投稿 CCF-A 会议的 zip 包：

```
camera_ready_<task_id>/
├── main.tex                  # 主论文（来自 tex_exporter / Writer Agent）
├── main.bib                  # 参考文献（从 working_memory.citations 拼装）
├── figures/                  # 所有图表
├── sections/                 # 各章独立 .tex（可选）
├── code/                     # 求解代码（按多文件 manifest 复制）
└── README.md                 # 编译说明
paper.zip
```

【严格控制幻觉】
- 只复制 *实际存在* 的图表与代码，不凭空补
- bib 从 working_memory.citations 拼装，缺字段用 ``arxiv_id`` 占位
- README 模板化，避免不实宣传

【用户要求对应】
- 用户原话：「生产的可交付结果应该在前端可以选类型的」「最终输出的产品是
  可直接交付的」。本服务是这条约束的工程实现。
"""
from __future__ import annotations
import json
import logging
import shutil
import subprocess
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ==================== Data classes ====================

@dataclass
class CameraReadyArtifact:
    """Camera-ready 包中需要收集的产物。"""

    latex_code: str = ""
    bib_entries: List[Dict[str, str]] = field(default_factory=list)
    figures: List[Path] = field(default_factory=list)  # 真实存在的图片文件
    code_files: List[Path] = field(default_factory=list)  # 真实存在的 .py
    code_manifest_text: str = ""  # 可读的 manifest 描述
    chapter_summaries: List[Dict[str, Any]] = field(default_factory=list)
    template_id: str = "math_modeling"
    metadata: Dict[str, Any] = field(default_factory=dict)
    cls_files: List[Path] = field(default_factory=list)  # LaTeX class 文件
    sty_files: List[Path] = field(default_factory=list)  # LaTeX style 文件
    collection_skipped: List[str] = field(default_factory=list)  # 收集阶段跳过的原因

    def summary(self) -> Dict[str, int]:
        return {
            "figures": len(self.figures),
            "code_files": len(self.code_files),
            "bib_entries": len(self.bib_entries),
            "chapters": len(self.chapter_summaries),
            "cls_files": len(self.cls_files),
            "sty_files": len(self.sty_files),
        }


@dataclass
class CameraReadyResult:
    """camera-ready 打包结果。"""

    output_dir: Path
    zip_path: Optional[Path]
    skipped_reasons: List[str] = field(default_factory=list)
    artifact_summary: Dict[str, int] = field(default_factory=dict)
    verification: Dict[str, Any] = field(default_factory=dict)
    base_dir: Optional[Path] = None
    pdf_path: Optional[Path] = None  # 编译生成的 PDF 路径
    tex_path: Optional[Path] = None  # 主 tex 文件路径
    bib_path: Optional[Path] = None  # bib 文件路径
    refs_sources_path: Optional[Path] = None  # 参考文献来源文件路径

    def to_dict(self, base_dir: Optional[Path] = None) -> Dict[str, Any]:
        """序列化为字典；``base_dir`` 为参考目录时返回相对路径。"""
        base = base_dir or self.base_dir
        out_rel = str(self.output_dir)
        zip_rel = str(self.zip_path) if self.zip_path else None
        pdf_rel = str(self.pdf_path) if self.pdf_path else None
        tex_rel = str(self.tex_path) if self.tex_path else None
        bib_rel = str(self.bib_path) if self.bib_path else None
        refs_rel = str(self.refs_sources_path) if self.refs_sources_path else None
        if base:
            try:
                out_rel = str(self.output_dir.relative_to(base))
            except ValueError:
                pass
            if self.zip_path:
                try:
                    zip_rel = str(self.zip_path.relative_to(base))
                except ValueError:
                    pass
            if self.pdf_path:
                try:
                    pdf_rel = str(self.pdf_path.relative_to(base))
                except ValueError:
                    pass
            if self.tex_path:
                try:
                    tex_rel = str(self.tex_path.relative_to(base))
                except ValueError:
                    pass
            if self.bib_path:
                try:
                    bib_rel = str(self.bib_path.relative_to(base))
                except ValueError:
                    pass
            if self.refs_sources_path:
                try:
                    refs_rel = str(self.refs_sources_path.relative_to(base))
                except ValueError:
                    pass
        return {
            "output_dir": out_rel,
            "zip_path": zip_rel,
            "pdf_path": pdf_rel,
            "tex_path": tex_rel,
            "bib_path": bib_rel,
            "refs_sources_path": refs_rel,
            "skipped_reasons": self.skipped_reasons,
            "artifact_summary": self.artifact_summary,
            "verification": self.verification,
        }


# ==================== Collection ====================

def collect_artifacts(
    task_id: str,
    task_output_dir: Path,
    template_id: str = "math_modeling",
) -> CameraReadyArtifact:
    """从任务输出目录收集 camera-ready 所需的所有产物。

    v5.1 多源兜底：
    - 优先读 final/ 磁盘文件
    - final/ 不存在或主 tex 缺失时，回退到 task_result.json 的 writer_agent.latex_code
    - citations 从多处汇总：chapter_summaries.json、chapters[*].citations、
      solution.json.citations、writer_agent.paper_memory.citations、
      research_agent.papers、working memory literature

    Args:
        task_id: 任务 ID。
        task_output_dir: 任务输出根目录（含 stage_*/ 与 final/）。
        template_id: 论文模板 ID。

    Returns:
        :class:`CameraReadyArtifact`，未找到的产物以空值存在。
    """
    skipped: List[str] = []
    artifact = CameraReadyArtifact(template_id=template_id)

    final_dir = task_output_dir / "final"

    # 1. LaTeX 主文件（优先 .tex，回退到 task_result.json 兜底）
    tex_paths = [
        final_dir / "MathModeling_Paper.tex",
        final_dir / "main.tex",
    ]
    for tp in tex_paths:
        if tp.exists():
            artifact.latex_code = tp.read_text(encoding="utf-8")
            break

    # 兜底：磁盘没 LaTeX → 从 task_result.json 读 writer_agent.latex_code
    if not artifact.latex_code:
        try:
            from ..core.task_persistence import load_task_result
            result = load_task_result(task_id)
            if result:
                writer_out = result.get("output", {}).get("writer_agent", {}) or {}
                artifact.latex_code = writer_out.get("latex_code", "")
                if artifact.latex_code:
                    skipped.append("latex_code 来自 task_result.json 兜底（final/ 缺 tex）")
                    artifact.metadata["_latex_source"] = "task_result.json"
        except Exception as exc:  # noqa: BLE001
            skipped.append(f"task_result.json 兜底失败: {exc}")

    if not final_dir.exists():
        # final/ 都没有，但 latex_code 可能从 task_result.json 拿到了；继续收集其他产物
        skipped.append("final dir not found")

    # 2. figures
    if final_dir.exists():
        fig_dir = final_dir / "figures"
        if not fig_dir.exists():
            fig_dir = task_output_dir / "stage_7_charts"
        if fig_dir.exists():
            for p in sorted(fig_dir.glob("*.png")):
                artifact.figures.append(p)
            for p in sorted(fig_dir.glob("*.pdf")):
                artifact.figures.append(p)

    # 3. code files（多文件）
    code_dir = task_output_dir / "code"
    if code_dir.exists():
        for p in sorted(code_dir.rglob("*.py")):
            artifact.code_files.append(p)
    if not artifact.code_files and final_dir.exists():
        # 回退到 final/code 或 final 根目录
        for p in sorted(final_dir.glob("*.py")):
            artifact.code_files.append(p)

    # 4. chapter_summaries（磁盘 + task_result.json 兜底）
    chap_summ_path = final_dir / "chapter_summaries.json"
    if chap_summ_path.exists():
        try:
            data = json.loads(chap_summ_path.read_text(encoding="utf-8"))
            artifact.chapter_summaries = data if isinstance(data, list) else []
        except json.JSONDecodeError:
            pass
    if not artifact.chapter_summaries:
        try:
            from ..core.task_persistence import load_task_result
            result = load_task_result(task_id)
            if result:
                chapters = (result.get("output", {}).get("writer_agent", {}) or {}).get("chapters", []) or []
                artifact.chapter_summaries = chapters
        except Exception:
            pass

    # 5. metadata 从 final/solution.json 读；缺失则从 task_result.json 兜底
    sol_path = final_dir / "solution.json" if final_dir.exists() else None
    solution_data: Dict[str, Any] = {}
    if sol_path and sol_path.exists():
        try:
            solution_data = json.loads(sol_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    if not solution_data:
        try:
            from ..core.task_persistence import load_task_result
            result = load_task_result(task_id)
            if result:
                solution_data = result.get("output", {}) or {}
        except Exception:
            pass
    if isinstance(solution_data, dict):
        # solution_data 可能是顶层 result.output（无 title/abstract），也可能是 final/solution.json
        # 优先从 solution.json 顶层取；没有再下钻 writer_agent
        artifact.metadata.update({
            "title": solution_data.get("title", ""),
            "abstract": solution_data.get("abstract", ""),
            "keywords": solution_data.get("keywords", []),
        })
        writer_out = solution_data.get("writer_agent") or {}
        if not artifact.metadata.get("title") and writer_out:
            artifact.metadata["title"] = writer_out.get("title", "")
            artifact.metadata["abstract"] = writer_out.get("abstract", "")
            artifact.metadata["keywords"] = writer_out.get("keywords", [])

    # 6. citations 多源汇总（v5.1 关键修复）
    # 来源优先级：
    #   (a) chapters[*].citations 内的实际引用
    #   (b) solution.json.citations / writer_agent.citations
    #   (c) paper_memory.citations（WriterAgent 全局记忆池）
    #   (d) research_agent.papers / papers 列表
    seen_keys: set = set()
    citations: List[Dict[str, str]] = []

    def _add_cite(c: Any) -> None:
        """去重并加入 citations 列表。"""
        if not isinstance(c, dict):
            return
        key = (
            c.get("key")
            or c.get("arxiv_id")
            or c.get("doi")
            or c.get("title")
        )
        if not key:
            return
        # 优先用 arxiv_id 或 doi 作唯一键，避免不同 key 同一文献
        unique = c.get("arxiv_id") or c.get("doi") or key
        if unique in seen_keys:
            return
        seen_keys.add(unique)
        citations.append({
            "key": str(key),
            "type": c.get("type", "article"),
            "title": c.get("title", ""),
            "author": c.get("author", ""),
            "year": str(c.get("year", "")),
            "venue": c.get("venue", "") or c.get("journal", ""),
            "doi": c.get("doi", ""),
            "arxiv_id": c.get("arxiv_id", ""),
            "url": c.get("url", "") or c.get("link", ""),
            "publisher": c.get("publisher", ""),
        })

    # (a) chapters[*].citations
    for ch in artifact.chapter_summaries or []:
        if isinstance(ch, dict):
            for c in ch.get("citations") or []:
                _add_cite(c)
    # (b) solution.json.citations / writer_agent.citations（顶层）
    if isinstance(solution_data, dict):
        for c in solution_data.get("citations") or []:
            _add_cite(c)
        writer_out = solution_data.get("writer_agent") or {}
        for c in writer_out.get("citations") or []:
            _add_cite(c)
        # (c) paper_memory.citations
        pm = writer_out.get("paper_memory") or {}
        for c in pm.get("citations") or []:
            _add_cite(c)
    # (d) research_agent.papers（research 阶段搜集的文献）
    if isinstance(solution_data, dict):
        research_out = solution_data.get("research_agent") or {}
        for paper in research_out.get("papers") or []:
            _add_cite(paper)

    artifact.bib_entries = citations

    # 7. 收集模板所需的 .cls / .sty 文件
    try:
        from ..core.paper_templates import load_template
        tpl = load_template(template_id)
        project_root = Path(__file__).parent.parent.parent.parent
        if tpl and tpl.cls_file:
            cls_path = Path(tpl.cls_file)
            if not cls_path.is_absolute():
                cls_path = project_root / tpl.cls_file
            if cls_path.exists():
                artifact.cls_files.append(cls_path)
            else:
                skipped.append(f"cls file not found: {tpl.cls_file}")
        # 收集模板显式指定的 sty_files
        if tpl and tpl.sty_files:
            for sty_rel in tpl.sty_files:
                sty_path = Path(sty_rel)
                if not sty_path.is_absolute():
                    sty_path = project_root / sty_rel
                if sty_path.exists():
                    artifact.sty_files.append(sty_path)
                else:
                    skipped.append(f"sty file not found: {sty_rel}")
        # 同时收集 .cls 同目录下的 .sty（向后兼容）
        if artifact.cls_files:
            cls_dir = artifact.cls_files[0].parent
            for p in sorted(cls_dir.glob("*.sty")):
                if p not in artifact.sty_files:
                    artifact.sty_files.append(p)
    except Exception as exc:  # noqa: BLE001
        skipped.append(f"failed to collect cls/sty files: {exc}")

    artifact.collection_skipped = skipped
    return artifact


# ==================== Build ====================

BIB_PLACEHOLDER = """% Auto-generated BibTeX entries. Replace fields if arxiv_id is the only known metadata.
"""

README_TEMPLATE = """# Camera-Ready Submission Package

**Task ID:** {task_id}
**Template:** {template_id}
**Generated:** {generated_at}
**Generated by:** MathModel-MutiAgentSystem / paper-factory

## Contents

- `main.tex` — Main LaTeX source
- `main.bib` — Bibliography
- `figures/` — {n_figures} figure files
- `code/` — {n_code} Python source files
- `README.md` — This file

## Compilation

```bash
# Edit main.tex preamble if needed (\\\\documentclass{{{documentclass}}})
# Then compile:
xelatex main.tex
bibtex main   # if .bib exists
xelatex main.tex
xelatex main.tex
```

## Notes

- This package was auto-generated. Please review and edit before submission.
- All code is preserved for reproducibility.
- Citation entries with ``arxiv_id`` only are placeholders; please fill in the
  full bibliographic fields before submission.
"""


def build_bib(entries: List[Dict[str, str]]) -> str:
    """从 citation 列表生成 .bib 文本。缺字段用 arxiv_id 占位。"""
    lines = [BIB_PLACEHOLDER]
    for i, e in enumerate(entries, 1):
        if not isinstance(e, dict):
            continue
        key = e.get("key") or e.get("arxiv_id") or f"ref_{i}"
        etype = e.get("type", "article").lower()
        arxiv = e.get("arxiv_id", "")
        title = e.get("title", "").replace("{", "").replace("}", "")
        author = e.get("author", "").replace("{", "").replace("}", "")
        year = str(e.get("year", ""))
        venue = e.get("venue", "") or e.get("journal", "")
        doi = e.get("doi", "")
        volume = str(e.get("volume", ""))
        number = str(e.get("number", ""))
        pages = e.get("pages", "")
        publisher = e.get("publisher", "")
        booktitle = e.get("booktitle", "")
        series = e.get("series", "")
        editor = e.get("editor", "")

        if etype == "article":
            lines.append(f"@article{{{key},")
        elif etype == "inproceedings":
            lines.append(f"@inproceedings{{{key},")
        else:
            lines.append(f"@misc{{{key},")
        if title:
            lines.append(f"  title={{{title}}},")
        if author:
            lines.append(f"  author={{{author}}},")
        if year:
            lines.append(f"  year={{{year}}},")
        if etype == "article" and venue:
            lines.append(f"  journal={{{venue}}},")
        elif etype == "inproceedings" and venue:
            lines.append(f"  booktitle={{{venue}}},")
        elif venue:
            lines.append(f"  howpublished={{{venue}}},")
        if volume:
            lines.append(f"  volume={{{volume}}},")
        if number:
            lines.append(f"  number={{{number}}},")
        if pages:
            lines.append(f"  pages={{{pages}}},")
        if publisher:
            lines.append(f"  publisher={{{publisher}}},")
        if series:
            lines.append(f"  series={{{series}}},")
        if editor:
            lines.append(f"  editor={{{editor}}},")
        if doi:
            lines.append(f"  doi={{{doi}}},")
        if arxiv:
            lines.append(f"  eprint={{{arxiv}}},")
            lines.append("  archivePrefix={arXiv},")
        lines.append("}")
        lines.append("")
    return "\n".join(lines) if len(lines) > 1 else "% No citations available\n"


def build_references_sources(entries: List[Dict[str, str]]) -> str:
    """从 citation 列表生成可读的参考文献来源文件（含链接、DOI、arXiv ID）。

    输出格式为纯文本，每篇文献一行，包含：
    - 标题
    - 作者
    - 年份
    - 来源/期刊
    - DOI 链接（如果有）
    - arXiv 链接（如果有）
    - URL（如果有）
    """
    lines = ["# 参考文献来源", "", "本文件列出论文中引用的所有文献及其原始来源链接。", ""]
    if not entries:
        lines.append("暂无引用文献。")
        return "\n".join(lines)

    for i, e in enumerate(entries, 1):
        if not isinstance(e, dict):
            continue
        title = e.get("title", "未知标题")
        author = e.get("author", "")
        year = str(e.get("year", ""))
        venue = e.get("venue", "") or e.get("journal", "")
        doi = e.get("doi", "")
        arxiv = e.get("arxiv_id", "")
        url = e.get("url", "")
        publisher = e.get("publisher", "")

        lines.append(f"[{i}] {title}")
        if author:
            lines.append(f"    作者: {author}")
        if year:
            lines.append(f"    年份: {year}")
        if venue:
            lines.append(f"    来源: {venue}")
        if publisher:
            lines.append(f"    出版商: {publisher}")
        if doi:
            lines.append(f"    DOI: https://doi.org/{doi}")
        # arXiv 链接：只要 arxiv_id 就输出；如果 url 已经是 arxiv 链接就不再重复
        arxiv_url = f"https://arxiv.org/abs/{arxiv}" if arxiv else ""
        if arxiv_url and url != arxiv_url:
            lines.append(f"    arXiv: {arxiv_url}")
        # url：只在不是 arxiv 直链时输出，避免冗余
        if url and url != arxiv_url and not url.startswith(f"https://arxiv.org/abs/{arxiv}"):
            lines.append(f"    URL: {url}")
        elif url and not arxiv:  # 没 arxiv_id 但有 url 的情况
            lines.append(f"    URL: {url}")
        lines.append("")

    return "\n".join(lines)


def build_readme(artifact: CameraReadyArtifact, task_id: str) -> str:
    """生成 README.md。模板化，避免不实宣传。"""
    from datetime import datetime
    summary = artifact.summary()
    # 从注册表取 documentclass 写到 README 编译说明
    doc_class = "article"
    try:
        from .code_manifest import CODE_MANIFEST_PROMPT  # noqa
        from ..core.paper_templates import load_template
        tpl = load_template(artifact.template_id)
        if tpl and tpl.documentclass:
            doc_class = tpl.documentclass
    except Exception:  # noqa: BLE001
        pass

    return README_TEMPLATE.format(
        task_id=task_id,
        template_id=artifact.template_id,
        generated_at=datetime.now().isoformat(),
        n_figures=summary["figures"],
        n_code=summary["code_files"],
        documentclass=doc_class,
    )


def _build_metadata_json(
    task_id: str,
    artifact: CameraReadyArtifact,
    skipped_reasons: List[str],
) -> Dict[str, Any]:
    """生成 metadata.json 内容。"""
    from datetime import datetime
    from ..core.paper_templates import load_template

    doc_class = "article"
    engine = "xelatex"
    try:
        tpl = load_template(artifact.template_id)
        if tpl:
            doc_class = tpl.documentclass or doc_class
            engine = tpl.compile_options.get("engine", engine)
    except Exception:  # noqa: BLE001
        pass

    summary = artifact.summary()
    return {
        "task_id": task_id,
        "template_id": artifact.template_id,
        "documentclass": doc_class,
        "engine": engine,
        "generated_at": datetime.now().isoformat(),
        "metadata": {
            "title": artifact.metadata.get("title", ""),
            "abstract": artifact.metadata.get("abstract", ""),
            "keywords": artifact.metadata.get("keywords", []),
        },
        "artifact_summary": summary,
        "skipped_reasons": skipped_reasons,
    }


def _verify_compilation(pkg_dir: Path, template_id: str) -> Dict[str, Any]:
    """尝试编译 main.tex，返回验证结果（不阻断打包）。"""
    from ..core.paper_templates import load_template

    main_tex = pkg_dir / "main.tex"
    if not main_tex.exists():
        return {"success": False, "message": "main.tex not found", "pdf_path": None}

    engine = "xelatex"
    try:
        tpl = load_template(template_id)
        if tpl:
            engine = tpl.compile_options.get("engine", engine)
    except Exception:  # noqa: BLE001
        pass

    # 优先使用 latexmk；若不可用则使用 engine 直接编译一次
    engines_to_try = ["latexmk", engine]
    if engine != "xelatex":
        engines_to_try.append("xelatex")

    for eng in engines_to_try:
        cmd_path = shutil.which(eng)
        if not cmd_path:
            continue
        cmd: List[str]
        if eng == "latexmk":
            cmd = [eng, "-pdf", "-interaction=nonstopmode", "-silent", "main.tex"]
        else:
            cmd = [eng, "-interaction=nonstopmode", "main.tex"]
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(pkg_dir),
                capture_output=True,
                text=True,
                timeout=120,
            )
            pdf_path = pkg_dir / "main.pdf"
            success = pdf_path.exists()
            try:
                pdf_rel = str(pdf_path.relative_to(pkg_dir.parent)) if success else None
            except ValueError:
                pdf_rel = str(pdf_path) if success else None
            return {
                "success": success,
                "engine": eng,
                "returncode": proc.returncode,
                "message": "ok" if success else f"{eng} failed (rc={proc.returncode})",
                "pdf_path": pdf_rel,
                "stderr_snippet": proc.stderr[:2000] if not success or proc.returncode != 0 else "",
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "engine": eng, "message": "compilation timeout", "pdf_path": None}
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "engine": eng, "message": str(exc), "pdf_path": None}

    return {"success": False, "message": "no latex engine available", "pdf_path": None}


def build(
    task_id: str,
    artifact: CameraReadyArtifact,
    output_dir: Path,
    make_zip: bool = True,
    max_zip_mb: int = 50,
) -> CameraReadyResult:
    """构造 camera-ready 包到 ``output_dir``，可选打 zip。

    Args:
        task_id: 任务 ID。
        artifact: 已收集的产物。
        output_dir: 输出根目录（包目录会创建在 ``output_dir/camera_ready_<task_id>/``）。
        make_zip: 是否同时打 zip。
        max_zip_mb: zip 超过该大小（MB）则跳过大文件并记录 skipped_reasons。

    Returns:
        :class:`CameraReadyResult`。
    """
    skipped: List[str] = list(getattr(artifact, "collection_skipped", []))
    pkg_dir = output_dir / f"camera_ready_{task_id}"
    pkg_dir.mkdir(parents=True, exist_ok=True)

    # 1. main.tex
    if artifact.latex_code:
        (pkg_dir / "main.tex").write_text(artifact.latex_code, encoding="utf-8")
    else:
        skipped.append("missing main.tex")

    # 2. main.bib — 过滤未验证的引用（_verified=False），保留未标记的（无验真流程时）
    verified_entries = [
        e for e in artifact.bib_entries
        if not isinstance(e, dict) or e.get("_verified", True)
    ]
    unverified_count = len(artifact.bib_entries) - len(verified_entries)
    if unverified_count:
        skipped.append(f"filtered {unverified_count} unverified references")
    bib_text = build_bib(verified_entries)
    bib_path = pkg_dir / "main.bib"
    bib_path.write_text(bib_text, encoding="utf-8")

    # 2.5 references_sources.txt（原始链接/DOI 来源，方便用户直接引用）
    refs_sources_text = build_references_sources(artifact.bib_entries)
    refs_sources_path = pkg_dir / "references_sources.txt"
    refs_sources_path.write_text(refs_sources_text, encoding="utf-8")

    # 3. figures/
    fig_dir = pkg_dir / "figures"
    if artifact.figures:
        fig_dir.mkdir(exist_ok=True)
        for src in artifact.figures:
            try:
                shutil.copy2(src, fig_dir / src.name)
            except Exception as exc:  # noqa: BLE001
                skipped.append(f"figure copy failed: {src.name}: {exc}")
    else:
        skipped.append("no figures available")

    # 4. code/（保留相对子目录结构）
    code_dir = pkg_dir / "code"
    if artifact.code_files:
        code_dir.mkdir(exist_ok=True)
        for src in artifact.code_files:
            try:
                # 尽量保留原始相对路径；若无法解析则平铺
                rel = src.name
                code_src_root = src
                # 向上寻找可能的 code 根目录（code/ 或 final/）
                for parent in src.parents:
                    if parent.name in ("code", "final") or parent == output_dir:
                        code_src_root = parent
                        break
                try:
                    rel = src.relative_to(code_src_root)
                except ValueError:
                    rel = Path(src.name)
                dst = code_dir / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            except Exception as exc:  # noqa: BLE001
                skipped.append(f"code copy failed: {src.name}: {exc}")
    else:
        skipped.append("no code files available")

    # 4.5 references/（论文全文阅读管线下载的 PDF 参考文献）
    project_name = getattr(artifact, "project_name", None)
    if project_name:
        from ..core.paths import get_project_base_dir
        project_refs = get_project_base_dir(project_name) / "references"
        if project_refs.exists():
            ref_dir = pkg_dir / "references"
            ref_dir.mkdir(exist_ok=True)
            for pdf in sorted(project_refs.glob("*.pdf")):
                try:
                    shutil.copy2(pdf, ref_dir / pdf.name)
                except Exception as exc:  # noqa: BLE001
                    skipped.append(f"reference copy failed: {pdf.name}: {exc}")

    # 5. manifest 描述
    if artifact.code_manifest_text:
        (pkg_dir / "code_manifest.md").write_text(artifact.code_manifest_text, encoding="utf-8")

    # 6. README.md
    (pkg_dir / "README.md").write_text(
        build_readme(artifact, task_id), encoding="utf-8"
    )

    # 7. .cls / .sty 文件（让 zip 拿到即可编译）
    if artifact.cls_files:
        for src in artifact.cls_files:
            try:
                shutil.copy2(src, pkg_dir / src.name)
            except Exception as exc:  # noqa: BLE001
                skipped.append(f"cls copy failed: {src.name}: {exc}")
    if artifact.sty_files:
        for src in artifact.sty_files:
            try:
                shutil.copy2(src, pkg_dir / src.name)
            except Exception as exc:  # noqa: BLE001
                skipped.append(f"sty copy failed: {src.name}: {exc}")

    # 8. metadata.json
    metadata = _build_metadata_json(task_id, artifact, skipped)
    (pkg_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 9. 编译验证（不阻断打包）
    verification = _verify_compilation(pkg_dir, artifact.template_id)
    if not verification.get("success"):
        skipped.append(f"compilation verification: {verification.get('message', 'failed')}")

    # 9b. 将 verification 写回 metadata.json
    metadata["verification"] = verification
    (pkg_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 10. 收集独立产物路径
    tex_path = pkg_dir / "main.tex" if artifact.latex_code else None
    pdf_path = None
    if verification.get("success"):
        compiled_pdf = pkg_dir / "main.pdf"
        if compiled_pdf.exists():
            pdf_path = compiled_pdf
            # 同时复制到 output_dir 根目录，方便用户直接获取
            try:
                root_pdf = output_dir / f"paper_{task_id}.pdf"
                shutil.copy2(compiled_pdf, root_pdf)
            except Exception:
                pass

    # 11. zip（可选，默认仍生成以兼容旧流程）
    zip_path: Optional[Path] = None
    if make_zip:
        zip_path = output_dir / f"camera_ready_{task_id}.zip"
        try:
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for p in pkg_dir.rglob("*"):
                    if p.is_file():
                        zf.write(p, p.relative_to(pkg_dir.parent))
        except Exception as exc:  # noqa: BLE001
            skipped.append(f"zip creation failed: {exc}")
            zip_path = None
        # 检查大小
        if zip_path and zip_path.exists():
            mb = zip_path.stat().st_size / (1024 * 1024)
            if mb > max_zip_mb:
                skipped.append(
                    f"zip too large ({mb:.1f} MB > {max_zip_mb} MB); figures may need re-compression"
                )

    return CameraReadyResult(
        output_dir=pkg_dir,
        zip_path=zip_path,
        skipped_reasons=skipped,
        artifact_summary=artifact.summary(),
        verification=verification,
        base_dir=output_dir,
        pdf_path=pdf_path,
        tex_path=tex_path,
        bib_path=bib_path if bib_path.exists() else None,
        refs_sources_path=refs_sources_path if refs_sources_path.exists() else None,
    )

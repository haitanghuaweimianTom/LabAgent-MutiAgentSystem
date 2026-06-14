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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "output_dir": str(self.output_dir),
            "zip_path": str(self.zip_path) if self.zip_path else None,
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
    if not final_dir.exists():
        skipped.append("final dir not found")
        artifact.collection_skipped = skipped
        return artifact

    # 1. LaTeX 主文件（优先 .tex，回退到 .md 转 tex）
    tex_path = final_dir / "MathModeling_Paper.tex"
    if not tex_path.exists():
        tex_path = final_dir / "main.tex"
    if tex_path.exists():
        artifact.latex_code = tex_path.read_text(encoding="utf-8")

    # 2. figures
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
    if not artifact.code_files:
        # 回退到 final/code 或 final 根目录
        for p in sorted(final_dir.glob("*.py")):
            artifact.code_files.append(p)

    # 4. bib：从 chapter_summaries.json 读 citations
    chap_summ_path = final_dir / "chapter_summaries.json"
    if chap_summ_path.exists():
        try:
            data = json.loads(chap_summ_path.read_text(encoding="utf-8"))
            artifact.chapter_summaries = data if isinstance(data, list) else []
        except json.JSONDecodeError:
            pass

    # 5. metadata 从 final/solution.json 读
    sol_path = final_dir / "solution.json"
    if sol_path.exists():
        try:
            data = json.loads(sol_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                artifact.metadata = {
                    "title": data.get("title", ""),
                    "abstract": data.get("abstract", ""),
                    "keywords": data.get("keywords", []),
                }
        except json.JSONDecodeError:
            pass

    # 6. 收集模板所需的 .cls / .sty 文件
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
        # 同时收集同目录下的 .sty
        if artifact.cls_files:
            cls_dir = artifact.cls_files[0].parent
            for p in sorted(cls_dir.glob("*.sty")):
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
            return {
                "success": success,
                "engine": eng,
                "returncode": proc.returncode,
                "message": "ok" if success else f"{eng} failed (rc={proc.returncode})",
                "pdf_path": str(pdf_path) if success else None,
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

    # 2. main.bib
    bib_text = build_bib(artifact.bib_entries)
    (pkg_dir / "main.bib").write_text(bib_text, encoding="utf-8")

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
                # 向上寻找可能的 code 根目录（output/code 或 final）
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

    # 8b. 将 verification 写回 metadata.json
    metadata["verification"] = verification
    (pkg_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 10. zip
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
    )

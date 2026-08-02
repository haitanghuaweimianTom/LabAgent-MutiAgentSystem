"""交付物组装服务 —— 将多智能体产出组装为结构化可交付文件夹。

目录命名: {project_name}_{YYYYMMDD}

结构:
  01_论文/          论文 LaTeX + Markdown
  02_参考文献/      参考文献索引 (MD + BibTeX)
  03_数据来源/      数据文件清单 + 来源说明
  04_实验方案/      实验设计 + 研究规划
  05_实验日志/      求解执行记录 + 时间线
  06_参数配置/      模型参数 + 求解配置
  07_代码/          源代码文件
  08_图表/          科研图表
  09_模型文档/      数学模型定义
  10_质量报告/      事实核查 + 同行评议 + 质量评估
  README.md         总览索引
"""
from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def assemble_deliverable(
    task_id: str,
    output_dir: Path,
    results: Dict[str, Any],
    state: Dict[str, Any],
    project_name: Optional[str] = None,
    chat_events: Optional[List[Dict[str, Any]]] = None,
) -> Optional[Path]:
    """组装交付文件夹。

    Args:
        task_id: 任务 ID
        output_dir: 项目输出目录 (get_project_output_dir)
        results: 已解析的全部 Agent 结果
        state: LangGraph 最终 state
        project_name: 项目名称
        chat_events: 聊天室事件列表（用于时间线）

    Returns:
        交付文件夹路径；失败返回 None。
    """
    try:
        date_str = datetime.now().strftime("%Y%m%d")
        safe_name = _safe_filename(project_name or "未命名项目")
        folder_name = f"{safe_name}_{date_str}"
        # project_name 为空时 output_dir=outputs/_global，其 parent=outputs/ 会把
        # 交付文件夹堆到顶层。改为始终用 outputs/<safe_name>/ 作为父目录，避免顶层污染。
        from ..core.paths import _PROJECT_ROOT
        project_root_dir = _PROJECT_ROOT / "outputs" / safe_name
        project_root_dir.mkdir(parents=True, exist_ok=True)
        deliverable_dir = project_root_dir / folder_name
        if deliverable_dir.exists():
            # 避免覆盖：追加序号
            for i in range(2, 99):
                candidate = project_root_dir / f"{folder_name}_{i}"
                if not candidate.exists():
                    deliverable_dir = candidate
                    break

        logger.info(f"[Deliverable:{task_id}] 组装交付文件夹: {deliverable_dir}")

        # 创建子目录
        dirs = {}
        for name in [
            "01_论文", "02_参考文献", "03_数据来源", "04_实验方案",
            "05_实验日志", "06_参数配置", "07_代码", "08_图表",
            "09_模型文档", "10_质量报告",
        ]:
            d = deliverable_dir / name
            d.mkdir(parents=True, exist_ok=True)
            dirs[name] = d

        # 各节独立构建，任一环节失败不影响其余
        builders = [
            ("01_论文", lambda: _build_paper(dirs["01_论文"], results, output_dir, task_id)),
            ("02_参考文献", lambda: _build_references(dirs["02_参考文献"], results, output_dir)),
            ("03_数据来源", lambda: _build_data_sources(dirs["03_数据来源"], results, state, output_dir)),
            ("04_实验方案", lambda: _build_experiment_plan(dirs["04_实验方案"], results, state)),
            ("05_实验日志", lambda: _build_experiment_log(dirs["05_实验日志"], results, state, chat_events)),
            ("06_参数配置", lambda: _build_parameters(dirs["06_参数配置"], results, state)),
            ("07_代码", lambda: _build_code(dirs["07_代码"], results, output_dir)),
            ("08_图表", lambda: _build_figures(dirs["08_图表"], results, output_dir)),
            ("09_模型文档", lambda: _build_model_docs(dirs["09_模型文档"], results, output_dir)),
            ("10_质量报告", lambda: _build_quality_report(dirs["10_质量报告"], results, output_dir)),
        ]
        for section_name, builder_fn in builders:
            try:
                builder_fn()
            except Exception as sec_exc:
                logger.warning(f"[Deliverable:{task_id}] {section_name} 构建失败（不影响其他节）: {sec_exc}")

        # README
        try:
            _build_readme(deliverable_dir, results, state, project_name, task_id)
        except Exception as readme_exc:
            logger.warning(f"[Deliverable:{task_id}] README 构建失败: {readme_exc}")

        logger.info(f"[Deliverable:{task_id}] 交付文件夹组装完成: {deliverable_dir}")
        return deliverable_dir

    except Exception as exc:
        logger.exception(f"[Deliverable:{task_id}] 交付物组装失败: {exc}")
        return None


def cleanup_intermediates(
    task_id: str,
    output_dir: Path,
    deliverable_dir: Path,
    keep_camera_ready_pkg: bool = False,
) -> Dict[str, Any]:
    """交付文件夹组装成功后，清理冗余中间产物。

    用户要求：最终交付只需一个分门别类的文件夹，不要 output/ 中间目录、
    不要 camera_ready 解压副本、不要 zip 压缩包。本函数把已被交付文件夹
    吸收的中间产物删除，使 outputs/<project>/ 下只剩交付文件夹。

    删除范围（均在 output_dir = outputs/<project>/output/ 内）：
    - camera_ready_<task_id>.zip         （用户明确不要压缩包）
    - camera_ready_<task_id>/            （解压副本，内容已在 01_论文 + 08_图表）
    - final/  code/  figures/  papers/  charts/  figs/  stage_*/
      以及散落的 *.json / *.png / *.tex 等运行期文件
    - 整个 output/ 目录本身（删空后重建空目录，保持 get_project_output_dir 契约）

    保留：
    - deliverable_dir（交付文件夹，output_dir.parent 下的 <name>_<date>/）
    - 可选保留 camera_ready_<task_id>/（keep_camera_ready_pkg=True，
      供旧版下载端点 fallback）

    Args:
        task_id: 任务 ID。
        output_dir: 项目输出目录 outputs/<project>/output/。
        deliverable_dir: 交付文件夹路径（不删）。
        keep_camera_ready_pkg: 是否保留 camera_ready_<task_id>/ 包目录。

    Returns:
        清理统计字典。
    """
    stats = {"removed_zip": False, "removed_camera_ready_pkg": False,
             "removed_output_dir": False, "freed_bytes": 0, "skipped": []}
    try:
        # 安全检查：deliverable_dir 必须在 output_dir.parent 下，且不能是 output_dir 本身
        if deliverable_dir.resolve() == output_dir.resolve():
            stats["skipped"].append("deliverable_dir == output_dir, abort")
            return stats
        if output_dir.parent not in deliverable_dir.parents:
            stats["skipped"].append("deliverable_dir not under output_dir.parent, abort")
            return stats

        def _size_of(p: Path) -> int:
            if p.is_file():
                return p.stat().st_size
            if p.is_dir():
                return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
            return 0

        # 1. zip
        zip_path = output_dir / f"camera_ready_{task_id}.zip"
        if zip_path.exists():
            stats["freed_bytes"] += _size_of(zip_path)
            zip_path.unlink()
            stats["removed_zip"] = True
            logger.info(f"[Deliverable:{task_id}] 清理 zip: {zip_path.name}")

        # 2. camera_ready_<task_id>/ 包目录
        cr_pkg = output_dir / f"camera_ready_{task_id}"
        if cr_pkg.exists() and not keep_camera_ready_pkg:
            stats["freed_bytes"] += _size_of(cr_pkg)
            shutil.rmtree(cr_pkg, ignore_errors=True)
            stats["removed_camera_ready_pkg"] = True
            logger.info(f"[Deliverable:{task_id}] 清理 camera_ready 包目录: {cr_pkg.name}")

        # 3. 整个 output/ 目录（中间产物已被交付文件夹吸收）
        if output_dir.exists():
            stats["freed_bytes"] += _size_of(output_dir)
            shutil.rmtree(output_dir, ignore_errors=True)
            stats["removed_output_dir"] = True
            # 重建空目录：get_project_output_dir 契约要求该目录可访问
            # （后续 rerun / 重新生成产物时会用到）
            output_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"[Deliverable:{task_id}] 清理 output 中间目录: {output_dir}")

        logger.info(
            f"[Deliverable:{task_id}] 中间产物清理完成，释放 "
            f"{stats['freed_bytes'] / 1024:.0f} KB"
        )
    except Exception as exc:
        logger.exception(f"[Deliverable:{task_id}] 中间产物清理失败: {exc}")
        stats["skipped"].append(f"exception: {exc}")
    return stats


def find_deliverable_dir(project_name: Optional[str]) -> Optional[Path]:
    """查找项目下最新的交付文件夹（outputs/<project>/<name>_<date>/）。

    交付文件夹命名形如 ``<safe_name>_<YYYYMMDD>[_<n>]``。返回最新（按名排序最大）的一个。
    供下载端点在 output/ 已被清理后，从交付文件夹提供 main.pdf/main.tex 等产物。
    """
    if not project_name:
        return None
    try:
        from ..core.paths import get_project_base_dir
        base = get_project_base_dir(project_name)
    except Exception:
        return None
    if not base.exists():
        return None
    candidates: List[Path] = []
    for d in base.iterdir():
        if not d.is_dir():
            continue
        # 跳过系统目录与 output/data 子目录
        if d.name in ("output", "data", "references", "_global"):
            continue
        # 交付文件夹须含 01_论文/ 子目录（特征匹配）
        if (d / "01_论文").is_dir():
            candidates.append(d)
    if not candidates:
        return None
    # 按目录名倒序，取最新
    candidates.sort(key=lambda p: p.name, reverse=True)
    return candidates[0]


def _build_paper(d: Path, results: Dict, output_dir: Path, task_id: str = "") -> None:
    """01_论文: LaTeX + Markdown + PDF 三态交付。"""
    writer = results.get("writer_agent", {})
    if not isinstance(writer, dict):
        return

    latex = writer.get("latex_code", "")
    if latex:
        (d / "main.tex").write_text(latex, encoding="utf-8")

    # ---- Markdown 导出 ----
    # Writer 只产出 latex_code，不产出 markdown_code。
    # 策略：优先用 writer 的 sections 结构重建 MD；若缺失则从 latex 粗略转换。
    md = writer.get("markdown_code", "") or writer.get("content", "")
    if not md or len(md) < 100:
        md = _latex_to_markdown(writer)
    if md and len(md) > 100:
        (d / "paper.md").write_text(md, encoding="utf-8")

    # ---- PDF 导出 ----
    # 优先级：1) camera_ready 编译的 PDF（output_dir/camera_ready_<task_id>/main.pdf，
    #            由 camera_ready.build 写入）  2) output_dir/paper_<task_id>.pdf
    #            （camera_ready.build 编译成功后复制到 output_dir 根目录）
    #            3) final/ 目录  4) 历史遗留的 _global/papers/ 位置
    pdf_candidates = [
        output_dir / "final" / "main.pdf",
        output_dir / "main.pdf",
    ]
    if task_id:
        pdf_candidates.extend([
            output_dir / f"camera_ready_{task_id}" / "main.pdf",
            output_dir / f"paper_{task_id}.pdf",
            # 兼容旧版本：曾把 PDF 复制到 _global/papers/paper_<task_id>.pdf
            output_dir.parent / "_global" / "papers" / f"paper_{task_id}.pdf",
        ])
    for candidate in pdf_candidates:
        if candidate.exists():
            shutil.copy2(candidate, d / "main.pdf")
            break

    # 元数据
    meta = {
        "title": writer.get("title", ""),
        "abstract": writer.get("abstract", ""),
        "keywords": writer.get("keywords", []),
        "generated_at": writer.get("generated_at", ""),
    }
    (d / "metadata.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _build_references(d: Path, results: Dict, output_dir: Path) -> None:
    """02_参考文献: MD 索引 + BibTeX。"""
    citations: List[Dict] = []
    seen_keys = set()

    def _add(c: Dict) -> None:
        key = c.get("key") or c.get("arxiv_id") or c.get("title", "")
        if key and key not in seen_keys:
            seen_keys.add(key)
            citations.append(c)

    # (a) writer_agent.chapters[].citations
    writer = results.get("writer_agent", {})
    if isinstance(writer, dict):
        for ch in writer.get("chapters", []):
            if isinstance(ch, dict):
                for c in ch.get("citations", []):
                    _add(c)
        # (b) writer_agent.paper_memory.citations
        pm = writer.get("paper_memory", {})
        if isinstance(pm, dict):
            for c in pm.get("citations", []):
                _add(c)
        # (c) 顶层 citations
        for c in writer.get("citations", []):
            _add(c)

    # (d) research_agent.papers
    research = results.get("research_agent", {})
    if isinstance(research, dict):
        for paper in research.get("papers", []):
            if isinstance(paper, dict):
                _add({
                    "key": paper.get("arxiv_id", paper.get("title", "")),
                    "title": paper.get("title", ""),
                    "authors": paper.get("authors", []),
                    "year": str(paper.get("year", "")),
                    "arxiv_id": paper.get("arxiv_id", ""),
                    "url": paper.get("url", "") or paper.get("link", ""),
                    "abstract": paper.get("abstract", ""),
                    "source": "research_agent",
                })

    # (e) summary_agent.literature_registry
    summary = results.get("task_summary", {}) or results.get("summary_agent", {})
    if isinstance(summary, dict):
        for lit in summary.get("literature_registry", []):
            if isinstance(lit, dict):
                _add({
                    "key": lit.get("arxiv_id", lit.get("title", "")),
                    "title": lit.get("title", ""),
                    "arxiv_id": lit.get("arxiv_id", ""),
                    "relevance": lit.get("relevance", ""),
                })

    # 生成 Markdown 索引
    md_lines = ["# 参考文献索引\n", f"共 {len(citations)} 篇文献\n"]
    for i, c in enumerate(citations, 1):
        title = c.get("title", "未知标题")
        authors = c.get("authors", [])
        if isinstance(authors, list):
            author_str = ", ".join(str(a) for a in authors[:5])
            if len(authors) > 5:
                author_str += " et al."
        else:
            author_str = str(authors) if authors else ""
        year = c.get("year", "")
        arxiv_id = c.get("arxiv_id", "")
        url = c.get("url", "")
        abstract = (c.get("abstract", "") or "")[:200]
        relevance = c.get("relevance", "")

        # 生成可点击链接
        if url:
            link = f"[链接]({url})"
        elif arxiv_id:
            link = f"[arXiv](https://arxiv.org/abs/{arxiv_id})"
        else:
            link = ""

        md_lines.append(f"## [{i}] {title}\n")
        if author_str:
            md_lines.append(f"- **作者**: {author_str}")
        if year:
            md_lines.append(f"- **年份**: {year}")
        if link:
            md_lines.append(f"- **链接**: {link}")
        if arxiv_id:
            md_lines.append(f"- **arXiv ID**: {arxiv_id}")
        if relevance:
            md_lines.append(f"- **关联说明**: {relevance}")
        if abstract:
            md_lines.append(f"- **摘要**: {abstract}...")
        # 本地 PDF 链接（如果 reading/ 目录有对应文件）
        if arxiv_id:
            md_lines.append(f"- **本地阅读**: `reading/{arxiv_id}.md`")
        md_lines.append("")

    (d / "references.md").write_text("\n".join(md_lines), encoding="utf-8")

    # 生成 BibTeX
    bib_lines = []
    for i, c in enumerate(citations, 1):
        key = c.get("key") or c.get("arxiv_id") or f"ref{i}"
        title = c.get("title", "")
        authors = c.get("authors", [])
        author_str = " and ".join(str(a) for a in authors) if isinstance(authors, list) else str(authors)
        year = c.get("year", "")
        bib_lines.append(f"@misc{{{key},")
        bib_lines.append(f"  title = {{{title}}},")
        if author_str:
            bib_lines.append(f"  author = {{{author_str}}},")
        if year:
            bib_lines.append(f"  year = {{{year}}},")
        if c.get("arxiv_id"):
            bib_lines.append(f"  eprint = {{{c['arxiv_id']}}},")
            bib_lines.append(f"  archivePrefix = {{arXiv}},")
        bib_lines.append("}\n")

    (d / "references.bib").write_text("\n".join(bib_lines), encoding="utf-8")


def _build_data_sources(d: Path, results: Dict, state: Dict, output_dir: Path) -> None:
    """03_数据来源: 数据文件清单 + 来源说明。"""
    md_lines = ["# 数据来源\n"]

    # 用户上传的文件
    data_files = state.get("files", [])
    if data_files:
        md_lines.append("## 用户上传数据\n")
        # 项目数据目录（用于解析相对路径）
        try:
            from ..core.paths import get_project_data_dir
            data_base = get_project_data_dir(state.get("project_name"))
        except Exception:
            data_base = None
        for f in data_files:
            fname = Path(f).name if isinstance(f, str) else str(f)
            md_lines.append(f"- `{fname}`")
            # 复制文件到交付目录（尝试绝对路径 + 项目数据目录）
            src = Path(f)
            if not src.exists() and data_base:
                # 尝试在项目数据目录中查找
                for sub in ("user_uploads", "", "user_upload"):
                    candidate = data_base / sub / fname if sub else data_base / fname
                    if candidate.exists():
                        src = candidate
                        break
            if src.exists():
                try:
                    shutil.copy2(src, d / fname)
                except Exception:
                    pass
        md_lines.append("")

    # data_agent 分析结果
    data_agent = results.get("data_agent", {})
    if isinstance(data_agent, dict) and data_agent:
        md_lines.append("## 数据分析摘要\n")
        insights = data_agent.get("insights", [])
        if insights:
            for ins in insights[:10]:
                md_lines.append(f"- {ins}")
        summary = data_agent.get("summary", "")
        if summary:
            md_lines.append(f"\n{summary}")
        md_lines.append("")

    # 自收集数据
    self_collected_dir = output_dir.parent / "data" / "self_collected"
    if self_collected_dir.exists():
        md_lines.append("## 系统自主收集数据\n")
        index_file = self_collected_dir / "_index.json"
        if index_file.exists():
            try:
                index = json.loads(index_file.read_text(encoding="utf-8"))
                for entry in index:
                    fname = entry.get("filename", "")
                    source = entry.get("source_url", entry.get("source", ""))
                    size = entry.get("size", 0)
                    md_lines.append(f"- `{fname}` ({size} bytes) — 来源: {source}")
                    # 复制
                    src = self_collected_dir / fname
                    if src.exists():
                        try:
                            shutil.copy2(src, d / fname)
                        except Exception:
                            pass
            except Exception:
                pass
        # 扫描目录中的实际文件
        for f in sorted(self_collected_dir.glob("*")):
            if f.is_file() and f.name != "_index.json":
                md_lines.append(f"- `{f.name}` ({f.stat().st_size} bytes)")
                try:
                    shutil.copy2(f, d / f.name)
                except Exception:
                    pass
        md_lines.append("")

    # summary 中的 dataset_registry
    summary = results.get("task_summary", {}) or {}
    if isinstance(summary, dict):
        datasets = summary.get("dataset_registry", [])
        if datasets:
            md_lines.append("## 数据集注册表\n")
            for ds in datasets:
                name = ds.get("name", "")
                source = ds.get("source", "")
                dtype = ds.get("type", "")
                md_lines.append(f"- **{name}** ({dtype}) — 来源: {source}")
            md_lines.append("")

    if len(md_lines) <= 1:
        md_lines.append("本任务未使用外部数据。\n")

    (d / "data_sources.md").write_text("\n".join(md_lines), encoding="utf-8")


def _build_experiment_plan(d: Path, results: Dict, state: Dict) -> None:
    """04_实验方案: 实验设计 + 研究规划。"""
    md_lines = ["# 实验方案\n"]

    # requirement_plan
    req_plan = state.get("requirement_plan")
    if isinstance(req_plan, dict) and req_plan:
        md_lines.append("## 研究规划\n")
        goal = req_plan.get("research_goal", "")
        if goal:
            md_lines.append(f"**研究目标**: {goal}\n")
        subtasks = req_plan.get("subtasks", [])
        if subtasks:
            md_lines.append("### 子任务\n")
            for st in subtasks:
                desc = st.get("description", "")
                agent = st.get("suggested_agent", "")
                priority = st.get("priority", "")
                md_lines.append(f"- [{priority}] {desc} (建议: {agent})")
            md_lines.append("")
        methods = req_plan.get("methodology_hints", [])
        if methods:
            md_lines.append("### 方法提示\n")
            for m in methods:
                md_lines.append(f"- {m}")
            md_lines.append("")

    # experimentation_agent
    exp = results.get("experimentation_agent", {})
    if isinstance(exp, dict) and exp:
        md_lines.append("## 实验设计\n")
        baselines = exp.get("baselines", [])
        if baselines:
            md_lines.append("### 基线方法\n")
            for b in baselines:
                name = b.get("name", "") if isinstance(b, dict) else str(b)
                cat = b.get("category", "") if isinstance(b, dict) else ""
                rationale = b.get("rationale", "") if isinstance(b, dict) else ""
                md_lines.append(f"- **{name}** [{cat}]: {rationale}")
            md_lines.append("")
        datasets = exp.get("datasets", [])
        if datasets:
            md_lines.append("### 数据集\n")
            for ds in datasets:
                name = ds.get("name", "") if isinstance(ds, dict) else str(ds)
                size = ds.get("size", "") if isinstance(ds, dict) else ""
                source = ds.get("source", "") if isinstance(ds, dict) else ""
                md_lines.append(f"- **{name}** ({size}) — {source}")
            md_lines.append("")
        metrics = exp.get("metrics", [])
        if metrics:
            md_lines.append("### 评价指标\n")
            for m in metrics:
                name = m.get("name", "") if isinstance(m, dict) else str(m)
                direction = m.get("direction", "") if isinstance(m, dict) else ""
                md_lines.append(f"- {name} ({direction})")
            md_lines.append("")
        ablation = exp.get("ablation_plan", [])
        if ablation:
            md_lines.append("### 消融实验\n")
            for a in ablation:
                comp = a.get("component", "") if isinstance(a, dict) else str(a)
                purpose = a.get("purpose", "") if isinstance(a, dict) else ""
                md_lines.append(f"- **{comp}**: {purpose}")
            md_lines.append("")

    # innovation_analysis
    innovation = state.get("innovation_analysis")
    if isinstance(innovation, dict) and innovation:
        md_lines.append("## 创新分析\n")
        gaps = innovation.get("research_gaps", [])
        if gaps:
            md_lines.append("### 研究空白\n")
            for g in gaps:
                desc = g.get("description", str(g)) if isinstance(g, dict) else str(g)
                md_lines.append(f"- {desc}")
            md_lines.append("")
        ideas = innovation.get("innovation_ideas", [])
        if ideas:
            md_lines.append("### 创新方案\n")
            for idea in ideas:
                title = idea.get("title", str(idea)) if isinstance(idea, dict) else str(idea)
                md_lines.append(f"- {title}")
            md_lines.append("")

    if len(md_lines) <= 1:
        md_lines.append("本任务未生成独立实验方案。\n")

    (d / "experiment_plan.md").write_text("\n".join(md_lines), encoding="utf-8")


def _build_experiment_log(
    d: Path, results: Dict, state: Dict,
    chat_events: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """05_实验日志: 求解执行记录 + 时间线。"""
    md_lines = ["# 实验日志\n"]

    # solver_agent 执行记录
    solver = results.get("solver_agent", {})
    if isinstance(solver, dict):
        solutions = solver.get("sub_problem_solutions", [])
        if solutions:
            md_lines.append("## 求解记录\n")
            for sol in solutions:
                sp_name = sol.get("sub_problem_name", f"子问题{sol.get('sub_problem_id', '?')}")
                success = sol.get("execution_success", False)
                status = "✅ 成功" if success else "❌ 失败"
                md_lines.append(f"### {sp_name} — {status}\n")
                # 执行结果
                exec_result = sol.get("execution_result", {})
                if isinstance(exec_result, dict):
                    output = exec_result.get("output", "")
                    if output:
                        md_lines.append(f"```\n{output[:1000]}\n```\n")
                # 数值结果
                numerical = sol.get("numerical_results", {})
                if numerical and isinstance(numerical, dict):
                    md_lines.append("**数值结果**:\n")
                    for k, v in numerical.items():
                        md_lines.append(f"- {k}: {v}")
                    md_lines.append("")
                # 关键发现
                findings = sol.get("results", {}).get("key_findings", [])
                if findings:
                    md_lines.append("**关键发现**:\n")
                    for f in findings:
                        md_lines.append(f"- {f}")
                    md_lines.append("")
                # Harness 评判
                harness = sol.get("harness", {})
                if isinstance(harness, dict):
                    passed = harness.get("passed", False)
                    md_lines.append(f"**Harness**: {'通过' if passed else '未通过'}\n")

    # 代码演化
    if isinstance(solver, dict):
        for sol in solver.get("sub_problem_solutions", []):
            evo = sol.get("code_evolution", {})
            if evo and isinstance(evo, dict) and evo.get("improved"):
                sp_name = sol.get("sub_problem_name", "")
                md_lines.append(f"### 代码自动演化 — {sp_name}\n")
                md_lines.append(f"- 改进幅度: {evo.get('improvement', 0):.1%}")
                md_lines.append(f"- 代数: {evo.get('generations', 0)}")
                md_lines.append(f"- 总评估次数: {evo.get('total_evaluations', 0)}\n")

    # 实验执行结果
    exp = results.get("experimentation_agent", {})
    if isinstance(exp, dict) and exp.get("executed"):
        md_lines.append("## 实验执行记录\n")
        exp_summary = exp.get("summary", exp.get("summary_text", ""))
        if exp_summary:
            md_lines.append(f"{exp_summary}\n")
        baseline_comp = exp.get("baseline_comparison", {})
        if baseline_comp:
            md_lines.append("### 基线对比\n")
            md_lines.append(f"```json\n{json.dumps(baseline_comp, ensure_ascii=False, indent=2)[:2000]}\n```\n")
        ablation_study = exp.get("ablation_study", {})
        if ablation_study:
            md_lines.append("### 消融实验结果\n")
            md_lines.append(f"```json\n{json.dumps(ablation_study, ensure_ascii=False, indent=2)[:2000]}\n```\n")

    # 时间线（从 chat_events）
    if chat_events:
        md_lines.append("## 执行时间线\n")
        for evt in chat_events[:50]:
            ts = evt.get("timestamp", "")
            agent = evt.get("agent", evt.get("sender", ""))
            msg = evt.get("message", evt.get("content", ""))
            if isinstance(msg, str) and len(msg) > 150:
                msg = msg[:150] + "..."
            md_lines.append(f"- `{ts}` **{agent}**: {msg}")
        md_lines.append("")

    if len(md_lines) <= 1:
        md_lines.append("无实验执行记录。\n")

    (d / "experiment_log.md").write_text("\n".join(md_lines), encoding="utf-8")


def _build_parameters(d: Path, results: Dict, state: Dict) -> None:
    """06_参数配置: 模型参数 + 求解配置。"""
    md_lines = ["# 重要参数配置\n"]

    # 模型参数
    modeler = results.get("modeler_agent", {})
    if not isinstance(modeler, dict):
        modeler = {}
    models = modeler.get("sub_problem_models", [])
    for model in models:
        if not isinstance(model, dict):
            continue
        name = model.get("model_name", model.get("sub_problem_name", "模型"))
        md_lines.append(f"## {name}\n")
        # 变量
        variables = model.get("decision_variables", [])
        if variables:
            md_lines.append("### 决策变量\n")
            md_lines.append("| 变量名 | 描述 | 类型 | 范围 |")
            md_lines.append("|--------|------|------|------|")
            for v in variables:
                if isinstance(v, dict):
                    md_lines.append(
                        f"| {v.get('name', '')} | {v.get('description', '')} "
                        f"| {v.get('type', '')} | {v.get('range', '')} |"
                    )
            md_lines.append("")
        # 参数
        params = model.get("parameters", [])
        if params:
            md_lines.append("### 参数\n")
            for p in params:
                if isinstance(p, dict):
                    md_lines.append(f"- **{p.get('name', '')}**: {p.get('description', '')} = {p.get('value', p.get('default', ''))}")
                else:
                    md_lines.append(f"- {p}")
            md_lines.append("")
        # 约束
        constraints = model.get("constraints", [])
        if constraints:
            md_lines.append("### 约束条件\n")
            for c in constraints:
                if isinstance(c, dict):
                    md_lines.append(f"- **{c.get('name', '')}**: {c.get('expression', '')}")
                else:
                    md_lines.append(f"- {c}")
            md_lines.append("")
        # 目标函数
        obj = model.get("objective_function", "")
        if obj:
            md_lines.append(f"### 目标函数\n\n{obj}\n")
        # 假设
        assumptions = model.get("model_assumptions", [])
        if assumptions:
            md_lines.append("### 模型假设\n")
            for a in assumptions:
                md_lines.append(f"- {a}")
            md_lines.append("")

    # 算法工程师参数
    algo = results.get("algorithm_engineer_agent", {})
    if isinstance(algo, dict) and algo:
        method = algo.get("proposed_method", {})
        if isinstance(method, dict):
            hypers = method.get("hyperparameters", [])
            if hypers:
                md_lines.append("## 算法超参数\n")
                md_lines.append("| 参数名 | 默认值 | 描述 |")
                md_lines.append("|--------|--------|------|")
                for hp in hypers:
                    if isinstance(hp, dict):
                        md_lines.append(
                            f"| {hp.get('name', '')} | {hp.get('default', '')} "
                            f"| {hp.get('description', '')} |"
                        )
                md_lines.append("")

    # 金融分析师参数
    fin = results.get("financial_analyst_agent", {})
    if isinstance(fin, dict) and fin:
        fm = fin.get("financial_model", {})
        if isinstance(fm, dict):
            params = fm.get("parameters", [])
            if params:
                md_lines.append("## 金融模型参数\n")
                md_lines.append("| 参数名 | 含义 | 估计值 |")
                md_lines.append("|--------|------|--------|")
                for p in params:
                    if isinstance(p, dict):
                        md_lines.append(
                            f"| {p.get('name', '')} | {p.get('meaning', '')} "
                            f"| {p.get('estimation', '')} |"
                        )
                md_lines.append("")

    if len(md_lines) <= 1:
        md_lines.append("本任务未记录参数配置。\n")

    (d / "parameters.md").write_text("\n".join(md_lines), encoding="utf-8")


def _build_code(d: Path, results: Dict, output_dir: Path) -> None:
    """07_代码: 源代码文件。"""
    solver = results.get("solver_agent", {})
    saved = []
    if isinstance(solver, dict):
        for sol in solver.get("sub_problem_solutions", []):
            sp_id = sol.get("sub_problem_id", "?")
            for cf in sol.get("code_files", []):
                filename = cf.get("filename", f"solver_sub{sp_id}.py")
                code = cf.get("code", "")
                if code:
                    filepath = d / filename
                    filepath.write_text(code, encoding="utf-8")
                    saved.append(filename)

    # 复制已有的代码目录
    code_src = output_dir / "code"
    if code_src.exists():
        for f in code_src.iterdir():
            if f.is_file() and f.name not in saved:
                try:
                    shutil.copy2(f, d / f.name)
                    saved.append(f.name)
                except Exception:
                    pass

    # 实验代码
    exp = results.get("experimentation_agent", {})
    if isinstance(exp, dict):
        for key in ("nas_code", "loss_function_code"):
            code = exp.get(key, "")
            if code:
                (d / f"{key}.py").write_text(code, encoding="utf-8")
                saved.append(f"{key}.py")

    if not saved:
        (d / "README.md").write_text("# 代码\n\n本任务未生成可执行代码。\n", encoding="utf-8")
    else:
        # 生成代码索引
        md = f"# 代码文件\n\n共 {len(saved)} 个文件\n\n"
        for f in sorted(saved):
            md += f"- `{f}`\n"
        (d / "INDEX.md").write_text(md, encoding="utf-8")


def _build_figures(d: Path, results: Dict, output_dir: Path) -> None:
    """08_图表: 复制已生成的图表文件。"""
    saved = []

    # 从 figure_agent 结果获取图表路径（figure_agent 返回 figure_path 键）
    figure = results.get("figure_agent", {})
    if isinstance(figure, dict):
        for fig in figure.get("figures", []):
            if isinstance(fig, dict):
                path = fig.get("figure_path", fig.get("path", fig.get("file_path", "")))
                if path and Path(path).is_file() and Path(path).exists():
                    try:
                        shutil.copy2(path, d / Path(path).name)
                        saved.append(Path(path).name)
                    except Exception:
                        pass

    # 扫描图表目录（figure_agent 保存到 output_dir/figures/ 和 output_dir/final/figures/）
    # 同时扫描 camera_ready 包内的 figures/ —— Writer 生成的 main.tex 引用的
    # 图片名（语义命名，如 correlation_heatmap.png）可能与 figure_agent 实际写出的
    # 文件名（如 city_heatmap.png）不一致；camera_ready.build 会把语义命名图复制
    # 进 camera_ready_<task>/figures/，纳入扫描才能保证交付文件夹自洽
    # （TeX 引用的每张图都能在 08_图表/ 找到，可独立重编译）。
    scan_dirs = [
        output_dir / "figures",
        output_dir / "final" / "figures",
    ]
    # 追加所有 camera_ready_<task>/figures/ 目录
    for cr_dir in output_dir.glob("camera_ready_*/figures"):
        scan_dirs.append(cr_dir)
    for fig_dir in scan_dirs:
        if fig_dir.exists():
            # 递归搜索所有子目录，支持所有常见图片格式
            for ext in ("*.png", "*.jpg", "*.jpeg", "*.svg", "*.pdf", "*.eps"):
                for f in fig_dir.rglob(ext):
                    if f.is_file() and f.name not in saved:
                        try:
                            shutil.copy2(f, d / f.name)
                            saved.append(f.name)
                        except Exception:
                            pass

    if not saved:
        (d / "README.md").write_text("# 图表\n\n本任务未生成图表文件。\n", encoding="utf-8")
    else:
        md = f"# 图表文件\n\n共 {len(saved)} 个文件\n\n"
        for f in sorted(saved):
            md += f"- ![{f}]({f})\n"
        (d / "INDEX.md").write_text(md, encoding="utf-8")


def _build_model_docs(d: Path, results: Dict, output_dir: Path) -> None:
    """09_模型文档: 数学模型定义 JSON。"""
    modeler = results.get("modeler_agent", {})
    if isinstance(modeler, dict):
        models = modeler.get("sub_problem_models", [])
        if models:
            (d / "models.json").write_text(
                json.dumps(models, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            # 可读版本
            md = "# 数学模型文档\n\n"
            for i, m in enumerate(models, 1):
                if not isinstance(m, dict):
                    continue
                md += f"## 模型 {i}: {m.get('model_name', m.get('sub_problem_name', ''))}\n\n"
                md += f"- **类型**: {m.get('model_type', '')}\n"
                md += f"- **目标函数**: {m.get('objective_function', '')}\n"
                vars_ = m.get("decision_variables", [])
                if vars_:
                    md += f"- **决策变量**: {len(vars_)} 个\n"
                constraints = m.get("constraints", [])
                if constraints:
                    md += f"- **约束条件**: {len(constraints)} 个\n"
                algo = m.get("algorithm", {})
                if isinstance(algo, dict) and algo:
                    md += f"- **算法**: {algo.get('name', '')}\n"
                md += "\n"
            (d / "models.md").write_text(md, encoding="utf-8")

    # 求解结果摘要
    solver = results.get("solver_agent", {})
    if isinstance(solver, dict):
        solutions = solver.get("sub_problem_solutions", [])
        if solutions:
            (d / "solves.json").write_text(
                json.dumps(solutions, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )

    # 复制已有的 models.json
    models_file = output_dir / "models.json"
    if models_file.exists() and not (d / "models.json").exists():
        shutil.copy2(models_file, d / "models.json")


def _build_quality_report(d: Path, results: Dict, output_dir: Path) -> None:
    """10_质量报告: 事实核查 + 同行评议 + 降级标记。"""
    md = "# 质量报告\n\n"

    # Fact Check
    fc = results.get("fact_checker", {})
    if isinstance(fc, dict) and fc:
        passed = fc.get("passed", False)
        md += f"## 事实核查: {'✅ 通过' if passed else '⚠️ 发现问题'}\n\n"
        issues = fc.get("issues", [])
        if issues:
            md += f"发现 {len(issues)} 个数值不一致:\n\n"
            for iss in issues[:10]:
                msg = iss.get("message", str(iss)) if isinstance(iss, dict) else str(iss)
                md += f"- {msg}\n"
            md += "\n"
        symbolic = fc.get("symbolic_findings", [])
        if symbolic:
            md += "### 符号审计发现\n\n"
            for f in symbolic:
                md += f"- [{f.get('severity', '')}] {f.get('message', '')}\n"
            md += "\n"
        fabrication = fc.get("fabrication_warning", "")
        if fabrication:
            md += f"### 编造检测\n\n{fabrication}\n\n"
    # 复制 fact_check_report.json
    fc_file = output_dir / "final" / "fact_check_report.json"
    if fc_file.exists():
        shutil.copy2(fc_file, d / "fact_check_report.json")

    # Peer Review
    pr = results.get("peer_review_agent", {})
    if isinstance(pr, dict) and pr:
        rec = pr.get("recommendation", "")
        score = pr.get("overall_score", 0)
        md += f"## 同行评议: {rec} (评分: {score}/5)\n\n"
        scores = pr.get("scores", {})
        if scores:
            md += "### 分项评分\n\n"
            for k, v in scores.items():
                md += f"- {k}: {v}\n"
            md += "\n"
        comments = pr.get("comments", {})
        if isinstance(comments, dict):
            major = comments.get("major", [])
            minor = comments.get("minor", [])
            if major:
                md += "### 主要意见\n\n"
                for c in major:
                    md += f"- {c}\n"
                md += "\n"
            if minor:
                md += "### 次要意见\n\n"
                for c in minor:
                    md += f"- {c}\n"
                md += "\n"

    # 降级标记
    quality = results.get("_quality_report", {})
    if isinstance(quality, dict) and quality:
        md += f"## 降级标记\n\n共 {quality.get('total_degraded', 0)} 个降级项:\n\n"
        for item in quality.get("degraded_items", []):
            md += f"- {item.get('agent', '')}: {item.get('reason', '')}\n"
        md += "\n"

    # Summary quality
    summary = results.get("task_summary", {}) or {}
    if isinstance(summary, dict):
        pq = summary.get("paper_quality", {})
        if isinstance(pq, dict):
            md += f"## 论文质量评估: {pq.get('overall_score', 0)}/100\n\n"
            chapters = pq.get("chapter_scores", {})
            if chapters:
                md += "| 章节 | 评分 |\n|------|------|\n"
                for ch, sc in chapters.items():
                    md += f"| {ch} | {sc} |\n"
                md += "\n"
            strengths = pq.get("strengths", [])
            if strengths:
                md += "### 优势\n\n"
                for s in strengths:
                    md += f"- {s}\n"
                md += "\n"
            weaknesses = pq.get("weaknesses", [])
            if weaknesses:
                md += "### 不足\n\n"
                for w in weaknesses:
                    md += f"- {w}\n"
                md += "\n"

    (d / "quality_report.md").write_text(md, encoding="utf-8")


def _build_readme(
    d: Path, results: Dict, state: Dict,
    project_name: Optional[str], task_id: str,
) -> None:
    """README.md: 总览索引。"""
    writer = results.get("writer_agent", {})
    title = writer.get("title", project_name or "论文") if isinstance(writer, dict) else (project_name or "论文")
    abstract = writer.get("abstract", "") if isinstance(writer, dict) else ""

    md = f"""# {title}

**项目**: {project_name or '未命名'}
**任务 ID**: {task_id}
**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}

## 摘要

{abstract or '无摘要'}

## 交付物目录

| 目录 | 说明 |
|------|------|
| [01_论文/](01_论文/) | 论文 LaTeX 源文件 + 元数据 |
| [02_参考文献/](02_参考文献/) | 参考文献索引 (MD) + BibTeX |
| [03_数据来源/](03_数据来源/) | 数据文件清单 + 来源说明 |
| [04_实验方案/](04_实验方案/) | 实验设计 + 研究规划 |
| [05_实验日志/](05_实验日志/) | 求解执行记录 + 时间线 |
| [06_参数配置/](06_参数配置/) | 模型参数 + 超参数配置 |
| [07_代码/](07_代码/) | 源代码文件 |
| [08_图表/](08_图表/) | 科研图表 |
| [09_模型文档/](09_模型文档/) | 数学模型定义 (JSON + MD) |
| [10_质量报告/](10_质量报告/) | 事实核查 + 同行评议 + 质量评估 |

## 关键词

{_format_keywords(writer.get('keywords', []) if isinstance(writer, dict) else [])}

## 子问题

"""
    sub_problems = state.get("sub_problems", [])
    for sp in sub_problems:
        name = sp.get("name", sp.get("description", ""))[:80]
        md += f"- {name}\n"

    md += f"""
## 系统信息

- **模板**: {state.get('paper_template', '')}
- **工作流**: {state.get('workflow_type', '')}
- **修订次数**: {state.get('revision_count', 0)}
- **生成引擎**: MathModel Multi-Agent System (LangGraph)
"""

    (d / "README.md").write_text(md, encoding="utf-8")


# ================================================================
# 工具函数
# ================================================================

def _format_keywords(keywords: Any) -> str:
    """格式化关键词为可读字符串。

    兼容两种存储形态：
    - list: ['房价预测', '长周期分析']  → '房价预测；长周期分析'
    - str:  '房价预测；长周期分析'      → 原样返回（修 historical bug:
      旧版用 ', '.join(str) 会把字符串按字符拆成 '房, 价, 预, 测, ...'）
    """
    if not keywords:
        return ""
    if isinstance(keywords, str):
        return keywords.strip()
    if isinstance(keywords, (list, tuple)):
        parts = [str(k).strip() for k in keywords if str(k).strip()]
        return "；".join(parts)
    return str(keywords)


def _safe_filename(name: str) -> str:
    """将项目名转为文件系统安全名称。"""
    # 保留中文、字母、数字、下划线、短横线
    safe = ""
    for ch in name:
        if ch.isalnum() or ch in ("_", "-", " ", "（", "）", "(", ")"):
            safe += ch
    safe = safe.strip().replace(" ", "_")
    return safe or "project"


def _latex_to_markdown(writer: Dict) -> str:
    """将 writer 产出转换为 Markdown 论文。

    Writer 只产出 latex_code，不产出 markdown_code。
    构建策略：优先用 sections 章节结构重建；缺失则从 latex 粗略转换。
    """
    import re

    sections = writer.get("sections", {})
    chapters = writer.get("chapters", [])
    latex = writer.get("latex_code", "")
    title = writer.get("title", "") or "论文"
    abstract = writer.get("abstract", "")
    keywords = writer.get("keywords", [])

    lines = [f"# {title}", ""]

    if abstract:
        lines.append("## 摘要")
        lines.append("")
        lines.append(abstract)
        lines.append("")

    if keywords:
        kw_str = "；".join(keywords) if isinstance(keywords, list) else str(keywords)
        lines.append(f"**关键词**: {kw_str}")
        lines.append("")

    # 策略 1: 从 sections dict 重建
    if sections and isinstance(sections, dict):
        for section_title, content in sections.items():
            if section_title in ("执行摘要", "摘要", "abstract"):
                continue
            clean_title = section_title.lstrip("0123456789. ").strip()
            lines.append(f"## {clean_title}")
            lines.append("")
            if isinstance(content, str):
                lines.append(content)
            elif isinstance(content, dict):
                lines.append(content.get("content", str(content)))
            else:
                lines.append(str(content))
            lines.append("")
        return "\n".join(lines)

    # 策略 2: 从 chapters list 重建
    if chapters and isinstance(chapters, list):
        for ch in chapters:
            if isinstance(ch, dict):
                ch_title = ch.get("title", ch.get("id", ""))
                clean_title = ch_title.lstrip("0123456789. ").strip()
                lines.append(f"## {clean_title}")
                lines.append("")
                ch_content = ch.get("content", "")
                lines.append(ch_content)
                lines.append("")
        return "\n".join(lines)

    # 策略 3: 从 latex 粗略转换
    if latex:
        # 去掉 documentclass/preamble，保留 body
        body_match = re.search(r"\\begin\{document\}(.*?)\\end\{document\}", latex, re.DOTALL)
        if body_match:
            body = body_match.group(1)
        else:
            body = latex

        # 基本转换: \section{...} → ## ..., \subsection{...} → ### ...
        body = re.sub(r"\\section\*?\{([^}]*)\}", r"\n## \1\n", body)
        body = re.sub(r"\\subsection\*?\{([^}]*)\}", r"\n### \1\n", body)
        body = re.sub(r"\\subsubsection\*?\{([^}]*)\}", r"\n#### \1\n", body)

        # 去掉 LaTeX 命令（保留内容）
        body = re.sub(r"\\textbf\{([^}]*)\}", r"**\1**", body)
        body = re.sub(r"\\textit\{([^}]*)\}", r"*\1*", body)
        body = re.sub(r"\\emph\{([^}]*)\}", r"*\1*", body)
        body = re.sub(r"\\texttt\{([^}]*)\}", r"`\1`", body)
        body = re.sub(r"\\begin\{itemize\}(.*?)\\end\{itemize\}", r"\1", body, flags=re.DOTALL)
        body = re.sub(r"\\begin\{enumerate\}(.*?)\\end\{enumerate\}", r"\1", body, flags=re.DOTALL)
        body = re.sub(r"\\item\s+", "- ", body)
        body = re.sub(r"\\cite\{(.*?)\}", r"[\1]", body)
        body = re.sub(r"\\ref\{(.*?)\}", r"[\1]", body)
        body = re.sub(r"\\maketitle", "", body)
        body = re.sub(r"\\begin\{abstract\}", "\n## 摘要\n", body)
        body = re.sub(r"\\end\{abstract\}", "\n", body)
        body = re.sub(r"\\begin\{keywords\}", "\n**关键词**: ", body)
        body = re.sub(r"\\end\{keywords\}", "\n", body)
        body = re.sub(r"\\begin\{table\}.*?\\end\{table\}", "[表格]", body, flags=re.DOTALL)
        body = re.sub(r"\\begin\{figure\}.*?\\end\{figure\}", "[图表]", body, flags=re.DOTALL)
        body = re.sub(r"\\includegraphics.*?\}", "[图表]", body)
        body = re.sub(r"\\label\{.*?\}", "", body)
        body = re.sub(r"\\caption\{([^}]*)\}", r"\n*\1*\n", body)
        body = re.sub(r"\\hline", "", body)
        body = re.sub(r"\\begin\{tabular\}.*?\\end\{tabular\}", "", body, flags=re.DOTALL)
        body = re.sub(r"\\centering", "", body)
        # 清理多余空行
        body = re.sub(r"\n{3,}", "\n\n", body)

        lines.append(body.strip())
        return "\n".join(lines)

    return "\n".join(lines)

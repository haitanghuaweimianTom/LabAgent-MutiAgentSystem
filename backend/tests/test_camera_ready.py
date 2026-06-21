"""backend.app.services.camera_ready 回归测试。"""
import json
import zipfile
from pathlib import Path

import pytest

from app.services.camera_ready import (
    collect_artifacts,
    build,
    build_bib,
    build_readme,
    build_references_sources,
    CameraReadyArtifact,
)


# ==================== 1. build_bib ====================

def test_build_bib_rich_entries():
    bib = build_bib([
        {"type": "article", "key": "smith2020", "title": "A Paper",
         "author": "Smith, J.", "year": "2020", "venue": "Nature", "arxiv_id": "2001.12345"},
        {"type": "inproceedings", "key": "jones2021", "title": "Another", "arxiv_id": "2101.00001"},
    ])
    assert "@article{smith2020" in bib
    assert "title={A Paper}" in bib
    assert "eprint={2001.12345}" in bib
    assert "@inproceedings{jones2021" in bib


def test_build_bib_empty():
    bib = build_bib([])
    assert "No citations available" in bib


def test_build_bib_minimal_arxiv_only():
    """仅 arxiv_id 时默认按 @article 渲染，结构仍合法。"""
    bib = build_bib([{"key": "x1", "arxiv_id": "1234.5678"}])
    assert "@article{x1" in bib
    assert "eprint={1234.5678}" in bib


def test_build_bib_ignores_non_dict():
    bib = build_bib([{"key": "ok"}, "not-a-dict", 42])
    assert "@article{ok" in bib  # default type is article
    # 不会因坏数据崩溃
    assert "ok" in bib


# ==================== 2. collect_artifacts ====================

@pytest.fixture
def sample_task_dir(tmp_path):
    """构造一个 mock 任务输出目录。"""
    final = tmp_path / "final"
    final.mkdir()
    (final / "MathModeling_Paper.tex").write_text(
        "\\documentclass{article}\n\\begin{document}\nT\\end{document}", encoding="utf-8"
    )
    (final / "chapter_summaries.json").write_text(
        '[{"title": "C1", "summary": "s1"}]', encoding="utf-8"
    )
    (final / "solution.json").write_text(
        '{"title": "My Paper", "abstract": "A", "keywords": ["k1"]}', encoding="utf-8"
    )
    fig = final / "figures"
    fig.mkdir()
    (fig / "fig1.png").write_text("png1", encoding="utf-8")
    (fig / "fig2.pdf").write_text("pdf2", encoding="utf-8")
    code = tmp_path / "code"
    code.mkdir()
    (code / "sub1.py").write_text("# sub1", encoding="utf-8")
    (code / "sub2.py").write_text("# sub2", encoding="utf-8")
    return tmp_path


def test_collect_artifacts_full(sample_task_dir):
    art = collect_artifacts("t1", sample_task_dir, template_id="math_modeling")
    assert "documentclass" in art.latex_code
    assert len(art.figures) == 2
    assert len(art.code_files) == 2
    assert art.metadata["title"] == "My Paper"
    assert len(art.chapter_summaries) == 1
    assert art.template_id == "math_modeling"


def test_collect_artifacts_no_final_dir(tmp_path):
    """没有 final/ 目录时返回空 artifact，不抛异常。"""
    art = collect_artifacts("empty", tmp_path)
    assert art.latex_code == ""
    assert art.figures == []
    assert art.code_files == []


def test_collect_artifacts_survives_bad_chapter_summaries(sample_task_dir):
    """chapter_summaries.json 损坏时不抛异常。"""
    (sample_task_dir / "final" / "chapter_summaries.json").write_text("not json", encoding="utf-8")
    art = collect_artifacts("t", sample_task_dir)
    assert art.chapter_summaries == []


# ==================== 3. build ====================

def test_build_full_zip(sample_task_dir, tmp_path):
    art = collect_artifacts("test", sample_task_dir)
    result = build("test", art, tmp_path, make_zip=True, max_zip_mb=50)
    pkg = tmp_path / "camera_ready_test"
    assert pkg.exists()
    assert (pkg / "main.tex").exists()
    assert (pkg / "main.bib").exists()
    assert (pkg / "figures" / "fig1.png").exists()
    assert (pkg / "code" / "sub1.py").exists()
    assert (pkg / "code" / "sub2.py").exists()
    assert (pkg / "README.md").exists()
    assert result.zip_path is not None
    assert result.zip_path.exists()

    # 验证 zip 内容
    with zipfile.ZipFile(result.zip_path) as zf:
        names = zf.namelist()
    assert any("main.tex" in n for n in names)
    assert any("main.bib" in n for n in names)
    assert any("README.md" in n for n in names)


def test_build_records_missing_artifacts(tmp_path):
    """空 artifact 时 skipped_reasons 记录所有缺失。"""
    art = CameraReadyArtifact(template_id="math_modeling")
    result = build("empty", art, tmp_path, make_zip=False)
    assert "missing main.tex" in result.skipped_reasons
    assert "no figures available" in result.skipped_reasons
    assert "no code files available" in result.skipped_reasons


def test_build_no_zip_when_disabled(sample_task_dir, tmp_path):
    art = collect_artifacts("t", sample_task_dir)
    result = build("t", art, tmp_path, make_zip=False)
    assert result.zip_path is None
    assert (tmp_path / "camera_ready_t" / "main.tex").exists()


def test_build_writes_code_manifest_md(sample_task_dir, tmp_path):
    art = collect_artifacts("t", sample_task_dir)
    art.code_manifest_text = "# Code Manifest\n- sub1.py\n- sub2.py"
    result = build("t", art, tmp_path, make_zip=False)
    assert (result.output_dir / "code_manifest.md").exists()
    content = (result.output_dir / "code_manifest.md").read_text(encoding="utf-8")
    assert "sub1.py" in content


# ==================== 4. README 模板化 ====================

def test_readme_includes_task_id_and_template():
    art = CameraReadyArtifact(template_id="ieee_conference", metadata={"title": "X"})
    readme = build_readme(art, "task_xyz")
    assert "**Task ID:** task_xyz" in readme
    assert "**Template:** ieee_conference" in readme
    assert "xelatex main.tex" in readme
    assert "auto-generated" in readme.lower()


def test_readme_uses_registry_documentclass():
    """README 编译说明要从 paper_templates 读 documentclass。"""
    art = CameraReadyArtifact(template_id="ieee_conference")
    readme = build_readme(art, "task_xyz")
    # IEEE 注册表 documentclass == IEEEtran
    assert "IEEEtran" in readme


def test_readme_uses_cumcm_for_math_modeling():
    art = CameraReadyArtifact(template_id="math_modeling")
    readme = build_readme(art, "task_cumcm")
    # CUMCM 注册表 documentclass == cumcmthesis
    assert "cumcmthesis" in readme


# ==================== 5. artifact summary ====================

def test_artifact_summary_counts():
    art = CameraReadyArtifact()
    s = art.summary()
    # 4 个核心字段必须存在且为 0
    assert s["figures"] == 0
    assert s["code_files"] == 0
    assert s["bib_entries"] == 0
    assert s["chapters"] == 0
    # v4.2 新增的 cls/sty 字段
    assert s.get("cls_files", 0) == 0
    assert s.get("sty_files", 0) == 0


def test_build_result_to_dict(sample_task_dir, tmp_path):
    art = collect_artifacts("t", sample_task_dir)
    result = build("t", art, tmp_path, make_zip=True)
    d = result.to_dict()
    assert "output_dir" in d
    assert "zip_path" in d
    assert "skipped_reasons" in d
    assert "artifact_summary" in d
    # v4.3: 独立交付物路径（用户可直接下载）
    assert "tex_path" in d
    assert "bib_path" in d
    assert "refs_sources_path" in d
    assert "pdf_path" in d


# ==================== 6. 参考文献来源文件 (v4.3 新增) ====================

def test_build_references_sources_with_doi_and_arxiv():
    """references_sources.txt 必须包含 DOI 和 arXiv 链接。"""
    text = build_references_sources([
        {
            "type": "article", "key": "smith2020", "title": "A Paper",
            "author": "Smith, J.", "year": "2020", "venue": "Nature",
            "doi": "10.1038/s41586-020-1234",
            "arxiv_id": "2001.12345",
        },
        {
            "type": "inproceedings", "key": "jones2021", "title": "Another",
            "url": "https://example.com/paper.pdf",
        },
    ])
    assert "[1] A Paper" in text
    assert "作者: Smith, J." in text
    assert "年份: 2020" in text
    assert "DOI: https://doi.org/10.1038/s41586-020-1234" in text
    assert "arXiv: https://arxiv.org/abs/2001.12345" in text
    assert "[2] Another" in text
    assert "URL: https://example.com/paper.pdf" in text


def test_build_references_sources_empty():
    text = build_references_sources([])
    assert "暂无引用文献" in text


def test_build_writes_references_sources_file(sample_task_dir, tmp_path):
    """build() 必须生成 references_sources.txt 文件。"""
    art = collect_artifacts("t", sample_task_dir)
    art.bib_entries = [
        {"key": "smith2020", "title": "X", "doi": "10.1/x", "arxiv_id": "2001.00001"},
    ]
    result = build("t", art, tmp_path, make_zip=False)
    refs_file = result.output_dir / "references_sources.txt"
    assert refs_file.exists()
    content = refs_file.read_text(encoding="utf-8")
    assert "参考文献来源" in content
    assert "https://doi.org/10.1/x" in content
    assert "https://arxiv.org/abs/2001.00001" in content
    # to_dict() 必须暴露路径
    d = result.to_dict()
    assert d["refs_sources_path"] is not None


def test_build_exposes_independent_paths(sample_task_dir, tmp_path):
    """build() 返回值必须包含 tex/bib/refs_sources/pdf 独立路径。"""
    art = collect_artifacts("t", sample_task_dir)
    result = build("t", art, tmp_path, make_zip=False)
    assert result.tex_path is not None
    assert result.tex_path.exists()
    assert result.bib_path is not None
    assert result.bib_path.exists()
    assert result.refs_sources_path is not None
    assert result.refs_sources_path.exists()
    # tex_path 指向 main.tex
    assert result.tex_path.name == "main.tex"
    assert result.bib_path.name == "main.bib"
    assert result.refs_sources_path.name == "references_sources.txt"


# ==================== 7. PDF 编译产物 ====================

def test_build_pdf_path_only_set_when_compilation_succeeds(sample_task_dir, tmp_path):
    """编译失败时 pdf_path 应为 None，编译成功时存在。"""
    art = collect_artifacts("t", sample_task_dir)
    result = build("t", art, tmp_path, make_zip=False)
    # 取决于测试环境是否有 latex 引擎：要么成功得到 pdf，要么失败时为 None
    if result.verification.get("success"):
        assert result.pdf_path is not None
        assert result.pdf_path.exists()
    else:
        assert result.pdf_path is None


# ==================== 8. v5.1: 多源兜底收集（latex_code + citations）====================

def test_collect_artifacts_falls_back_to_task_result_for_latex(tmp_path, monkeypatch):
    """final/ 缺 main.tex 时，必须能从 task_result.json 拿到 latex_code。

    用户反馈：之前 task_93d120fd88db 的 camera_ready 目录里压根没 main.tex。
    根因：LangGraph 路径下没保存 final/main.tex；collect_artifacts 又只信磁盘。
    修复：collect_artifacts 必须兜底到 task_result.json。
    """
    # 模拟 final/ 完全不存在
    out_dir = tmp_path / "output"
    out_dir.mkdir()
    # 不创建 final/ 目录

    # mock load_task_result 返回带 latex_code 的 writer_agent
    expected_latex = "\\documentclass{article}\n\\begin{document}Hi\\end{document}"
    expected_title = "兜底测试"

    import app.services.camera_ready as cr_module
    monkeypatch.setattr(cr_module, "load_task_result", lambda task_id: {
        "output": {
            "writer_agent": {
                "latex_code": expected_latex,
                "title": expected_title,
                "abstract": "abstract",
                "keywords": ["k1"],
            }
        }
    }) if False else None

    # 因为 import 在函数内部，用 patch mock 函数返回
    from app.core import task_persistence
    monkeypatch.setattr(task_persistence, "load_task_result", lambda task_id: {
        "task_id": task_id,
        "output": {
            "writer_agent": {
                "latex_code": expected_latex,
                "title": expected_title,
                "abstract": "abstract",
                "keywords": ["k1"],
            }
        },
    })

    art = collect_artifacts("t_fallback", out_dir, template_id="math_modeling")
    assert art.latex_code == expected_latex
    assert art.metadata["title"] == expected_title


def test_collect_artifacts_merges_citations_from_multiple_sources(tmp_path, monkeypatch):
    """citations 必须从 chapters/solution/writer_agent/paper_memory/research_agent 多源汇总。"""
    out_dir = tmp_path / "output"
    out_dir.mkdir()
    final = out_dir / "final"
    final.mkdir()
    # 放一个带 citations 的 chapter
    (final / "chapter_summaries.json").write_text(json.dumps([
        {"id": "intro", "title": "Intro", "citations": [
            {"key": "k1", "title": "From Chapter", "arxiv_id": "1111.11111"},
        ]},
    ]), encoding="utf-8")
    (final / "solution.json").write_text(json.dumps({
        "title": "T", "abstract": "A", "keywords": [],
        "citations": [
            {"key": "k2", "title": "From Solution", "doi": "10.1/k2"},
        ],
        "writer_agent": {
            "paper_memory": {
                "citations": [
                    {"key": "k3", "title": "From PaperMemory", "arxiv_id": "3333.33333"},
                ]
            },
            "citations": [
                {"key": "k2", "title": "Dup from WriterAgent", "doi": "10.1/k2"},  # 重复
            ],
        },
        "research_agent": {
            "papers": [
                {"title": "From Research", "arxiv_id": "4444.44444"},
            ],
        },
    }), encoding="utf-8")

    art = collect_artifacts("t_multi", out_dir, template_id="math_modeling")
    keys = [c["key"] for c in art.bib_entries]
    # 4 个不同来源的 citations 都该被收集
    assert "k1" in keys
    assert "k2" in keys
    assert "k3" in keys
    # k2 因 doi 重复应只出现一次
    k2_count = sum(1 for c in art.bib_entries if c.get("key") == "k2")
    assert k2_count == 1
    # research_agent 的 paper 没有 key，但 arxiv_id 唯一，应该被收集
    arxiv_ids = [c.get("arxiv_id", "") for c in art.bib_entries]
    assert "4444.44444" in arxiv_ids


def test_build_writes_main_tex_even_without_final_dir(tmp_path, monkeypatch):
    """final/ 不存在时，build() 必须能从 task_result.json 兜底写出 main.tex。"""
    out_dir = tmp_path / "output"
    out_dir.mkdir()

    expected_latex = "\\documentclass{article}\n\\begin{document}X\\end{document}"
    from app.core import task_persistence
    monkeypatch.setattr(task_persistence, "load_task_result", lambda task_id: {
        "output": {"writer_agent": {"latex_code": expected_latex, "title": "T"}},
    })

    art = collect_artifacts("t_no_final", out_dir, template_id="math_modeling")
    result = build("t_no_final", art, out_dir, make_zip=False)
    pkg_dir = result.output_dir
    assert (pkg_dir / "main.tex").exists()
    content = (pkg_dir / "main.tex").read_text(encoding="utf-8")
    assert content == expected_latex

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

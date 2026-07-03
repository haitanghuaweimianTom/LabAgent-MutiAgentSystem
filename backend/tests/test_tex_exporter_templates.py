"""src.paper.tex_exporter 整改后的回归测试（Phase 1E）。

覆盖：
1. ``__init__`` 接受 ``template_id`` 参数并解析出 documentclass/cls_file。
2. 未知 / None template_id 兜底到 math_modeling（CUMCM）。
3. CUMCM 路径保留 ``\mcmsetup`` 完整结构。
4. IEEE / NeurIPS / ACM 等通用路径使用标准 preamble（无 mcmsetup）。
5. ``export`` 写出 .tex 并尝试复制对应 cls_file。
6. ``_build_document`` 不再硬编码 mcmthesis。
"""
import sys
from pathlib import Path

import pytest

# src/ 在 backend 的父目录
SRC_DIR = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(SRC_DIR.parent))  # 让 from src.paper.tex_exporter import 生效

from src.paper.tex_exporter import MarkdownToTexConverter  # noqa: E402


# ---------- 1. 模板解析 ----------

@pytest.mark.parametrize("template_id,expected_dc,expected_cls_fragment", [
    ("math_modeling", "cumcmthesis", "mcmthesis.cls"),
    ("coursework", "article", ""),
    ("financial_analysis", "article", ""),
    ("research_survey", "article", ""),
    ("ieee_conference", "IEEEtran", "IEEEtran.cls"),
    ("neurips_2024", "neurips_2024", ""),  # neurips 用 sty_files，无 cls_file
    ("acm_sigconf", "acmart", "acmart.cls"),
    ("springer_lncs", "llncs", "llncs.cls"),
    ("nonexistent-xxx", "cumcmthesis", "mcmthesis.cls"),  # 未知 → fallback
])
def test_resolve_template(template_id, expected_dc, expected_cls_fragment, tmp_path):
    conv = MarkdownToTexConverter(
        template_dir=tmp_path,
        output_dir=tmp_path / "out",
        template_id=template_id,
    )
    assert conv.documentclass == expected_dc
    if expected_cls_fragment:
        assert expected_cls_fragment in conv.cls_file
    else:
        assert conv.cls_file == ""


def test_none_template_id_falls_back_to_math_modeling(tmp_path):
    conv = MarkdownToTexConverter(
        template_dir=tmp_path, output_dir=tmp_path / "out", template_id=None,
    )
    assert conv.documentclass == "cumcmthesis"


# ---------- 2. CUMCM 完整结构 ----------

def test_cumcm_doc_has_mcmsetup(tmp_path):
    conv = MarkdownToTexConverter(
        template_dir=tmp_path, output_dir=tmp_path / "out", template_id="math_modeling",
    )
    doc = conv._build_document("body", "T")
    assert "\\mcmsetup" in doc
    assert "palatino" in doc
    assert "CTeX = true" in doc
    assert "\\maketitle" in doc


# ---------- 3. 通用模板（IEEE / NeurIPS） ----------

@pytest.mark.parametrize("template_id", ["ieee_conference", "neurips_2024", "acm_sigconf", "springer_lncs", "coursework"])
def test_generic_template_uses_clean_preamble(template_id, tmp_path):
    conv = MarkdownToTexConverter(
        template_dir=tmp_path, output_dir=tmp_path / "out", template_id=template_id,
    )
    doc = conv._build_document("body", "T")
    assert "\\mcmsetup" not in doc  # 不是 CUMCM，不该有 \mcmsetup
    assert "geometry" in doc  # 通用分支带 geometry
    assert "\\maketitle" in doc
    # documentclass 出现在 \documentclass{X} 中
    assert f"\\documentclass{{{conv.documentclass}}}" in doc


# ---------- 4. 端到端 export ----------

def test_export_writes_tex_file(tmp_path):
    md = tmp_path / "paper.md"
    md.write_text("# T\n\nbody.\n", encoding="utf-8")
    out_dir = tmp_path / "out"
    conv = MarkdownToTexConverter(
        template_dir=tmp_path, output_dir=out_dir, template_id="math_modeling",
    )
    out_tex = conv.export(md, out_dir / "paper.tex")
    assert out_tex.exists()
    assert out_tex.read_text(encoding="utf-8").startswith("\\documentclass")


def test_export_does_not_raise_on_missing_cls(tmp_path):
    """cls_file 不存在时 export 不抛异常（仅写 .tex）。"""
    md = tmp_path / "paper.md"
    md.write_text("# T\n", encoding="utf-8")
    out_dir = tmp_path / "out"
    conv = MarkdownToTexConverter(
        template_dir=tmp_path, output_dir=out_dir, template_id="ieee_conference",
    )
    # 实际 IEEEtran.cls 不在测试 tmp_path，export 仍应完成
    out_tex = conv.export(md, out_dir / "paper.tex")
    assert out_tex.exists()


# ---------- 5. 隔离性：不影响 mcmthesis 路径 ----------

def test_legacy_mcmthesis_path_unchanged(tmp_path):
    """旧调用方式（不传 template_id）行为与原 mcmthesis 一致。"""
    conv = MarkdownToTexConverter(template_dir=tmp_path, output_dir=tmp_path / "out")
    assert conv.documentclass == "cumcmthesis"
    doc = conv._build_document("body", "T")
    assert "\\mcmsetup" in doc
    assert "CTeX = true" in doc

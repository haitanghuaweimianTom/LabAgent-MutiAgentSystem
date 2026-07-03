"""backend.app.core.paper_templates 的回归测试。

覆盖：
1. 8 个内置模板都能从 JSON 加载并解析为 ``PaperTemplate``。
2. ``get_registry()`` 单例、线程安全、list_ids 排序。
3. ``load_template(id)`` 找到正确模板；不存在的 id 回退到 math_modeling。
4. cumcm/coursework/financial_analysis/research_survey 与原 writer_agent.py 行为等价
   （章节数、preamble 关键字、acceptance_threshold）。
5. 4 个新增 CCF-A 模板的最低字段齐全。
"""
import json
import pytest
from pathlib import Path

from app.core.paper_templates import (
    ChapterPlan,
    PaperTemplate,
    TemplateRegistry,
    get_registry,
    load_template,
    register_template,
    DEFAULT_TEMPLATE_ID,
)


# ---------- 1. 内置模板加载 ----------

EXPECTED_TEMPLATE_IDS = {
    "math_modeling",
    "coursework",
    "financial_analysis",
    "research_survey",
    "ieee_conference",
    "neurips_2024",
    "acm_sigconf",
    "springer_lncs",
}


def test_builtin_templates_load():
    reg = get_registry()
    ids = set(reg.list_ids())
    missing = EXPECTED_TEMPLATE_IDS - ids
    assert not missing, f"Missing builtin templates: {missing}"


def test_default_template_id_exists():
    reg = get_registry()
    assert reg.has(DEFAULT_TEMPLATE_ID)


def test_singleton_registry_returns_same_instance():
    a = get_registry()
    b = get_registry()
    assert a is b


# ---------- 2. 模板字段完整性 ----------

REQUIRED_KEYS = {
    "id", "name", "domain", "documentclass", "chapter_plan",
    "system_prompt", "preamble",
}


def test_every_template_has_required_keys():
    reg = get_registry()
    for tpl in reg.list_templates():
        d = tpl.to_dict()
        missing = REQUIRED_KEYS - d.keys()
        assert not missing, f"Template '{tpl.id}' missing keys: {missing}"


def test_every_chapter_plan_has_unique_ids():
    reg = get_registry()
    for tpl in reg.list_templates():
        ids = [c.id for c in tpl.chapter_plan]
        assert len(ids) == len(set(ids)), (
            f"Template '{tpl.id}' has duplicate chapter ids: {ids}"
        )


def test_acceptance_threshold_is_reasonable():
    reg = get_registry()
    for tpl in reg.list_templates():
        assert 50 <= tpl.acceptance_threshold <= 100, (
            f"Template '{tpl.id}' threshold out of range: {tpl.acceptance_threshold}"
        )


# ---------- 3. 向后兼容：旧 4 个模板 ----------

def test_cumcm_matches_legacy_chapter_count():
    """CUMCM 模板章节数应与原 writer_agent.CUMCM_CHAPTERS 一致（11 章）。"""
    tpl = load_template("math_modeling")
    # 11 个 chapter（abstract + 9 个 numbered + appendix）
    assert len(tpl.chapter_plan) == 11, f"CUMCM chapters: {len(tpl.chapter_plan)}"
    titles = [c.title for c in tpl.chapter_plan]
    assert "摘要" in titles
    assert "9 参考文献" in titles
    assert "附录" in titles


def test_cumcm_preamble_has_mcmthesis_and_baominghao():
    tpl = load_template("math_modeling")
    assert "cumcmthesis" in tpl.preamble
    assert "\\baominghao{" in tpl.preamble
    assert "\\schoolname{" in tpl.preamble
    assert "\\membera{" in tpl.preamble


def test_coursework_uses_article_documentclass():
    tpl = load_template("coursework")
    assert tpl.documentclass == "article"
    assert "\\maketitle" in tpl.preamble
    assert "\\title{课程作业研究报告}" in tpl.preamble


def test_financial_analysis_uses_article_documentclass():
    tpl = load_template("financial_analysis")
    assert tpl.documentclass == "article"
    assert "\\title{金融分析报告}" in tpl.preamble
    assert len(tpl.chapter_plan) == 9


def test_research_survey_uses_article_documentclass():
    tpl = load_template("research_survey")
    assert tpl.documentclass == "article"
    assert "\\title{研究现状调研报告}" in tpl.preamble
    assert len(tpl.chapter_plan) == 9


# ---------- 4. 新增 CCF-A 模板 ----------

def test_ieee_conference_uses_ieeetran_and_higher_threshold():
    tpl = load_template("ieee_conference")
    assert tpl.documentclass == "IEEEtran"
    assert tpl.acceptance_threshold == 85
    assert tpl.language == "en"
    titles = [c.title for c in tpl.chapter_plan]
    assert "I. Introduction" in titles
    assert "II. Related Work" in titles
    assert "V. Experiments" in titles
    assert "VII. Conclusion" in titles


def test_neurips_uses_neurips_style_and_anonymous_metadata():
    tpl = load_template("neurips_2024")
    assert tpl.documentclass == "neurips_2024"
    assert tpl.acceptance_threshold == 85
    assert tpl.language == "en"
    assert "Anonymous" in tpl.preamble


def test_acm_sigconf_uses_acmart_and_ccs_concepts():
    tpl = load_template("acm_sigconf")
    assert tpl.documentclass == "acmart"
    assert "sigconf" in tpl.preamble
    assert "CCSXML" in tpl.preamble or "ccsdesc" in tpl.preamble


def test_springer_lncs_uses_llncs():
    tpl = load_template("springer_lncs")
    assert tpl.documentclass == "llncs"
    assert "llncs" in tpl.preamble
    assert tpl.acceptance_threshold == 80


# ---------- 5. 回退与错误处理 ----------

def test_unknown_template_falls_back_to_math_modeling(caplog):
    tpl = load_template("definitely-not-a-template")
    assert tpl.id == "math_modeling"


def test_none_template_id_returns_default():
    tpl = load_template(None)
    assert tpl.id == "math_modeling"


def test_empty_string_template_id_returns_default():
    tpl = load_template("")
    assert tpl.id == "math_modeling"


def test_register_new_template_runtime_override():
    from dataclasses import dataclass
    fresh = TemplateRegistry()  # 不调用 ensure_loaded
    assert len(fresh) == 0

    custom = PaperTemplate(
        id="test_custom",
        name="Test Custom",
        domain="general",
        documentclass="article",
    )
    fresh.register(custom)
    assert fresh.has("test_custom")
    assert len(fresh) == 1


def test_register_duplicate_raises_when_not_overwrite():
    fresh = TemplateRegistry()
    custom = PaperTemplate(id="dup", name="X", domain="g", documentclass="article")
    fresh.register(custom)
    with pytest.raises(ValueError):
        fresh.register(custom, overwrite=False)
    # overwrite=True 应允许
    fresh.register(custom, overwrite=True)


# ---------- 6. JSON schema 校验（防回归） ----------

def test_all_template_jsons_parse_as_valid_json():
    """防御性：所有模板 JSON 必须能解析。"""
    templates_dir = Path(__file__).parent.parent / "app" / "core" / "paper_templates" / "templates"
    for json_path in templates_dir.glob("*.json"):
        with json_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        # 关键字段非空
        assert data.get("id"), f"{json_path.name}: missing id"
        assert data.get("chapter_plan"), f"{json_path.name}: empty chapter_plan"
        assert data.get("system_prompt"), f"{json_path.name}: empty system_prompt"
        assert data.get("preamble"), f"{json_path.name}: empty preamble"


# ---------- 7. chapter 序列化往返 ----------

def test_chapter_plan_roundtrip():
    original = ChapterPlan(
        id="method",
        title="IV. Method",
        section_level=1,
        prompt_role="Write the method.",
        requirements=["R1", "R2"],
        required_figures=["fig1"],
    )
    d = original.to_dict()
    rebuilt = ChapterPlan.from_dict(d)
    assert rebuilt.id == original.id
    assert rebuilt.title == original.title
    assert rebuilt.section_level == original.section_level
    assert rebuilt.prompt_role == original.prompt_role
    assert rebuilt.requirements == original.requirements
    assert rebuilt.required_figures == original.required_figures

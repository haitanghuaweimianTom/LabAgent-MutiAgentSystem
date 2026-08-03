# backend/tests/test_presentation_template.py
"""PPT(Beamer) 模板加载与结构测试。"""
from app.core.paper_templates import load_template


def test_presentation_template_exists():
    tpl = load_template("presentation")
    assert tpl is not None
    assert tpl.documentclass == "beamer"


def test_presentation_has_compile_options():
    tpl = load_template("presentation")
    assert tpl.compile_options.get("engine") in ("xelatex", "pdflatex", "latexmk")


def test_presentation_chapter_plan_has_frames():
    tpl = load_template("presentation")
    assert len(tpl.chapter_plan) >= 6


def test_presentation_system_prompt_nonempty():
    tpl = load_template("presentation")
    assert len(tpl.system_prompt) > 200

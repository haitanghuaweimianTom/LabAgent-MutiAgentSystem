"""Tests for template_skills registry and literature verification.

- 12 个模板的 SKILL.md + references.md 都存在
- 至少 N 条真实 arxiv 引用（按模板类型）
- verify_reference 能查到真实 arxiv ID
- find_citation_in_text 检测引用
- filter_fake_references 区分真假
"""
from __future__ import annotations

import pytest


class TestSkillsRegistry:
    def test_list_12_templates(self):
        from src.knowledge.template_skills import list_template_skills
        ids = list_template_skills()
        assert len(ids) == 12, f"expected 12 templates, got {len(ids)}: {ids}"
        # 用户提的 8 个核心模板
        for required in ["math_modeling", "neurips_2024", "acm_sigconf",
                          "ieee_conference", "springer_lncs", "research_survey",
                          "coursework", "financial_analysis"]:
            assert required in ids, f"missing {required}"

    def test_get_skill_returns_non_empty(self):
        from src.knowledge.template_skills import get_template_skill
        for tpl_id in ["math_modeling", "neurips_2024"]:
            skill = get_template_skill(tpl_id)
            assert skill is not None, f"{tpl_id} skill not loaded"
            assert len(skill.skill_md) > 1000, f"{tpl_id} SKILL.md too short"
            assert len(skill.references_md) > 200, f"{tpl_id} references.md too short"

    def test_skill_has_real_references(self):
        from src.knowledge.template_skills import get_real_references
        for tpl_id in ["math_modeling", "neurips_2024", "iclr_2024"]:
            refs = get_real_references(tpl_id)
            assert len(refs) >= 5, f"{tpl_id} has only {len(refs)} refs"

    def test_skill_has_checklist(self):
        from src.knowledge.template_skills import get_checklist
        for tpl_id in ["math_modeling", "neurips_2024"]:
            cl = get_checklist(tpl_id)
            assert len(cl) >= 3, f"{tpl_id} checklist has only {len(cl)} items"

    def test_total_references_count(self):
        from src.knowledge.template_skills import get_real_references, list_template_skills
        total = sum(len(get_real_references(t)) for t in list_template_skills())
        # 12 模板 × 平均 7 篇 = 84+ 预期
        assert total >= 80, f"only {total} total real refs, expected ≥80"


class TestLiteratureVerifier:
    @pytest.mark.parametrize("arxiv_id,expected_substr", [
        ("2401.00029", "6D-Diff"),  # CVPR 2024
        ("2401.02116", "Starling"),  # SIGMOD 2024
    ])
    def test_verify_reference_real(self, arxiv_id, expected_substr):
        from src.knowledge.template_skills import verify_reference
        info = verify_reference(arxiv_id)
        if info is None:  # 网络问题，跳过
            pytest.skip(f"network failed for {arxiv_id}")
        assert info["title"]
        assert expected_substr.lower() in info["title"].lower(), \
            f"{arxiv_id} title '{info['title']}' doesn't contain '{expected_substr}'"

    def test_verify_reference_fake(self):
        from src.knowledge.template_skills import verify_reference
        info = verify_reference("9999.99999")
        assert info is None, "fake arxiv id should return None"

    def test_find_citation_in_text(self):
        from src.knowledge.template_skills import find_citation_in_text
        text = "We compare with Starling [2401.02116] and prior work arXiv:2401.00029."
        assert find_citation_in_text(text, "2401.02116")
        assert find_citation_in_text(text, "2401.00029")
        assert not find_citation_in_text(text, "1234.56789")

    def test_filter_fake_references(self):
        from src.knowledge.template_skills import filter_fake_references, get_real_references
        real_pool = get_real_references("neurips_2024")
        # 构造混合文本：1 真 1 假
        text = f"Compare with [{real_pool[0]}] and [9999.99999]."
        results = filter_fake_references(text, real_pool)
        assert len(results) == 2
        real_count = sum(1 for r in results if r["is_real"])
        assert real_count >= 1

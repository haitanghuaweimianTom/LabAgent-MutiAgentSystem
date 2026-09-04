"""Tests for issue_signature.py - problem signature & dedup."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from issue_signature import (
    build_issue_key,
    normalize_synonyms,
    normalize_text,
    ALLOWED_CATEGORIES,
)


class TestNormalizeSynonyms:
    def test_english_lowercased(self):
        assert normalize_synonyms("TIMEOUT OCCURRED") == "timeout occurred"

    def test_chinese_timeout_maps_to_canonical(self):
        assert "timeout" in normalize_synonyms("运行超时导致失败")

    def test_mixed_language(self):
        assert "timeout" in normalize_synonyms("the task 超时 during run")

    def test_citation_cross_language_same_target(self):
        a = normalize_synonyms("虚假参考文献是被拒绝的原因")
        b = normalize_synonyms("hallucinated reference is the reason for rejection")
        # 两者都应规范化为含 canonical token "citation"
        assert "citation" in a
        assert "citation" in b


class TestNormalizeText:
    def test_strips_iteration_numbers(self):
        assert normalize_text("iteration 3 failed") == normalize_text("iteration 7 failed")

    def test_strips_numbers_and_units(self):
        assert normalize_text("took 30min") == normalize_text("took 75%")
        assert normalize_text("n=5") == normalize_text("n=12")

    def test_strips_punctuation(self):
        assert normalize_text("hello, world") == normalize_text("hello world")


class TestBuildIssueKey:
    def test_same_meaning_same_key(self):
        k1 = build_issue_key("运行超时 60 秒导致失败", "system")
        k2 = build_issue_key("timeout exceeded caused failure", "system")
        assert k1 == k2

    def test_token_order_insensitive(self):
        k1 = build_issue_key("missing ablation study", "experiment")
        k2 = build_issue_key("ablation study missing", "experiment")
        assert k1 == k2

    def test_category_differentiates(self):
        k1 = build_issue_key("code crashed", "experiment")
        k2 = build_issue_key("code crashed", "system")
        assert k1 != k2

    def test_different_meaning_different_key(self):
        k1 = build_issue_key("graph too crowded", "writing")
        k2 = build_issue_key("algorithm too slow", "writing")
        assert k1 != k2

    def test_returns_category_preview_hash(self):
        key = build_issue_key("syntax error in model.py", "experiment")
        parts = key.split(":")
        assert len(parts) == 3
        assert parts[0] == "experiment"
        assert parts[1] != ""
        assert len(parts[2]) == 12  # sha1[:12]

    def test_allowed_categories(self):
        assert "experiment" in ALLOWED_CATEGORIES
        assert "system" in ALLOWED_CATEGORIES
        assert "efficiency" in ALLOWED_CATEGORIES
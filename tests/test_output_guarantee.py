"""Tests for output_guarantee module."""
import tempfile
from pathlib import Path
from scripts.output_guarantee import LaTeXFormatter, ReferenceVerifier, IdeaDeduplicator, OutputGuarantee


class TestLaTeXFormatter:
    def test_escape_special_chars(self):
        text = "Hello & World % Test"
        escaped = LaTeXFormatter.escape_text(text)
        assert r"\&" in escaped
        assert r"\%" in escaped

    def test_preserve_math_mode(self):
        text = "The value is $x^2$ and more text"
        escaped = LaTeXFormatter.escape_text(text)
        assert "$x^2$" in escaped

    def test_ensure_math_mode(self):
        text = "Time complexity is O(n log n)"
        result = LaTeXFormatter.ensure_math_mode(text)
        assert "$O(n log n)$" in result

    def test_validate_latex_valid(self):
        tex = r"\begin{document} Hello \end{document}"
        result = LaTeXFormatter.validate_latex(tex)
        assert result["valid"] is True

    def test_validate_latex_missing_begin(self):
        tex = r"Hello \end{document}"
        result = LaTeXFormatter.validate_latex(tex)
        assert result["valid"] is False
        assert any("begin{document}" in e for e in result["errors"])

    def test_validate_latex_unclosed_math(self):
        tex = r"\begin{document} $x \end{document}"
        result = LaTeXFormatter.validate_latex(tex)
        assert result["valid"] is False
        assert any("数学模式" in e for e in result["errors"])

    def test_format_bibliography(self):
        refs = [
            {"arxiv_id": "2401.00001", "title": "Test Paper", "authors": ["Author A"], "year": "2024"},
            {"arxiv_id": "2401.00002", "title": "Another Paper", "authors": ["Author B", "Author C"], "year": "2024"},
        ]
        bib = LaTeXFormatter.format_bibliography(refs)
        assert r"\begin{thebibliography}" in bib
        assert r"\end{thebibliography}" in bib
        assert r"\bibitem{2401.00001}" in bib
        assert r"\bibitem{2401.00002}" in bib


class TestReferenceVerifier:
    def test_verify_arxiv_real(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            verifier = ReferenceVerifier(Path(tmpdir))
            result = verifier.verify_arxiv("2401.00029")
            assert result["is_real"] is True
            assert result["title"] is not None

    def test_verify_arxiv_fake(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            verifier = ReferenceVerifier(Path(tmpdir))
            result = verifier.verify_arxiv("9999.99999")
            assert result["is_real"] is False

    def test_check_citation_in_text(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            verifier = ReferenceVerifier(Path(tmpdir))
            text = "We refer to arXiv:2401.00029 for details."
            assert verifier.check_citation_in_text(text, "2401.00029") is True
            assert verifier.check_citation_in_text(text, "2401.99999") is False

    def test_deduplicate_references(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            verifier = ReferenceVerifier(Path(tmpdir))
            refs = [
                {"arxiv_id": "2401.00001", "title": "Paper 1"},
                {"arxiv_id": "2401.00002", "title": "Paper 2"},
                {"arxiv_id": "2401.00001", "title": "Paper 1 Duplicate"},
            ]
            unique = verifier.deduplicate_references(refs)
            assert len(unique) == 2


class TestIdeaDeduplicator:
    def test_check_duplicate_exact(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dedup = IdeaDeduplicator(Path(tmpdir))
            # 记录一个 idea
            dedup.record_idea("Optimal path planning for logistics", "test_project")
            # 检查相同 idea
            result = dedup.check_duplicate("Optimal path planning for logistics")
            assert result["is_duplicate"] is True
            assert result["max_similarity"] == 1.0

    def test_check_duplicate_similar(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dedup = IdeaDeduplicator(Path(tmpdir))
            dedup.record_idea("Optimal path planning for logistics network", "test_project")
            result = dedup.check_duplicate("Optimal path planning for logistics system")
            # 相似度应该很高
            assert result["max_similarity"] > 0.5

    def test_check_duplicate_unique(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dedup = IdeaDeduplicator(Path(tmpdir))
            dedup.record_idea("Optimal path planning for logistics", "test_project")
            result = dedup.check_duplicate("Deep learning for image classification")
            assert result["is_duplicate"] is False

    def test_record_and_get_all(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dedup = IdeaDeduplicator(Path(tmpdir))
            dedup.record_idea("Idea 1", "project1")
            dedup.record_idea("Idea 2", "project2")
            all_ideas = dedup.get_all_ideas()
            assert len(all_ideas) == 2


class TestOutputGuarantee:
    def test_guarantee_output_pass(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            guarantee = OutputGuarantee(Path(tmpdir))
            
            tex = r"\begin{document} Hello World \end{document}"
            paper_md = "# Test Paper\n\nReference: arXiv:2401.00029"
            references = [{"arxiv_id": "2401.00029", "title": "Test Paper"}]
            real_pool = ["2401.00029"]
            idea = "Test research idea"
            project_name = "test_project"
            
            result = guarantee.guarantee_output(
                tex, paper_md, references, real_pool, idea, project_name
            )
            
            assert result["format_valid"] is True
            assert result["reference_valid"] is True
            assert result["idea_unique"] is True
            assert result["overall_pass"] is True

    def test_guarantee_output_fail_format(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            guarantee = OutputGuarantee(Path(tmpdir))
            
            tex = r"Hello World \end{document}"  # 缺少 \begin{document}
            paper_md = "# Test Paper"
            references = []
            real_pool = []
            idea = "Test research idea"
            project_name = "test_project"
            
            result = guarantee.guarantee_output(
                tex, paper_md, references, real_pool, idea, project_name
            )
            
            assert result["format_valid"] is False
            assert result["overall_pass"] is False

"""Tests for EntityExtractor (kg_extractor)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from app.services.kg_extractor import EntityExtractor


class TestEntityExtractorInit:
    def test_default_init(self):
        ext = EntityExtractor()
        assert ext.call_llm is None

    def test_init_with_llm(self):
        def fake_llm(prompt, sys_prompt):
            return '{"nodes": [], "relationships": []}'
        ext = EntityExtractor(call_llm=fake_llm)
        assert ext.call_llm is not None


class TestExtract:
    def test_empty_content(self):
        ext = EntityExtractor()
        result = ext.extract("")
        assert result == {"nodes": [], "relationships": []}

    def test_none_content(self):
        ext = EntityExtractor()
        result = ext.extract(None)
        assert result == {"nodes": [], "relationships": []}

    def test_whitespace_only(self):
        ext = EntityExtractor()
        result = ext.extract("   \n\t  ")
        assert result == {"nodes": [], "relationships": []}

    def test_uses_llm_when_available(self):
        calls = []

        def mock_llm(prompt, sys_prompt):
            calls.append((prompt, sys_prompt))
            return '{"nodes": [{"label": "Paper", "properties": {"id": "p1", "title": "Test"}}], "relationships": []}'

        ext = EntityExtractor(call_llm=mock_llm)
        result = ext.extract("Some paper content")

        assert len(calls) == 1
        assert "Some paper content" in calls[0][0]
        assert len(result["nodes"]) == 1
        assert result["nodes"][0]["label"] == "Paper"

    def test_falls_back_to_rules_on_llm_error(self):
        def bad_llm(prompt, sys_prompt):
            raise RuntimeError("LLM unavailable")

        ext = EntityExtractor(call_llm=bad_llm)
        result = ext.extract("This paper proposes a new method for classification.")
        assert "nodes" in result
        assert isinstance(result["nodes"], list)

    def test_truncation(self):
        def mock_llm(prompt, sys_prompt):
            assert len(prompt) < 500
            return '{"nodes": [], "relationships": []}'

        ext = EntityExtractor(call_llm=mock_llm)
        ext.extract("A" * 10000, max_chars=200)


class TestParseLLMResponse:
    def test_valid_json(self):
        ext = EntityExtractor()
        response = '{"nodes": [{"label": "Paper", "properties": {"id": "p1", "title": "T"}}], "relationships": []}'
        result = ext._parse_llm_response(response)
        assert len(result["nodes"]) == 1
        assert result["nodes"][0]["label"] == "Paper"

    def test_json_in_markdown_block(self):
        ext = EntityExtractor()
        response = '```json\n{"nodes": [{"label": "Method", "properties": {"id": "m1", "name": "X"}}], "relationships": []}\n```'
        result = ext._parse_llm_response(response)
        assert len(result["nodes"]) == 1

    def test_empty_response(self):
        ext = EntityExtractor()
        result = ext._parse_llm_response("")
        assert result == {"nodes": [], "relationships": []}

    def test_none_response(self):
        ext = EntityExtractor()
        result = ext._parse_llm_response(None)
        assert result == {"nodes": [], "relationships": []}

    def test_invalid_json(self):
        ext = EntityExtractor()
        result = ext._parse_llm_response("not json at all")
        assert result == {"nodes": [], "relationships": []}

    def test_missing_keys_filtered(self):
        ext = EntityExtractor()
        response = '{"nodes": [{"label": "Paper"}], "relationships": [{"from_label": "A", "from_id": "1"}]}'
        result = ext._parse_llm_response(response)
        assert len(result["nodes"]) == 0
        assert len(result["relationships"]) == 0

    def test_mixed_valid_invalid(self):
        ext = EntityExtractor()
        response = '{"nodes": [{"label": "Paper", "properties": {"id": "p1"}}, {"bad": "node"}], "relationships": []}'
        result = ext._parse_llm_response(response)
        assert len(result["nodes"]) == 1


class TestRuleBasedExtract:
    def test_extracts_title(self):
        ext = EntityExtractor()
        result = ext._rule_based_extract("Title: My Great Paper About AI")
        paper_nodes = [n for n in result["nodes"] if n["label"] == "Paper"]
        assert len(paper_nodes) >= 1
        assert "My Great Paper About AI" in paper_nodes[0]["properties"]["title"]

    def test_extracts_method(self):
        ext = EntityExtractor()
        result = ext._rule_based_extract("We propose a novel transformer architecture for NLP tasks.")
        method_nodes = [n for n in result["nodes"] if n["label"] == "Method"]
        assert len(method_nodes) >= 1

    def test_extracts_dataset(self):
        ext = EntityExtractor()
        result = ext._rule_based_extract("We evaluate on the ImageNet dataset.")
        dataset_nodes = [n for n in result["nodes"] if n["label"] == "Dataset"]
        assert len(dataset_nodes) >= 1

    def test_extracts_metrics(self):
        ext = EntityExtractor()
        result = ext._rule_based_extract("Achieved 95% accuracy and 0.92 f1-score.")
        metric_nodes = [n for n in result["nodes"] if n["label"] == "Metric"]
        assert len(metric_nodes) >= 1

    def test_relationships_created(self):
        ext = EntityExtractor()
        result = ext._rule_based_extract(
            "Title: Test Paper\nWe propose a new method. Evaluated on ImageNet dataset using accuracy."
        )
        assert len(result["relationships"]) >= 1


class TestBatchExtract:
    def test_batch_empty(self):
        ext = EntityExtractor()
        result = ext.batch_extract([])
        assert result == []

    def test_batch_single(self):
        ext = EntityExtractor()
        result = ext.batch_extract(["Some content"])
        assert len(result) == 1
        assert "nodes" in result[0]

    def test_batch_multiple(self):
        ext = EntityExtractor()
        contents = ["Paper one", "Paper two", "Paper three"]
        result = ext.batch_extract(contents, batch_size=2)
        assert len(result) == 3

    def test_batch_with_llm(self):
        call_count = [0]

        def mock_llm(prompt, sys_prompt):
            call_count[0] += 1
            return '{"nodes": [{"label": "Paper", "properties": {"id": "p1"}}], "relationships": []}'

        ext = EntityExtractor(call_llm=mock_llm)
        result = ext.batch_extract(["a", "b", "c"], batch_size=2)
        assert call_count[0] == 3
        assert len(result) == 3

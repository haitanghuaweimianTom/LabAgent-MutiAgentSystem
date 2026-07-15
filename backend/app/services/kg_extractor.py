"""
EntityExtractor: LLM-based entity and relationship extraction for knowledge graph construction.
"""
import json
import re
from typing import Dict, List, Optional, Callable, Any


EXTRACTION_PROMPT = """Extract entities and relationships from the following academic paper content.
Return a JSON object with exactly this structure:
{{
  "nodes": [{{"label": "NodeType", "properties": {{"id": "unique_id", "name": "..."}}}}],
  "relationships": [{{"from_label": "NodeType", "from_id": "id", "to_label": "NodeType", "to_id": "id", "type": "RELATIONSHIP_TYPE"}}]
}}

Node types: Paper, Method, Algorithm, Dataset, Metric, ProblemType, Benchmark, Author, Institution, CodeRepo
Relationship types: USES, PROPOSED_BY, EVALUATED_ON, OUTPERFORMS, IMPLEMENTS, AFFILIATED_WITH, CITES, BENCHMARK_FOR, SOLVES, PUBLISHED_AT, HAS_AUTHOR, HAS_CODE

Content:
{content}

Return ONLY valid JSON, no other text."""

SYSTEM_PROMPT = "You are an expert at extracting structured information from academic papers. Output only valid JSON."


class EntityExtractor:
    """Extracts entities and relationships from paper content using LLM or rule-based fallback."""

    def __init__(self, call_llm: Optional[Callable[[str, str], str]] = None):
        """
        Args:
            call_llm: Optional callback(prompt, system_prompt) -> str that calls an LLM.
                      If None, rule-based extraction is used.
        """
        self.call_llm = call_llm

    def extract(self, content: str, max_chars: int = 8000) -> Dict:
        """Extract entities and relationships from paper content.

        Args:
            content: Raw text content from a paper.
            max_chars: Maximum characters to send to LLM.

        Returns:
            Dict with 'nodes' and 'relationships' keys.
        """
        if not content or not content.strip():
            return {"nodes": [], "relationships": []}

        truncated = content[:max_chars]

        if self.call_llm:
            try:
                prompt = EXTRACTION_PROMPT.format(content=truncated)
                response = self.call_llm(prompt, SYSTEM_PROMPT)
                return self._parse_llm_response(response)
            except Exception:
                pass

        return self._rule_based_extract(truncated)

    def _parse_llm_response(self, response: str) -> Dict:
        """Parse LLM JSON output into structured extraction result.

        Args:
            response: Raw string output from the LLM.

        Returns:
            Parsed dict with 'nodes' and 'relationships'.
        """
        if not response:
            return {"nodes": [], "relationships": []}

        text = response.strip()

        json_match = re.search(r"\{[\s\S]*\}", text)
        if not json_match:
            return {"nodes": [], "relationships": []}

        try:
            data = json.loads(json_match.group())
        except json.JSONDecodeError:
            return {"nodes": [], "relationships": []}

        nodes = data.get("nodes", [])
        relationships = data.get("relationships", [])

        validated_nodes = []
        for node in nodes:
            if isinstance(node, dict) and "label" in node and "properties" in node:
                validated_nodes.append(node)

        validated_rels = []
        for rel in relationships:
            if isinstance(rel, dict) and all(k in rel for k in ("from_label", "from_id", "to_label", "to_id", "type")):
                validated_rels.append(rel)

        return {"nodes": validated_nodes, "relationships": validated_rels}

    def _rule_based_extract(self, content: str) -> Dict:
        """Extract entities using regex-based heuristics (fallback when no LLM).

        Args:
            content: Truncated paper text.

        Returns:
            Dict with 'nodes' and 'relationships'.
        """
        nodes = []
        relationships = []

        title_match = re.search(r"(?:title|paper)[:\s]+(.+)", content, re.IGNORECASE)
        if title_match:
            title = title_match.group(1).strip()[:200]
            nodes.append({
                "label": "Paper",
                "properties": {"id": "p1", "title": title, "name": title}
            })

        method_patterns = [
            r"(?:propose|introduce|present|develop)\s+(?:a\s+|an\s+|the\s+)?([\w\s-]+?)(?:\s+(?:for|to|that|which|method|model|framework|approach))",
            r"(?:method|model|framework|approach)\s+(?:called|named|termed)\s+[\"']?([\w\s-]+)[\"']?",
        ]
        method_id = 1
        for pattern in method_patterns:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                method_name = match.group(1).strip()[:100]
                if len(method_name) > 3 and not any(n["properties"]["name"] == method_name for n in nodes if n["label"] == "Method"):
                    nodes.append({
                        "label": "Method",
                        "properties": {"id": f"m{method_id}", "name": method_name}
                    })
                    if nodes[0]["label"] == "Paper":
                        relationships.append({
                            "from_label": "Paper",
                            "from_id": "p1",
                            "to_label": "Method",
                            "to_id": f"m{method_id}",
                            "type": "PROPOSES"
                        })
                    method_id += 1

        dataset_pattern = r"(?:on|using|from|dataset)\s+[\"']?([\w\s\-]+?)[\"']?\s*(?:dataset|benchmark|corpus|collection)"
        for match in re.finditer(dataset_pattern, content, re.IGNORECASE):
            ds_name = match.group(1).strip()[:100]
            if len(ds_name) > 2:
                ds_id = f"d{len([n for n in nodes if n['label'] == 'Dataset']) + 1}"
                nodes.append({
                    "label": "Dataset",
                    "properties": {"id": ds_id, "name": ds_name}
                })
                if nodes[0]["label"] == "Paper":
                    relationships.append({
                        "from_label": "Paper",
                        "from_id": "p1",
                        "to_label": "Dataset",
                        "to_id": ds_id,
                        "type": "EVALUATED_ON"
                    })

        metric_pattern = r"(?:accuracy|f1[- ]?score|precision|recall|bleu|rouge|auc|rmse|mae|mse|accuracy@k|hit@k|mrr|ndcg)"
        for match in re.finditer(metric_pattern, content, re.IGNORECASE):
            metric_name = match.group(0).strip()
            metric_id = f"mt{len([n for n in nodes if n['label'] == 'Metric']) + 1}"
            if not any(n["properties"]["name"].lower() == metric_name.lower() for n in nodes if n["label"] == "Metric"):
                nodes.append({
                    "label": "Metric",
                    "properties": {"id": metric_id, "name": metric_name}
                })
                if nodes[0]["label"] == "Paper":
                    relationships.append({
                        "from_label": "Paper",
                        "from_id": "p1",
                        "to_label": "Metric",
                        "to_id": metric_id,
                        "type": "EVALUATED_ON"
                    })

        return {"nodes": nodes, "relationships": relationships}

    def batch_extract(self, contents: List[str], batch_size: int = 5) -> List[Dict]:
        """Extract entities from multiple paper contents.

        Args:
            contents: List of paper text content strings.
            batch_size: Number of papers to process per batch (for future optimization).

        Returns:
            List of extraction result dicts.
        """
        results = []
        for i in range(0, len(contents), batch_size):
            batch = contents[i:i + batch_size]
            for content in batch:
                results.append(self.extract(content))
        return results

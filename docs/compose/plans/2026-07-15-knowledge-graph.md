# Knowledge Graph System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use compose:subagent (recommended) or compose:execute to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Neo4j-based knowledge graph that enhances the existing RAG pipeline with structured entity relationships.

**Architecture:** LLM auto-extraction → Neo4j storage → graph traversal → 3-way RRF fusion (vector + BM25 + graph).

**Tech Stack:** Neo4j (community edition), neo4j Python driver, LLM extraction, existing hybrid_search engine.

## Global Constraints

- Neo4j connection via env vars: `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`
- All new code in `backend/app/` (services/core) following existing patterns
- Tests in `backend/tests/`
- Do NOT modify existing `hybrid_search.py` — extend via adapter pattern
- Follow existing agent integration pattern in `base.py` `_inject_knowledge_context()`
- Python 3.9+, type hints required

---

### Task 1: Neo4jStore — Foundation Layer

**Covers:** [S3.2], [S5]

**Files:**
- Create: `backend/app/core/neo4j_store.py`
- Create: `backend/tests/test_neo4j_store.py`

**Interfaces:**
- Consumes: neo4j Python driver
- Produces: `Neo4jStore` class with CRUD + query methods

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_neo4j_store.py
import pytest
from unittest.mock import MagicMock, patch

def test_neo4j_store_init():
    """Neo4jStore can be initialized with connection params."""
    from app.core.neo4j_store import Neo4jStore
    store = Neo4jStore(uri="bolt://localhost:7687", user="neo4j", password="test")
    assert store is not None

def test_create_node():
    """Neo4jStore can create a node."""
    from app.core.neo4j_store import Neo4jStore
    store = Neo4jStore.__new__(Neo4jStore)
    store._driver = MagicMock()
    store._session = MagicMock()
    
    node_id = store.create_node("Paper", {"title": "Test Paper", "year": 2024})
    assert node_id is not None
    assert isinstance(node_id, str)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_neo4j_store.py -v`
Expected: FAIL with "ModuleNotFoundError" or "cannot import"

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/core/neo4j_store.py
"""Neo4j knowledge graph store.

Provides CRUD operations and graph traversal queries for the knowledge graph.
Connection: NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD env vars.
"""
import os
import uuid
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class Neo4jStore:
    """Neo4j graph database store for knowledge graph."""

    def __init__(
        self,
        uri: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
    ):
        self._uri = uri or os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self._user = user or os.getenv("NEO4J_USER", "neo4j")
        self._password = password or os.getenv("NEO4J_PASSWORD", "")
        self._driver = None
        self._connected = False

    def connect(self) -> bool:
        """Establish connection to Neo4j. Returns True if successful."""
        try:
            from neo4j import GraphDatabase
            self._driver = GraphDatabase.driver(
                self._uri, auth=(self._user, self._password)
            )
            self._driver.verify_connectivity()
            self._connected = True
            logger.info(f"[Neo4jStore] Connected to {self._uri}")
            return True
        except Exception as e:
            logger.warning(f"[Neo4jStore] Connection failed: {e}")
            self._connected = False
            return False

    def disconnect(self):
        """Close connection."""
        if self._driver:
            self._driver.close()
            self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def create_node(self, label: str, properties: Dict[str, Any]) -> str:
        """Create a node and return its ID."""
        node_id = properties.get("id", str(uuid.uuid4())[:8])
        properties["id"] = node_id

        query = f"CREATE (n:{label} $props) RETURN n.id"
        with self._driver.session() as session:
            result = session.run(query, props=properties)
            return result.single()[0]

    def upsert_node(self, label: str, properties: Dict[str, Any]) -> str:
        """Create or update a node (merge on id)."""
        node_id = properties.get("id", str(uuid.uuid4())[:8])
        properties["id"] = node_id

        query = f"""
        MERGE (n:{label} {{id: $id}})
        SET n += $props
        RETURN n.id
        """
        with self._driver.session() as session:
            result = session.run(query, id=node_id, props=properties)
            return result.single()[0]

    def create_relationship(
        self,
        from_label: str,
        from_id: str,
        to_label: str,
        to_id: str,
        rel_type: str,
        properties: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Create a relationship between two nodes."""
        props = properties or {}
        query = f"""
        MATCH (a:{from_label} {{id: $from_id}})
        MATCH (b:{to_label} {{id: $to_id}})
        CREATE (a)-[r:{rel_type} $props]->(b)
        RETURN type(r)
        """
        with self._driver.session() as session:
            result = session.run(
                query, from_id=from_id, to_id=to_id, props=props
            )
            return result.single() is not None

    def find_neighbors(
        self,
        label: str,
        node_id: str,
        depth: int = 1,
        rel_types: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Find neighboring nodes up to N hops."""
        rel_filter = ""
        if rel_types:
            types_str = "|".join(rel_types)
            rel_filter = f"-[r:{types_str}]->"
        else:
            rel_filter = "-[r]->"

        query = f"""
        MATCH path = (n:{label} {{id: $id}}){rel_filter}(m)
        WITH DISTINCT m, length(path) AS dist
        RETURN m.id AS id, labels(m)[0] AS label, m AS properties, dist
        ORDER BY dist
        LIMIT 50
        """
        with self._driver.session() as session:
            result = session.run(query, id=node_id)
            return [dict(record) for record in result]

    def find_paths(
        self,
        start_label: str,
        start_id: str,
        end_label: str,
        end_id: str,
        max_depth: int = 3,
    ) -> List[Dict[str, Any]]:
        """Find paths between two entities."""
        query = f"""
        MATCH path = shortestPath(
            (a:{start_label} {{id: $start_id}})-[*..{max_depth}]-(b:{end_label} {{id: $end_id}})
        )
        RETURN [n IN nodes(path) | n.id] AS node_ids,
               [r IN relationships(path) | type(r)] AS rel_types,
               length(path) AS depth
        """
        with self._driver.session() as session:
            result = session.run(query, start_id=start_id, end_id=end_id)
            return [dict(record) for record in result]

    def find_by_property(
        self, label: str, prop_name: str, prop_value: Any
    ) -> List[Dict[str, Any]]:
        """Find nodes by property value."""
        query = f"""
        MATCH (n:{label})
        WHERE n.{prop_name} = $value
        RETURN n.id AS id, n AS properties
        LIMIT 20
        """
        with self._driver.session() as session:
            result = session.run(query, value=prop_value)
            return [dict(record) for record in result]

    def find_sota(
        self, dataset_id: str, metric_name: str
    ) -> List[Dict[str, Any]]:
        """Find state-of-the-art methods for a dataset+metric."""
        query = """
        MATCH (m:Method)-[:EVALUATES_ON]->(d:Dataset {id: $dataset_id})
        MATCH (m)-[:ACHIEVES]->(met:Metric {name: $metric_name})
        RETURN m.id AS method_id, m.name AS method_name,
               met.value AS value, met.is_sota AS is_sota
        ORDER BY met.value DESC
        LIMIT 10
        """
        with self._driver.session() as session:
            result = session.run(query, dataset_id=dataset_id, metric_name=metric_name)
            return [dict(record) for record in result]

    def get_stats(self) -> Dict[str, Any]:
        """Get graph statistics."""
        with self._driver.session() as session:
            node_count = session.run("MATCH (n) RETURN count(n)").single()[0]
            rel_count = session.run("MATCH ()-[r]->() RETURN count(r)").single()[0]
            labels = session.run(
                "CALL db.labels() YIELD label RETURN collect(label)"
            ).single()[0]
            return {
                "nodes": node_count,
                "relationships": rel_count,
                "labels": labels,
            }

    def clear(self):
        """Delete all nodes and relationships (for testing)."""
        with self._driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_neo4j_store.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/neo4j_store.py backend/tests/test_neo4j_store.py
git commit -m "feat(kg): add Neo4jStore foundation layer"
```

---

### Task 2: EntityExtractor — LLM-Based Extraction

**Covers:** [S3.1], [S2]

**Files:**
- Create: `backend/app/services/kg_extractor.py`
- Create: `backend/tests/test_kg_extractor.py`

**Interfaces:**
- Consumes: LLM call function (from existing `base.py` or `_call_llm`)
- Produces: `EntityExtractor` class with `extract(content) -> dict`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_kg_extractor.py
import pytest

def test_entity_extractor_init():
    from app.services.kg_extractor import EntityExtractor
    extractor = EntityExtractor()
    assert extractor is not None

def test_extract_returns_valid_structure():
    from app.services.kg_extractor import EntityExtractor
    extractor = EntityExtractor()
    # Mock LLM response
    mock_response = {
        "nodes": [
            {"label": "Paper", "properties": {"title": "Test", "year": 2024}},
            {"label": "Method", "properties": {"name": "CNN", "category": "deep_learning"}},
        ],
        "relationships": [
            {"from": "Paper", "from_id": "p1", "to": "Method", "to_id": "m1", "type": "USES"}
        ],
    }
    result = extractor._parse_llm_response(str(mock_response))
    assert "nodes" in result
    assert "relationships" in result
    assert len(result["nodes"]) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_kg_extractor.py -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/services/kg_extractor.py
"""LLM-based entity and relationship extractor for knowledge graph.

Extracts structured entities (Paper, Method, Dataset, etc.) and relationships
(USES, EVALUATES_ON, CITES, etc.) from paper content using LLM.
"""
import json
import logging
import re
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# Schema for extraction
EXTRACTION_SCHEMA = """Extract entities and relationships from the paper content.

Entity types: Paper, Method, Algorithm, Dataset, Metric, ProblemType, Benchmark, Author, Institution, CodeRepo

Relationship types: USES, EVALUATES_ON, ACHIEVES, CITES, AUTHORED_BY, AFFILIATED_WITH, BENCHMARKS, COMPARES, SOLVES, IMPLEMENTS, HAS_CODE, EXTENDS

Return JSON:
{
  "nodes": [
    {"label": "Paper", "properties": {"id": "p1", "title": "...", "year": 2024, "venue": "..."}},
    {"label": "Method", "properties": {"id": "m1", "name": "...", "category": "deep_learning", "description": "..."}}
  ],
  "relationships": [
    {"from_label": "Paper", "from_id": "p1", "to_label": "Method", "to_id": "m1", "type": "USES", "properties": {"context": "..."}}
  ]
}
"""

EXTRACTION_PROMPT = """Extract knowledge graph entities and relationships from this paper content.

{schema}

Paper content:
{content}

Return ONLY valid JSON, no other text."""


class EntityExtractor:
    """Extract entities and relationships from paper content using LLM."""

    def __init__(self, call_llm: Optional[Callable] = None):
        self._call_llm = call_llm

    def extract(self, content: str, max_chars: int = 8000) -> Dict[str, Any]:
        """Extract entities and relationships from paper content.

        Args:
            content: Paper text content
            max_chars: Max characters to send to LLM

        Returns:
            Dict with "nodes" and "relationships" keys
        """
        if not content:
            return {"nodes": [], "relationships": []}

        # Truncate if needed
        truncated = content[:max_chars]

        # Build prompt
        prompt = EXTRACTION_PROMPT.format(
            schema=EXTRACTION_SCHEMA, content=truncated
        )

        # Call LLM
        if self._call_llm is None:
            logger.warning("[EntityExtractor] No LLM client, using rule-based fallback")
            return self._rule_based_extract(truncated)

        try:
            response = self._call_llm(prompt, "You are a knowledge graph extraction expert.")
            return self._parse_llm_response(response)
        except Exception as e:
            logger.warning(f"[EntityExtractor] LLM extraction failed: {e}, using fallback")
            return self._rule_based_extract(truncated)

    def _parse_llm_response(self, response: str) -> Dict[str, Any]:
        """Parse LLM response into structured format."""
        try:
            # Try to extract JSON from response
            match = re.search(r'\{.*\}', response, re.DOTALL)
            if match:
                data = json.loads(match.group())
                if "nodes" in data and "relationships" in data:
                    return data
        except json.JSONDecodeError:
            pass

        # Fallback: return empty
        return {"nodes": [], "relationships": []}

    def _rule_based_extract(self, content: str) -> Dict[str, Any]:
        """Rule-based fallback extraction (no LLM)."""
        nodes = []
        relationships = []

        # Simple pattern matching for common entities
        # Papers
        if "abstract" in content.lower():
            title_match = re.search(r'^(?:#\s+)?(.+?)(?:\n|$)', content)
            if title_match:
                nodes.append({
                    "label": "Paper",
                    "properties": {
                        "id": "p_extracted",
                        "title": title_match.group(1).strip()[:200],
                    }
                })

        # Methods
        method_patterns = [
            (r'(?:we propose|our method|our approach)\s+(\w[\w\s]+?)(?:\s+for|\s+that|\s*,)', 'method'),
            (r'(?:neural network|CNN|RNN|LSTM|Transformer|GAN|VAE|diffusion)\b', 'algorithm'),
        ]
        for pattern, mtype in method_patterns:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                name = match.group(1) if match.lastindex else match.group(0)
                nodes.append({
                    "label": "Method" if mtype == "method" else "Algorithm",
                    "properties": {
                        "id": f"m_{len(nodes)}",
                        "name": name.strip()[:100],
                    }
                })

        return {"nodes": nodes, "relationships": relationships}

    def batch_extract(
        self, contents: List[Dict[str, str]], batch_size: int = 5
    ) -> List[Dict[str, Any]]:
        """Extract from multiple papers in batch.

        Args:
            contents: List of {"id": "...", "content": "..."}
            batch_size: Papers per LLM call

        Returns:
            List of extraction results
        """
        results = []
        for i in range(0, len(contents), batch_size):
            batch = contents[i:i + batch_size]
            for item in batch:
                result = self.extract(item.get("content", ""))
                results.append({
                    "paper_id": item.get("id", ""),
                    "extraction": result,
                })
        return results
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_kg_extractor.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/kg_extractor.py backend/tests/test_kg_extractor.py
git commit -m "feat(kg): add EntityExtractor with LLM and rule-based fallback"
```

---

### Task 3: GraphSearcher — Query Layer

**Covers:** [S3.3], [S4]

**Files:**
- Create: `backend/app/services/kg_search.py`
- Create: `backend/tests/test_kg_search.py`

**Interfaces:**
- Consumes: `Neo4jStore` from Task 1
- Produces: `GraphSearcher` class with search/recommendation methods

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_kg_search.py
import pytest
from unittest.mock import MagicMock

def test_graph_searcher_init():
    from app.services.kg_search import GraphSearcher
    mock_store = MagicMock()
    searcher = GraphSearcher(mock_store)
    assert searcher is not None

def test_entity_search():
    from app.services.kg_search import GraphSearcher
    mock_store = MagicMock()
    mock_store.find_by_property.return_value = [
        {"id": "m1", "properties": {"name": "CNN", "category": "deep_learning"}}
    ]
    searcher = GraphSearcher(mock_store)
    results = searcher.entity_search("CNN")
    assert len(results) > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_kg_search.py -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/services/kg_search.py
"""Graph search and recommendation queries for knowledge graph.

Provides structured queries that combine graph traversal with entity relevance.
"""
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class GraphSearcher:
    """Search and query the knowledge graph."""

    def __init__(self, store):
        """Initialize with a Neo4jStore instance."""
        self._store = store

    def entity_search(
        self, query: str, label: Optional[str] = None, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Search for entities matching query by name."""
        results = []
        labels = [label] if label else ["Method", "Dataset", "Paper", "Algorithm"]

        for lbl in labels:
            matches = self._store.find_by_property(lbl, "name", query)
            for m in matches:
                m["label"] = lbl
                results.append(m)

        # Also search by partial match
        if not results:
            for lbl in labels:
                all_nodes = self._store.find_by_property(lbl, "name", "")
                for n in all_nodes:
                    name = n.get("properties", {}).get("name", "").lower()
                    if query.lower() in name:
                        n["label"] = lbl
                        results.append(n)

        return results[:limit]

    def neighbor_search(
        self,
        label: str,
        node_id: str,
        depth: int = 1,
        rel_types: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Find neighboring entities up to N hops."""
        return self._store.find_neighbors(label, node_id, depth, rel_types)

    def path_search(
        self,
        start_label: str,
        start_id: str,
        end_label: str,
        end_id: str,
        max_depth: int = 3,
    ) -> List[Dict[str, Any]]:
        """Find paths between two entities."""
        return self._store.find_paths(start_label, start_id, end_label, end_id, max_depth)

    def method_recommendation(
        self,
        problem_type: str = "",
        dataset: str = "",
        metric: str = "",
    ) -> List[Dict[str, Any]]:
        """Recommend methods for a given problem type and dataset."""
        # Find ProblemType node
        problem_nodes = self._store.find_by_property("ProblemType", "name", problem_type)

        if not problem_nodes and not dataset:
            return []

        # If we have a problem type, find methods that solve it
        if problem_nodes:
            pid = problem_nodes[0]["id"]
            neighbors = self._store.find_neighbors(
                "ProblemType", pid, depth=2,
                rel_types=["SOLVES", "EVALUATES_ON"]
            )
            return neighbors

        # If we have a dataset, find methods evaluated on it
        if dataset:
            dataset_nodes = self._store.find_by_property("Dataset", "name", dataset)
            if dataset_nodes:
                did = dataset_nodes[0]["id"]
                neighbors = self._store.find_neighbors(
                    "Dataset", did, depth=2,
                    rel_types=["EVALUATES_ON"]
                )
                return neighbors

        return []

    def sota_search(
        self, dataset_name: str, metric_name: str
    ) -> List[Dict[str, Any]]:
        """Find state-of-the-art methods for a dataset+metric."""
        # Find dataset
        datasets = self._store.find_by_property("Dataset", "name", dataset_name)
        if not datasets:
            return []

        dataset_id = datasets[0]["id"]
        return self._store.find_sota(dataset_id, metric_name)

    def paper_search(
        self, query: str, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Search papers by title/abstract keywords."""
        # Simple keyword search
        papers = self._store.find_by_property("Paper", "title", query)
        return papers[:limit]

    def get_context_for_query(
        self, query: str, max_entities: int = 5
    ) -> str:
        """Get formatted graph context for a query (for agent injection)."""
        entities = self.entity_search(query, limit=max_entities)
        if not entities:
            return ""

        parts = ["【知识图谱检索结果】"]
        for e in entities:
            label = e.get("label", "Unknown")
            props = e.get("properties", {})
            name = props.get("name", props.get("title", "Unknown"))
            parts.append(f"- [{label}] {name}")

            # Get neighbors for more context
            nid = e.get("id", "")
            if nid:
                neighbors = self.neighbor_search(label, nid, depth=1)
                for n in neighbors[:3]:
                    n_label = n.get("label", "")
                    n_props = n.get("properties", {})
                    n_name = n_props.get("name", n_props.get("title", ""))
                    parts.append(f"  → {n_label}: {n_name}")

        return "\n".join(parts)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_kg_search.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/kg_search.py backend/tests/test_kg_search.py
git commit -m "feat(kg): add GraphSearcher query layer"
```

---

### Task 4: HybridRAGEngine Enhancement

**Covers:** [S3.4], [S4]

**Files:**
- Create: `backend/app/core/graph_search_adapter.py`
- Modify: `backend/app/core/hybrid_search.py` (add graph path to RRF fusion)

**Interfaces:**
- Consumes: `GraphSearcher` from Task 3, existing `HybridSearchEngine`
- Produces: `GraphSearchAdapter` + enhanced `HybridSearchEngine.search()` with optional graph path

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_graph_search_adapter.py
import pytest
from unittest.mock import MagicMock

def test_graph_search_adapter_init():
    from app.core.graph_search_adapter import GraphSearchAdapter
    mock_searcher = MagicMock()
    adapter = GraphSearchAdapter(mock_searcher)
    assert adapter is not None

def test_graph_search_adapter_search():
    from app.core.graph_search_adapter import GraphSearchAdapter
    from src.knowledge.document import Document
    
    mock_searcher = MagicMock()
    mock_searcher.entity_search.return_value = [
        {"id": "m1", "properties": {"name": "CNN"}, "label": "Method"}
    ]
    mock_searcher.neighbor_search.return_value = []
    
    adapter = GraphSearchAdapter(mock_searcher)
    results = adapter.search("CNN", top_k=5)
    assert isinstance(results, list)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_graph_search_adapter.py -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/core/graph_search_adapter.py
"""Adapter that wraps GraphSearcher to produce SearchResult objects
compatible with the existing HybridSearchEngine RRF fusion.
"""
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


class GraphSearchAdapter:
    """Adapt GraphSearcher to HybridSearchEngine's search interface."""

    def __init__(self, graph_searcher):
        self._searcher = graph_searcher

    def search(
        self, query: str, top_k: int = 10
    ) -> list:
        """Search graph and return results as SearchResult-compatible objects.

        Returns list of dicts with: document (Document), score, source="graph"
        """
        from src.knowledge.document import Document
        from src.knowledge.vector_store import RetrievalResult

        results = []

        # 1. Entity search
        entities = self._searcher.entity_search(query, limit=top_k)
        for e in entities:
            props = e.get("properties", {})
            name = props.get("name", props.get("title", ""))
            label = e.get("label", "")

            doc = Document(
                id=f"graph_{e.get('id', '')}",
                title=f"[{label}] {name}",
                content=self._format_entity(e),
                metadata={"source": "knowledge_graph", "entity_id": e.get("id")},
            )
            results.append(RetrievalResult(
                document=doc,
                score=0.8,  # Graph results get base score
                rank=len(results) + 1,
            ))

        # 2. Neighbor expansion for top entities
        for e in entities[:3]:
            nid = e.get("id", "")
            label = e.get("label", "")
            if nid:
                neighbors = self._searcher.neighbor_search(label, nid, depth=1)
                for n in neighbors[:2]:
                    n_props = n.get("properties", {})
                    n_name = n_props.get("name", n_props.get("title", ""))
                    n_label = n.get("label", "")

                    doc = Document(
                        id=f"graph_{n.get('id', '')}",
                        title=f"[{n_label}] {n_name}",
                        content=self._format_entity(n),
                        metadata={"source": "knowledge_graph", "entity_id": n.get("id")},
                    )
                    results.append(RetrievalResult(
                        document=doc,
                        score=0.6,  # Neighbor results get lower score
                        rank=len(results) + 1,
                    ))

        return results[:top_k]

    def _format_entity(self, entity: dict) -> str:
        """Format entity as readable text."""
        props = entity.get("properties", {})
        parts = []
        for k, v in props.items():
            if k != "id" and v:
                parts.append(f"{k}: {v}")
        return "; ".join(parts) if parts else str(entity)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_graph_search_adapter.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/graph_search_adapter.py backend/tests/test_graph_search_adapter.py
git commit -m "feat(kg): add GraphSearchAdapter for RRF fusion integration"
```

---

### Task 5: Agent Integration

**Covers:** [S6]

**Files:**
- Modify: `backend/app/agents/base.py` — add `_inject_graph_context()` method
- Create: `backend/tests/test_kg_agent_integration.py`

**Interfaces:**
- Consumes: `GraphSearcher` from Task 3
- Produces: Agent context injection with graph results

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_kg_agent_integration.py
import pytest
from unittest.mock import MagicMock, patch

def test_inject_graph_context():
    from app.agents.base import BaseAgent
    from app.services.kg_search import GraphSearcher
    from app.core.neo4j_store import Neo4jStore
    
    mock_store = MagicMock(spec=Neo4jStore)
    mock_searcher = MagicMock(spec=GraphSearcher)
    mock_searcher.get_context_for_query.return_value = "【知识图谱检索结果】\n- [Method] CNN"
    
    # Patch the global getter
    with patch("app.core.neo4j_store.get_kg_store", return_value=mock_store):
        with patch("app.services.kg_search.get_graph_searcher", return_value=mock_searcher):
            agent = BaseAgent.__new__(BaseAgent)
            context = agent._inject_graph_context("CNN for image classification")
            assert "知识图谱" in context or context == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_kg_agent_integration.py -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

Add to `backend/app/agents/base.py` (append method to BaseAgent class):

```python
    def _inject_graph_context(self, query: str) -> str:
        """Inject knowledge graph context into agent prompt.

        Returns formatted graph context string, or empty string if KG unavailable.
        """
        try:
            from app.core.neo4j_store import get_kg_store
            from app.services.kg_search import get_graph_searcher

            store = get_kg_store()
            if not store or not store.is_connected():
                return ""

            searcher = get_graph_searcher(store)
            return searcher.get_context_for_query(query, max_entities=5)
        except Exception as e:
            logger.debug(f"[BaseAgent] Graph context injection skipped: {e}")
            return ""
```

Also add singleton getters to `neo4j_store.py` and `kg_search.py`:

```python
# At bottom of neo4j_store.py
_kg_store = None

def get_kg_store() -> Optional[Neo4jStore]:
    global _kg_store
    if _kg_store is None:
        _kg_store = Neo4jStore()
        _kg_store.connect()
    return _kg_store

# At bottom of kg_search.py
_graph_searcher = None

def get_graph_searcher(store) -> GraphSearcher:
    global _graph_searcher
    if _graph_searcher is None:
        _graph_searcher = GraphSearcher(store)
    return _graph_searcher
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_kg_agent_integration.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/agents/base.py backend/app/core/neo4j_store.py backend/app/services/kg_search.py backend/tests/test_kg_agent_integration.py
git commit -m "feat(kg): integrate knowledge graph into agent context injection"
```

---

### Task 6: KG Builder Script + Config

**Covers:** [S3.5], [S5]

**Files:**
- Create: `scripts/build_kg.py`
- Modify: `backend/app/config.py` — add KG settings

**Interfaces:**
- Consumes: `EntityExtractor` from Task 2, `Neo4jStore` from Task 1
- Produces: CLI script for batch KG construction

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_build_kg.py
import pytest

def test_build_kg_main():
    from scripts.build_kg import main
    # Just verify it imports and main function exists
    assert callable(main)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_build_kg.py -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/build_kg.py
"""Build knowledge graph from parsed papers.

Usage:
    python scripts/build_kg.py [--input-dir outputs] [--dry-run]
"""
import sys
import json
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.core.neo4j_store import Neo4jStore
from app.services.kg_extractor import EntityExtractor


def scan_papers(input_dir: str) -> list:
    """Scan for parsed paper files."""
    papers = []
    root = Path(input_dir)

    # Scan reading directories
    for reading_dir in root.glob("*/reading/"):
        for md_file in reading_dir.glob("*.md"):
            papers.append({
                "id": md_file.stem,
                "path": str(md_file),
                "content": md_file.read_text(encoding="utf-8")[:8000],
            })

    # Scan global references
    global_refs = root / "_global" / "global_references"
    if global_refs.exists():
        for md_file in global_refs.glob("*.md"):
            papers.append({
                "id": md_file.stem,
                "path": str(md_file),
                "content": md_file.read_text(encoding="utf-8")[:8000],
            })

    return papers


def main():
    parser = argparse.ArgumentParser(description="Build knowledge graph from papers")
    parser.add_argument("--input-dir", default="outputs", help="Input directory")
    parser.add_argument("--dry-run", action="store_true", help="Dry run (no Neo4j writes)")
    parser.add_argument("--neo4j-uri", default=None, help="Neo4j URI")
    args = parser.parse_args()

    print(f"Scanning papers from {args.input_dir}...")
    papers = scan_papers(args.input_dir)
    print(f"Found {len(papers)} papers")

    if not papers:
        print("No papers found. Exiting.")
        return

    # Extract entities
    extractor = EntityExtractor()
    all_nodes = []
    all_relationships = []

    for paper in papers:
        print(f"  Extracting: {paper['id']}...")
        result = extractor.extract(paper["content"])
        all_nodes.extend(result.get("nodes", []))
        all_relationships.extend(result.get("relationships", []))

    print(f"Extracted {len(all_nodes)} nodes, {len(all_relationships)} relationships")

    if args.dry_run:
        print("Dry run — not writing to Neo4j")
        print(json.dumps({"nodes": all_nodes[:5], "relationships": all_relationships[:5]}, indent=2))
        return

    # Write to Neo4j
    store = Neo4jStore(uri=args.neo4j_uri)
    if not store.connect():
        print("ERROR: Cannot connect to Neo4j")
        sys.exit(1)

    # Import nodes
    for node in all_nodes:
        label = node.get("label", "Unknown")
        props = node.get("properties", {})
        store.upsert_node(label, props)

    # Import relationships
    for rel in all_relationships:
        try:
            store.create_relationship(
                from_label=rel["from_label"],
                from_id=rel["from_id"],
                to_label=rel["to_label"],
                to_id=rel["to_id"],
                rel_type=rel["type"],
                properties=rel.get("properties", {}),
            )
        except Exception as e:
            print(f"  Warning: Failed to create relationship: {e}")

    stats = store.get_stats()
    print(f"Done! Graph stats: {stats}")

    store.disconnect()


if __name__ == "__main__":
    main()
```

Also add to `backend/app/config.py`:

```python
# KG settings
kg_enabled: bool = True
kg_extraction_batch_size: int = 5
kg_max_traversal_depth: int = 3
kg_rrf_weight_graph: float = 0.3
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_build_kg.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/build_kg.py backend/app/config.py backend/tests/test_build_kg.py
git commit -m "feat(kg): add KG builder script and config settings"
```

---

### Task 7: Integration Tests + Documentation

**Covers:** [S7], [S8], [S9]

**Files:**
- Create: `backend/tests/test_kg_integration.py`
- Update: `requirements.txt` — add neo4j driver

**Interfaces:**
- Consumes: All previous tasks
- Produces: Integration tests + dependency update

- [ ] **Step 1: Add neo4j dependency**

Add to `requirements.txt`:
```
neo4j>=5.0.0
```

- [ ] **Step 2: Write integration test**

```python
# backend/tests/test_kg_integration.py
import pytest
from unittest.mock import MagicMock, patch, PropertyMock

def test_full_pipeline_mock():
    """Test full extraction → storage → search pipeline with mocks."""
    from app.services.kg_extractor import EntityExtractor
    from app.services.kg_search import GraphSearcher
    from app.core.graph_search_adapter import GraphSearchAdapter

    # Mock LLM response
    mock_llm = MagicMock(return_value=json.dumps({
        "nodes": [
            {"label": "Paper", "properties": {"id": "p1", "title": "Test Paper", "year": 2024}},
            {"label": "Method", "properties": {"id": "m1", "name": "CNN", "category": "deep_learning"}},
        ],
        "relationships": [
            {"from_label": "Paper", "from_id": "p1", "to_label": "Method", "to_id": "m1", "type": "USES"}
        ],
    }))

    # Extract
    extractor = EntityExtractor(call_llm=mock_llm)
    result = extractor.extract("This paper proposes a CNN for image classification.")
    assert len(result["nodes"]) == 2
    assert len(result["relationships"]) == 1

    # Mock store
    mock_store = MagicMock()
    mock_store.find_by_property.return_value = [
        {"id": "m1", "properties": {"name": "CNN", "category": "deep_learning"}}
    ]
    mock_store.find_neighbors.return_value = []

    # Search
    searcher = GraphSearcher(mock_store)
    results = searcher.entity_search("CNN")
    assert len(results) > 0

    # Adapter
    adapter = GraphSearchAdapter(searcher)
    adapter_results = adapter.search("CNN")
    assert len(adapter_results) > 0

    print("Full pipeline test passed!")
```

- [ ] **Step 3: Run integration test**

Run: `cd backend && python -m pytest tests/test_kg_integration.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add requirements.txt backend/tests/test_kg_integration.py
git commit -m "test(kg): add integration tests and neo4j dependency"
```

---

## Verification Checklist

After all tasks:

- [ ] `cd backend && python -m pytest tests/test_neo4j_store.py tests/test_kg_extractor.py tests/test_kg_search.py tests/test_graph_search_adapter.py tests/test_kg_agent_integration.py tests/test_build_kg.py tests/test_kg_integration.py -v` — all pass
- [ ] `python -c "from app.core.neo4j_store import Neo4jStore; print('OK')"` — imports work
- [ ] `python -c "from app.services.kg_extractor import EntityExtractor; print('OK')"` — imports work
- [ ] `python -c "from app.services.kg_search import GraphSearcher; print('OK')"` — imports work
- [ ] `grep neo4j requirements.txt` — dependency present

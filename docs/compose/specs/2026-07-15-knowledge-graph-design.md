# Knowledge Graph System Design Spec

> **For agentic workers:** This is the design specification for the knowledge graph system. Implementation plan should follow compose:plan skill.

**Goal:** Build a Neo4j-based knowledge graph that enhances the existing RAG pipeline with structured entity relationships, enabling cross-paper knowledge association and agent decision support.

**Architecture:** LLM auto-extraction → Neo4j storage → graph traversal enhanced retrieval → 3-way fusion (vector + BM25 + graph) ranking.

**Tech Stack:** Neo4j (community edition), neo4j Python driver, LLM extraction, existing hybrid_search engine.

---

## [S1] Problem Statement

The current RAG system (`hybrid_search.py`) uses flat document retrieval (vector + BM25). It cannot answer relationship-type queries like "which method works best on which dataset" or "what are the common limitations across papers on topic X". This limits agent decision quality in modeling, algorithm selection, and experiment design.

## [S2] Entity-Relationship Model

### Node Types (10)

| Node | Key Attributes | Source |
|------|---------------|--------|
| Paper | title, authors, year, venue, abstract, arxiv_id, doi | research_agent |
| Method | name, category (statistical/ml/deep_learning/optimization), description, complexity | LLM extraction |
| Algorithm | name, type (exact/heuristic/meta-learning), pseudocode, parameters | solver_agent + LLM |
| Dataset | name, size, source, domain, license, features | research_agent + LLM |
| Metric | name, direction (higher/lower_is_better), category (accuracy/efficiency/robustness) | experimentation_agent |
| ProblemType | name, description, subtypes (prediction/optimization/classification/clustering) | analyzer_agent |
| Benchmark | name, dataset, metric, year, best_method, best_value | LLM extraction |
| Author | name, affiliation, h_index | research_agent |
| Institution | name, country, type (university/industry/lab) | research_agent |
| CodeRepo | url, framework (pytorch/tensorflow/jax), stars, license | LLM extraction |

### Relationship Types (12)

| Relationship | From → To | Properties |
|-------------|-----------|-----------|
| USES | Paper → Method | context (how method is used) |
| EVALUATES_ON | Method → Dataset | result, metric_value, year |
| ACHIEVES | Method → Metric | value, is_sota (bool) |
| CITES | Paper → Paper | context (why cited) |
| AUTHORED_BY | Paper → Author | order (first/middle/last) |
| AFFILIATED_WITH | Author → Institution | period |
| BENCHMARKS | Benchmark → Dataset | split (train/val/test) |
| COMPARES | Method → Method | basis (same dataset/metric) |
| SOLVES | Method → ProblemType | approach description |
| IMPLEMENTS | Algorithm → Method | framework, language |
| HAS_CODE | Paper → CodeRepo | language, version |
| EXTENDS | Method → Method | improvement description |

## [S3] Architecture Components

### [S3.1] EntityExtractor (`backend/app/services/kg_extractor.py`)

- Input: parsed paper content (title, abstract, sections)
- LLM prompt extracts structured JSON: `{nodes: [...], relationships: [...]}`
- Validates extracted entities against schema
- Batch mode: process multiple papers in one call
- Fallback: rule-based extraction for LLM failures

### [S3.2] Neo4jStore (`backend/app/core/neo4j_store.py`)

- Connection management (URI, auth from env vars `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`)
- CRUD operations: `create_node()`, `create_relationship()`, `upsert_node()`
- Query methods: `find_neighbors()`, `find_paths()`, `find_by_property()`
- Batch import: `bulk_import(nodes, relationships)`
- Schema constraints: unique IDs, indexes on key properties
- Health check: `verify_connection()`

### [S3.3] GraphSearcher (`backend/app/services/kg_search.py`)

- `entity_search(query)` — find relevant entities by name/description
- `neighbor_search(entity_id, depth, rel_types)` — traverse N hops
- `path_search(start_entity, end_entity, max_depth)` — find paths between entities
- `method_recommendation(problem_type, dataset)` — "what methods work for this problem on this dataset"
- `paper_recommendation(query)` — combine graph traversal with entity relevance
- `sota_search(dataset, metric)` — find state-of-the-art methods

### [S3.4] HybridRAGEngine Enhancement (`backend/app/core/hybrid_search.py`)

Extend existing `HybridSearchEngine` with a third retrieval path:

```
query → 1. Vector search (existing)
        2. BM25 search (existing)
        3. Entity extraction → Graph traversal (new)
        → RRF fusion (3-way) → ranked results
```

- `GraphSearchAdapter` class wraps `GraphSearcher` to produce `SearchResult` objects compatible with existing fusion
- `RRFFusion` updated to handle 3 input lists with configurable weights

### [S3.5] KG Builder Script (`scripts/build_kg.py`)

- Scans `outputs/*/reading/` and `global_references/` for parsed papers
- Runs EntityExtractor on each paper
- Bulk imports into Neo4j
- Reports: nodes created, relationships created, errors

## [S4] Data Flow

### Ingestion Flow

```
Paper parsed → EntityExtractor.extract(content)
             → {nodes: [...], relationships: [...]}
             → Neo4jStore.bulk_import(nodes, relationships)
             → Entity resolution (merge duplicate entities)
```

### Query Flow

```
User/Agent query
  → EntityExtractor.extract_entities(query)
  → For each entity: GraphSearcher.neighbor_search(entity, depth=2)
  → GraphSearcher.path_search for multi-entity queries
  → Convert graph results to SearchResult objects
  → RRF fusion with vector + BM25 results
  → Top-k ranked results
```

### Agent Integration Flow

```
Agent needs knowledge → calls _inject_knowledge_context(query)
  → HybridSearchEngine.search(query) [now includes graph path]
  → Returns enriched context with entity relationships
  → Agent uses structured relationships in reasoning
```

## [S5] Configuration

```python
# Neo4j connection (env vars)
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=<password>

# KG settings (config.py or runtime_config)
kg_enabled: bool = True
kg_extraction_batch_size: int = 5
kg_max_traversal_depth: int = 3
kg_rrf_weight_graph: float = 0.3  # graph path weight in RRF fusion
```

## [S6] Agent Integration Points

| Agent | Integration | Query |
|-------|------------|-------|
| research_agent | Paper ingestion → auto-extract entities | "extract entities from this paper" |
| modeler_agent | Method recommendation | "what methods solve {problem_type} on {dataset}" |
| algorithm_engineer | Algorithm selection | "what algorithms implement {method} with best {metric}" |
| experimentation_agent | Baseline recommendation | "what are common baselines for {dataset} on {metric}" |
| innovation_agent | Gap discovery | "what {metric} values are achieved on {dataset}" |

## [S7] Testing Strategy

- Unit tests for EntityExtractor (mock LLM responses)
- Unit tests for Neo4jStore (testcontainers or mock)
- Unit tests for GraphSearcher (graph traversal correctness)
- Integration test: full ingestion → query → result pipeline
- Performance test: query latency < 200ms for depth-2 traversal

## [S8] Dependencies

- `neo4j` Python driver (new dependency)
- Neo4j Community Edition (Docker or local install)
- Existing: `hybrid_search.py`, `knowledge_manager.py`, `research_agent.py`

## [S9] Success Criteria

1. Entity extraction: ≥80% precision on test papers
2. Graph traversal: depth-2 query < 200ms
3. RRF fusion: graph-enhanced retrieval outperforms vector-only by ≥10% on relevance
4. Agent integration: modeler_agent and algorithm_engineer can query graph for recommendations
5. Zero regression: existing RAG performance unchanged when KG is disabled

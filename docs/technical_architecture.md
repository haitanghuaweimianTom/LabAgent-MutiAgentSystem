# Technical Architecture Document

> Multi-Agent Paper Production System v8.0
> Internal documentation for developers and researchers

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Core Architecture](#2-core-architecture)
3. [Agent System](#3-agent-system)
4. [Zero-Hallucination Pipeline](#4-zero-hallucination-pipeline)
5. [Knowledge Base System](#5-knowledge-base-system)
6. [Memory System](#6-memory-system)
7. [GPU Execution](#7-gpu-execution)
8. [Security](#8-security)
9. [API Design](#9-api-design)
10. [Deployment](#10-deployment)

---

## 1. System Overview

### Purpose

Automate academic paper production from problem analysis to Camera-Ready submission.

### Tech Stack

- **Backend**: Python 3.9+ / FastAPI / LangGraph / asyncio
- **Frontend**: Next.js 14 / React / Zustand / Tailwind CSS
- **LLM**: Multi-provider support (OpenAI, Anthropic, Kimi, DeepSeek, etc.)
- **Execution**: Python sandbox (namespace isolation) + optional GPU
- **Storage**: File-based (JSON) + SQLite for task state

### Key Design Principles

1. **Code-as-Truth**: LLM generates code, sandbox executes it, numbers come from real execution
2. **Zero Fallback**: No mock data, no placeholder values, no fake results
3. **Defense in Depth**: Multiple verification layers catch different types of errors

---

## 2. Core Architecture

### Request Flow

```
User Request → FastAPI Router → LangGraph Orchestrator → Agent Chain → Response
```

### LangGraph Orchestrator

The orchestrator uses LangGraph's `StateGraph` to manage the workflow:

```python
# Simplified workflow
StateGraph(TaskState)
  .add_node("requirement_decomposition", ...)
  .add_node("preflight_decision", ...)
  .add_node("analyzer", ...)
  .add_node("parallel_analysis", ...)  # data + research + innovation in parallel
  .add_node("discuss_approach", ...)
  .add_node("modeler", ...)           # or algorithm_engineer / financial_analyst
  .add_node("experiment", ...)
  .add_node("iterative_solver", ...)
  .add_node("writer", ...)
  .add_node("peer_review", ...)
  .add_node("fact_check", ...)
  .add_node("compliance_check", ...)
  .add_node("summary", ...)
```

### State Management

`TaskState` is a TypedDict containing:

```python
class TaskState(TypedDict):
    task_id: str
    problem_text: str
    paper_template: str
    workflow_type: str
    sub_problems: List[Dict]
    results: Dict[str, Any]          # Agent outputs keyed by agent name
    solver_attempts: List[Dict]      # Execution history
    paper_memory: Dict               # Global paper memory pool
    current_step: str                # Current workflow step
    # ... more fields
```

### Checkpoint System

LangGraph checkpoints are saved to `backend/data/tasks/`:

```python
# Checkpoint structure
{
    "task_id": "task_xxx",
    "step": "solver",
    "state": { ... },           # Serialized TaskState
    "timestamp": "2026-07-10T...",
    "config": { ... }
}
```

Tasks can be resumed from any checkpoint via `POST /tasks/{id}/resume`.

---

## 3. Agent System

### BaseAgent

All agents inherit from `BaseAgent`:

```python
class BaseAgent:
    name: str
    label: str
    description: str
    default_model: str
    
    async def execute(self, task_input: Dict, context: Dict) -> Dict:
        """Override in subclass"""
        pass
    
    async def call_llm(self, messages: List[Dict], **kwargs) -> Dict:
        """Unified LLM call with retry, caching, rate limiting"""
        pass
    
    def _inject_knowledge_context(self, context: Dict) -> str:
        """Auto-inject relevant knowledge base content"""
        pass
```

### Agent Factory

```python
@AgentFactory.register("solver_agent")
class SolverAgent(BaseAgent):
    name = "solver_agent"
    label = "Solver"
    # ...
```

### Model Routing

`AgentModelRouter` selects the LLM model based on (agent, template):

```python
# Default routing
analyzer / data / modeler / solver → sonnet
research / experimentation → haiku
writer → opus (for CCF-A templates)

# Override via API
PUT /api/v1/agents/{name}/model
```

### ReAct Tool Loop

Agents use ReAct (Reasoning + Acting) for complex tasks:

```
Thought: I need to search for papers about X
Action: web_search("X topic papers")
Observation: Found 5 relevant papers...
Thought: I should also check arXiv
Action: arxiv_search("X")
Observation: Found 3 papers...
... (repeat until done)
```

---

## 4. Anti-Death-Spiral Architecture (v8.2)

### Problem Statement

When the Coder Agent generates complex training scripts, sandbox execution failures can cascade into a "death spiral" — repeated errors that waste compute and stall the pipeline. Additionally, even when code runs successfully, the system may hit a "template bottleneck" where metrics plateau due to overly constrained code generation.

### Three Mechanisms

#### 4.1 Component Injection (组件化注入)

**Module**: `_node_coder_agent()` in `langgraph_orchestrator.py`

In `restricted` mode, the Coder Agent can only generate:
- `nn.Module` subclasses (network architecture components)
- Loss function components
- Training loop components

The system automatically injects these into a pre-validated Base Template:

```python
# Coder outputs (restricted mode):
# COMPONENT: nn.Module
class MyModel(nn.Module): ...

# COMPONENT: loss
def my_loss(pred, target): ...

# System assembles into complete training script
```

**State fields**:
- `execution_mode`: `"restricted"` | `"jailbreak"`
- `circuit_breaker_threshold`: dynamic (3 → 1 after jailbreak)

#### 4.2 AST Safety Shell (AST 安全壳)

**Module**: `safety_shell.py` + `audit_and_patch()` in `code_audit.py`

The `SafetyShellTransformer` performs AST-level code transformation:

1. **try-except wrapping**: Catches all exceptions to prevent sandbox crash
2. **cuda.empty_cache() injection**: After every `torch.cuda.*` call
3. **gc.collect() injection**: In finally block for memory cleanup

```python
# Before transformation
model = MyModel().cuda()
output = model(data)

# After transformation
try:
    model = MyModel().cuda()
    output = model(data)
    torch.cuda.empty_cache()  # injected
except Exception as _safety_exc:
    traceback.print_exc()
finally:
    gc.collect()  # injected
```

#### 4.3 Progressive Jailbreak Circuit Breaker (渐进式越狱熔断)

**Module**: `_node_reviewer_reflection()` + `_route_after_reviewer()` in `langgraph_orchestrator.py`

The Reviewer Agent monitors execution metrics and dynamically adjusts the execution mode:

| State | Condition | Action |
|-------|-----------|--------|
| Normal | `error_count < 3` | Keep current mode |
| Death Spiral | `error_count >= 3` | Degrade to `restricted`, threshold=3 |
| Template Bottleneck | Metrics plateau 2+ rounds | Upgrade to `jailbreak`, threshold=1 |
| Max Retries | Still failing in `restricted` | Proceed to paper generation (degraded) |

**State fields**:
- `error_count`: consecutive sandbox failures (reset on success)
- `metrics_trend`: last 5 metric values for trend analysis

### Graph Integration

```
iterative_solver → coder_agent_node → ast_audit_node
    → sandbox_execution_node → reviewer_reflection_node
    → coder_agent_node (loop) | writer (continue)
```

---

## 5. Zero-Hallucination Pipeline

### Layer 1: AST Code Audit (`code_audit.py`)

Before code execution, Python AST analysis detects:

```python
# Detected issues:
- accuracy = 0.95          # Hardcoded metric
- f1 = 0.89                # Hardcoded metric
- print("Accuracy: 95.2%") # Fake output
- No read_csv() call       # Missing data source
```

Scoring: 100 - (20 × error_count) - (5 × warning_count)

### Layer 2: Sandbox Execution (`sandbox.py`)

```python
SandboxConfig(
    max_cpu_time=120,      # seconds
    max_memory_mb=1024,    # MB
    workspace_persist=True
)
```

4-layer defense:
1. Resource limits (CPU, memory, time)
2. Namespace isolation (unshare --net)
3. Import hook (block dangerous modules)
4. Static analysis (regex scan for os.system, eval, etc.)

### Layer 3: Symbolic Auditor (`symbolic_auditor.py`)

Validates results using deterministic algorithms:

```python
# Checks:
- Table column sums match total row
- Percentages sum to 100%
- accuracy ∈ [0, 1], R² ∈ [-1, 1]
- "A better than B" claims match actual values
```

### Layer 4: Fact Checker (`fact_checker.py`)

Compares LaTeX numbers against solver output:

```python
# Extract numbers from main.tex
latex_numbers = {"accuracy": 0.95, "f1": 0.89}

# Extract numbers from solves.json
solve_numbers = {"accuracy": 0.948, "f1": 0.887}

# Compare with threshold
issues = compare(latex_numbers, solve_numbers, threshold=0.05)
```

### Layer 5: Reference Verifier (`reference_verifier.py`)

```python
# Verification pipeline:
1. DOI → CrossRef API (title match > 0.8)
2. arXiv ID → arXiv API / Semantic Scholar
3. URL → HTTP HEAD check
```

---

## 5. Knowledge Base System

### Architecture

```
KnowledgeManager
  ├─ HybridSearchEngine
  │   ├─ SemanticSearch (sentence-transformers)
  │   └─ BM25Search (rank_bm25)
  ├─ Scope: global | project
  └─ Source Tracking
```

### Hybrid Search

```python
# RRF (Reciprocal Rank Fusion)
score(d) = 1/(k + rank_semantic(d)) + 1/(k + rank_bm25(d))

# Fallback: if BM25 unavailable, use semantic only
# Fallback: if semantic unavailable, use TF-IDF
```

### Scope Isolation

```python
# Global KB: shared across all projects
data/knowledge_bases/global/<kb_id>.json

# Project KB: only visible to specific project
data/knowledge_bases/projects/<project_name>/<kb_id>.json
```

### Auto-Injection

```python
# Priority order:
1. Explicit knowledge_base_ids (user selected)
2. Project-specific KBs
3. Global KBs
```

---

## 6. Memory System

### Three-Tier Architecture

```
┌─────────────────────────────────────────┐
│  Lessons Memory (cross-task)            │
│  - Experience extraction on completion  │
│  - Tag-based retrieval                  │
│  - Feedback loop (use_count increment)  │
│  Storage: data/memory/lessons.json      │
└─────────────────────────────────────────┘
                    ↑↓
┌─────────────────────────────────────────┐
│  Episodic Memory (per-task)             │
│  - Event stream: Agent actions, votes   │
│  - Timeline: chronological decisions    │
│  - Replayable via debug-history API     │
│  Storage: data/memory/tasks/{id}.json   │
└─────────────────────────────────────────┘
                    ↑↓
┌─────────────────────────────────────────┐
│  Working Memory (in-context)            │
│  - Current task state                   │
│  - Agent private memory pools           │
│  - Global paper memory pool             │
│  Storage: In-memory + TaskState         │
└─────────────────────────────────────────┘
```

### Paper Memory Pool

Ensures consistency across long papers:

```python
paper_memory = {
    "terminology": {"LSTM": "modeling", ...},
    "symbols": {"W": {"meaning": "weight matrix", ...}},
    "key_claims": [{"claim": "...", "evidence": "..."}],
    "model_names": ["LSTM", "ARIMA", ...],
    "metrics": ["Accuracy", "F1", ...],
}
```

---

## 7. GPU Execution

### GPUExecutor

```python
# Unified GPU training/inference
gpu_exec = get_gpu_executor()
result = gpu_exec.execute_training(
    script_path="train.py",
    args={},
    timeout=300,
)
```

### VRAMMonitor

- Polls `torch.cuda.memory_allocated()` every 2 seconds
- 85% usage → warning log
- 95% usage → OOM protection (kill training process)

### CheckpointManager

```python
# Auto-save during training
checkpoint_manager.save(model, optimizer, epoch, path)

# Auto-restore
checkpoint_manager.load_latest(path)  # Returns (model, optimizer, epoch)
```

---

## 8. Security

### Input Validation

```python
class TaskCreateRequest(BaseModel):
    problem_text: str = Field(min_length=1, max_length=100000)
    project_name: Optional[str] = Field(max_length=100, pattern=r'^[a-zA-Z0-9_-]+$')
```

### Path Traversal Prevention

```python
def validate_path_within(path: Path, base: Path) -> bool:
    """Ensure path doesn't escape base directory"""
    return path.resolve().is_relative_to(base.resolve())
```

### Prompt Injection Defense

```python
def wrap_user_content(content: str) -> str:
    """Wrap user input with XML tags + HTML entity escaping"""
    escaped = html.escape(content)
    return f"<user_input>{escaped}</user_input>"
```

### Sandbox Isolation

```python
# 4-layer defense
1. Resource limits (setrlimit)
2. Network namespace (unshare --net)
3. Import hook (block os, subprocess, etc.)
4. Static analysis (regex scan)
```

---

## 9. API Design

### REST Endpoints

All endpoints under `/api/v1`:

- **Tasks**: `/tasks/submit`, `/tasks/{id}/status`, `/tasks/{id}/stream`
- **Providers**: `/providers/`, `/providers/{id}/test`
- **Knowledge**: `/knowledge/bases`, `/knowledge/bases/{id}/search`
- **Memory**: `/memory/tasks/{id}/working`, `/memory/lessons`

### SSE Event Stream

```python
# GET /tasks/{id}/stream
event: agent_start
data: {"agent": "solver_agent", "phase": "executing"}

event: agent_complete
data: {"agent": "solver_agent", "result": {...}}

event: task_complete
data: {"task_id": "task_xxx", "status": "completed"}
```

### WebSocket (Future)

Planned for real-time collaboration features.

---

## 10. Deployment

### Docker

```dockerfile
FROM python:3.11-slim
RUN apt-get update && apt-get install -y texlive-xetex fonts-noto-cjk
COPY backend/ /app/backend/
RUN pip install -r /app/backend/requirements.txt
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Docker Compose

```yaml
services:
  backend:
    build: .
    ports: ["8000:8000"]
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    volumes:
      - ./data:/app/data
  redis:
    image: redis:7
    ports: ["6379:6379"]
```

### Production Checklist

- [ ] Set `MATHMODEL_API_KEY` for API authentication
- [ ] Configure CORS origins for frontend domain
- [ ] Set up log rotation for `backend/app.log`
- [ ] Configure backup for `backend/data/` directory
- [ ] Monitor GPU memory usage in production

---

## Appendix: File Structure

```
backend/app/
├── agents/           # Agent implementations
│   ├── base.py       # BaseAgent + AgentFactory + ReAct
│   ├── langgraph_orchestrator.py  # Main orchestrator
│   ├── solver_agent.py
│   ├── writer_agent.py
│   └── ...
├── core/             # Core modules
│   ├── code_audit.py        # AST analysis + dual-responsibility audit
│   ├── safety_shell.py      # AST safety shell transformer (v8.2)
│   ├── sandbox.py           # Code execution
│   ├── gpu_executor.py      # GPU training
│   ├── memory.py            # Memory system
│   ├── data_provenance.py   # SHA-256 tracking
│   └── ...
├── services/         # Service layer
│   ├── fact_checker.py      # Number verification
│   ├── reference_verifier.py # DOI/arXiv verification
│   ├── symbolic_auditor.py  # Statistical validation
│   ├── camera_ready.py      # ZIP packaging
│   └── ...
├── routers/          # FastAPI routes
├── schemas/          # Pydantic models
└── main.py           # FastAPI app
```

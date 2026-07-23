# Technical Architecture Document

> Multi-Agent Paper Production System v8.2
> Internal documentation for developers and researchers

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Core Architecture](#2-core-architecture)
3. [Agent System](#3-agent-system)
4. [Anti-Death-Spiral Architecture (v8.2)](#4-anti-death-spiral-architecture-v82)
5. [Zero-Hallucination Pipeline](#5-zero-hallucination-pipeline)
6. [Knowledge Base System](#5-knowledge-base-system)
7. [Memory System](#6-memory-system)
8. [GPU Execution & ML Training](#7-gpu-execution)
   - 7.1 [ML Training Module](#71-ml-training-module-v82-new)
   - 7.2 [Contextual Bandit (LinUCB)](#72-contextual-bandit--adaptive-retry-decision-v83)
   - 7.3 [BugFinder API Service](#73-bugfinder-api-service-v83)
   - 7.4 [Experiment Tree Search](#74-experiment-tree-search)
   - 7.5 [Claims Traceability](#75-claims-traceability)
   - 7.6 [VLM Figure Review Loop](#76-vlm-figure-review-loop)
   - 7.7 [Other ML-Enhanced Capabilities](#77-other-ml-enhanced-capabilities)
9. [Security](#8-security)
10. [API Design](#9-api-design)
11. [Deployment](#10-deployment)

---

## 1. System Overview

### Purpose

Automate academic paper production from problem analysis to Camera-Ready submission.

### Tech Stack

- **Backend**: Python 3.11+ / FastAPI / LangGraph / asyncio
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

## 7.1 ML Training Module (v8.2 New)

### Bug Finder Agent

The Bug Finder Agent provides local inference code error diagnosis with zero API cost:

**Architecture**:

```
Input: error_traceback + code_context
    │
    ▼
Qwen2.5-Coder-1.5B (QLoRA fine-tuned)
    │
    ▼
Output: Structured JSON
{
    "error_type": "OOM" | "SyntaxError" | ... | "Other",
    "error_location": "line 42-45",
    "root_cause": "tensor shape mismatch...",
    "fix_suggestion": "change nn.Linear(512, 256) to nn.Linear(768, 256)",
    "confidence": 0.87
}
```

**Training Pipeline**:

```python
# Data collection (20 system runs → ~30-50 failure cases)
# Augmentation (template + mutation → 800+ samples)
# QLoRA training (RTX 4060 8GB, ~36 minutes)
# Evaluation (11 error types, target >85% accuracy)
```

**Key Metrics**:

| Metric | Target | Achieved |
|--------|--------|----------|
| error_type_accuracy | >85% | 100% (with label mapping) |
| location_accuracy | >75% | 100% |
| avg_latency_ms | <200ms | ~560ms |

**Integration with Solver**:

```
Solver(LLM) → Generate Code → Sandbox → Failure
    │
    ▼
Bug Finder Agent (local, zero API cost)
    ├── Error classification
    ├── Line localization
    └── Fix suggestion generation
    │
    ▼
Solver(LLM) applies structured diagnosis → Precise fix
```

## 7.2 Contextual Bandit — Adaptive Retry Decision (v8.3)

### Problem

The original circuit breaker used fixed rules:
- `error_count >= 3` → force degrade
- 2 consecutive no-improvement → upgrade mode

This is rigid and doesn't adapt to different task characteristics.

### Solution: LinUCB Contextual Bandit

Replace fixed rules with a learned policy that adapts based on context.

**Context Features (7-dimensional)**:
```
[error_count_normalized, mode_restricted, mode_jailbreak,
 attempt_normalized, metric_trend_slope, metric_last, consecutive_failures]
```

**Action Space**:
| Action | Description |
|--------|-------------|
| `continue` | Retry with current mode |
| `degrade` | Switch to restricted mode (component injection) |
| `upgrade` | Switch to jailbreak mode (free code generation) |
| `abort` | Give up on current problem |

**LinUCB Algorithm**:
```
For each action a, maintain:
  A_a (d×d matrix): Regularized covariance
  b_a (d-vector): Reward accumulator

Select action:
  a* = argmax_a θ_a^T x + α √(x^T A_a^{-1} x)
  where θ_a = A_a^{-1} b_a

Update after reward r:
  A_a += x x^T
  b_a += r x
```

**Reward Function**:
- Execution success + metric improvement: +1.0
- Execution success, no improvement: -0.2
- Execution failure: -1.0

**Safety Net**: If `error_count >= 5`, bypass Bandit and force degrade (prevents catastrophic exploration).

**Offline Evaluation**: Importance Sampling estimates new policy's expected reward from historical logs.

**File**: `backend/app/core/contextual_bandit.py`

## 7.3 BugFinder API Service (v8.3)

### Architecture

BugFinder Agent refactored from direct model loading to API-based architecture:

```
BugFinderAgent
    │
    ├── BaseAgent.call_llm()  ← Unified API interface
    │       │
    │       ├── Ollama (local)
    │       ├── vLLM (local)
    │       └── Remote API (fallback)
    │
    └── Rule Engine (fallback when no model available)
```

**API Server**: `ml/serve_bug_finder.py`
- FastAPI + uvicorn
- Loads Qwen2.5-Coder-1.5B + LoRA adapter
- OpenAI-compatible `/v1/chat/completions` endpoint
- Port 8100, ~2.9GB VRAM, 2.4s cold start

**Integration**:
- All Agents use unified `BaseAgent.call_llm()` interface
- AgentModelRouter routes to appropriate model
- No local model → automatic fallback to rule engine

## 7.4 Experiment Tree Search

### Architecture

`ExperimentTreeSearch` implements shallow tree search for experiment optimization:

```
Root (baseline)
├── Seed 1 (different hyperparams)
│   ├── Beam 1.1 (further refinement)
│   └── Beam 1.2 (alternative approach)
├── Seed 2 (different architecture)
│   └── Failure → Pivot (change strategy)
└── Seed 3 (ablation study)
```

**Key Features**:
- Parallel seed/beam evaluation
- Failure pivot: when a branch fails, pivot to alternative approach
- Budget-aware: stops when compute budget exhausted
- Result aggregation into paper-ready tables

**File**: `backend/app/services/experiment_tree_search.py`

## 7.5 Claims Traceability

### Problem

Papers make claims ("Our method achieves 95% accuracy") but these claims must be traceable to actual solver outputs and experiment logs.

### Solution

`ClaimsTraceability` builds a mapping table:

```json
{
  "claim": "Model achieves 95% accuracy on test set",
  "source_type": "solver_output",
  "source_file": "experiment_results.json",
  "source_metric": "accuracy",
  "source_value": 0.95,
  "verified": true
}
```

**Verification Chain**:
1. Extract claims from paper text
2. Match claims to solver outputs / experiment results
3. Flag unverified claims
4. Generate audit trail for peer review

**File**: `backend/app/services/claims_traceability.py`

## 7.6 VLM Figure Review Loop

### Problem

AI-generated figures often have quality issues (wrong labels, inconsistent styles, misleading visualizations).

### Solution

Vision-Language Model (VLM) reads the generated figure and provides feedback:

```
Figure Generation → VLM Review → Quality Assessment
                                    │
                                    ├── Content consistency check
                                    ├── Aesthetic evaluation
                                    ├── Label accuracy verification
                                    │
                                    ▼
                             Modification Suggestions
                                    │
                                    ▼
                             Regenerate Figure (with fixes)
```

**Loop**: Up to 3 iterations until quality threshold met.

**File**: `backend/app/core/vlm_figure_reviewer.py`

## 7.7 Other ML-Enhanced Capabilities

### Symbolic Auditor
- Uses SymPy to verify mathematical formulas
- Checks algebraic equivalence, dimensional consistency
- File: `backend/app/services/symbolic_auditor.py`

### Idea Archive
- Cross-run idea tracking with novelty detection
- GPU value HITL gate for expensive experiments
- File: `backend/app/core/idea_archive.py`

### Data Provenance
- SHA-256 hash tracking for all data transformations
- Reproducibility bundle generation
- File: `backend/app/core/data_provenance.py`

### Context Compressor
- 3-level strategy: soft compress → LLM summarize → truncate
- Protects critical deliverables (LaTeX, title, abstract, citations)
- File: `backend/app/core/context_compressor.py`

### Token Budget Manager
- 7-category allocation: system/user/knowledge/memory/react/feedback/summary
- Prevents context window explosion
- File: `backend/app/core/token_budget.py`

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
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
```

### Docker Compose

```yaml
services:
  backend:
    build: .
    ports: ["8001:8001"]
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
│   ├── langgraph_orchestrator.py  # Main orchestrator (LangGraph)
│   ├── bug_finder_agent.py        # Bug Finder (API mode)
│   ├── solver_agent.py
│   ├── writer_agent.py
│   └── ...
├── core/             # Core modules
│   ├── contextual_bandit.py    # LinUCB adaptive retry (v8.3)
│   ├── code_audit.py           # AST analysis + dual-responsibility audit
│   ├── safety_shell.py         # AST safety shell transformer (v8.2)
│   ├── sandbox.py              # Code execution (4-layer defense)
│   ├── gpu_executor.py         # GPU training + OOM protection
│   ├── memory.py               # 3-layer memory system
│   ├── data_provenance.py      # SHA-256 tracking
│   ├── context_compressor.py   # 3-level context compression
│   ├── token_budget.py         # 7-category token allocation
│   ├── idea_archive.py         # Cross-run idea tracking
│   └── ...
├── services/         # Service layer
│   ├── fact_checker.py         # Number verification
│   ├── reference_verifier.py   # DOI/arXiv verification
│   ├── symbolic_auditor.py     # SymPy formula verification
│   ├── claims_traceability.py  # Paper claims ↔ solver results
│   ├── experiment_tree_search.py # Shallow tree search
│   ├── vlm_figure_review.py    # VLM figure quality check
│   └── ...
├── routers/          # FastAPI routes
├── schemas/          # Pydantic models
├── mcp/              # MCP tool integration
├── pdf_parsing/      # PDF parsing (MinerU/PyMuPDF)
ml/
├── serve_bug_finder.py  # BugFinder API server (FastAPI)
├── train_bug_finder.py  # QLoRA training script
├── evaluation/          # Evaluation scripts
├── collected_data/      # Training/eval data
└── configs/             # Training configs
└── main.py           # FastAPI app
```

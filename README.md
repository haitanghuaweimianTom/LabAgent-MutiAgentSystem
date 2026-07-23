# LabAgent v8.2

> Fully automated multi-agent platform for generating academic papers (CCF-A conferences, math modeling competitions, coursework, and financial analysis reports).

[中文文档](README_CN.md)

---

## Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [Features](#features)
- [Architecture](#architecture)
- [Anti-Death-Spiral Mechanisms](#anti-death-spiral-mechanisms)
- [API Reference](#api-reference)
- [Configuration](#configuration)
- [Development](#development)
- [Troubleshooting](#troubleshooting)
- [Version History](#version-history)

---

## Overview

LabAgent automates the entire academic paper production pipeline:

1. **Problem Analysis** — Decompose complex problems into sub-problems
2. **Literature Review** — Search arXiv + Semantic Scholar for real papers
3. **Mathematical Modeling** — Select appropriate models and algorithms
4. **Code Generation & Execution** — Generate Python code, execute in sandbox, auto-fix errors
5. **Experiment Execution** — Run experiments with GPU support, baseline comparison, ablation study
6. **Paper Writing** — Generate LaTeX documents with consistent terminology
7. **Peer Review** — 4-dimension scoring + reproducibility check
8. **Fact Check** — Verify numbers against actual execution results
9. **Compliance Check** — Filter investment advice language for financial reports
10. **Camera-Ready Packaging** — Package into submittable ZIP

### What's New in v8.2

| Feature | Description |
|---------|-------------|
| **Component Injection** | Restricted mode Coder generates only nn.Module/Loss components, auto-injected into Base Templates |
| **AST Safety Shell** | Auto-inject try-except + cuda.empty_cache() + gc.collect() to prevent sandbox crashes |
| **Progressive Jailbreak Circuit Breaker** | Dynamic mode switching: restricted → jailbreak based on metrics trend |
| **SHA-256 Data Provenance** | Full-chain hash tracking for tamper-proof results |
| **AST Anti-Fabrication** | Detect hardcoded metrics (`accuracy = 0.95`), block fake outputs |
| **Code Quality Fixes** | Fixed debug endpoint, unified versions, added CI/CD, rate limiting |
| **Bug Finder Agent** | Qwen2.5-Coder-1.5B QLoRA fine-tuned, local inference code error diagnosis (11 types, 100% accuracy) |
| **ML Training Pipeline** | Complete model training pipeline: data collection → augmentation → QLoRA training → evaluation |

---

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 20+ (for Web UI)
- An LLM API key (OpenAI, Anthropic, Kimi, DeepSeek, or any compatible provider)

### 1. Install Dependencies

```bash
# Backend
cd backend
pip install -r requirements.txt

# Frontend
cd frontend
npm install
```

### 2. Configure LLM Provider

Create `backend/.env`:

```bash
# Option A: OpenAI
OPENAI_API_KEY=sk-...

# Option B: Anthropic
ANTHROPIC_API_KEY=sk-ant-...

# Option C: Kimi (Anthropic-compatible)
ANTHROPIC_BASE_URL=https://api.kimi.com/coding/
ANTHROPIC_AUTH_TOKEN=sk-kimi-...

# Option D: Any provider via Web UI Settings tab
```

### 3. Start the System

```bash
# Terminal 1: Backend
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8001

# Terminal 2: Frontend
cd frontend
npm run dev
```

### 4. Open Web UI

Navigate to **http://localhost:3000**:

1. Go to **Settings** tab → Add your LLM provider → Set as default
2. Go to **Generate** tab → Select template → Enter problem description → Submit
3. Watch real-time progress in the task list
4. When complete, go to **PDF** tab → Generate Camera-Ready → Download ZIP

---

## Features

### Paper Templates (8 Built-in + Extensible)

| Template | Use Case | Level |
|----------|----------|-------|
| `math_modeling` | Math modeling competition (CUMCM) | — |
| `neurips_2024` | NeurIPS 2024 | **CCF-A** |
| `acm_sigconf` | ACM SIG Conference | **CCF-A** |
| `ieee_conference` | IEEE Conference | **CCF-A** |
| `springer_lncs` | Springer LNCS | CCF-B |
| `research_survey` | Literature survey/review | — |
| `coursework` | Course assignments | — |
| `financial_analysis` | Financial analysis report | — |

New templates: Add JSON + `.cls/.sty` files to `backend/app/core/paper_templates/templates/`.

### Agent Team (15 Agents)

| Agent | Role | Key Capability |
|-------|------|----------------|
| analyzer | Analyst | Problem decomposition, type classification |
| data | Data Analyst | File parsing, insight extraction |
| research | Researcher | arXiv + Semantic Scholar search |
| innovation | Innovation Expert | Research gap identification |
| modeler | Modeler | Mathematical modeling |
| algorithm_engineer | Algorithm Engineer | CCF-A algorithm design |
| financial_analyst | Financial Analyst | Financial modeling, risk analysis |
| solver | Solver | Real code execution, auto-fix retry |
| writer | Writer | Chapter-by-chapter LaTeX generation |
| peer_review | Peer Reviewer | 4-dimension scoring + reproducibility check |
| experimentation | Experimenter | Experiment design + auto-iteration |
| summary | Summarizer | Task summary + experience extraction |
| debugger | Debugger | Intelligent error analysis |
| compliance | Compliance | Financial report compliance check |
| coordinator | Coordinator | Workflow orchestration |

### Zero-Hallucination Architecture

```
Code Generation → AST Audit → Safety Shell → Sandbox Execution → Result Validation → Fact Check
       ↓              ↓              ↓              ↓                  ↓               ↓
   LLM writes    Detect fake    try-except +    Real Python       Verify ranges    Compare LaTeX
     code       hardcoded metrics  cuda guard    execution        & sums          vs actual
```

### Anti-Death-Spiral Architecture (v8.2)

All templates passing through `iterative_solver` are protected by AST safety shell + sandbox error statistics.

| Template | Flow | Component Injection | Jailbreak |
|----------|------|--------------------|-----------| 
| math_modeling | iterative_solver → ast_audit → sandbox → figure | — | — |
| coursework | iterative_solver → ast_audit → sandbox → figure | — | — |
| financial_analysis | iterative_solver → ast_audit → sandbox → figure | — | — |
| neurips_2024 | iterative_solver → coder → ast_audit → sandbox → reviewer → figure | Yes | Yes |
| ieee_conference | iterative_solver → coder → ast_audit → sandbox → reviewer → figure | Yes | Yes |
| acm_sigconf | iterative_solver → coder → ast_audit → sandbox → reviewer → figure | Yes | Yes |
| springer_lncs | iterative_solver → coder → ast_audit → sandbox → reviewer → figure | Yes | Yes |
| research_survey | Direct to writer (no code execution) | — | — |

### Knowledge Base System

- **Hybrid Search**: Semantic (sentence-transformers) + BM25 keyword search
- **Scope Isolation**: Global (shared across projects) + Project-specific
- **Source Tracking**: Every search result tagged with source document
- **Auto-classification**: Resources classified by type/domain/method/quality

### GPU Support (Optional)

- **GPUExecutor**: Unified GPU training/inference lifecycle
- **VRAMMonitor**: Real-time GPU memory monitoring (85% warning, 95% OOM protection)
- **CheckpointManager**: Auto-save/restore training checkpoints
- Falls back to CPU when GPU is unavailable

### ML Training Module (v8.2 New)

**Bug Finder Agent** — Local inference code error diagnosis, zero API cost

| Capability | Description |
|------------|-------------|
| Error Classification | 11 error types: IndexError, KeyError, ValueError, ZeroDivisionError, TypeError, AttributeError, FileNotFoundError, ImportError, RuntimeError, LogicError, OOM |
| Error Localization | Line-level localization, 100% accuracy |
| Fix Suggestions | Structured JSON output with root_cause and fix_suggestion |
| Inference Latency | ~560ms (RTX 4060), optimizable with INT4 quantization |

**Training Pipeline**:

```bash
# Data collection and augmentation
python ml/collect_data.py --problems 20

# QLoRA training (RTX 4060 8GB)
python ml/train_bug_finder.py --config ml/configs/bug_finder_qlora.yaml

# Evaluation
python ml/evaluation/eval_bug_finder.py \
    --model ml/checkpoints/bug_finder \
    --data ml/collected_data/bug_finder_eval_v2.json
```

**Collaboration with other modules**:

```
Solver(LLM) → Generate Code → Sandbox Execution → Failure
    │
    ▼
Bug Finder Agent (Local inference, zero API cost)
    ├── Error Classification (OOM/Syntax/Logic/...)
    ├── Locate error code line
    └── Generate fix suggestion
    │
    ▼
Solver(LLM) applies structured diagnosis → Precise fix
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Web UI (Next.js 14 + Zustand)                                  │
│  10 tabs: Generate / Data / PDF / History / Settings             │
└──────────────────────┬──────────────────────────────────────────┘
                       │ REST + SSE
┌──────────────────────▼──────────────────────────────────────────┐
│  FastAPI Backend (app.main)                                      │
│  ├─ LangGraph Orchestrator (StateGraph)                          │
│  │   requirement_decomposition → preflight → analyzer            │
│  │   → parallel_analysis [data+research+innovation]              │
│  │   → discuss → modeler → experiment → solver                   │
│  │   → [v8.2] coder_agent → ast_audit → sandbox → reviewer      │
│  │   → writer → peer_review → fact_check → compliance            │
│  │   → summary → END                                             │
│  ├─ Agent Layer (15 agents)                                      │
│  ├─ Core Modules                                                 │
│  │   ├─ code_audit.py        (AST analysis + anti-fabrication)   │
│  │   ├─ safety_shell.py      (AST safety shell transformer)      │
│  │   ├─ reference_verifier.py (DOI/arXiv verification)           │
│  │   ├─ symbolic_auditor.py  (statistical validation)            │
│  │   ├─ data_provenance.py   (SHA-256 tracking)                  │
│  │   ├─ sandbox.py           (code execution)                    │
│  │   ├─ gpu_executor.py      (GPU training)                      │
│  │   └─ memory.py            (3-tier memory)                     │
│  └─ Services                                                    │
│      ├─ fact_checker.py      (number verification)               │
│      ├─ camera_ready.py      (ZIP packaging)                     │
│      ├─ preflight.py         (problem analysis)                  │
│      └─ reference_verifier.py                                    │
└─────────────────────────────────────────────────────────────────┘
```

### Data Flow

1. User submits problem → Preflight analyzes problem type
2. Analyzer decomposes into sub-problems
3. Parallel: Data analysis + Literature review + Innovation discovery
4. Agents discuss approach (voting system)
5. Modeler creates mathematical models
6. **[v8.2]** Coder Agent (restricted/jailbreak) → AST Audit → Sandbox → Reviewer
7. Writer generates LaTeX chapter by chapter
8. Peer reviewer scores and suggests revisions (auto-iterate up to 3 rounds)
9. Fact checker verifies numbers against execution results
10. Compliance agent filters financial advice (for financial reports)
11. Camera-Ready packages everything into submittable ZIP

---

## Anti-Death-Spiral Mechanisms

### Mechanism 1: Component Injection

**Problem**: Full training scripts generated by Coder contain multiple errors, causing repeated sandbox failures.

**Solution**: In restricted mode, Coder only generates nn.Module and Loss components. The system auto-injects them into pre-validated Base Templates.

```python
# Restricted mode: Coder outputs only components
# COMPONENT: nn.Module
class MyModel(nn.Module):
    def __init__(self):
        super().__init__()
        self.fc = nn.Linear(784, 10)

# COMPONENT: loss
def my_loss(pred, target):
    return F.cross_entropy(pred, target)
```

### Mechanism 2: AST Safety Shell

**Problem**: Uncaught exceptions (especially CUDA OOM) crash the entire pipeline.

**Solution**: SafetyShellTransformer performs AST-level code transformation.

```python
# Before
model = MyModel().cuda()
output = model(data)

# After safety shell injection
try:
    model = MyModel().cuda()
    output = model(data)
    torch.cuda.empty_cache()  # auto-injected
except Exception as _safety_exc:
    traceback.print_exc()
finally:
    gc.collect()  # auto-injected
```

### Mechanism 3: Progressive Jailbreak Circuit Breaker

**Problem**: Restricted mode may hit "template bottleneck" — code runs but metrics don't improve.

**Solution**: Reviewer Agent monitors metrics trend, dynamically adjusts execution mode.

| State | Condition | Action |
|-------|-----------|--------|
| Normal | error_count < 3 | Keep current mode |
| Death Spiral | error_count >= 3 | Degrade to restricted, threshold=3 |
| Template Bottleneck | Metrics plateau 2+ rounds | Upgrade to jailbreak, threshold=1 |
| Max Retries | Still failing in restricted | Proceed to paper generation (degraded) |

---

## API Reference

Base URL: `http://localhost:8001/api/v1`

### Task Management

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/tasks/submit` | POST | Submit new task |
| `/tasks/` | GET | List all tasks |
| `/tasks/{id}/status` | GET | Get task status |
| `/tasks/{id}/stream` | GET | SSE event stream |
| `/tasks/{id}/result` | GET | Task results |
| `/tasks/{id}/camera-ready` | POST | Generate Camera-Ready ZIP |
| `/tasks/{id}/pause` | POST | Pause task |
| `/tasks/{id}/resume` | POST | Resume task |
| `/tasks/{id}/cancel` | POST | Cancel task |
| `/tasks/{id}/rerun` | POST | Rerun task |

### Submit Task Example

```bash
curl -X POST http://localhost:8001/api/v1/tasks/submit \
  -H "Content-Type: application/json" \
  -d '{
    "problem_text": "Predict GDP for 2030 based on 2024 data...",
    "project_name": "my_project",
    "options": {"template": "math_modeling"}
  }'
```

---

## Configuration

### Environment Variables

```bash
# LLM Provider (choose one)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...

# Optional
LABAGENT_API_KEY=your-secret-key    # Enable API authentication
CUDA_VISIBLE_DEVICES=0               # GPU selection
NEXT_PUBLIC_API_URL=http://localhost:8001  # Backend URL for frontend
```

### Runtime Configuration (`backend/app/config.py`)

| Config | Default | Description |
|--------|---------|-------------|
| `auto_mode_enabled` | True | Full auto mode |
| `max_concurrent_tasks` | 3 | Max concurrent tasks |
| `task_timeout_seconds` | 7200 | Task timeout (2 hours) |
| `experiment_max_iterations` | 3 | Experiment iteration limit |

### Docker Deployment

```bash
docker compose up -d    # Start backend + Redis
```

---

## Development

### Project Structure

```
├── backend/                 # FastAPI backend
│   ├── app/
│   │   ├── agents/          # Agent implementations
│   │   │   ├── base.py      # BaseAgent class
│   │   │   ├── claude_code.py # Claude Code CLI integration
│   │   │   └── mcp_tools.py # MCP tool definitions
│   │   ├── core/            # Core modules
│   │   ├── routers/         # API routes
│   │   └── services/        # Business logic
│   └── tests/               # Backend tests
├── frontend/                # Next.js frontend
├── ml/                      # ML training module
│   ├── train_bug_finder.py  # Bug Finder training script
│   ├── configs/             # Training configs (QLoRA/DPO)
│   ├── collected_data/      # Training data (v1-v7 iterations)
│   ├── checkpoints/         # Model checkpoints
│   ├── evaluation/          # Evaluation scripts
│   └── models/              # Base models (Qwen2.5-Coder-1.5B)
├── config/                  # Configuration files
├── scripts/                 # Utility scripts
├── .github/workflows/       # CI/CD pipeline
├── CONTRIBUTING.md          # Contribution guidelines
├── CHANGELOG.md             # Version history
└── requirements-dev.txt     # Development dependencies
```

### Running Tests

```bash
# Backend
cd backend
python -m pytest tests/ -v

# Frontend
cd frontend
npm test
```

### Code Quality

```bash
# Linting
ruff check backend/
ruff format backend/

# Pre-commit hooks
pre-commit install
pre-commit run --all-files
```

---

## Troubleshooting

### Task Stuck on Solver

- Solver generates code → executes in sandbox → auto-fixes errors (up to 3 retries)
- **v8.2**: If stuck in death spiral, system auto-degrades to restricted mode
- Check `backend/app.log` for error details

### GPU OOM

- **v8.2**: Safety shell auto-injects `torch.cuda.empty_cache()` after CUDA calls
- System auto-estimates batch size, but LLM-generated code may ignore it
- Check VRAMMonitor logs for memory usage

### Task Interrupted

- Tasks auto-save checkpoints to `backend/data/tasks/`
- Resume via `POST /tasks/{id}/resume`

---

## Version History

### v8.2 (2026-07) — Anti-Death-Spiral Architecture + ML Training Module
- Component injection: restricted mode Coder generates only nn.Module/Loss components
- AST safety shell: auto-inject try-except + cuda.empty_cache() + gc.collect()
- Progressive jailbreak circuit breaker: dynamic mode switching based on metrics trend
- Dual-responsibility AST audit: anti-fabrication + anti-crash in single pass
- **Bug Finder Agent**: Qwen2.5-Coder-1.5B QLoRA fine-tuned, 11-class error diagnosis with 100% accuracy
- **ML Training Pipeline**: Complete data collection → augmentation → QLoRA training → evaluation workflow
- Project renamed to **LabAgent**
- Code quality: fixed debug endpoint, unified versions, added CI/CD, rate limiting
- Refactored BaseAgent: extracted claude_code.py and mcp_tools.py modules

### v8.0 (2026-07) — Zero-Hallucination Architecture
- AST code audit for hardcoded metrics detection
- Reference verification via CrossRef/arXiv APIs
- Symbolic auditor for statistical validation
- Debugger Agent for intelligent error analysis
- Data provenance with SHA-256 tracking
- Compliance Agent for financial report filtering

### v7.4 (2026-07) — Security Hardening
- Input validation, path traversal prevention, prompt injection defense

### v7.0 (2026-07) — Full Auto AI Scientist
- Requirement decomposition, innovation discovery, multi-agent discussion

### v6.0 (2026-06) — 5 Research Capabilities
- NAS, auto loss function design, cross-paper gap identification, code evolution, AutoML

---

## License

For academic research and educational use only. Please comply with target venue submission guidelines.

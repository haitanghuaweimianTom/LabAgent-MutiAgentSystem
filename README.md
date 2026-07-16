# Multi-Agent Paper Production System v8.0

> A fully automated multi-agent platform for generating academic papers (CCF-A conferences, math modeling competitions, coursework, and financial analysis reports).

---

## Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [Features](#features)
- [Architecture](#architecture)
- [API Reference](#api-reference)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)
- [Version History](#version-history)

---

## Overview

This system automates the entire academic paper production pipeline:

1. **Problem Analysis** — Decompose complex problems into sub-problems
2. **Literature Review** — Search arXiv + Semantic Scholar for real papers
3. **Mathematical Modeling** — Select appropriate models and algorithms
4. **Code Generation & Execution** — Generate Python code, execute in sandbox, auto-fix errors
5. **Experiment Execution** — Run experiments with GPU support, baseline comparison, ablation study
6. **Paper Writing** — Generate LaTeX documents with consistent terminology
7. **Peer Review** — 4-dimension scoring + reproducibility check
8. **Fact Check** — Verify numbers against actual execution results
9. **Compliance Check** — Filter investment advice language for financial reports
10. **Camera-Ready Packaging** — Package LaTeX + figures + code into submittable ZIP

### What's New in v8.0 (Zero-Hallucination Architecture)

| Feature | Description |
|---------|-------------|
| **AST Code Audit** | Detect hardcoded metrics (`accuracy = 0.95`) before code execution |
| **Reference Verification** | Verify DOI/arXiv IDs via CrossRef/arXiv APIs |
| **Symbolic Auditor** | Validate table sums, percentage totals, metric ranges |
| **Debugger Agent** | Intelligent error analysis with root cause identification |
| **Data Provenance** | SHA-256 hashing, execution logs, reproducibility packages |
| **Compliance Agent** | Detect investment advice language, auto-generate disclaimers |
| **AI Usage Declaration** | Auto-generate ACM/IEEE/ACL-compliant AI usage statements |

---

## Quick Start

### Prerequisites

- Python 3.9+
- Node.js 18+ (for Web UI)
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
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

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

### One-Command Start (Development)

```bash
# Backend
cd backend && python -m uvicorn app.main:app --reload --port 8000 &

# Frontend
cd frontend && npm run dev &
```

---

## Features

### Paper Templates (8 Built-in + Extensible)

| Template | Use Case |
|----------|----------|
| `math_modeling` | Math modeling competition (CUMCM) |
| `neurips_2024` | NeurIPS 2024 (CCF-A) |
| `acm_sigconf` | ACM SIG Conference (CCF-A) |
| `ieee_conference` | IEEE Conference (CCF-A) |
| `springer_lncs` | Springer LNCS (CCF-B) |
| `research_survey` | Literature survey/review |
| `coursework` | Course assignments |
| `financial_analysis` | Financial analysis report |

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
Code Generation → AST Audit → Sandbox Execution → Result Validation → Fact Check
       ↓              ↓              ↓                  ↓               ↓
   LLM writes    Detect fake    Real Python       Verify ranges    Compare LaTeX
     code       hardcoded metrics  execution        & sums          vs actual
```

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

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Web UI (Next.js 14 + Zustand)                          │
│  10 tabs: Generate / Data / PDF / History / Settings     │
└──────────────────────┬──────────────────────────────────┘
                       │ REST + SSE
┌──────────────────────▼──────────────────────────────────┐
│  FastAPI Backend (app.main)                              │
│  ├─ LangGraph Orchestrator (StateGraph)                  │
│  │   requirement_decomposition → preflight → analyzer    │
│  │   → parallel_analysis [data+research+innovation]      │
│  │   → discuss → modeler → experiment → solver           │
│  │   → writer → peer_review → fact_check → compliance    │
│  │   → summary → END                                     │
│  ├─ Agent Layer (15 agents)                              │
│  ├─ Core Modules                                         │
│  │   ├─ code_audit.py        (AST analysis)              │
│  │   ├─ reference_verifier.py (DOI/arXiv verification)   │
│  │   ├─ symbolic_auditor.py  (statistical validation)    │
│  │   ├─ data_provenance.py   (SHA-256 tracking)          │
│  │   ├─ sandbox.py           (code execution)            │
│  │   ├─ gpu_executor.py      (GPU training)              │
│  │   └─ memory.py            (3-tier memory)             │
│  └─ Services                                            │
│      ├─ fact_checker.py      (number verification)       │
│      ├─ camera_ready.py      (ZIP packaging)             │
│      ├─ preflight.py         (problem analysis)          │
│      └─ reference_verifier.py                            │
└─────────────────────────────────────────────────────────┘
```

### Data Flow

1. User submits problem → Preflight analyzes problem type
2. Analyzer decomposes into sub-problems
3. Parallel: Data analysis + Literature review + Innovation discovery
4. Agents discuss approach (voting system)
5. Modeler creates mathematical models
6. Solver generates code → AST audit → Sandbox execution → Auto-fix retry
7. Writer generates LaTeX chapter by chapter
8. Peer reviewer scores and suggests revisions (auto-iterate up to 3 rounds)
9. Fact checker verifies numbers against execution results
10. Compliance agent filters financial advice (for financial reports)
11. Camera-Ready packages everything into submittable ZIP

---

## API Reference

Base URL: `http://localhost:8000/api/v1`

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

### Provider Management

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/providers/` | GET | List providers |
| `/providers/{id}/default` | POST | Set as default |
| `/providers/{id}/test` | POST | Test connectivity |
| `/providers/presets` | GET | List preset providers |

### Knowledge Base

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/knowledge/bases` | GET/POST | List/Create knowledge bases |
| `/knowledge/bases/{id}/items` | POST | Add knowledge items |
| `/knowledge/bases/{id}/search` | POST | Hybrid search |

### Submit Task Example

```bash
curl -X POST http://localhost:8000/api/v1/tasks/submit \
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
ANTHROPIC_BASE_URL=https://api.kimi.com/coding/
ANTHROPIC_AUTH_TOKEN=sk-kimi-...

# Optional
MATHMODEL_API_KEY=your-secret-key    # Enable API authentication
CUDA_VISIBLE_DEVICES=0               # GPU selection
```

### Runtime Configuration (`backend/app/config.py`)

| Config | Default | Description |
|--------|---------|-------------|
| `auto_mode_enabled` | True | Full auto mode |
| `max_concurrent_tasks` | 3 | Max concurrent tasks |
| `task_timeout_seconds` | 7200 | Task timeout (2 hours) |
| `auto_retry_on_failure` | True | Auto-retry on failure |
| `max_retry_count` | 2 | Max retry count |
| `experiment_max_iterations` | 3 | Experiment iteration limit |

### Docker Deployment

```bash
docker compose up -d    # Start backend + Redis
# or
docker build -t mathmodel-backend .
docker run -p 8000:8000 mathmodel-backend
```

---

## Troubleshooting

### Backend Won't Start

```bash
# Missing dependencies
pip install -r requirements.txt

# Port in use
python -m uvicorn app.main:app --port 8001

# Check logs
tail -50 backend/app.log
```

### LLM API Errors

```bash
# Test provider connectivity
curl -X POST http://localhost:8000/api/v1/providers/{id}/test

# Common issues:
# - 429 Rate Limit: Wait or switch provider
# - 401 Unauthorized: Check API key
# - 404 Not Found: Check API base URL
```

### Task Stuck on Solver

- Solver generates code → executes in sandbox → auto-fixes errors (up to 3 retries)
- Check `backend/app.log` for error details
- For complex problems, use `--mode sequential`

### LaTeX Compilation Errors

```bash
# Install TeX Live
sudo apt install texlive-full

# Install CJK fonts (for Chinese)
sudo apt install fonts-noto-cjk

# Manual compile
cd outputs/<project>/output
xelatex -interaction=nonstopmode main.tex
```

### GPU OOM

- System auto-estimates batch size, but LLM-generated code may ignore it
- Manually reduce batch size in generated code
- Check VRAMMonitor logs for memory usage

### Task Interrupted

- Tasks auto-save checkpoints to `backend/data/tasks/`
- Resume via `POST /tasks/{id}/resume`
- Or rerun via `POST /tasks/{id}/rerun`

---

## Version History

### v8.0 (2026-07) — Zero-Hallucination Architecture
- AST code audit for hardcoded metrics detection
- Reference verification via CrossRef/arXiv APIs
- Symbolic auditor for statistical validation
- Debugger Agent for intelligent error analysis
- Data provenance with SHA-256 tracking
- Compliance Agent for financial report filtering
- AI usage declaration auto-generation

### v7.4 (2026-07) — Security Hardening
- Input validation, path traversal prevention, prompt injection defense
- 81 security tests

### v7.3 (2026-07) — Docker + Rate Limiting
- Docker deployment, API rate limiting, LLM call caching

### v7.2 (2026-07) — SSE + Parallel Execution
- Real-time SSE event streaming, parallel agent execution

### v7.1 (2026-07) — ReAct Improvements
- Dynamic iteration, token budget optimization, sliding window + summary

### v7.0 (2026-07) — Full Auto AI Scientist
- Requirement decomposition, innovation discovery, multi-agent discussion

### v6.0 (2026-06) — 5 Research Capabilities
- NAS, auto loss function design, cross-paper gap identification, code evolution, AutoML

---

## Acknowledgments

This project's architecture (Knowledge Base, Agent Manager, MCP integration, LLM Provider system) was inspired by [Cherry Studio](https://github.com/CherryHQ/cherry-studio), an open-source AI chat application. The original submodule reference has been removed to reduce repository size; design patterns are referenced in code comments throughout the codebase.

---

## License

For academic research and educational use only. Please comply with target venue submission guidelines.

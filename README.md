# Multi-Agent Paper Production System v8.2

> 全自动多智能体学术论文生产平台 | Fully automated multi-agent platform for generating academic papers (CCF-A conferences, math modeling competitions, coursework, and financial analysis reports).

---

## Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [Features](#features)
- [Architecture](#architecture)
- [CCF-A Paper Workflow](#ccf-a-paper-workflow) **[NEW]**
- [Anti-Death-Spiral Mechanisms](#anti-death-spiral-mechanisms) **[NEW]**
- [API Reference](#api-reference)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)
- [Version History](#version-history)

---

## Overview

本系统自动化整个学术论文生产流程：从问题分析到 Camera-Ready 提交。

This system automates the entire academic paper production pipeline:

1. **Problem Analysis** — 问题分解与类型分类 | Decompose complex problems into sub-problems
2. **Literature Review** — 文献检索（arXiv + Semantic Scholar） | Search real papers
3. **Mathematical Modeling** — 数学建模与算法设计 | Select appropriate models and algorithms
4. **Code Generation & Execution** — 代码生成 + 沙箱执行 + 自动修复 | Generate Python code, execute in sandbox, auto-fix errors
5. **Experiment Execution** — 实验执行（GPU 支持、Baseline 对比、消融实验） | Run experiments with GPU support, baseline comparison, ablation study
6. **Paper Writing** — LaTeX 论文逐章生成 | Generate LaTeX documents with consistent terminology
7. **Peer Review** — 同行评议（4 维评分 + 可复现性检查） | 4-dimension scoring + reproducibility check
8. **Fact Check** — 事实核查（数值与执行结果对比） | Verify numbers against actual execution results
9. **Compliance Check** — 合规审查（金融报告投顾话术过滤） | Filter investment advice language for financial reports
10. **Camera-Ready Packaging** — 交付物打包（LaTeX + 图表 + 代码） | Package into submittable ZIP

### What's New in v8.2 (Anti-Death-Spiral Architecture)

| Feature | Feature (EN) | Description |
|---------|-------------|-------------|
| **组件化注入** | Component Injection | 受限模式下 Coder 只生成 nn.Module/Loss 组件，自动注入 Base Template |
| **AST 安全壳** | AST Safety Shell | 自动包裹 try-except + cuda.empty_cache()，防止沙箱 OOM 崩溃 |
| **渐进式越狱熔断** | Progressive Jailbreak Circuit Breaker | 动态调整执行模式：restricted → jailbreak，熔断阈值自适应 |
| **SHA-256 数据溯源** | SHA-256 Data Provenance | 全链路数据哈希追踪，确保结果不可篡改 |
| **AST 防造假** | AST Anti-Fabrication | 检测硬编码指标（`accuracy = 0.95`），拦截伪造输出 |

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

```
┌─────────────────────────────────────────────────────────────────┐
│  Coder Agent (restricted / jailbreak 模式切换)                   │
│  ├─ restricted: 只生成 nn.Module/Loss 组件，注入 Base Template    │
│  └─ jailbreak: 允许生成完整代码（指标瓶颈时自动升级）               │
└──────────────────────┬──────────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────────┐
│  AST Audit Agent (双重职责)                                      │
│  ├─ 防造假: 检测硬编码指标 (accuracy = 0.95)                      │
│  └─ 防崩溃: SafetyShellTransformer 自动打补丁                    │
│      - 包裹 try-except                                          │
│      - 注入 cuda.empty_cache()                                  │
│      - 注入 gc.collect()                                        │
└──────────────────────┬──────────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────────┐
│  Sandbox Execution → Reviewer Reflection                        │
│  ├─ error_count >= 3 → 降级为 restricted（死亡螺旋熔断）          │
│  └─ 指标连续未提升 → 升级为 jailbreak（模板瓶颈越狱）              │
└─────────────────────────────────────────────────────────────────┘
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
│  │   ├─ safety_shell.py      (AST safety shell transformer) [NEW]│
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
6. **[v8.2]** Coder Agent (restricted/jailbreak) → AST Audit (anti-fabrication + safety shell) → Sandbox Execution → Reviewer Reflection (circuit breaker)
7. Writer generates LaTeX chapter by chapter
8. Peer reviewer scores and suggests revisions (auto-iterate up to 3 rounds)
9. Fact checker verifies numbers against execution results
10. Compliance agent filters financial advice (for financial reports)
11. Camera-Ready packages everything into submittable ZIP

---

## CCF-A Paper Workflow

CCF-A 论文模板（NeurIPS、IEEE、ACM、Springer）使用专用工作流，包含额外的实验设计和消融分析步骤。

### CCF-A 专用节点

| Node | Description |
|------|-------------|
| `algorithm_engineer` | CCF-A 算法设计专家，提出可发表的算法（形式化定义 + 伪代码 + 复杂度分析） |
| `experimentation` | 实验设计（Baseline、数据集、指标、硬件预算、消融计划） |
| `coder_agent_node` | 组件化注入模式代码生成 |
| `ast_audit_node` | AST 双重审计（防造假 + 防崩溃安全壳） |
| `sandbox_execution_node` | 沙箱执行 + 错误统计 |
| `reviewer_reflection_node` | 渐进式越狱与熔断路由 |

### CCF-A 工作流

```
analyzer → parallel_analysis → algorithm_engineer → experiment
    → [v8.2] coder_agent → ast_audit → sandbox → reviewer
    → writer → peer_review → fact_check → summary → END
```

### CCF-A 论文质量保证

1. **算法创新性检查**: algorithm_engineer 确保方法有形式化定义和理论分析
2. **实验完整性检查**: experimentation 确保有 baseline 对比 + 消融实验
3. **可复现性检查**: peer_review 检查 random seed、超参数、数据集划分
4. **数值一致性检查**: fact_check 对比 LaTeX 中的数字与实际执行结果
5. **防死亡螺旋**: v8.2 三机制确保代码执行不会陷入无限失败循环

---

## Anti-Death-Spiral Mechanisms

### 机制 1: 组件化注入 (Component Injection)

**问题**: Coder Agent 生成的完整训练脚本容易包含多种错误，导致沙箱反复失败。

**解决方案**: 受限模式下，Coder 只能生成 nn.Module 和 Loss 组件代码，系统自动注入到预置的 Base Template 中。

```python
# restricted 模式：Coder 只输出组件
# COMPONENT: nn.Module
class MyModel(nn.Module):
    def __init__(self):
        super().__init__()
        self.fc = nn.Linear(784, 10)

# COMPONENT: loss
def my_loss(pred, target):
    return F.cross_entropy(pred, target)
```

系统自动组装为完整训练脚本。

### 机制 2: AST 安全壳 (AST Safety Shell)

**问题**: 沙箱中的未捕获异常（特别是 CUDA OOM）导致整个流程崩溃。

**解决方案**: SafetyShellTransformer 对代码进行 AST 变换，自动注入防护层。

```python
# 原始代码
model = MyModel().cuda()
output = model(data)

# 安全壳注入后
try:
    model = MyModel().cuda()
    output = model(data)
    torch.cuda.empty_cache()  # 自动注入
except Exception as _safety_exc:
    traceback.print_exc()
finally:
    gc.collect()  # 自动注入
```

### 机制 3: 渐进式越狱熔断 (Progressive Jailbreak Circuit Breaker)

**问题**: 受限模式可能陷入"模板瓶颈"——代码能运行但指标无法提升。

**解决方案**: Reviewer Agent 监控指标趋势，动态调整执行模式。

| 状态 | 条件 | 动作 |
|------|------|------|
| 正常运行 | error_count < 3 | 保持当前模式 |
| 死亡螺旋 | error_count >= 3 | 降级为 restricted，熔断阈值=3 |
| 模板瓶颈 | 指标连续 2 次未提升 | 升级为 jailbreak，熔断阈值=1 |
| 最大重试 | restricted 模式下仍连续失败 | 进入论文生成（带降级标记） |

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
| `experiment_max_iterations` | 3 | Experiment iteration limit |

### Docker Deployment

```bash
docker compose up -d    # Start backend + Redis
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

### v8.2 (2026-07) — Anti-Death-Spiral Architecture
- Component injection: restricted mode Coder generates only nn.Module/Loss components
- AST safety shell: auto-inject try-except + cuda.empty_cache() + gc.collect()
- Progressive jailbreak circuit breaker: dynamic mode switching based on metrics trend
- Dual-responsibility AST audit: anti-fabrication + anti-crash in single pass

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

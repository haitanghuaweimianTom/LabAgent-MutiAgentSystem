# LabAgent — 多智能体学术论文自动生成系统

> **版本**：v8.2 | **代号**：MathModel-MutiAgentSystem | **定位**：基于多 Agent LLM 协作的全自动学术论文生产平台

---

## 一、项目概述

**一句话定位**：基于 LangGraph 的 15 Agent 协作系统，输入一段问题描述 + 可选数据文件，自动输出一篇可提交的完整学术论文。

**技术栈**：FastAPI + LangGraph StateGraph + Next.js 14 + sentence-transformers + PyTorch

**代码规模**：31.5K 行 Python，15 个 Agent 实现，40+ LangGraph 节点，31 个单元测试用例

**支持场景**：
- CCF-A 会议论文（NeurIPS、ACM SIGCONF、IEEE）
- 数学建模竞赛（CUMCM / MCM / ICM）
- 课程报告、文献综述
- 金融分析报告

**核心价值**：只给一个问题描述，系统自主执行 10 阶段 Pipeline，产出包含真实数值结果、真实文献引用、自动生成图表的 LaTeX/Markdown/DOCX 论文。所有数字必须经过沙箱真实执行验证——系统承诺"零数字幻觉"。

---

## 二、系统架构

### 2.1 整体架构

系统提供两个并行入口，共享同一套 Agent 和 Core 基础设施：

```
┌─────────────────────────────────────────────────────┐
│                  Web UI Pipeline                      │
│  Next.js 14 Frontend (port 3000)                     │
│       │ REST + SSE                                    │
│       ▼                                               │
│  FastAPI Backend (port 8001)                          │
│       ├── LangGraph StateGraph 编排器                 │
│       │   (langgraph_orchestrator.py, ~4000 行)       │
│       ├── 15 Agent 实现                               │
│       │   (backend/app/agents/*.py)                   │
│       ├── Core 核心模块                               │
│       │   (sandbox, AST, memory, circuit_breaker...)  │
│       └── Services 业务服务                           │
│           (experiment_runner, fact_checker...)         │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│                  CLI Pipeline                         │
│  python main.py --auto --template <name>              │
│       │                                               │
│       ▼                                               │
│  UnifiedWorkflow (src/agent_workflow.py)              │
│       ├── CrewAI 风格 Agent/Task/Crew 编排            │
│       ├── 4 阶段 Pipeline                             │
│       │   (analysis → modeling → solving → writing)   │
│       ├── 显式记忆池 (Dict[str, str])                 │
│       └── 输出: Markdown + DOCX + LaTeX               │
└─────────────────────────────────────────────────────┘
```

两个入口的区别：
- **Web UI Pipeline**：使用 LangGraph StateGraph，支持 SSE 实时进度推送，适合生产环境
- **CLI Pipeline**：使用 CrewAI 风格编排，轻量快速，适合命令行批量运行

### 2.2 10 阶段 Pipeline

| 阶段 | 名称 | Agent(s) | 输出 |
|------|------|----------|------|
| 0 | Preflight | — | 问题类型分类、模板选择 |
| 1 | 问题分析 | analyzer | 子问题拆解、DAG 依赖图、关键假设 |
| 2 | 并行分析 | data + research + innovation | 数据洞察、文献引用、研究空白 |
| 3 | 讨论投票 | coordinator | 基于投票的方案选择 |
| 4 | 数学建模 | modeler | 公式推导、变量定义、模型假设 |
| 5 | 代码生成与执行 | solver (+ debugger) | Python 代码、沙箱执行结果 |
| 6 | 论文撰写 | writer | LaTeX/Markdown 论文，逐章生成 |
| 7 | 同行评审 | peer_review | 4 维度评分、修改建议（最多 3 轮） |
| 8 | 事实核查 | — | 数值与执行结果交叉验证 |
| 9 | 合规检查 | compliance | 投资建议语言过滤（金融报告专用） |
| 10 | Camera-Ready | — | ZIP 打包（LaTeX + 图表 + 代码） |

### 2.3 LangGraph 编排详解

核心编排器 `langgraph_orchestrator.py`（~4000 行）使用 LangGraph 的 `StateGraph` 构建：

```python
# 状态定义（TypedDict）
class TaskState(TypedDict):
    messages: List[dict]          # 对话历史
    files: List[str]              # 上传的文件
    preflight: dict               # Preflight 结果
    execution_mode: str           # restricted / jailbreak
    error_count: int              # 沙箱错误计数
    metrics_trends: List[float]   # 指标趋势
    react_history: str            # ReAct 历史
    # ... 更多字段
```

**关键设计**：
- **~40 个节点**：每个 Agent 对应 1-2 个 LangGraph 节点
- **条件边**：根据 execution_mode、error_count 等动态选择路径
- **ReAct 循环**：Solver 节点内嵌 ReAct，支持动态迭代次数（1.5x 预留）
- **滑动窗口 + 摘要混合**：防止 ReAct 历史膨胀导致上下文溢出

---

## 三、核心技术创新点

### 3.1 零幻觉架构（Zero-Hallucination）

**核心原则**：论文中的每一个数字都必须追溯到真实代码执行。LLM 只输出代码，数字由沙箱真实运行产生。

**完整验证链**：

```
LLM 生成代码
    │
    ▼
AST 审计 (code_audit.py)
    │  检测硬编码指标：accuracy = 0.95 → 拦截
    ▼
安全壳注入 (safety_shell.py)
    │  AST 变换自动注入 try-except + cuda.empty_cache() + gc.collect()
    ▼
沙箱执行 (sandbox.py / unified_sandbox.py)
    │  4 层防御：subprocess + namespace + import hook + 静态扫描
    ▼
结果验证 (result_validator.py)
    │  检查输出格式、数值范围、完整性
    ▼
事实核查 (fact_checker.py)
    │  LaTeX 数字与 results.json 交叉验证
    ▼
数据溯源 (data_provenance.py)
    │  SHA-256 哈希链保证结果不可篡改
```

**涉及模块**：
- `code_audit.py`：AST 分析，检测 36 种硬编码指标变量名 + 6 种可疑 print 模式
- `safety_shell.py`：Python AST 变换器，在代码执行前自动注入崩溃保护
- `sandbox.py` / `unified_sandbox.py`：基于 subprocess 的代码执行，支持 Linux namespace 隔离
- `fact_checker.py`：提取 LaTeX 中的数字，与沙箱执行的 results.json 交叉验证
- `data_provenance.py`：SHA-256 哈希链，每个执行结果带完整溯源信息

### 3.2 反死亡螺旋架构（Anti-Death-Spiral）

**问题**：多 Agent 系统中，代码执行失败后自动重试，容易陷入无限循环——每次重试都失败，浪费 token 和时间，最终论文质量严重下降。

**解决方案（v8.2 三机制）**：

**机制一：组件注入模式（Restricted Mode）**

传统方式：Coder 生成完整训练脚本 → 频繁失败
改进方式：Coder 只生成 `nn.Module` 和 `Loss` 组件 → 自动注入预验证的 Base Template

```python
# 受限模式：Coder 只输出组件
components = """
class MyModel(nn.Module):
    def __init__(self):
        super().__init__()
        self.fc1 = nn.Linear(784, 128)
    def forward(self, x):
        return self.fc1(x)
"""
# 系统自动注入到 _BASE_TEMPLATE_MATH_MODELING 中
# 避免 LLM 生成错误的 import、main 函数等
```

**机制二：渐进式越狱熔断器**

```
CLOSED (正常)
    │ 连续 N 次失败
    ▼
OPEN (熔断，N 分钟冷却)
    │ 冷却时间到
    ▼
HALF_OPEN (允许 1 次试探)
    │ 试探成功 → CLOSED
    │ 试探失败 → OPEN
```

**机制三：动态模式切换**

```
error_count < 3 → 保持当前模式
error_count >= 3 → 降级到 restricted mode
指标停滞 2+ 轮 → 升级到 jailbreak (全代码生成)
超过最大重试 → 带降级质量继续论文生成
```

### 3.3 多 Agent 记忆与协作

**三级记忆系统**：

| 层级 | 存储 | 生命周期 | 用途 |
|------|------|---------|------|
| 短期记忆 | 内存 (Dict) | 会话级 | Agent 间信息传递 |
| 中期记忆 | JSON 文件 | 任务级 | 跨阶段状态保持 |
| 长期记忆 | 知识库 | 永久 | 经验积累与检索 |

**记忆模块**：
- `memory.py`：MemoryManager 统一管理三级记忆
- `LessonsMemory`：LLM 智能摘要 + 关键词检索，从历史任务中提取经验
- `EpisodicMemory`：事件驱动的经验积累，记录每次执行的成功/失败模式
- `knowledge_manager.py`：知识库管理，支持全局和项目级隔离

**协作机制**：
- `chat_room.py`：多 Agent 投票讨论，类似"辩论会"——多个 Agent 各自提出方案，投票选择最优
- `agent_discussion.py`：结构化的 Agent 间对话，支持 Critique-Improvement 循环
- `coordinator.py`：DAG 依赖图拓扑排序，管理 Agent 间的执行顺序

### 3.4 沙箱安全体系

**四层防御架构**：

```
Layer 1: subprocess + resource limit
    │  所有平台通用，限制 CPU 时间、内存、文件描述符
    ▼
Layer 2: Linux namespace 隔离
    │  mount, net, pid 命名空间隔离（最佳努力）
    ▼
Layer 3: Python import hook
    │  阻止危险模块导入（os, sys, subprocess 等）
    ▼
Layer 4: 静态代码扫描
    │  regex pattern matching 拦截危险调用模式
```

**网络隔离**：使用 `unshare --net` 创建真实的 Linux 网络命名空间，而非简单的环境变量代理。

**统一沙箱**：合并了 `services/code_sandbox.py` 和 `core/sandbox.py` 两个实现为统一的 `CodeSandbox`，通过 `SandboxConfig` 配置化。

### 3.5 知识检索系统

**三阶段检索管线**：

```
Query
    │
    ▼
Stage 1: BM25 关键词检索 (rank_bm25)
    │  快速召回，~100 候选
    ▼
Stage 2: sentence-transformers 语义检索
    │  向量相似度，精排到 ~20 候选
    ▼
Stage 3: CrossEncoder Reranker
    │  精确相关性评分，输出 Top-K
```

**涉及模块**：
- `vector_store.py`：sentence-transformers 本地 embedding
- `rerankers.py`：支持 CrossEncoder / Tfidf / Jina / VoyageAI / TEI 多种后端
- `hybrid_search.py`：融合语义与关键词的混合搜索
- `algorithm_library.py`：精选数学建模算法目录

### 3.6 LLM Provider 抽象层

**统一接口**：

```python
class LLMProvider(ABC):
    def generate(self, prompt: str, system_prompt: str = None, timeout: int = 600) -> str
    def generate_stream(self, prompt: str, system_prompt: str = None) -> Iterator[str]
```

**支持 5+ Provider**：
- OpenAI、Anthropic、Gemini、Ollama、Claude Code CLI
- 还支持 Kimi、DeepSeek、智谱等国产模型（通过 OpenAI 兼容接口）

**自动降级链**：Configured API Provider → Claude CLI 子进程 → RuntimeError

**工厂模式**：`LLMProviderFactory` + `ProviderManager`，支持运行时切换 Provider。

### 3.7 Token 预算管理

**问题**：15 个 Agent 协作，每个 Agent 都调用 LLM，上下文窗口容易溢出。

**解决方案**：
- `context_compressor.py`：基于 tiktoken 的精确 token 计数（替代粗略的字符估算）
- `token_budget.py`：分层 token 预算分配（Agent 级、阶段级）
- 自动压缩：超限时触发摘要 + 滑动窗口，保证关键信息不丢失

### 3.8 异步任务与实时推送

- `AsyncTaskManager`：基于 asyncio.Task 的异步任务管理，支持状态持久化
- `EventBus`：基于 asyncio.Queue 的 SSE 实时进度推送
- `AsyncTokenBucket`：令牌桶限流器，防止 API 配额耗尽
- 并行 Agent 执行：data + research + innovation 三个 Agent 可并行运行

---

## 四、15 个 Agent 详解

| Agent ID | 文件 | 职责 | 特殊能力 |
|----------|------|------|----------|
| analyzer | analyzer_agent.py | 问题拆解 | DAG 依赖图构建 |
| data | data_agent.py | 数据文件解析 | xlsx/csv 加载、洞察提取 |
| research | research_agent.py | 文献搜索 | arXiv + Semantic Scholar API |
| innovation | innovation_agent.py | 研究空白识别 | 跨论文创新点发现 |
| modeler | modeler_agent.py | 数学建模 | 公式生成、Critique-Improvement 循环 |
| algorithm_engineer | algorithm_engineer_agent.py | 算法设计 | CCF-A 级别算法规划 |
| solver | solver_agent.py | 代码生成与执行 | 沙箱运行、自动修复重试（3 轮） |
| debugger | debugger_agent.py | 错误分析 | 智能根因诊断 |
| writer | writer_agent.py | 论文撰写 | 逐章 LaTeX 生成、模板感知 |
| peer_review | peer_review_agent.py | 同行评审 | 4 维度评分、可复现性检查 |
| experimentation | experimentation_agent.py | 实验设计 | 基线对比、消融实验 |
| financial_analyst | financial_analyst_agent.py | 金融建模 | 风险分析、合规预处理 |
| compliance | compliance_agent.py | 合规检查 | 投资建议语言过滤 |
| summary | summary_agent.py | 任务总结 | 经验提取、记忆更新 |
| coordinator | coordinator.py | 编排协调 | 工作流状态管理 |

**Agent 设计原则**：
1. 每个 Agent 单一职责，不直接调用其他 Agent
2. 所有 Agent 通过 `_call_llm()` 调用 LLM，统一处理重试、超时、降级
3. Agent 间通信由编排器管理，通过 memory_pool 传递上下文

---

## 五、8 种论文模板

| 模板 ID | 场景 | 语言 | LaTeX 类 |
|---------|------|------|---------|
| `math_modeling` | CUMCM/MCM/ICM 竞赛 | 中文 | 自定义 |
| `neurips_2024` | NeurIPS (CCF-A) | 英文 | neurips_2024.sty |
| `acm_sigconf` | ACM SIG Conference (CCF-A) | 英文 | acmart.cls |
| `ieee_conference` | IEEE Conference (CCF-A) | 英文 | IEEEtran.cls |
| `springer_lncs` | Springer LNCS (CCF-B) | 英文 | llncs.cls |
| `research_survey` | 文献综述 | 中文 | — |
| `coursework` | 课程报告 | 中文 | — |
| `financial_analysis` | 金融分析报告 | 中文 | — |

模板配置：`backend/app/core/paper_templates/templates/` 下的 JSON 文件

---

## 六、核心模块一览

| 模块 | 功能 |
|------|------|
| `sandbox.py` / `unified_sandbox.py` | 代码执行，namespace 隔离 + 资源限制 |
| `safety_shell.py` | AST 级代码变换，自动注入崩溃保护 |
| `code_audit.py` | AST 分析，检测伪造指标 |
| `circuit_breaker.py` | 渐进式越狱熔断器状态机 |
| `data_provenance.py` | SHA-256 哈希链，结果完整性保证 |
| `gpu_executor.py` | GPU 训练生命周期，VRAM 监控，检查点管理 |
| `memory.py` | 三级记忆系统（短/中/长期） |
| `knowledge_manager.py` | 知识库，混合搜索（语义 + BM25） |
| `hybrid_search.py` | sentence-transformers + BM25 关键词搜索 |
| `context_compressor.py` | Token 感知的上下文裁剪 |
| `chat_room.py` | 多 Agent 讨论/投票机制 |
| `agent_discussion.py` | 结构化 Agent 间对话 |
| `coordinator.py` | DAG 任务依赖管理 |
| `event_bus.py` | 内部事件系统 |
| `state_store.py` | 任务状态持久化 |
| `security.py` | 输入验证、路径遍历防护、Prompt 注入防御 |
| `token_budget.py` | 分层 token 预算管理 |

---

## 七、数据流全景

```
用户输入（问题描述 + 数据文件）
    │
    ▼
Preflight → 问题类型检测 + 模板选择
    │
    ▼
Analyzer → 子问题拆解 + DAG 依赖图
    │
    ├──→ Data Agent（文件解析）
    ├──→ Research Agent（arXiv/Scholar）
    └──→ Innovation Agent（创新点识别）
    │
    ▼
Discussion（投票）→ 方案选择
    │
    ▼
Modeler → 数学公式推导（带 Critique 循环）
    │
    ▼
Solver → 代码生成 → AST 审计 → 安全壳 → 沙箱执行
    │                                           │
    │                                    ┌──────┘
    │                                    ▼
    │                              Debugger（失败时）
    │
    ▼
Writer → LaTeX 论文（逐章生成，模板感知）
    │
    ▼
Peer Review → 4 维度评分 → 修改（最多 3 轮）
    │
    ▼
Fact Check → 数值验证
    │
    ▼
Compliance → 金融语言过滤（如适用）
    │
    ▼
Camera-Ready → ZIP 打包（LaTeX + 图表 + 代码）
```

---

## 八、技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | FastAPI (Python 3.11+) |
| 编排引擎 | LangGraph StateGraph, CrewAI 风格 Agent/Task/Crew |
| LLM Provider | OpenAI, Anthropic, Gemini, Ollama, Claude CLI, Kimi, DeepSeek |
| 前端 | Next.js 14 + Zustand + Tailwind CSS |
| 向量检索 | sentence-transformers (本地 embedding) |
| 关键词检索 | BM25 (rank_bm25) |
| 代码执行 | Subprocess 沙箱 + Linux namespace |
| GPU 支持 | torch.cuda, VRAMMonitor, CheckpointManager |
| 论文格式 | LaTeX (pandoc DOCX 转换) |
| 任务持久化 | JSON 文件 (backend/data/tasks/) |
| CI/CD | GitHub Actions |
| 容器化 | Docker Compose |

---

## 九、项目文件结构

```
├── main.py                          # CLI 入口
├── src/                             # CLI Pipeline 模块
│   ├── agent_workflow.py            # UnifiedWorkflow (CrewAI 风格)
│   ├── workflow/                     # 核心工作流组件
│   ├── agents/crew/                  # Agent/Task/Crew 实现
│   ├── llm/                          # LLM Provider 抽象层
│   ├── knowledge/                    # 向量存储、算法库、知识库
│   ├── paper/                        # LaTeX 导出、论文生成
│   ├── charts/                       # 图表生成
│   ├── memory/                       # 记忆系统
│   ├── mcp/                          # MCP 工具集成
│   └── document_processing/          # 文件加载 (xlsx, csv, pdf)
├── backend/                          # FastAPI Web Pipeline
│   └── app/
│       ├── main.py                   # FastAPI 应用定义
│       ├── agents/                   # 15 个 Agent 实现
│       │   ├── langgraph_orchestrator.py  # LangGraph 编排器 (~4000 行)
│       │   └── *_agent.py            # 各 Agent
│       ├── core/                     # 核心模块 (sandbox, AST, memory...)
│       ├── services/                 # 业务服务
│       └── routers/                  # REST API 路由
├── frontend/                         # Next.js 14 Web UI
├── config/                           # 配置文件
├── data/                             # 运行时数据
├── scripts/                          # 工具脚本
├── tests/                            # 测试套件
└── ml/                               # 模型训练（算法岗新增）
    ├── train_bug_finder.py
    ├── train_reward_model.py
    ├── train_reranker.py
    ├── train_fabrication_detector.py
    ├── data_collection/
    ├── configs/
    └── evaluation/
```

---

## 十、代码不变量（面试中可强调的设计约束）

1. **所有 LLM 调用必须经过 `_call_llm()`** —— 禁止直接 API 调用。该函数统一处理 Provider 选择、重试、超时、降级。

2. **沙箱执行是数值结果的唯一来源** —— 论文中不允许出现未经沙箱执行的 LLM 生成数字。

3. **AST 审计在每次沙箱执行前运行** —— `code_audit.py` 检测硬编码指标；`safety_shell.py` 注入崩溃保护。

4. **每个 Agent 单一职责** —— Agent 间不直接调用，由编排器管理所有通信。

5. **记忆单向流动** —— 每个阶段生成摘要传递给下一阶段，不存在信息回流。

6. **模板控制输出格式** —— 同一个 10 阶段 Pipeline，根据模板 JSON 产出不同结构的论文。

7. **系统优雅降级** —— 任何阶段失败，Pipeline 带降级输出继续，不整体崩溃（反死亡螺旋）。

---

## 十一、部署方式

### Docker 部署（推荐）

```bash
docker-compose up -d
```

### 本地部署

```bash
# 后端
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8001

# 前端
cd frontend
npm install
npm run dev
```

### 环境变量

```bash
# LLM Provider（任选其一）
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
# 或使用国产模型
ANTHROPIC_BASE_URL=https://api.deepseek.com
ANTHROPIC_AUTH_TOKEN=sk-...
```

---

## 十二、面试亮点总结

| 维度 | 亮点 | 面试价值 |
|------|------|---------|
| 系统设计 | 15 Agent + 40 LangGraph 节点 + 10 阶段 Pipeline | 极高 |
| 安全架构 | 零幻觉 + 4 层沙箱 + AST 审计 + SHA-256 溯源 | 极高 |
| 反死亡螺旋 | 组件注入 + 渐进式熔断 + 动态模式切换 | 极高 |
| 记忆系统 | 三级记忆 + LLM 智能摘要 + 知识库 | 高 |
| 检索管线 | BM25 → 语义 → Reranker 三阶段 | 高 |
| Token 管理 | tiktoken 精确计数 + 分层预算 + 自动压缩 | 高 |
| 异步架构 | SSE 推送 + 并行 Agent + 令牌桶限流 | 高 |
| 工程实践 | Docker + CI/CD + 单元测试 + 多 Provider | 中 |

---

*文档版本：v2.0 | 最后更新：2026-07-22 | 面试准备使用*

# 多智能体协作论文生产系统 v3.1

> 面向 **CCF-A 顶会 / 数学建模竞赛** 的多智能体协作论文全自动产线。
> 内置 8 套论文模板（含 NeurIPS 2024、ACM SIGCONF、IEEE Conference、Springer LNCS、综述、CUMCM），
> LangGraph 编排 + ReAct 工具循环 + 实时协作讨论 + 自动迭代 + 真实代码执行 + 真实 arXiv 文献检索 + 跨方法交叉验证 + Camera-Ready 自动打包。

---

## 📑 目录

- [系统能力](#-系统能力)
- [论文产出样例](#-论文产出样例)
- [快速开始](#-快速开始)
- [Web UI 使用](#-web-ui-使用)
- [命令行使用](#-命令行使用)
- [API 说明](#-api-说明)
- [系统架构](#-系统架构)
- [算法与论文模板](#-算法与论文模板)
- [项目结构](#-项目结构)
- [配置说明](#-配置说明)
- [故障排除](#-故障排除)
- [版本历史](#-版本历史)

---

## 🚀 系统能力

### 论文产线
- **8 套论文模板**：`NeurIPS 2024` / `ACM SIGCONF` / `IEEE Conference` / `Springer LNCS` / `Research Survey` / `Financial Analysis` / `Coursework` / `CUMCM`，新模板只需在 `backend/app/core/paper_templates/templates/` 下放 JSON + `.cls/.sty` 即可热加载。
- **真实文献检索**：ResearchAgent 通过 arXiv MCP Server 拉真实论文，并经 Semantic Scholar 二次增强（引用、影响因子、PDF 链接）。
- **真实代码执行**：SolverAgent 调 LLM 写 Python → 沙箱执行 → 结果验证 → 自动 fix retry，最多 3 次，确保数值真实。
- **跨方法交叉验证**：对每子任务结果用 CrossValidator 比对，差异 > 5% 自动报警（占位 baseline，等 B1 接入真方法）。
- **同行评议 + 修订**：PeerReviewAgent 4 维评分（格式/内容/引用/图表），自动打回重写。
- **Camera-Ready 一键打包**：调 `/tasks/{id}/camera-ready` 自动收集 main.tex / figures / code / bib，打包为可投稿 zip。
- **9 阶段任务状态机**：前端 `useTaskState` hook + 后端 SSE 实时推送，毫秒级进度刷新。

### Agent 团队
| Agent | 角色 | 关键能力 |
|------|------|---------|
| coordinator | 协调者 | 工作流编排、暂停/恢复、跨 Agent 黑板 |
| analyzer_agent | 分析师 | 子问题分解、问题类型识别、难度评估 |
| data_agent | 数据分析师 | 数据文件解析、洞察抽取 |
| research_agent | 研究员 | arXiv 检索 + Semantic Scholar 增强 + 可插拔 Reranker |
| modeler_agent | 建模师 | 数学建模、模型选择、算法推荐 |
| algorithm_engineer_agent | 算法工程师 | CCF-A / 数学建模双模式：设计创新算法、复杂度与理论保证、实验方案 |
| financial_analyst_agent | 金融分析师 | 金融数学建模、风险分析、回测设计 |
| solver_agent | 求解器 | 真实代码执行、CrossValidator 集成 |
| writer_agent | 写作专家 | 按章节独立 LLM 调用、可用图表自动注入 |
| peer_review_agent | 同行评议 | 4 维评分 |
| experimentation_agent | 实验设计 | 补充实验与消融 |
| peer_review_agent | 同行评议 | 4 维评分（写作 / 引用 / 方法 / 形式） |

### AgentModelRouter（按 (agent, template) 路由模型）
- 默认：analyzer / data / modeler / solver / peer_review = sonnet；research / experimentation = haiku；writer = opus。
- CCF-A 4 套模板（neurips_2024 / ieee_conference / acm_sigconf / springer_lncs）强制 writer = opus。
- 通过 `backend/app/core/agent_model_map.py` 注册表 + 前端 Settings 动态覆盖。

### 模板化建模路由
LangGraph 编排器根据 `paper_template` + `workflow_type` 自动选择最合适的建模专家：
- **数学建模 / 课程作业 / quick / code_focused** → `modeler_agent`
- **金融分析** → `financial_analyst_agent`
- **CCF-A 模板（IEEE / NeurIPS / ACM / Springer）或 `research_paper` workflow** → `algorithm_engineer_agent`
- **调研/综述（deep_research / research_survey）** → 跳过建模，直接进入写作

三种 Agent 的输出统一归一化为 `sub_problem_models` 标准格式，保证 `solver_agent` 与 `writer_agent` 无需感知具体建模专家；原始丰富输出保留在 `_raw_output` 中供写作时使用。

### 防编造与结果可审计
- **系统级禁令**：所有建模 Agent 的 system prompt 中明确禁止编造数据、股价、收益率、baseline 结果、引用、数据集等。
- **程序化校验**：`_validate_no_fabrication` 检测无来源的价格/收益率、无引用的具体性能数字、异常的作者-年份引用，生成 `_fabrication_flags` 与 `_fabrication_score`。
- **写作端警示**：`writer_agent` 在构建章节上下文时读取 `_fabrication_flags`，对可疑内容添加“需谨慎处理或删除”的提示。
- **兜底模板审计**：`modeler_agent` 的 `MODEL_TEMPLATES` 仅作为 LLM 输出无效时的最后占位；使用时自动标记 `_used_fallback_template=True`，并在局限性中声明“必须根据具体问题重新校验或替换”。

### 持久化记忆
- `MemoryManager` 三级记忆架构：Working Memory（任务上下文）/ Episodic Memory（事件流）/ Lessons Memory（跨任务经验教训）
- 每个 Agent 独立记忆池，支持关键词检索 + Prompt 自动注入
- 跨任务经验提取：完成后自动 `extract_lessons_from_result`，下次任务用 `retrieve_relevant` 检索
- **LangGraph State 外部化**：`TaskResultStore` 将 Agent 大输出从 `TaskState` 中剥离，state 仅保留引用标记，避免节点间反复深拷贝；结果持久化在 `backend/data/langgraph_results/`。

### 环境管理器
- 统一封装 `conda` / `venv` 环境生命周期：列出、创建、删除、安装依赖、激活、在指定环境中执行命令。
- 前端「环境」Tab 可直观管理，API 路径 `/api/v1/environments`。
- 当前激活环境持久化在 `backend/data/active_environment.json`，SolverAgent 执行代码时优先使用激活环境的 Python 解释器。

### Provider / MCP / 知识库（CC Switch 风格）
- 15+ 预设 Provider：OpenAI、Anthropic、阿里百炼、硅基流动、智谱、Kimi、DeepSeek、Ollama、OpenRouter 等
- 5 种 API 格式：OpenAI Chat/Responses、Anthropic、Gemini、Ollama
- MCP 工具管理：stdio / SSE / StreamableHttp 三种传输
- 知识库 RAG：TF-IDF 语义检索 + Agent 自动注入

### 多智能体实时协作讨论
- **Agent 讨论协议**：`discuss_approach` 节点让分析师、建模师、研究员在研究方案阶段互相讨论，形成讨论记录。
- **用户实时参与**：前端 AgentChat 支持用户输入消息，实时出现在 Agent 讨论流中。用户可以修正方向、提出建议、指定方法。
- **自动迭代**：用户不发言时，系统自动迭代修订论文（peer review → writer 修订 → 再审），最多 3 轮，直到评分 ≥ 4.0。
- **等待用户决策**：达到修订上限或用户主动发言后，系统暂停等待用户指导。
- **SSE 实时推送**：ChatRoom 支持消息订阅，前端实时收到每条 Agent 发言（无需轮询）。

### Web UI（Next.js 14）
- 首页 / 生成 / 数据 / PDF / 历史 / Agent / 流程 / 记忆 / 环境 / 设置 10 个 Tab
- SSE 实时消息流 + 任务状态机可视化 + Camera-Ready 面板
- 用户可在 Agent 讨论中实时发言，参与决策
- 暂停 / 恢复 / 取消 / Edit-and-Continue 完整生命周期
- 14+ React 组件 + Zustand 状态管理

---

## 📚 论文产出样例

本系统已在 `outputs/` 下产出两篇 CCF-A 级别的智能体记忆研究方向论文（中英双语）：

| 论文 | 模板 | 任务 ID | 路径 | PDF |
|------|------|---------|------|-----|
| Memora: Structured Episodic Memory for Long-Horizon LLM-Based Multi-Agent Collaboration | NeurIPS 2024 | `task_2254a4eaf8b6` | `outputs/agent_memory_paper_en/output/` | `main.pdf` (21 页) |
| 面向长程多智能体协作的结构化情景记忆机制研究 | ACM SIGCONF | `task_13db1ab8780c` | `outputs/agent_memory_paper_zh/output/` | `main.pdf` |

每个输出目录结构：
```
output/
├── main.pdf              # 编译好的 PDF
├── main.tex              # LaTeX 源文件
├── models.json           # 所有模型设计
├── solves.json           # 求解结果（含数值结果、key_findings）
├── code/                 # 每个子问题的 Python 求解代码
└── htgmm_results.png     # 实验结果图（如有）
```

---

## ⚡ 快速开始

### 环境要求
- Python 3.9+
- Node.js 18+（Web UI）
- TeX Live（含 `xelatex`、`acmart`、`llncs`、`ieeeconf`）— 仅打包 Camera-Ready 时需要
- 可访问 LLM Provider（OpenAI / Anthropic / 阿里百炼 / Kimi / DeepSeek 等任意一个）

### 启动后端

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置 Provider（在 .env 或前端 Settings 里）
# 示例：Kimi
export ANTHROPIC_BASE_URL="https://api.kimi.com/coding/"
export ANTHROPIC_AUTH_TOKEN="sk-kimi-..."

# 3. 启动后端
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
# → http://localhost:8000/api/v1
# → API 文档 http://localhost:8000/docs
```

### 启动前端

```bash
cd frontend
npm install
npm run dev
# → http://localhost:3000
```

### 一句话启动（开发模式）

```bash
# 后端
cd backend && python -m uvicorn app.main:app --reload --port 8000 &

# 前端
cd frontend && npm run dev &
```

---

## 🖥️ Web UI 使用

1. 打开 http://localhost:3000
2. **「设置」** Tab → 添加 Provider（输入 base_url、api_key、model）→ 设为默认
3. **「生成」** Tab → 选模板（CUMCM / NeurIPS / ACM / IEEE / Springer）→ 输入题目 → 提交
4. **「生成」** Tab 实时显示 9 阶段状态：
   - `phase1_running` → `phase1_reviewing`（用户确认子问题）
   - `phase2_running` → `peer_review` → `revising` → `finalizing` → `completed`
5. 完成后 **「PDF」** Tab 触发 Camera-Ready 打包 → 下载 zip

---

## ⌨️ 命令行使用

### CLI 单题模式
```bash
python main.py \
    --problem "智能体记忆研究方向论文：设计长程协作的结构化记忆框架" \
    --template neurips_2024 \
    --project my_paper \
    --mode batch
```

### 全自动扫描
```bash
python main.py --auto --workspace ./workspace
```

---

## 🔌 API 说明

所有端点前缀：`/api/v1`。

### 任务管理
| 端点 | 方法 | 说明 |
|------|------|------|
| `/tasks/submit` | POST | 提交新任务 |
| `/tasks/{id}/status` | GET | 获取任务状态 |
| `/tasks/{id}/stream` | GET | SSE 事件流 |
| `/tasks/{id}/result` | GET | 任务结果（含各 Agent 输出） |
| `/tasks/{id}/camera-ready` | POST | 一键打包可投稿 zip |
| `/tasks/{id}/pause` / `/resume` / `/cancel` | POST | 生命周期控制 |
| `/tasks/{id}/messages` | GET | Agent 协作消息 |
| `/tasks/{id}/debug-history` | GET | 任务执行历史 |

### Provider 管理
| 端点 | 方法 | 说明 |
|------|------|------|
| `/providers/` | GET | 列出所有 Provider |
| `/providers/` | POST | 创建自定义 Provider |
| `/providers/{id}` | PUT / DELETE | 修改 / 删除 |
| `/providers/{id}/default` | POST | 设为默认 |
| `/providers/{id}/test` | POST | 测试连通性 |
| `/providers/presets` | GET | 列出 15+ 预设 |
| `/providers/import-preset` | POST | 一键导入预设 |

### Agent 管理
| 端点 | 方法 | 说明 |
|------|------|------|
| `/agents/` | GET | 列出所有 Agent |
| `/agents/{name}/model` | PUT | 修改 Agent 使用的模型 |
| `/agents/{name}/test-model` | POST | 测试 Agent 模型连通性 |

### 环境管理
| 端点 | 方法 | 说明 |
|------|------|------|
| `/environments/backends` | GET | 列出可用后端（conda / venv） |
| `/environments/` | GET | 列出所有环境 |
| `/environments/` | POST | 创建环境 |
| `/environments/active` | GET | 获取当前激活环境 |
| `/environments/activate` | POST | 激活指定环境 |
| `/environments/install` | POST | 在指定环境安装依赖 |
| `/environments/run` | POST | 在指定环境执行命令 |
| `/environments/{backend}/{name}` | DELETE | 删除环境 |
| 端点 | 方法 | 说明 |
|------|------|------|
| `/mcp/servers` | GET / POST | 列出 / 创建 MCP Server |
| `/mcp/servers/{id}` | PUT / DELETE | 修改 / 删除 |
| `/mcp/servers/{id}/test` | POST | 测试连接 |
| `/mcp/tools` | GET | 列出所有可用工具 |

### 知识库管理
| 端点 | 方法 | 说明 |
|------|------|------|
| `/knowledge/bases` | GET / POST | 列出 / 创建知识库 |
| `/knowledge/bases/{id}/items` | POST | 添加知识点 |
| `/knowledge/bases/{id}/search` | POST | TF-IDF 语义检索 |

### 记忆管理
| 端点 | 方法 | 说明 |
|------|------|------|
| `/memory/tasks/{id}/working` | GET | 任务工作记忆 |
| `/memory/tasks/{id}/episodic` | GET | 任务事件流 |
| `/memory/lessons` | GET / POST | 跨任务经验教训 |
| `/memory/lessons/{id}/feedback` | POST | 用例反馈，更新 use_count |

---

## 🏗️ 系统架构

```
Web UI (Next.js 14 + Zustand)
        ↓ REST + SSE
FastAPI Backend
  ├─ Routers (tasks / agents / providers / mcp / knowledge / memory)
  ├─ Orchestrator (两阶段工作流)
  │    ├─ Phase 1: analyzer → data → research → [暂停]
  │    └─ Phase 2: modeler + solver → writer → peer_review → finalizing
  ├─ AgentModelRouter (按 (agent, template) 路由 LLM)
  ├─ MemoryManager (三级记忆: working / episodic / lessons)
  ├─ PaperTemplateRegistry (JSON-driven 模板注册)
  └─ LLM Provider Layer (15+ Provider, 5 种 API 格式)
        ↓ HTTPS
   OpenAI / Anthropic / 阿里百炼 / Kimi / DeepSeek / Ollama / ...
```

### 关键模块
- `backend/app/agents/orchestrator.py` — 两阶段主编排器
- `backend/app/agents/{base,analyzer,data,research,modeler,solver,writer,peer_review,experimentation}_agent.py` — Agent 实现
- `backend/app/agents/base.py` — BaseAgent + AgentFactory + AgentModelRouter
- `backend/app/agents/demo_code_templates.py` — 15+ 数学建模算法模板
- `backend/app/core/agent_model_map.py` — AgentModelRouter 注册表
- `backend/app/core/paper_templates/` — 论文模板注册表
- `backend/app/core/memory.py` — 三级记忆系统
- `backend/app/services/result_validator.py` — ResultValidator + CrossValidator
- `backend/app/services/camera_ready.py` — Camera-Ready 打包

---

## 📐 算法与论文模板

### 经典数学建模算法（15+）
`demo_code_templates.py` 内置：
- 优化：LP、IP、MILP、GA、PSO
- 预测：ARIMA、灰色预测、LSTM
- 评价：AHP、TOPSIS、熵权法、灰色关联
- 图论：最短路径、最小生成树、网络流
- 统计：聚类、判别、主成分、因子分析
- 数值方法：插值、拟合、数值积分

### 论文模板（6 套 + 可扩展）
在 `backend/app/core/paper_templates/templates/` 下：
- `cumcm.json` — 全国大学生数学建模竞赛
- `neurips_2024.json` — NeurIPS 2024（CCF-A）
- `acm_sigconf.json` — ACM SIG Conference（CCF-A）
- `ieee_conference.json` — IEEE Conference（CCF-A）
- `springer_lncs.json` — Springer LNCS（CCF-B）
- `research_survey.json` — Research Survey

新增模板只需在 `templates/` 下加 JSON + 对应 `.cls/.sty`，注册表自动加载。

---

## 📁 项目结构

```
MathModel-MutiAgentSystem/
├── backend/                       # FastAPI 后端
│   ├── app/
│   │   ├── agents/                # 所有 Agent 实现
│   │   │   ├── base.py            # BaseAgent + AgentFactory + AgentModelRouter
│   │   │   ├── orchestrator.py    # 两阶段主编排器
│   │   │   ├── analyzer_agent.py
│   │   │   ├── data_agent.py
│   │   │   ├── research_agent.py
│   │   │   ├── modeler_agent.py
│   │   │   ├── solver_agent.py    # 含 CrossValidator 跨方法验证
│   │   │   ├── writer_agent.py
│   │   │   ├── peer_review_agent.py
│   │   │   └── experimentation_agent.py
│   │   ├── core/                  # 核心模块
│   │   │   ├── memory.py          # 三级记忆系统
│   │   │   ├── agent_model_map.py # AgentModelRouter
│   │   │   ├── paper_templates/   # 论文模板注册表
│   │   │   ├── chat_room.py
│   │   │   ├── paths.py
│   │   │   └── task_persistence.py
│   │   ├── services/              # 服务层
│   │   │   ├── result_validator.py  # ResultValidator + CrossValidator
│   │   │   ├── camera_ready.py      # Camera-Ready 打包
│   │   │   ├── knowledge.py
│   │   │   └── code_manifest.py
│   │   ├── mcp/                   # MCP 客户端
│   │   ├── routers/               # FastAPI 路由
│   │   ├── schemas/               # Pydantic 模型
│   │   └── main.py                # FastAPI app
│   ├── data/
│   ├── tests/
│   └── app.log
├── frontend/                      # Next.js 14 Web UI
│   └── src/app/
│       ├── page.tsx               # 主页面（9 个 Tab）
│       ├── components/            # 13+ 组件
│       ├── hooks/                  # useTaskState 等
│       └── store/                  # Zustand
├── config/
│   ├── latex_templates/           # LaTeX 样式文件
│   └── mcp_config.json
├── outputs/                       # 论文产出
│   ├── agent_memory_paper_en/     # 英文 Memora 论文
│   └── agent_memory_paper_zh/     # 中文 ACM 论文
├── data/                          # 共享数据
├── workspace/                     # 用户工作空间
├── .env                           # Provider 密钥
├── docker-compose.yml
├── main.py                        # CLI 入口
├── requirements.txt
└── README.md
```

---

## ⚙️ 配置说明

### `.env`（必填项）
```bash
# Provider 选一
ANTHROPIC_API_KEY=sk-ant-...
# 或
OPENAI_API_KEY=sk-...
# 或（Anthropic 兼容）
ANTHROPIC_BASE_URL=https://api.kimi.com/coding/
ANTHROPIC_AUTH_TOKEN=sk-kimi-...

# 可选
DEFAULT_MODEL=sonnet
DATABASE_URL=sqlite:///./data/agents.db
```

> 注：运行时产物统一输出到 `outputs/<project>/`（无项目时写入 `outputs/_global/`），无需通过环境变量配置输出根目录。

---

## 🔧 故障排除

### 后端启动失败
- **缺包**：`pip install -r requirements.txt`
- **端口占用**：改 `--port 8001`
- **`.env` 缺失**：从 `.env.example` 复制

### Provider 调用失败
- `curl http://localhost:8000/api/v1/providers/{id}/test` 测试连通性
- 查看 `backend/app.log` 或 `uvicorn.log`

### 论文卡在 `solver_agent`
- SolverAgent 调 LLM 写代码 → 沙箱执行 → retry。失败 3 次会 fallback 到 demo 模板。
- 复杂问题可改 `--mode sequential` 逐题递进。

### Camera-Ready 提示 `main.tex not found`
- WriterAgent 的 latex_code 字段已含完整 LaTeX，但 orchestrator 默认不会把它写到磁盘。
- Workaround：用 `POST /api/v1/tasks/{id}/result` 拿 `output.writer_agent.latex_code` → 写到 `output/main.tex` → 再调 camera-ready。
- 或手动打 zip：`cd outputs/.../output && xelatex main.tex && zip camera_ready_paper_xx.zip main.tex code/ figures/ solves.json models.json`

### LaTeX 中文乱码
- 确保系统装了 Noto CJK 字体（`apt install fonts-noto-cjk`）
- 编译命令：`xelatex -interaction=nonstopmode main.tex`

---

## 📜 版本历史

### v3.1（2026-06）— 当前
- **模板化建模路由**：`math_modeling`→modeler、`financial_analysis`→financial_analyst、CCF-A/`research_paper`→algorithm_engineer；deep_research/research_survey 跳过建模
- **算法工程师双模式**：`ALGORITHM_ENGINEER_SYSTEM_CCFA` + `ALGORITHM_ENGINEER_SYSTEM_MATH_MODELING`，按模板自动切换
- **金融分析师**：金融数学建模、风险分析、回测设计，强化防编造纪律
- **结果归一化**：三种建模 Agent 输出统一为 `sub_problem_models`，保留 `_raw_output` 供 writer 使用
- **防编造校验**：`_validate_no_fabrication` 检测无来源价格/收益率、无引用性能数字、异常引用；`_fabrication_flags` 透传给 writer
- **环境管理器**：`conda` / `venv` 生命周期管理 + `/api/v1/environments` API + 前端「环境」Tab
- **LangGraph State 外部化**：`TaskResultStore` 避免节点间深拷贝大输出
- **清理硬编码兜底模板**：移除 SiC/报童等过于具体的 `MODEL_TEMPLATES`，改为通用类别模板，并标记兜底结果

### v3.0（2026-06）
- **Phase 7** AgentModelRouter + CrossValidator
- **Phase 6** Camera-Ready + useTaskState hook + TaskStatusBadge
- **Phase 5** PDF 双轨统一 + PaperMetadata LRU 缓存
- **Phase 4** 可插拔 Reranker + LessonsMemory use_count 闭环
- **Phase 3** 实验设计 Agent + PeerReview 4 维评分
- **Phase 2** 8 数学建模模板 + 拆文件编程 + 同行评议 + Camera-Ready
- **Phase 1** 14 个 git commit 落地的通用论文产线

### 历史版本
- v2.6 — CC Switch 风格 Provider 管理 + MCP 增强
- v2.0 — CrewAI 风格多 Agent 架构
- v1.0 — 数学建模单题 CLI

---

## 🔮 Phase 7+：LangGraph + ReAct + Harness 数据驱动改造（进行中）

本阶段目标是把系统改造成**数据驱动的全自动 CCF-A 论文产线**：任务提交时先做 Preflight 决策，没有数据时 LLM 主动规划并尝试搜集，搜集不到再提醒用户上传；编排器迁移到 LangGraph StateGraph；Agent 内部支持 ReAct 工具循环；Solver 失败后在 Harness 评判下自动迭代修复。

### 新增/修改的核心文件

| 文件 | 作用 |
|---|---|
| `backend/app/services/preflight.py` | Preflight 决策器：数据 schema 分析 + LLM 综合判断 + collection_plan |
| `backend/app/agents/langgraph_orchestrator.py` | LangGraph StateGraph 编排器（节点 + 条件边） |
| `backend/app/agents/base.py` | ReAct 工具循环、5 种 provider tools 适配 |
| `backend/app/agents/solver_agent.py` | 显式重试循环 + 错误分类 + 修复建议注入 |
| `backend/app/services/contract_validator.py` | Agent 输出 Pydantic schema 校验 |
| `backend/app/services/fact_checker.py` | main.tex 数字与 solves.json 数值对账 |
| `backend/app/routers/tasks.py` | submit_task 先跑 preflight，支持 data_mismatch / self_collect / 422 |
| `frontend/src/app/components/ProblemInput.tsx` | 数据来源、问题类型、提交 data_files |
| `frontend/src/app/components/PreFlightPanel.tsx` | 预检报告展示与确认 |

### 功能开关（`backend/app/config.py` / `.env`）

```python
use_langgraph_orchestrator=False   # 默认关闭，开启后走 LangGraph 编排
use_react_tools=True               # BaseAgent.call_llm 支持 tools
use_iterative_solver=False         # solver 失败自动迭代（LangGraph 节点内生效）
```

### 状态枚举扩展

后端 `TaskStatus` 与前端 `TaskStateName` 新增：
- `preflight_running`
- `self_collecting_data`
- `iterating_solver`
- `cannot_solve`

---

## 📝 引用

如使用本系统产出学术论文，请引用本仓库：

```bibtex
@misc{memm2026,
  title={A Multi-Agent System for Automated CCF-A Paper Generation with Real Code Execution and Cross-Method Validation},
  author={Anonymous Authors},
  year={2026},
  howpublished={\url{https://github.com/your-org/MathModel-MutiAgentSystem}}
}
```

---

## 📄 许可证

本项目仅供学术研究与教学使用。产出的论文请遵守目标期刊/会议的投稿规范与作者署名要求。

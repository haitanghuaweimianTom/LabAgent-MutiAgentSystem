# 数学建模论文全自动生成系统 v2.1

> **融合 LLM-MM-Agent + Cherry Studio 架构，集成 15 类经典数学建模算法库**
>
> 全自动分段生成 | 显式记忆池 | 代码执行闭环 | 算法智能推荐 | LaTeX/Word 双格式交付 | Web UI 交互

---

## 概述

本项目是一个面向**数学建模竞赛（MCM/ICM/高教社杯）**的论文全自动生成系统。用户可通过**命令行**或**Web 界面**提交赛题，系统即可自动完成问题分析、数学建模、算法设计、代码求解、图表绘制到完整论文撰写的全链路工作，最终交付可直接提交的 **LaTeX PDF** 或 **Word 文档**。

### 核心能力

- **视觉理解赛题**：支持 PDF 题目解析，通过视觉分析提取几何参数与图示信息
- **算法智能推荐**：集成 [Algorithms_MathModels](https://github.com/HuangCongQing/Algorithms_MathModels) 15 类经典算法库，建模阶段自动检索并推荐适用方法
- **代码执行闭环**：生成 Python 代码 → 隔离执行 → 结果验证 → 自动修复，确保论文数据真实可溯源
- **分段记忆衔接**：12 章逐章独立生成，显式记忆池传递结构化摘要，避免上下文溢出
- **双格式交付**：同时输出 Markdown（便于审阅）+ LaTeX PDF（竞赛标准格式）+ Word（备用格式）
- **Web UI 可视化**：基于 Next.js 的交互界面，实时展示四阶段流水线、Agent 协作讨论、算法推荐与论文预览

---

## 技术架构

### 借鉴与融合

本系统并非从零构建，而是在深入理解两个优秀开源项目的基础上，针对数学建模场景进行了大量场景化改造：

| 来源 | 借鉴内容 | 我们的改造 |
|------|---------|-----------|
| **LLM-MM-Agent** | Coordinator + DAG 调度、Critique-Improvement 质量循环、四阶段工作流、HMML 方法知识库 | 统一单一流水线、扩展为 20 维评估体系、预生成大纲 + 字数保障 |
| **Cherry Studio** | Provider 多 LLM 抽象、Agent 注册表、RAG 知识库、MCP Hub | 新增 Claude CLI Provider、8 种数学建模专用角色、算法库集成 |

### 自主设计

- **显式记忆池**（Explicit Memory Pool）：5 类结构化摘要跨阶段传递，替代文本截断
- **代码执行闭环**：纯净代码提取 → 隔离执行 → 结果契约（JSON）→ 自动修复（最多 4 轮）
- **算法知识库检索**：基于问题描述自动从 15 类算法中推荐 top-3 适用方法并注入 Prompt
- **内容净化层**：自动过滤 LLM 幻觉输出的题目原文、重复标题等污染内容
- **Provider Fallback 链**：API 失败自动回退到 Claude CLI，确保高可用
- **Web 前端重构**：组件化四阶段流水线可视化、实时 Agent 讨论、论文预览、算法推荐展示

---

## 快速开始

### 环境要求

- Python 3.9+
- Node.js 18+（如需使用 Web UI）
- 至少配置一个 LLM API Key（见下方）

### 安装依赖

```bash
# Python 后端依赖
pip install -r requirements.txt

# 前端依赖（如需使用 Web UI）
cd frontend && npm install
```

### 配置 LLM

**方案 A：Anthropic API（推荐）**

```bash
export ANTHROPIC_API_KEY="your-api-key"
```

**方案 B：OpenAI API**

```bash
export OPENAI_API_KEY="your-api-key"
```

**方案 C：本地 Ollama（免费）**

```bash
export OLLAMA_MODEL="qwen2.5:14b"
export OLLAMA_HOST="http://localhost:11434"
```

**方案 D：Claude Code CLI（备用）**

```bash
npm install -g @anthropic-ai/claude-code
# 无需 API Key，但需登录 Anthropic 账号
```

> 系统支持多 Provider fallback：Anthropic → OpenAI → Gemini → Ollama → Claude CLI，无需手动切换。

### 准备赛题与数据

将文件放在项目根目录：

- **赛题文件**：`problem.md` 或 `2024A-Problem.md` 等包含"题目/赛题/problem"的 `.md` 文件
  - 也支持 `.pdf` 格式，系统会自动提取文本和图片
- **数据文件**：`result1.xlsx`, `result2.xlsx` 等 Excel 文件

---

## 使用方式

### 方式一：命令行（CLI）

适合自动化脚本、服务器部署或无图形界面环境。

```bash
# 全自动生成（默认数学建模模板）
python main.py --auto

# 指定输出目录
python main.py --auto --output-dir work_custom

# 禁用 Critique 加速（适合快速测试）
python main.py --auto --no-critique

# 使用课程作业模板
python main.py --auto --template coursework
```

### 方式二：Web UI（推荐）

适合可视化操作、实时监控生成进度、查看算法推荐与论文预览。

**1. 启动后端（FastAPI）**

```bash
# 在项目根目录
python -m backend.app.main
# 或
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

后端服务将运行在 `http://localhost:8000`，API 文档地址：`http://localhost:8000/docs`

**2. 启动前端（Next.js）**

```bash
cd frontend
npm run dev
```

前端服务将运行在 `http://localhost:3000`

**3. 打开浏览器访问 `http://localhost:3000`**

Web UI 功能：
- **🏠 首页**：系统状态检测 + 赛题输入（支持 OCR/PDF 上传、工作流选择、模板选择）
- **🚀 生成**：实时四阶段流水线进度 + Agent 团队讨论 + 暂停/恢复
- **📁 数据**：数据文件上传与管理（CSV / Excel / JSON / 图片 / PDF）
- **📋 历史**：历史任务列表、详情查看（含算法推荐、论文预览 Markdown/LaTeX、导出到桌面）
- **⚙️ 设置**：API 密钥配置

### 查看结果

生成完成后，交付物位于 `work/final/`：

```
work/final/
├── MathModeling_Paper.md          # 完整论文（Markdown）
├── MathModeling_Paper.tex         # LaTeX 源文件（JXUSTmodeling 模板）
├── MathModeling_Paper.pdf         # 排版后的 PDF（竞赛标准格式）
├── 数学建模论文.docx               # Word 格式论文（备用）
├── solution.json                  # 完整解决方案（含子任务结果）
├── memory_pool.json               # 显式记忆池（阶段摘要）
└── chapter_summaries.json         # 各章结构化摘要
```

---

## 系统架构

### 四阶段流水线

```
┌─────────────────────────────────────────────────────────────────────┐
│                    数学建模论文全自动生成系统 v2.1                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Stage 1: 问题分析 (Problem Analysis)                                │
│  ├── LLM 深度分析赛题，提取子任务、约束、数据需求                      │
│  ├── 构建 DAG 任务依赖图（5 种依赖类型）                               │
│  └── 生成 analysis_summary → memory_pool                             │
│                               ↓                                     │
│  Stage 2: 数学建模 (Mathematical Modeling)                           │
│  ├── 按 DAG 拓扑序逐任务建模                                          │
│  ├── 🔍 算法库检索：自动推荐 15 类经典算法中的适用方法                    │
│  ├── 生成变量定义表、核心公式（LaTeX）、模型假设                        │
│  └── 生成 modeling_summary → memory_pool                             │
│                               ↓                                     │
│  Stage 3: 计算求解 (Computational Solving)                           │
│  ├── 设计求解算法                                                     │
│  ├── 生成 Python 代码（纯净提取，去除 markdown 标记）                   │
│  ├── 隔离执行（subprocess 沙箱，60s 超时）                             │
│  ├── 自动修复循环（失败 → 分析 stderr → LLM 修复 → 重试，最多 4 轮）     │
│  └── 生成 algorithm_summary + results_summary → memory_pool          │
│                               ↓                                     │
│  Stage 4: 论文生成 (Paper Generation)                                │
│  ├── 预生成 12 章详细大纲（分批，每批 4 章）                            │
│  ├── 逐章生成：本章大纲 + 相关阶段摘要 + 前 2 章摘要                     │
│  ├── 每章：字数检查 → Critique-Improvement → 扩展 → 章节摘要            │
│  ├── 内容净化：过滤题目原文、重复标题                                   │
│  ├── 图表自动生成（基于计算结果绘制对比图、饼图，300 DPI PNG）            │
│  └── 组装完整论文 + LaTeX 排版 + Word 导出                             │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 显式记忆池

```
memory_pool
├── analysis_summary      # Stage 1 问题分析摘要（400-500 字）
│                         #   含：背景、子问题、核心假设、解决思路、关键约束
├── modeling_summary      # Stage 2 数学建模摘要（400-500 字）
│                         #   含：核心变量、核心公式、求解策略、子问题映射
├── algorithm_summary     # Stage 3 算法设计摘要（200-300 字）
│                         #   含：算法名称、输入、核心步骤、输出格式
├── results_summary       # Stage 3 计算结果摘要（400-500 字）
│                         #   含：关键数值表格、主要发现、可视化建议
└── chapter_summaries     # Stage 4 各章结构化摘要（200-300 字/章）
```

每份摘要严格限制长度，按固定结构组织，确保 LLM prompt 不会溢出。

---

## 算法知识库

系统集成了 15 类经典数学建模算法，共 67 个 MATLAB/Python 源文件。

### 支持的算法类别

| 类别 | 代表性方法 | 适用场景 |
|------|-----------|---------|
| **层次分析法 (AHP)** | 判断矩阵、一致性检验 | 多准则决策、权重确定、方案排序 |
| **元胞自动机** | 生命游戏、森林火灾、交通流 | 复杂系统演化模拟、空间动力学 |
| **模糊数学模型** | 模糊综合评价、模糊聚类 | 边界不清晰的不确定性问题 |
| **目标规划** | 偏差变量、优先级优化 | 多目标冲突优化、资源配置 |
| **图论** | Dijkstra、Floyd | 最短路径、网络优化、物流调度 |
| **灰色系统** | GM(1,1)、GM(2,1)、Verhulst | 小样本预测、中长期趋势分析 |
| **启发式算法** | 遗传算法、模拟退火、神经网络 | 组合优化、函数极值、参数调优 |
| **整数规划** | 0-1 变量、分支定界 | 指派问题、选址问题、背包问题 |
| **插值** | 拉格朗日、样条、双线性 | 缺失数据填补、曲线光滑、图像处理 |
| **线性规划** | 单纯形法 | 生产计划、运输问题、投资组合 |
| **多元分析** | 聚类分析、主成分分析 (PCA) | 数据降维、样本分类、特征提取 |
| **神经网络** | BP 网络、LVQ | 非线性回归、模式识别、时间序列 |
| **非线性规划** | 梯度下降、拟牛顿法 | 工程设计优化、参数估计 |
| **回归分析** | 线性回归、多项式回归、逐步回归 | 趋势预测、因素分析、因果推断 |
| **时间序列** | 移动平均、指数平滑、自适应滤波 | 经济指标预测、销售量预测 |

### 自动检索机制

在 Stage 2 数学建模阶段，系统对每个子任务自动执行：

1. **关键词提取**：从 `task_description + problem_text` 中提取中/英文关键词
2. **相关度计算**：基于 tag 匹配、场景匹配、描述匹配、子类型匹配计算综合分数
3. **Top-3 推荐**：将最相关的算法（含名称、描述、数学模型、优缺点）注入建模 Prompt
4. **显式约束**：Prompt 中要求"若算法库推荐了适用的算法，请在模型中明确采用并说明理由"

---

## 项目结构

```
MathModel-MutiAgentSystem/
├── main.py                          # CLI 主入口
├── requirements.txt                 # Python 依赖清单
├── build_algorithm_library.py       # 算法知识库索引构建脚本
├── README.md                        # 本文档
├── 技术说明文档.md                   # 详细技术说明（借鉴与自主设计）
│
├── backend/                         # FastAPI 后端服务
│   ├── app/
│   │   ├── main.py                  # FastAPI 入口
│   │   ├── schemas.py               # Pydantic 模型定义
│   │   ├── routers/                 # API 路由（tasks / data / workflows / agents）
│   │   ├── agents/                  # Agent 实现（Orchestrator + 7 个专用 Agent）
│   │   ├── core/                    # 任务持久化、路径管理、运行时配置
│   │   └── config.py                # 配置管理
│   └── data/
│       └── uploads/                 # 上传的数据文件存储
│
├── frontend/                        # Next.js 前端界面
│   ├── src/app/
│   │   ├── page.tsx                 # 主页面（Dashboard / Generate / Files / History / Settings）
│   │   ├── layout.tsx               # 根布局
│   │   └── components/              # 组件目录
│   │       ├── StageProgress.tsx    # 四阶段流水线可视化
│   │       ├── ProblemInput.tsx     # 赛题输入（OCR / 模板 / 工作流选择）
│   │       ├── AgentChat.tsx        # Agent 实时讨论
│   │       ├── SystemStatus.tsx     # 系统状态面板
│   │       ├── TaskHistory.tsx      # 历史任务列表
│   │       ├── TaskDetail.tsx       # 任务详情（含算法推荐、论文预览）
│   │       ├── PaperPreview.tsx     # Markdown / LaTeX 论文预览
│   │       ├── AlgorithmRecommend.tsx # 算法推荐展示
│   │       └── FileManager.tsx      # 数据文件管理
│   └── package.json
│
├── src/                             # 核心源码（CLI 与后端共用）
│   ├── agent_workflow.py            # 统一工作流引擎 v2.1（核心）
│   ├── framework.py                 # 模板驱动工作流（兼容层）
│   ├── workflow/                    # 工作流模块
│   │   ├── paper_generator.py       # 大纲驱动分段论文生成器
│   │   ├── critique_engine.py       # Actor-Critic-Improvement 质量引擎
│   │   ├── code_executor.py         # 代码生成 + 自动执行 + 结果读取
│   │   ├── coordinator.py           # DAG 调度器 + 黑板内存
│   │   ├── templates.py             # 论文模板定义（3 种模板）
│   │   └── ...
│   ├── agents/                      # Agent 管理系统（借鉴 Cherry Studio）
│   │   ├── manager/                 # Agent 管理器、注册表、工厂
│   │   ├── solver_agent.py          # 自修复求解 Agent
│   │   └── ...
│   ├── llm/                         # 多 LLM Provider 抽象层
│   │   ├── base.py                  # Provider 基类
│   │   ├── factory.py               # Provider 工厂
│   │   └── providers/               # Anthropic/OpenAI/Gemini/Ollama/ClaudeCLI
│   ├── knowledge/                   # 知识库与 RAG
│   │   ├── algorithm_library.py     # 算法检索与推荐引擎
│   │   ├── algorithm_index.json     # 算法知识库索引（15 类 / 67 文件）
│   │   ├── knowledge_base.py        # RAG 知识库
│   │   ├── embeddings.py            # 向量嵌入模型
│   │   └── vector_store.py          # 向量存储与检索
│   ├── mcp/                         # MCP 工具管理（借鉴 Cherry Studio）
│   └── document_processing/         # 文档加载器（Excel/Markdown/PDF）
│
├── work_2024A/                      # 示例输出（2024A 板凳龙题目）
│   ├── stage_1_analysis/            # 问题分析结果
│   ├── stage_2_modeling/            # 数学建模公式
│   ├── stage_4_coding/              # 生成代码
│   ├── stage_5_execution/           # 执行结果
│   ├── stage_7_charts/              # 自动生成图表
│   └── final/                       # 最终交付物
│       ├── MathModeling_Paper.md
│       ├── MathModeling_Paper.tex
│       ├── MathModeling_Paper.pdf
│       ├── 数学建模论文.docx
│       └── ...
│
├── 2024A-cn/                        # 示例赛题素材
│   ├── A题.pdf                      # 原始赛题 PDF
│   ├── page_1.png ~ page_3.png      # PDF 转图片（视觉分析用）
│   └── 附件/                        # 数据文件
│
├── 2024A-Problem.md                 # 视觉理解后撰写的赛题描述
├── result1.xlsx                     # 数据文件
├── result2.xlsx
└── result4.xlsx
```

---

## API 说明

后端提供 RESTful API，所有接口前缀为 `/api/v1`。

### 核心端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/tasks/submit` | 提交任务 |
| `GET`  | `/tasks/{id}/status` | 查询任务状态 |
| `GET`  | `/tasks/{id}/stream` | SSE 实时进度流 |
| `GET`  | `/tasks/{id}/result` | 获取任务结果 |
| `GET`  | `/tasks/{id}/messages` | 获取 Agent 讨论消息 |
| `POST` | `/tasks/{id}/pause` | 暂停任务 |
| `POST` | `/tasks/{id}/resume` | 恢复任务 |
| `POST` | `/tasks/export` | 导出结果到桌面 |
| `POST` | `/data/upload` | 上传数据文件 |
| `GET`  | `/data/files` | 列出已上传文件 |
| `GET`  | `/workflows` | 列出预定义工作流 |
| `GET`  | `/info` | 系统信息（Provider 状态等） |
| `POST` | `/settings` | 更新运行时设置 |

完整 API 文档启动后端后访问：`http://localhost:8000/docs`

---

## 论文输出规格

| 指标 | 规格 |
|------|------|
| **总字数** | 18000-25000 中文字符 |
| **结构** | 摘要、问题重述、问题分析、模型假设、符号说明、模型建立、模型求解、结果分析、灵敏度分析、模型评价与改进、参考文献、附录 |
| **公式** | LaTeX 格式，完整编号与推导 |
| **图表** | 自动生成的对比图/饼图（300 DPI PNG）+ Markdown 表格 |
| **代码** | Python 实现，附录或独立文件 |
| **格式** | Markdown + LaTeX PDF（JXUSTmodeling 模板）+ Word（.docx） |

---

## 配置说明

### 论文模板

支持三种模板：

| 模板 | 说明 | 章节数 |
|------|------|--------|
| `math_modeling` | 数学建模竞赛论文（MCM/ICM/高教社杯标准） | 12 |
| `coursework` | 一般课程作业论文 | 8 |
| `financial_analysis` | 金融数据分析与投资报告 | 10 |

### 工作流模式

| 模式 | 说明 |
|------|------|
| `standard` | 标准流程：研究 → 分析 → 建模 → 求解 → 论文 |
| `quick` | 快速生成：跳过研究阶段 |
| `deep_research` | 深度研究：强化资料搜集 |
| `code_focused` | 代码优先：强化求解与调试 |

### 可选环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `ANTHROPIC_API_KEY` | Anthropic API 密钥 | - |
| `OPENAI_API_KEY` | OpenAI API 密钥 | - |
| `GEMINI_API_KEY` | Google Gemini API 密钥 | - |
| `OLLAMA_MODEL` | Ollama 本地模型名 | - |
| `OLLAMA_HOST` | Ollama 服务地址 | `http://localhost:11434` |
| `ANTHROPIC_BASE_URL` | Anthropic API 代理地址 | - |

---

## 故障排除

### LLM 调用超时或失败

**现象**：`The read operation timed out` 或 `RuntimeError: LLM 调用失败`

**解决**：
- 检查是否配置了至少一个 API Key：`echo $ANTHROPIC_API_KEY`
- 检查网络连接（如需代理，设置 `ANTHROPIC_BASE_URL`）
- 使用 `--no-critique` 跳过质量评估循环以减少调用次数
- 改用 Ollama 本地模型，完全离线运行

### 代码执行失败

**现象**：`success=False` 或 `results.json` 为空

**解决**：
- 系统已内置自动修复循环（最多 4 次尝试）
- 检查 `work/execution/solve.py` 中的代码逻辑
- 手动运行：`cd work/execution && python solve.py`
- 检查是否缺少依赖：`pip install numpy pandas scipy matplotlib openpyxl`

### LaTeX 编译失败

**现象**：`xelatex` 报错或缺少字体

**解决**：
- 安装完整 TeX Live：`sudo apt install texlive-xetex texlive-lang-chinese texlive-fonts-extra`
- 或安装简化版后手动安装缺失包
- 系统会自动将 `SimSun` 替换为 `Noto Serif CJK SC`（Linux 可用字体）

### 论文字数不足

**现象**：某章字数远低于目标

**解决**：
- 系统会自动触发扩展机制（调用 LLM 增加推导和分析）
- 检查赛题文件是否包含足够的信息和约束条件
- 检查数据文件是否有效且被正确读取

### 前端无法连接后端

**现象**：Web UI 显示"无法连接到后端"

**解决**：
- 确认后端已启动：`curl http://localhost:8000/health`
- 检查浏览器控制台网络请求是否被 CORS 拦截
- 前端通过 `window.__API_BASE__` 自动推断后端地址，确保前后端在同一域名或正确配置跨域

---

## 版本历史

| 版本 | 日期 | 主要更新 |
|------|------|----------|
| **v2.1** | 2026-05-01 | 分段逐章生成 + 显式记忆池 + 算法知识库集成 + LaTeX 模板排版 + 视觉理解 + Web UI 重构 |
| **v2.0** | 2026-04-29 | 统一工作流引擎 + Critique-Improvement + 代码自动执行 + Word 导出 |
| **v1.0** | 2026-04-25 | 初始多 Agent 协作框架 |

---

## 许可证

MIT License

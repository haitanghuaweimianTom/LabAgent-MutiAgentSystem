# 数学建模论文自动生成系统 v2.1

> 全自动分段生成 + 显式记忆池 + 多Agent协作

## 概述

本项目是一个基于大语言模型（LLM）和多Agent协作架构的**数学建模竞赛论文全自动生成系统**。用户只需提供赛题描述（Markdown）和数据文件（Excel），系统即可自动完成从问题分析、数学建模、算法设计、代码执行到完整论文生成的全部工作，最终交付可直接提交的数学建模论文（Markdown + Word）。

### v2.1 核心升级

- **分段逐章生成**：论文不再一次性生成，而是按12个标准章节逐章生成，每章调用独立LLM请求
- **显式记忆池**：每阶段完成后自动生成结构化摘要，后续阶段显式调用，确保上下文衔接
- **预生成大纲**：正式写章前先批量生成各章详细大纲，避免LLM偏离主题
- **章节摘要机制**：每章生成后自动提炼200-300字摘要，供后续章节引用衔接
- **内容净化层**：自动检测并过滤LLM输出的题目原文、重复标题等污染内容

---

## 核心特性

| 特性 | 说明 |
|------|------|
| **全自动工作流** | 一键运行，无需人工干预，完成分析→建模→算法→代码→论文全链路 |
| **分段记忆衔接** | 显式Memory Pool传递阶段摘要，论文各章逻辑连贯、数据一致 |
| **Critique-Improvement** | Actor-Critic质量评估循环，自动改进低质量内容 |
| **代码自动执行** | 生成Python代码并自动运行，提取数值结果写入论文 |
| **图表自动生成** | 基于计算结果自动绘制对比图、饼图等可视化图表 |
| **Word自动导出** | 论文自动生成 .docx 格式，可直接提交 |
| **多模板支持** | 支持数学建模、课程作业、金融分析三种论文模板 |
| **Provider fallback** | API超时自动回退到Claude CLI，确保高可用性 |

---

## 快速开始

### 环境要求

- Python 3.9+
- 依赖包（见 `requirements.txt`）

### 安装依赖

```bash
pip install -r requirements.txt
```

### 准备文件

将以下文件放在项目根目录：

- **赛题文件**：`problem.md` 或 `2025A-Problem.md` 或包含"题目/赛题/problem"的 `.md` 文件
- **数据文件**：`result1.xlsx`, `result2.xlsx`, ...（任意 `.xlsx` 文件，排除 config/settings）

### 运行生成

```bash
# 全自动生成（默认数学建模模板）
python main.py --auto

# 指定输出目录
python main.py --auto --output-dir work_custom

# 使用课程作业模板
python main.py --auto --template coursework

# 禁用Critique加速
python main.py --auto --no-critique
```

### 查看结果

生成完成后，所有交付物位于 `work/final/`：

```
work/final/
├── MathModeling_Paper.md      # 完整论文（Markdown）
├── 数学建模论文.docx           # Word格式论文
├── solution.json              # 完整解决方案（含5个子任务结果）
├── memory_pool.json           # 显式记忆池（阶段摘要）
└── chapter_summaries.json     # 各章结构化摘要
```

---

## 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                     数学建模论文自动生成系统 v2.1                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   Stage 1: 问题分析                                              │
│   ├── 生成问题分析摘要 → memory_pool["analysis_summary"]         │
│   └── 构建DAG任务依赖图                                          │
│                              ↓                                  │
│   Stage 2: 数学建模（逐任务）                                     │
│   ├── task_1 ~ task_n 分别建模                                   │
│   └── 生成建模摘要 → memory_pool["modeling_summary"]             │
│                              ↓                                  │
│   Stage 3: 计算求解                                              │
│   ├── 设计算法 → memory_pool["algorithm_summary"]                │
│   ├── 生成代码 → work/execution/solve.py                         │
│   ├── 自动执行 → work/execution/results.json                     │
│   └── 结果解读 → memory_pool["results_summary"]                  │
│                              ↓                                  │
│   Stage 4: 论文生成（分段逐章 + 记忆衔接）                         │
│   ├── 预生成各章大纲（分批，每批4章）                             │
│   ├── 逐章生成：本章大纲 + 相关摘要 + 前2章摘要                    │
│   ├── 每章：字数检查 → Critique → 扩展 → 章节摘要                │
│   └── 组装完整论文 + 导出Word                                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 显式记忆池（v2.1 核心）

```
memory_pool
├── analysis_summary      # Stage 1 问题分析摘要（400-500字）
├── modeling_summary      # Stage 2 数学建模摘要（400-500字）
├── algorithm_summary     # Stage 3 算法设计摘要（200-300字）
├── results_summary       # Stage 3 计算结果摘要（400-500字）
└── chapter_summaries     # Stage 4 各章结构化摘要（200-300字/章）
```

每份摘要严格限制长度，按固定结构组织（结论/数据/衔接点），确保LLM prompt不会溢出。

---

## 项目结构

```
MathModel-MutiAgentSystem/
├── main.py                          # 主入口（命令行参数解析）
├── requirements.txt                 # Python依赖
├── src/
│   ├── agent_workflow.py            # 统一工作流引擎 v2.1（核心）
│   ├── workflow/
│   │   ├── paper_generator.py       # 大纲驱动分段论文生成器
│   │   ├── critique_engine.py       # Actor-Critic质量评估引擎
│   │   ├── code_executor.py         # 代码生成+自动执行+结果读取
│   │   ├── templates.py             # 论文模板定义
│   │   └── ...                      # 其他工作流模块
│   ├── providers.py                 # 多LLM Provider抽象层
│   └── ...                          # 其他模块
├── work/                            # 默认输出目录（示例）
│   ├── stage_1_analysis/            # 问题分析结果
│   ├── stage_2_modeling/            # 数学建模公式与JSON
│   ├── stage_3_algorithm/           # 算法设计
│   ├── stage_4_coding/              # 生成代码
│   ├── stage_5_execution/           # 执行结果
│   ├── stage_7_charts/              # 自动生成图表
│   └── final/                       # 最终交付物
│       ├── MathModeling_Paper.md
│       ├── 数学建模论文.docx
│       ├── solution.json
│       ├── memory_pool.json
│       └── chapter_summaries.json
├── 2025A-Problem.md                 # 示例赛题（2025高教社杯A题）
├── result1.xlsx                     # 示例数据文件
├── result2.xlsx
├── result3.xlsx
└── README.md
```

---

## 论文输出规格

生成的论文满足数学建模竞赛（MCM/ICM/高教社杯）标准格式：

| 指标 | 规格 |
|------|------|
| **总字数** | 20000-25000 中文字符 |
| **结构** | 摘要、问题重述、问题分析、模型假设、符号说明、模型建立、模型求解、结果分析、灵敏度分析、模型评价与改进、参考文献、附录 |
| **公式** | LaTeX格式，完整编号与推导 |
| **图表** | 自动生成的对比图/饼图，Markdown表格 |
| **代码** | Python实现，附于附录或独立文件 |
| **格式** | Markdown + Word (.docx) 双格式 |

---

## 配置说明

### LLM Provider

系统支持多Provider fallback链：

1. **Anthropic API**（首选）：通过 `anthropic` SDK调用，支持长上下文
2. **Claude CLI**（回退）：通过 `claude` 命令行工具调用，API超时时自动切换

Provider配置在代码中自动初始化，无需手动配置。

### 论文模板

支持三种模板，通过 `--template` 参数指定：

| 模板 | 说明 | 章节数 |
|------|------|--------|
| `math_modeling` | 数学建模竞赛论文（MCM/ICM/高教社杯标准） | 12 |
| `coursework` | 一般课程作业论文 | 8 |
| `financial_analysis` | 金融数据分析与投资报告 | 10 |

---

## 故障排除

### 1. LLM调用超时

**现象**：`The read operation timed out`

**解决**：系统已内置3次重试 + Claude CLI回退机制。如持续超时，可：
- 检查网络连接
- 使用 `--no-critique` 跳过质量评估以加速

### 2. 论文字数不足

**现象**：某章字数远低于目标

**解决**：系统会自动触发扩展机制。如扩展失败，检查：
- 赛题文件是否包含足够信息
- 数据文件是否有效
- 是否启用了 `--no-critique`（禁用后扩展仍生效）

### 3. 代码执行失败

**现象**：`execution_result.json` 为空或报错

**解决**：系统会自动修复常见代码错误（最多4次尝试）。如仍失败：
- 检查 `work/execution/solve.py` 代码逻辑
- 手动安装缺失的依赖包

### 4. 论文章节出现题目原文

**现象**：某章开头出现赛题原文

**解决**：v2.1已增加 `_sanitize_chapter_content` 净化层，自动过滤题目原文和重复标题。如仍出现，请检查 `paper_generator.py` 中的 `problem_markers` 列表是否包含该赛题特征文本。

---

## 版本历史

| 版本 | 日期 | 主要更新 |
|------|------|----------|
| **v2.1** | 2026-05-01 | 分段逐章生成 + 显式记忆池 + 预生成大纲 + 章节摘要 + 内容净化层 |
| **v2.0** | 2026-04-29 | 统一工作流引擎 + Critique-Improvement + 代码自动执行 + Word导出 |
| **v1.0** | 2026-04-25 | 初始多Agent协作框架 |

---

## 许可证

MIT License

# 数学建模多Agent论文自动生成系统

## 概述

通用数学建模框架，采用多Agent协作工作流，支持上传赛题和数据文件后自动生成15000-25000字的完整数学建模论文。


具体交付效果请查看work文件夹（2025国赛B题的建模论文及代码的结果）
### 核心特性

- **多Agent协作**：问题分析Agent、数学建模Agent、算法设计Agent、代码编写Agent、结果分析Agent、论文撰写Agent
- **全自动生成**：只需提供赛题（Markdown格式）和数据文件（Excel格式），自动完成全部工作
- **LLM驱动**：集成Claude Code CLI，使用大语言模型生成高质量论文内容
- **通用框架**：可用于任意数学建模问题，不局限于特定领域

## 快速开始

### 环境要求

- Python 3.8+
- Claude Code CLI (需安装并配置)
- 依赖包: numpy, scipy, matplotlib, openpyxl, pandas

### 安装依赖

```bash
pip install numpy scipy matplotlib openpyxl pandas
```

### 安装Claude Code CLI

确保已安装Claude Code并添加到PATH：

```bash
# 检查是否已安装
which claude-code

# 如果未安装，请参考Claude Code官方文档进行安装
```

### 运行

```bash
# 全自动生成论文（推荐）
python main.py --auto

# 查看生成的论文
cat work/final/MathModeling_Paper.md
```

## 使用方法

### 1. 准备文件

将以下文件放在项目根目录：

- `problem.md` 或 `2025B-Problem.md` 或 `题目.md` - 赛题/问题描述（Markdown格式）
- `附件1.xlsx`, `附件2.xlsx`, ... - 数据文件（Excel格式）

赛题文件应为Markdown格式，包含：
- 问题背景描述
- 具体问题要求
- 数据文件说明

### 2. 运行生成

```bash
python main.py --auto
```

系统会自动：
- 检测并加载赛题文件
- 检测并加载数据文件
- 依次完成问题分析、数学建模、算法设计、代码编写
- 执行计算获得结果
- 生成图表设计
- 撰写完整论文

### 3. 查看结果

- 最终论文：`work/final/MathModeling_Paper.md`
- 各阶段输出：`work/stage_X/` 目录
- 求解代码：`work/stage_4_coding/solve.py`

## 工作流程

```
┌─────────────────────────────────────────────────────────────┐
│                 多Agent协作工作流程                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  问题分析Agent → 数学建模Agent → 算法设计Agent             │
│         ↓              ↓              ↓                   │
│    问题分析         数学模型         算法设计                │
│         ↓              ↓              ↓                   │
│  代码编写Agent → 执行计算Agent → 结果分析Agent              │
│         ↓              ↓              ↓                   │
│      代码          计算结果        结果分析                 │
│                                                             │
│                           ↓                                 │
│                    论文撰写Agent                             │
│                           ↓                                 │
│                    完整论文（15000-25000字）                 │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 阶段说明

| 阶段 | Agent | 说明 | 输出 |
|------|-------|------|------|
| 1. 问题分析 | problem_analyzer | 分析赛题，提取关键信息 | 结构化分析结果 |
| 2. 数学建模 | model_designer | 建立数学模型 | 模型公式 |
| 3. 算法设计 | algorithm_designer | 设计求解算法 | 算法伪代码 |
| 4. 代码编写 | code_writer | 编写Python代码 | solve.py |
| 5. 执行计算 | executor | 运行代码 | 计算结果 |
| 6. 结果分析 | result_analyzer | 分析结果 | 分析报告 |
| 7. 图表设计 | chart_designer | 设计论文图表 | 图表方案 |
| 8. 论文撰写 | paper_writer | 生成完整论文 | MathModeling_Paper.md |

## 项目结构

```
MathModel-MutiAgentSystem/
├── main.py                    # 主入口
├── src/
│   ├── agent_workflow.py      # Agent工作流引擎（集成LLM调用）
│   ├── prompts.py             # Agent提示词模板
│   ├── workflow.py            # 分步骤工作流程框架
│   ├── framework.py           # 通用框架
│   ├── data/                  # 数据加载模块
│   ├── models/                # 数学模型
│   ├── solver/                # 求解器
│   ├── visualization/         # 可视化
│   ├── paper/                 # 论文生成
│   └── agents/                # Agent模块
├── work/                      # 工作目录（生成后）
│   ├── stage_1_analysis/      # 问题分析
│   ├── stage_2_modeling/      # 数学建模
│   ├── stage_3_algorithm/     # 算法设计
│   ├── stage_4_coding/        # 代码编写
│   ├── stage_5_execution/     # 执行计算
│   ├── stage_6_result_analysis/ # 结果分析
│   ├── stage_7_charts/        # 图表设计
│   └── final/                 # 最终论文
│       └── MathModeling_Paper.md
├── 2025B-Problem.md          # 赛题示例
├── 附件1.xlsx                 # 数据文件示例
└── README.md
```

## 论文输出规格

生成的论文满足以下规格：

- **字数**：正文15000-25000字
- **结构**：包含摘要、问题重述、问题分析、模型假设、模型建立、模型求解、结果分析、灵敏度分析、模型评价、参考文献、附录
- **格式**：使用标准数学建模论文格式
- **公式**：使用LaTeX格式，完整推导
- **图表**：清晰的图表设计和说明

## 提示词模板

系统使用精心设计的提示词模板，包括：

- **problem_analyzer**：问题分析Agent提示词
- **model_designer**：数学建模Agent提示词
- **algorithm_designer**：算法设计Agent提示词
- **code_writer**：代码编写Agent提示词
- **result_analyzer**：结果分析Agent提示词
- **paper_writer**：论文撰写Agent提示词

这些提示词经过优化，确保生成的论文内容详尽、分析深入。

## 依赖说明

```
numpy>=1.20.0      # 数值计算
scipy>=1.7.0       # 科学计算
matplotlib>=3.4.0  # 图表生成
openpyxl>=3.0.0   # Excel数据读取
pandas>=1.3.0     # 数据处理
```

## 注意事项

1. **Claude Code CLI**：必须安装并配置好API密钥
2. **数据文件格式**：Excel (.xlsx)，支持多列数据
3. **赛题文件格式**：Markdown (.md)
4. **生成时间**：完整论文生成可能需要5-10分钟
5. **论文输出**：为Markdown格式，可转换为LaTeX或Word

## 故障排除

### LLM调用失败

如果遇到"Claude Code CLI未找到"错误：
1. 确认已安装Claude Code
2. 确认Claude Code在PATH中
3. 确认已配置API密钥

### 论文字数不足

确保：
1. 赛题文件内容详尽
2. 数据文件有效
3. LLM调用正常

### 数据加载失败

检查Excel文件：
1. 文件格式是否为.xlsx
2. 数据是否在第一个工作表
3. 数据是否包含数值列

## 版本历史

- **v2.1.0** (2026-04-25) - 集成LLM调用，支持全自动论文生成
- **v2.0.0** (2026-04-25) - 通用分步骤工作流程框架
- **v1.0.0** - 初始SiC专用版本

## 许可证

MIT License

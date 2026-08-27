# MathModel-MutiAgentSystem

> **从想法到论文，一步到位。**  
> 多智能体协作系统，自动生成学术论文 —— 数学建模竞赛、课程作业、科研论文，全覆盖。

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-186%20passed-brightgreen.svg)](tests/)

---

## 为什么要做这个？

写论文太慢？建模太累？代码跑不通？

**LabAgent：把「想法 → 论文」的周期从几天压缩到几分钟。**

输入一个问题描述，系统自动完成：
- 📚 文献调研（真实 arXiv 论文，不是编的）
- 📐 数学建模（自动选择算法）
- 💻 代码生成 + 执行（沙箱隔离，自动修 bug）
- 📝 论文写作（LaTeX 排版，专业格式）
- 🔍 同行评审（4 维度打分，自动修订）
- 📊 图表生成（Nature 风格配色）

---

## 核心亮点

### 🎯 三层保障，杜绝三大痛点

| 痛点 | 解决方案 | 实现 |
|------|---------|------|
| **排版乱码** | LaTeX 智能转义 | 数学模式保护、CJK 支持、格式验证 |
| **参考文献造假** | 多层验证 | arXiv API 校验 + 标题匹配 + 引用去重 |
| **想法重复** | 历史指纹 | Jaccard 相似度检测，>70% 自动拦截 |

### 🛡️ 代码沙箱，安全执行

```
生成代码 → AST 审计（检测硬编码） → 自动安装依赖 → 沙箱执行 → 失败自动修复
    ↓              ↓                    ↓              ↓            ↓
 LLM 生成      拒绝 accuracy=0.95    pip install     隔离环境    LLM 重写代码
```

- **AST 审计**：检测硬编码指标、input() 调用、语法错误
- **依赖自愈**：检测缺失包，自动 pip install（复用 conda 环境）
- **自动修复**：执行失败时，LLM 分析错误并重写代码（最多 2 次）

### 🤖 6人多视角辩论，不是一个人说了算

```
研究方向 → Planner（策略规划）    ─┐
         → Experimenter（实验设计）─┼→ 结构化综合 → 最终决策
         → Critic（质量评审）      ─┤
         → Skeptic（魔鬼代言人）   ─┤
         → Writer（论文结构）      ─┤
         → Editor（语言编辑）      ─┘
```

参考 Sibyl 的6人辩论系统，从不同角度评估方案，避免单一模型盲区。

### 🧬 自进化系统，越用越聪明

```
每次运行 → 提取教训 → 存储 → 注入下次运行 → 自动改进
    ↓           ↓        ↓           ↓
  记录错误   分类总结   JSONL存储   生成prompt overlay
```

- **7大类教训**：系统、实验、写作、分析、文献、流水线、创意
- **时间衰减**：近期教训权重更高（30天半衰期）
- **跨项目学习**：每个项目的经验都会惠及后续项目

### 🧠 持久化记忆，跨项目知识积累

```
项目经验 → 记忆存储 → 语义检索 → 注入新项目
    ↓           ↓           ↓           ↓
 成功模式   分类存储   相似度匹配   提升决策质量
```

- **7大类记忆**：创意、实验、写作、分析、参考、系统、流水线
- **语义检索**：基于内容相似度和时间衰减的智能召回
- **跨项目**：一个项目的成功经验可以应用到其他项目

### 🎯 HITL 人机协作，关键决策由你掌控

```
自动暂停 → 展示选项 → 等待决策 → 继续执行
    ↓           ↓           ↓           ↓
 6种模式    结构化问题   交互式提示   自动/手动
```

- **6种干预模式**：方向选择、设计审批、PIVOT决策、论文评审、最终批准、紧急处理
- **自动模式**：默认自动决策，关键节点可切换为手动
- **完整日志**：所有决策记录到磁盘，可追溯

### 🔄 自修复系统，自动处理错误

```
错误检测 → 分类诊断 → 自动修复 → 熔断保护
    ↓           ↓           ↓           ↓
 结构化捕获  9大类别    LLM修复建议   防止无限循环
```

- **9大错误类别**：语法、导入、运行时、超时、内存、API、逻辑、数据、未知
- **熔断器**：防止无限修复循环（最多3次尝试）
- **自动诊断**：根据错误类型提供修复建议

### 📊 自适应质量门禁，智能决策

```
质量评估 → 加权评分 → 自动决策 → 修订/继续/终止
    ↓           ↓           ↓           ↓
 多维度指标  动态阈值   基于历史    迭代优化
```

- **自适应阈值**：根据历史表现动态调整
- **修订追踪**：自动修订直到质量达标或达到上限
- **决策日志**：所有质量决策记录到磁盘

### 📊 质量门禁，步步把关

| 阶段 | 门禁规则 | 不通过处理 |
|------|---------|-----------|
| 文献调研 | ≥3 真实引用、≥200 字内容 | 警告 |
| 建模 | ≥1 子问题、≥3 符号 | 警告 |
| 代码 | 语法有效、≥10 行、有 print | 自动修复 |
| 写作 | ≥3 章节、≥100 字摘要、≥5 引用 | 警告 |
| 评审 | ≥2.0 分 | 自动修订（最多 2 轮） |

---

## 支持 12 种模板

| 模板 | 场景 | 级别 |
|------|------|------|
| `math_modeling` | 数学建模竞赛（CUMCM/MCM） | — |
| `neurips_2024` | NeurIPS | **CCF-A** |
| `iclr_2024` | ICLR | **CCF-A** |
| `icml_2024` | ICML | **CCF-A** |
| `aaai_2024` | AAAI | **CCF-A** |
| `acm_sigconf` | ACM 会议 | **CCF-A** |
| `ieee_conference` | IEEE 会议 | **CCF-A** |
| `springer_lncs` | Springer LNCS | CCF-B |
| `research_survey` | 综述论文 | — |
| `coursework` | 课程作业 | — |
| `financial_analysis` | 金融分析报告 | — |
| `presentation` | 演示文稿 | — |

**每个模板都有：**
- 风格指南（SKILL.md）
- 真实参考文献池（references.md）
- 检查清单（checklist）

---

## 快速开始

### 安装

```bash
git clone https://github.com/haitanghuaweimianTom/MathModel-MutiAgentSystem.git
cd MathModel-MutiAgentSystem
pip install -r requirements.txt
```

### 配置

```bash
cp .env.example .env
# 编辑 .env，填入 MiniMax API Key
```

### 运行

```bash
# 一行命令生成论文
python scripts/generate_paper.py \
  --template math_modeling \
  --problem "求解某物流网络的最优路径" \
  --project-name logistics_optimization \
  --output-dir ./outputs
```

### 输出结构

```
outputs/logistics_optimization/
├── paper.pdf           # 编译后的 PDF
├── paper.md            # Markdown 源
├── paper.tex           # LaTeX 源
├── code/model.py       # 可执行代码
├── figures/            # 图表
├── peer_review.md      # 同行评审
├── guarantee_report.md # 输出保障报告
├── evolution_report.md # 自进化报告（新增）
├── references.bib      # 参考文献
├── evolution/          # 自进化存储（新增）
│   └── lessons.jsonl   # 教训记录
├── memory/             # 持久化记忆（新增）
│   └── memory.jsonl    # 记忆存储
├── hitl/               # 人机协作记录（新增）
│   ├── intervention_requests.jsonl
│   └── intervention_responses.jsonl
├── healer/             # 自修复记录（新增）
│   └── errors.jsonl    # 错误记录
├── quality_gate/       # 质量门禁记录（新增）
│   └── quality_decisions.jsonl
└── README.md           # 项目说明
```

---

## 架构设计

```
┌─────────────────────────────────────────────────────────────────┐
│                        Pipeline 7 步                            │
├─────────────────────────────────────────────────────────────────┤
│  Step 1: 文献调研 ──→ Step 1b: 多模型辩论                       │
│      ↓                                                         │
│  Step 2: 数学建模 ──→ 质量门禁                                  │
│      ↓                                                         │
│  Step 3: 代码生成 ──→ AST 审计 ──→ 沙箱执行 ──→ 自动修复        │
│      ↓                                                         │
│  Step 4: 论文写作 ──→ 反模式检测                                │
│      ↓                                                         │
│  Step 5: 同行评审 ──→ 评分低时自动修订                           │
│      ↓                                                         │
│  Step 6: PDF 编译 ──→ 图表生成                                  │
│      ↓                                                         │
│  Step 7: 输出保障 ──→ 排版/引用/Idea 三重检查                    │
└─────────────────────────────────────────────────────────────────┘
```

### 核心模块

| 模块 | 文件 | 功能 |
|------|------|------|
| Pipeline | `scripts/generate_paper.py` | 7 步主流程 |
| 沙箱 | `scripts/sandbox_and_gates.py` | 代码执行 + 质量门禁 + 多模型辩论 |
| 保障 | `scripts/output_guarantee.py` | 排版/引用/Idea 三重检查 |
| 知识库 | `src/knowledge/template_skills/` | 12 模板 skill + 真实文献池 |

---

## 测试

```bash
# 运行全部测试
python -m pytest tests/ -v

# 运行特定测试
python -m pytest tests/test_sandbox_and_gates.py -v
python -m pytest tests/test_output_guarantee.py -v
```

**68 个测试，全部通过。**

---

## 技术栈

- **LLM**: MiniMax-M3（500K 上下文 / 512K 推理）
- **代码执行**: Python subprocess + AST 审计
- **图表**: Matplotlib（Nature 风格配色）
- **排版**: LaTeX + xelatex（支持 CJK）
- **文献**: arXiv API + CrossRef 验证

---

## 贡献

欢迎提交 Issue 和 Pull Request！

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'Add amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 创建 Pull Request

---

## 致谢

本项目参考了以下开源项目的设计：
- [MAARS](https://github.com/dozybot001/MAARS) - 多智能体研究系统
- [PoggioAI/MSc](https://github.com/PoggioAI/PoggioAI_MSc) - 多模型 counsel 协议
- [math_model](https://github.com/Linference/math_model) - 反模式检测设计
- [MARS](https://github.com/HarryYangthu/MARS-Multi-Agent-Research-System) - 质量门禁设计

---

## License

MIT License

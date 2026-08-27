# MathModel-MutiAgentSystem

> **从想法到论文，一步到位。**  
> 多智能体协作系统，自动生成学术论文 —— 数学建模竞赛、课程作业、科研论文，全覆盖。

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-68%20passed-brightgreen.svg)](tests/)

---

## 为什么要做这个？

写论文太慢？建模太累？代码跑不通？

**我们做了一个系统，把「想法 → 论文」的周期从几天压缩到几分钟。**

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

### 🤖 多模型辩论，不是一个人说了算

```
研究方向 → Practical（实用性） ─┐
         → Rigor（严谨性）   ─┼→ 结构化综合 → 最终决策
         → Narrative（叙事性）─┘
```

参考 MSc counsel 协议，3 个角色从不同角度评估方案，避免单一模型盲区。

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
├── references.bib      # 参考文献
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

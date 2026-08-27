---
name: research-survey-skill
description: Use when writing a research survey / deep literature review (8-chapter structure: landscape + gaps + cross-domain + ideas + reading list + datasets + results + conclusion, 10-30 pages, Chinese, numeric citations, claim-then-evidence, taxonomy-driven). Triggers on tasks like "write research survey", "literature review", "深度调研", "文献综述", "state-of-the-art survey".
---

# research_survey Skill

> 来源：基于 6 篇 arxiv 综述论文 + arxiv 2024 全学科目录验证（CS/q-fin.ST/q-fin.GN/q-bio.NC）
> 生成日期：2026-08-16
> 适用模板：`research_survey`（深度文献综述 / 调研报告）

## 1. 写作风格基线

**写作目标不是文献罗列，而是建立"分类 → 批判 → 创新"闭环**。在参考的 6 篇 arxiv 综述中（最长达 144 页、1081 引用的 *A Survey of Large Language Models*），顶级综述均满足三个共性：第一，给出**清晰的层级 taxonomy**（通常 3-4 级分类），第二，对每类方法显式标注**代表论文 + 关键贡献 + 优缺点**，第三，从分类中自然引出**研究空白**与**未来方向**。本模板的"全景图 → Research Gaps → 交叉学科启发 → 创新点提案"四章正是这一闭环的中文工程化落地。

**结构密度高、引用密度极高**。综述类论文典型 References 数：80-300+，如 `2303.18223`（144 页 / 1081 引用）、`2307.03109`（45 页 / 多维评估）、`2312.02783`（25 页 / 三分类法）。本模板要求"必读文献 10-15 篇"是底线，但实际正文引用通常 30-80 个 `\cite`（中文技术调研常见）。

**段落主张 + 证据二段式**。每个观点句必须紧随具体论文支撑（作者 + 年份 + 关键贡献），不允许出现"许多研究表明..."这类无源断言。中文写作时引用格式遵循 `\cite{key}`（numeric 风格，配合 `\bibliographystyle{plain}`，参考文献自动编号）。

**claim-then-evidence + 量化论据**。在描述某个 SOTA 时，必须给出量化数字（如 "在 ImageNet 1k 上达到 89.5% Top-1"）。当论文未给出统一指标时，需主动指出"各论文使用不同 benchmark，难以直接对比"，并用表格汇总。Markdown / 项目符号在 LaTeX 正文里**严禁**出现，全部用 `\begin{itemize}` / `\begin{enumerate}`。

**批判 + 启发并重**。综述不是文献赞美诗。第三章 Gaps 必须从方法、数据、评估、应用四个维度展开批判；第四章交叉学科启发必须给出**具体可迁移的理论或方法**（不是"启发"二字打住），例如："信息论中的 channel coding 可迁移到 federated learning 的通信压缩"。

## 2. 章节结构与命名约定

模板固定 8 章（与 `research_survey.json` chapter_plan 一致）：

1. **摘要（abstract）** — 300-500 字，包含：调研目标 / 核心领域 / 主要发现（3-5 个关键结论）/ 研究空白 / 创新点方向。关键词 5-8 个，中英文各半。
2. **一、研究全景图：现有方法分类与 SOTA 剖析** — 核心章节，按"方法 / 架构 / 范式"三级分类；每类含"核心思想 + 代表论文（名称+年份+关键贡献）+ 优缺点"；必须使用 `\begin{table}` 三线表对比各方法适用场景与性能。
3. **二、核心 Research Gaps 分析** — 核心价值所在。从多维度批判（方法、数据、评估、应用、理论），每个 Gap 必须说明"为什么重要 / 现有方法为什么无法解决 / 解决的技术挑战"，按"紧迫性 + 可行性"排序。
4. **三、交叉学科启发与迁移** — 跨学科章节。来源可以是：认知科学、分布式系统、控制论、信息论、生物学、博弈论、统计学、物理学等。对每个启发给出"如何迁移 / 具体技术路径 / 可行性 / 潜在价值"。
5. **四、论文创新点提案（核心部分）** — 最核心产出。3-5 个 Idea，每个必含：Idea Title（英文）/ Motivation & Gap / Core Methodology（具体算法/架构）/ Cross-Domain Inspiration / Experimental Design（指标 + Baseline + 场景）/ Expected Contribution / Potential Risks & Mitigation。**拒绝"简单增加容量"或"单纯拼接"**。
6. **五、调研必读文献清单** — 10-15 篇，按相关性排序，标注 `★★★必读 / ★★推荐 / ★参考`。覆盖：经典奠基 + 最新 SOTA + 交叉学科参考。
7. **六、数据集与实验设置** — 汇总数据集、评价指标、实验设置；用表格对比各数据集特点与适用场景；分析现有评估体系的不足。
8. **七、结果对比与讨论** — 对比各方法关键结果；讨论性能差异原因；指出方法适用场景；分析实验设计局限性。
9. **八、结论与展望** — 总结 3-5 条核心发现；指出最具潜力方向；给后续研究者建议。

**章节标题一律使用 `\section{...}`**；子章节用 `\subsection{...}`；中文标点统一（`，。；！？`），不使用全角空格。

## 3. 公式与符号使用

**公式环境**：`equation`（单行编号）、`align`（多行对齐）、`gather`（无对齐多行）、`cases`（分段函数）。重要公式加 `\label{eq:xxx}` 供 back-reference。

**典型符号约定**（按研究领域自适应）：
- ML / DL：`\mathcal{X}` 表示样本空间，`\mathbf{x}` 表示输入向量，`y` 表示标签，`\theta` 表示参数，`\mathcal{L}` 表示损失函数
- 金融 / 经济：`r_t` 表示收益率，`\mu` 表示均值收益，`\sigma` 表示波动率，`\mathbb{E}[\cdot]` 表示期望算子
- 物理 / 化学：`\psi` 表示波函数，`\nabla` 表示梯度算子，`\partial_t` 表示偏导
- 通用：`\mathbb{R}` 实数集，`\mathcal{H}` 假设空间

**Theorem / Proposition 比例**：综述类极少使用 `\begin{theorem}`，仅在第三、四章涉及理论分析时使用 1-2 个 Proposition 配合证明 sketch。完整证明放附录或留作 future work。

**数学密度**：综述类平均每页 2-5 个 display equations（远低于原创论文的 8-15 个），主要用于：分类框架图、关键公式复现、损失函数定义。

## 4. 引用风格

**Numeric 编号**：`\cite{key}` → `[12]`、`\citep{key}` → `[(12)]`（与 `plainnat` 配合）。本模板 `bib_style=plain`，使用 `\bibliographystyle{plain}`。**禁止 author-year**（`\citet{Smith2020}` ❌）。

**引用密度**：每段 2-4 个 `\cite` 是常态。Introduction 约 15-25 个引用，全景图约 30-60 个，Research Gaps 约 20-40 个，交叉学科启发约 15-30 个，创新点提案每个 Idea 约 5-10 个支撑文献。

**总引用数**：本调研报告 References 应 ≥ 50 条（中文技术综述的工程要求）；高水平英文综述 100-300+。

**中文引用约定**：直接用中文期刊名称 + 年份（如"张三 等, 2023"），或论文标题（避免 `\cite` 中文 key 的兼容问题，可在 bibtex 中使用拼音或缩写 key）。

**必读清单格式**（第五章）：
```
[1] 张三 等. *论文标题*. **会议/期刊**, 年份. ★★★必读
    一句话阅读指导：核心贡献 + 阅读理由。
```

## 5. 图表风格

**Figure 1**：通常是"分类框架图"或"研究全景图"，用 TikZ / drawio 嵌入 PDF。多 panel 时用 `(a) (b) (c)` 子标。

**Figure 2+**：方法对比、性能趋势、t-SNE 可视化、数据集示例。

**Caption 风格**：完整句子（不以句号结尾的 cmds 块 ❌），简短描述图像 + 关键 takeaway。如 *"图 1：现有方法分类全景图，按'范式 → 架构 → 代表方法'三级展开"*。

**Table 风格**：**强制 `booktabs` 三线表**（`\toprule` / `\midrule` / `\bottomrule`），列名带单位（`FID↓` / `PSNR↑`），数值带 std（`0.83 ± 0.01`），最优值加粗 (`\textbf{0.83}`)，次优下划线 (`\underline{0.85}`)。

**不确定性**：所有数字必须 ± std over ≥3 seeds 或 95% CI；multi-task 报告时额外给出任务间 std。

**典型表格**：
- 表 1：方法分类表（方法名 + 核心思想 + 发表年份 + 关键数据集 + 优缺点）
- 表 2：SOTA 性能对比表（任务 + 数据集 + 各方法得分 + 备注）
- 表 3：数据集汇总表（数据集名 + 规模 + 模态 + 评估指标 + 适用场景）

**可视化偏好**：分类树状图 > 性能雷达图 > 训练曲线 > t-SNE / UMAP 散点。

## 6. 真实综述示例（6 篇，均 WebFetch 验证过）

| arxiv-id | 标题 | 主题 | 关键数字 |
|---|---|---|---|
| [2303.18223] | A Survey of Large Language Models (Zhao et al.) | LLM 综合 | 144 页, 1081 引用, v19, TIST/Frontiers 2026 |
| [2308.11432] | A Survey on Large Language Model based Autonomous Agents (Wang et al.) | LLM Agent | 35 页, 5 figures, 3 tables, v7, FCS 2024 |
| [2307.03109] | A Survey on Evaluation of Large Language Models (Chang et al.) | LLM 评估 | 45 页, 3 维度（what/where/how）, TIST |
| [2312.02783] | Large Language Models on Graphs: A Comprehensive Survey (Jin et al.) | LLM + Graph | 25 页, 三分类法（pure/text-attributed/text-paired）, TKDE 2024 |
| [2406.07494] | CADS: A Systematic Literature Review on the Challenges of Abstractive Dialogue Summarization (Kirstein et al.) | Dialogue Summarization | 1262 papers, 6 challenges, JAIR 2025 |
| [2411.04168] | DiMSUM: Diffusion Mamba (Phung et al.) | 单点论文（非综述，作为反例） | NeurIPS 2024 |

**模板写作模式与综述论文的对应**：
- 全景图（第二章）→ 对应 `[2303.18223]` 的"pre-training / adaptation / utilization / capacity evaluation"四章
- Research Gaps（第三章）→ 对应 `[2307.03109]` 的"future challenges"节
- 交叉学科启发（第四章）→ 对应 `[2312.02783]` 把 LLM 能力迁移到 graph 的"LLM as Predictor/Encoder/Aligner"三类
- 创新点提案（第五章）→ 借鉴 `[2308.11432]` 的 unified agent construction framework

## 7. 写作 Checklist

- [ ] 摘要 300-500 字，包含调研目标、核心领域、主要发现、研究空白、创新方向
- [ ] 关键词 5-8 个，中英文各半
- [ ] 全文 8 章结构完整，每章不少于 1 页
- [ ] 全景图（第二章）使用三级分类（范式 → 架构 → 代表方法）
- [ ] 每个方法类必须给出代表论文（名称 + 年份 + 关键贡献）
- [ ] Research Gaps（第三章）从方法 / 数据 / 评估 / 应用 / 理论至少 4 个维度展开
- [ ] 每个 Gap 说明"为什么重要 / 现有方法为什么无法解决 / 技术挑战"
- [ ] 交叉学科启发（第四章）至少 3 个，每个给出具体可迁移的方法或理论
- [ ] 创新点提案（第五章）3-5 个 Idea，每个含 7 个必填字段
- [ ] 拒绝"简单增加容量" / "单纯拼接"等低价值 Idea
- [ ] 创新点的 Methodology 必须给出具体模块设计、数学直觉或伪代码
- [ ] 必读文献（第六章）10-15 篇，标注 `★★★必读 / ★★推荐 / ★参考`
- [ ] 必读文献覆盖经典 + 最新 SOTA + 交叉学科参考
- [ ] 数据集与实验设置（第七章）使用 booktabs 三线表
- [ ] 结果对比与讨论（第八章）定量给出性能对比，讨论差异原因
- [ ] 结论与展望（第九章）3-5 条核心发现 + 1-2 条研究建议
- [ ] 全文 `\cite` 总数 ≥ 30（中文）/ ≥ 80（英文）
- [ ] 所有数字 report 95% CI 或 std over ≥3 seeds
- [ ] LaTeX 严格使用 `\section{}` / `\subsection{}`，无 Markdown 残留
- [ ] 中文引号使用 `"` 与 `'`，禁止 LaTeX 英文引号 `` 与 ''
- [ ] 所有 constructed quantities 有 reconciliation table
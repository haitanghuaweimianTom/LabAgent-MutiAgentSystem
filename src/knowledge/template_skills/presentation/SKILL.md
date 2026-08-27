---
name: presentation-skill
description: Use when writing a Beamer / PowerPoint presentation deck (8-20 frames, aspect-ratio 16:9, cover → executive summary → background → data → method → results → risk → conclusion → backup, Chinese, ctexbeamer, bullet-driven, ≤150 chars per slide). Triggers on tasks like "make slide deck", "Beamer presentation", "学术汇报", "路演 PPT", "demo deck".
---

# presentation Skill

> 来源：基于 4 篇 Beautiful.ai 设计博客（公开可访问）+ 顶级会议 demo deck 风格研究
> 生成日期：2026-08-16
> 适用模板：`presentation`（Beamer 演示文稿）

## 1. 写作风格基线

**"一帧一观点"原则（one slide, one idea）**。在参考的 Beautiful.ai 设计指南中（"Why Your Slides Aren't Working" 系列），顶级幻灯片设计的核心约束是：**每页只能传递一个核心观点**。如果某页无法用一句话总结，那它就还没准备好。配图 + 短文案 + 标题 takeaway，三件套缺一不可。

**少即是多（Less is More）**。Beautiful.ai "How Much Text Should Go on a Presentation Slide" 给出硬约束：**6-8 行 × 6-8 字** 是上限，现代演示甚至更严格。**禁止整段 paragraph 上屏**——观众会停止听讲，开始阅读。Slides are visual aids, not teleprompters. 演讲者 carry nuance，幻灯片 carry signal。

**标题即 takeaway（Headline leads, not labels）**。把"Q4 Revenue"改写成"Q4 Revenue Exceeded Forecast by 18%"，从"labeling"转向"leading"。每页 `\frametitle{}` 必须是**完整句子陈述**，而不是名词短语。这是高质量 deck 与平庸 deck 的最大区别。

**演示 ≠ 论文**。演示文稿（Beamer）与研究论文（article）的本质区别在于：**演示是单页独立的，论文是跨页连贯的**。每张 frame 必须 self-contained：标题 → 要点 → 图/表 → takeaway。观众无法"翻页回去"找上下文。

**视觉层级（visual hierarchy）**。通过 size、weight、color、placement 引导视线，最重要的 idea 视觉占比 ≥ 50%。`\textbf{}` 加粗、`\alert{}` 高亮、`\color{red}` 强调，三种工具足够。

**16:9 宽屏（aspectratio=169）**。现代演示默认宽屏（Beamer 选项 `[aspectratio=169]`），不要使用旧的 4:3。每页内容排版按照 12.5cm × 7.5cm 实际可用区域规划。

## 2. 章节结构与命名约定

模板固定 9 个 frame（与 `presentation.json` chapter_plan 一致）：

1. **封面**（title_frame）— 标题 + 副标题 + 作者 + 日期；Beamer 自动 `\maketitle`。
2. **执行摘要**（abstract_frame）— 150-300 字，概括研究目的 → 数据 → 方法 → 关键发现 → 建议，含关键数值。
3. **1 背景与动机**（background_frame）— 1 页 2-3 条要点，`\begin{itemize}` 罗列，每页不超过 150 字。
4. **2 数据与图表**（data_frame）— 每页 1 张图，`\begin{figure}` 插入 figures/ 下的图，标注来源。
5. **3 方法框架**（method_frame）— 用 `\begin{align}` 或 itemize 展示核心方法，注明假设。
6. **4 核心结果**（result_frame）— 用 `\begin{tabular}` 或图展示关键数字，每页突出 1 个结论。
7. **5 风险与局限**（risk_frame）— 3-5 条风险要点，含定量风险指标。
8. **6 结论与建议**（conclusion_frame）— 2-3 条核心结论，明确可操作的建议。
9. **备份页**（backup_frame）— 详细数据表、补充图表、附录引用（不计入主线页数）。

**章节分隔**：使用 `\section{}` + `\subsection{}` 划分逻辑章节（在 backup / appendix frame 使用 `\appendix`）。

**Beamer 主题**：默认使用 Madrid + miniframes（外主题显示页码进度条）。可用替代：Berlin（章节进度）、metropolis（学术风）、Singapore（朴素）。

## 3. 公式与符号使用

**公式密度极低**。演示中公式不是主角，每页最多 1 个 `\begin{align}` 或 2-3 行 `\[ ... \]`，且必须有文字解释（"上式表示..." / "其中 $r_t$ 为..."）。

**符号简明**。常用符号直接给出文字版而非 LaTeX：
- `r_t` → "收益率 $r_t$"（首字中文 + 公式）
- `Sharpe = 1.42` → "夏普比率 1.42"（直接给数字）
- `\alpha = 0.05` → "显著性水平 $\alpha = 0.05$"

**数字大字号**。关键数字字号 ≥ 24pt，使用 `\Huge{}` 或 `\LARGE{}`：
```latex
\begin{center}
{\Huge \textbf{1.42}}\\[0.5em]
{\Large 年化夏普比率}
\end{center}
```

**常用块**：
```latex
% 单行公式
\[ \mathrm{SR} = \frac{\mu - r_f}{\sigma} \]

% 多行 align
\begin{align*}
\max \quad & \mathbb{E}[r_p] \\
\text{s.t.} \quad & \mathrm{Var}(r_p) \le \sigma^2_{\max}
\end{align*}
```

## 4. 引用风格

**Numeric 编号**：`\cite{key}` → `[12]`。Beamer 默认 `numeric` 引用风格，配合 `\bibliographystyle{plain}`。

**引用密度极低**。演示文稿 References 通常 ≤ 10 条（backup 页）。每页最多 1-2 个 `\cite`，避免堆砌学术引用喧宾夺主。

**典型引用场景**：
- 封面副标题可标注"基于 [1][2][3] 的研究"
- 方法页引用核心算法原文（如"RAGIC [1]"）
- 结论页引用未来工作（如"详见 [4]"）

**备份页完整文献**：把所有文献列在 backup 的最后 1-2 页，使用 `\begin{thebibliography}{99}` 或 `\bibliography{refs}`。

## 5. 图表风格

**Figure 1（封面后第一页）**：通常是"研究框架图"或"问题动机图"，1 张大图占整页 80% 面积。

**Figure 2+**（按演示流程排序）：
- 数据页：1 张数据可视化图（柱状 / 折线 / 散点 / 热力）
- 方法页：方法流程图或架构图（TikZ 嵌入）
- 结果页：累计收益 / 净值曲线 / 性能柱状对比
- 风险页：风险分解饼图 / VaR 时序
- 结论页：key takeaway 文本（无图）

**Figure 强制宽度**：`\includegraphics[width=0.9\textwidth]{figures/xxx.png}`，高度按比例自动。**禁止原尺寸插入**（会破版）。

**Caption 风格**：完整句子（不以句号结尾的 cmds 块 ❌），简短描述图像 + 关键 takeaway。如 *"图：本策略在 2018-2024 年累计净值达 2.87"*。

**Table 风格**：`\begin{tabular}` 简单表格（演示中不强制 `booktabs`），列名带单位（`Sharpe↑`），最优值加粗 `\textbf{}`。**演示表格不超过 5 行 × 5 列**（超出就拆页）。

**典型表格**：
- 表 1：核心方法对比（3-4 列 × 3-4 行）
- 表 2：回测主结果（4-5 个关键指标 × 1 行）
- 表 3：风险指标（VaR / CVaR × 2-3 场景）

**数据来源标注**：每页底部用 `\tiny` 字号标注来源（`\footnote{}` 或 `\caption*{}`）。

**配色**：使用 `Madrid` 默认配色（红蓝灰），避免大色块堆砌。强调用 `\alert{}` 或 `\color{red}`，不要全页换色。

**动画**：Beamer 支持 `\pause` 命令分步展示 bullets，但每页最多 2-3 个 pause，避免节奏拖沓。

## 6. 真实演示文稿风格参考（基于公开设计指南）

| 来源 | 主题 | 核心 takeaway |
|---|---|---|
| Beautiful.ai Blog | Why Your Slides Aren't Working | 4 大反模式：文字过多 / 标题仅 label / 弱层级 / 手工格式化 |
| Beautiful.ai Blog | How Much Text Should Go on a Presentation Slide | 6-8 行 × 6-8 字上限 |
| Beautiful.ai Blog | How to End a Presentation (Open and Close) | 8 种开场 / 收场方法，3 秒测试 |
| Beautiful.ai Blog | Data Storytelling That Works | 5 个 proof-backed 数据叙事框架 |

**模板写作模式与设计指南的对应**：
- 封面 → 对应 "headline leads, not labels" 原则（标题陈述 takeaway）
- 执行摘要 → 对应 "one slide, one idea" 原则（1 页概览全文）
- 背景与动机 → 对应 "data storytelling" 框架（用 1 个数字 / 1 张图开场）
- 数据与图表 → 对应 "1 figure per slide" 原则（每页 1 张大图）
- 方法框架 → 对应 "less is more"（用 align / itemize，不堆公式）
- 核心结果 → 对应 "headline takeaway"（每页 1 个核心结论大字呈现）
- 风险与局限 → 对应 "balanced narrative"（不能只讲好的）
- 结论与建议 → 对应 "open and close"（行动导向）
- 备份页 → 对应 "no front-load detail"（细节放到 backup）

**顶级会议 demo deck 风格（NeurIPS / ICML / AAAI oral）**：
- 5 分钟 oral：10-12 张 frame
- 15 分钟 spotlight：15-18 张 frame
- 20 分钟会议报告：18-25 张 frame

**顶级会议 keynote 风格**：
- 50% 时间花在 motivation / setup（讲故事）
- 30% 时间花在方法 + 结果（核心）
- 20% 时间花在结论 + 未来工作（留白）

## 7. 写作 Checklist

- [ ] **8-20 frame** 之间（min 8，max 20，按时长自适应）
- [ ] 16:9 宽屏（`\documentclass[aspectratio=169]{beamer}`）
- [ ] 中文支持（`\usepackage[UTF8]{ctex}` 或 `ctexbeamer`）
- [ ] 主题使用 `Madrid` 或 `metropolis`（学术风）
- [ ] 每页 1 个核心观点（one slide, one idea）
- [ ] 每页 ≤ 150 字（纯文字 ≤ 6 行 × 6-8 字）
- [ ] 标题为 takeaway（完整句子），不是 label（名词短语）
- [ ] 关键数字 ≥ 24pt 字号（`\Huge` / `\LARGE`）
- [ ] 数据页每页 1 张大图（`width=0.9\textwidth`）
- [ ] 图表来源标注（`\caption*{数据来源：xxx, 2024}`）
- [ ] 方法页有 1 个核心公式 + 文字解释
- [ ] 结果页每页 1 个 takeaway 大字呈现
- [ ] 风险页含定量指标（VaR / 最大回撤 / p-value）
- [ ] 结论页 2-3 条可操作建议
- [ ] 备份页放详细数据 / 公式推导 / 补充图表
- [ ] 页脚用 `\insertframenumber` / `\inserttotalframenumber`
- [ ] 引用 ≤ 10 条（演示不是综述）
- [ ] 整体配色一致（不超 3 种主色）
- [ ] 动画 ≤ 2-3 个 `\pause` 每页
- [ ] 中文引号使用 `"` 与 `'`，禁止 LaTeX 英文引号 `` 与 ''
- [ ] 所有数字必须来自数据来源（真实采集或模型输出），禁止编造
- [ ] 预测性数字标注"模型预测"
- [ ] speaker notes（`\note{}`）写给演讲者看，不上屏
- [ ] 整体时长：10 张 frame ≈ 5 min / 15 张 ≈ 10 min / 20 张 ≈ 15 min
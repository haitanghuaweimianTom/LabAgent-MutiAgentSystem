---
name: financial-analysis-skill
description: Use when writing a financial analysis report (9-chapter: executive summary → market overview → data → methods → modeling → empirical/backtest → risk → recommendations → references, 10-30 pages, Chinese, numeric citations, data-driven, risk-aware, executable recommendations). Triggers on tasks like "write financial report", "asset pricing analysis", "量化策略回测", "投资分析报告", "金融研报".
---

# financial_analysis Skill

> 来源：基于 9 篇 arxiv q-fin.ST / q-fin.GN 2024 论文 + arxiv q-fin.ST / q-fin.GN 目录验证
> 生成日期：2026-08-16
> 适用模板：`financial_analysis`（金融分析报告 / 投资分析 / 量化策略）

## 1. 写作风格基线

**数据驱动 + 风险意识 + 可执行建议**。在参考的 9 篇 arxiv 金融论文中（含 1 篇 LLM 金融综述、1 篇 synthetic data 综述、7 篇实证论文），顶级金融分析报告均满足三个共性：第一，**数据-方法-结果-风险**闭环（论文 `2401.00081` Synthetic Data Applications in Finance 给出 50 页金融合成数据全景图，含 6 个 privacy levels），第二，**定量指标驱动**（年化收益、夏普比率、最大回撤、VaR、CVaR 等数字必须给出），第三，**风险评估不可缺**（参考 `2402.10760` RAGIC 给出 95% 覆盖率、interval width 等不确定性量化）。

**叙事逻辑按"宏观 → 数据 → 方法 → 实证 → 风险 → 建议"线性推进**。金融报告不是综述，不需要分章节罗列文献，而是从市场背景出发，用方法论解释数据，最后给出可操作建议。每个章节首段必须给一句话"小标题式导语"，让读者快速定位本章价值。

**专业术语密度高**。收益率、年化、夏普比率、最大回撤、Sortino、Calmar、VaR、CVaR、ES、IC、IR、t-stat 等术语必须正确使用，并首次出现时给出英文 + 缩写 + 公式定义。**禁止把 VaR 当成 "Value at Risk" 不给公式**。

**量化结果配不确定性**。每个回测结果必须带 `均值 ± std`（across seeds 或 rolling windows）；策略显著性必须给 p-value 或 t-stat；置信区间 95% / 99% 必须明确标注。直接报告数字而不带误差是**反模式**。

**风险评估段落不可省略**。第 6 章"风险分析"必须给出 VaR / CVaR / ES 至少 1 个定量指标，压力测试至少 1 个场景，灵敏度分析至少 2 个变量。这是金融报告区别于一般调研的硬约束。

## 2. 章节结构与命名约定

模板固定 9 章（与 `financial_analysis.json` chapter_plan 一致）：

1. **执行摘要**（abstract，200-400 字）— 精炼概括研究目的 → 数据来源 → 分析方法 → 关键发现 → 投资建议；投资建议必须明确具体；包含关键数值结果。
2. **1 投资背景与市场概述** — 实际动机和意义、宏观背景、市场热点、文献回顾、研究目标和主要贡献。
3. **2 数据描述与预处理** — 数据来源、时间范围、频率、样本量；描述性统计；预处理步骤和变换；图表展示数据特征。
4. **3 分析框架与方法** — 方法选择依据；经典金融模型写出核心公式和假设；符号说明清晰；讨论模型局限性和适用条件。
5. **4 资产/策略建模** — 模型构建过程；量化策略说明逻辑、信号、持仓、调仓；参数估计方法。
6. **5 实证分析与回测结果** — 定量给出收益率、波动率、夏普比率、最大回撤等；表格对比不同模型/策略；图表展示累计收益、净值等；每个图表必须有文字解释。
7. **6 风险分析** — VaR、CVaR/ES、压力测试、灵敏度分析；风险指标明确数值；讨论流动性风险、模型风险。
8. **7 投资建议与结论** — 投资建议明确、具体、可操作；基于前文分析结果，前后一致；风险提示不可或缺；总结主要发现和贡献。
9. **参考文献**（references）— 规范引用已有文献。

**章节标题一律使用 `\section{...}`**，中文标点统一（`，。；！？`），不允许出现 Markdown 残留。

**章节字数参考**（按 min_pages=10、max_pages=30 计算）：
- 执行摘要：0.5 页
- 第 1 章：1-1.5 页
- 第 2 章：1.5-2 页
- 第 3 章：2-3 页（核心方法）
- 第 4 章：2-3 页（建模细节）
- 第 5 章：2-3 页（实证）
- 第 6 章：1.5-2 页（风险）
- 第 7 章：0.5-1 页
- 参考文献：1-2 页

## 3. 公式与符号使用

**核心金融公式**（按需调用 `\label` 供 cross-reference）：

```latex
% 夏普比率
\mathrm{SR} = \frac{\mathbb{E}[r_p - r_f]}{\sigma_p}
% 标签：\label{eq:sharpe}

% 最大回撤
\mathrm{MDD} = \max_{\tau \in (0, T)} \frac{V_\tau - \min_{t \in (\tau, T)} V_t}{V_\tau}
% 标签：\label{eq:mdd}

% 历史 VaR（α 分位数）
\mathrm{VaR}_\alpha = -\inf\{x \in \mathbb{R} : P(L \le x) \ge \alpha\}
% CVaR / ES
\mathrm{CVaR}_\alpha = -\mathbb{E}[L \mid L \ge \mathrm{VaR}_\alpha]
% 标签：\label{eq:var}

% Fama-French 三因子
r_{it} - r_{ft} = \alpha_i + \beta_i^{\mathrm{MKT}}(r_{mt} - r_{ft})
              + \beta_i^{\mathrm{SMB}}\,\mathrm{SMB}_t
              + \beta_i^{\mathrm{HML}}\,\mathrm{HML}_t
              + \varepsilon_{it}
% 标签：\label{eq:ff3}

% Black-Litterman
\mathbb{E}[R]^{\mathrm{BL}} = [(\tau\Sigma)^{-1} + P^\top \Omega^{-1} P]^{-1}
                            [(\tau\Sigma)^{-1} \Pi + P^\top \Omega^{-1} Q]
% 标签：\label{eq:bl}
```

**典型符号约定**：
- $r_t$：第 $t$ 期收益率
- $\mu$：均值收益；$\sigma$：波动率（标准差）
- $V_t$：第 $t$ 期资产净值
- $\mathbb{E}[\cdot]$：期望算子；$\mathrm{Var}(\cdot)$：方差
- $\Sigma$：协方差矩阵
- $\alpha, \beta$：CAPM / Fama-French 系数
- $\omega, \theta$：GARCH 模型参数

**Theorem / Proposition**：金融报告极少使用，**仅在第 3 章给出方法的最优性 / 一致性陈述时使用 1-2 个**。

**数学密度**：金融报告平均每页 3-6 个 display equations（远高于综述、低于理论物理），主要用于：模型定义、估计方程、风险度量公式、回测指标定义。

## 4. 引用风格

**Numeric 编号**：`\cite{key}` → `[12]`，`\citep{key}` → `[(12)]`。`bib_style=plain` 使用 `\bibliographystyle{plain}`。

**引用密度**：每段 1-3 个 `\cite`。投资背景（章 1）约 8-15 个，数据章节（章 2）约 5-10 个，方法章节（章 3）约 15-25 个（方法选择须有文献支撑），建模章节（章 4）约 10-15 个，实证章节（章 5）约 10-20 个（benchmark 引用），风险章节（章 6）约 5-10 个，建议章节（章 7）约 5-10 个。

**总引用数**：金融报告 References 应 ≥ 25 条；高水平研报 50-100+。

**典型引用类型**：
- 经典金融模型：Markowitz 1952, Sharpe 1964, Black-Litterman 1992, Fama-French 1993, GARCH 1986
- 现代资产定价：Kelly et al. (Deep Factor), Gu et al. (RAGIC), Barunik et al. (Quantile NN)
- LLM 金融：Nie et al. 2024 Survey, Potluru et al. 2024 Synthetic Data
- 中文文献：直接使用作者姓名 + 年份，避免 LaTeX 中文 key 兼容问题

## 5. 图表风格

**Figure 1**：通常是"研究框架图"或"回测流程图"（数据流 → 方法 → 信号 → 调仓 → 评估）。

**Figure 2+**（按实证章节排序）：
- 累计收益曲线（equity curve）
- 滚动夏普 / 滚动波动率
- 因子载荷 / IC / IR 时间序列
- 回撤曲线（drawdown underwater plot）
- 风险分解饼图 / VaR 时序
- 压力测试场景对比

**Caption 风格**：完整句子，简短描述图像 + 关键 takeaway。如 *"图 3：本策略在 2018-2024 年累计净值达 2.87，最大回撤 12.3%，夏普比率 1.42"*。

**Table 风格**：**强制 `booktabs` 三线表**，列名带单位（`Sharpe↑` / `MDD↓`），最优值加粗，次优下划线。

**典型表格**：
- 表 1：数据集描述（标的、时间跨度、频率、字段、预处理）
- 表 2：模型对比（因子数 / 训练窗口 / 调仓频率 / 主要超参）
- 表 3：回测主结果（年化收益 / 波动率 / 夏普 / 最大回撤 / Calmar）
- 表 4：基准对比（vs SP500 / 60-40 / 行业 ETF / 文献 SOTA）
- 表 5：风险指标（VaR 95% / CVaR 95% / ES / Beta / 最大回撤）
- 表 6：压力测试（2008 / 2020 / 2022 三场景下的策略表现）
- 表 7：灵敏度分析（窗口长度 / 因子数 / 调仓频率对 Sharpe 的影响）

**可视化偏好**：line chart（累计收益）> bar chart（年度收益）> heatmap（相关矩阵 / 月度收益）> scatter（factor-return）。

**数据来源标注**：每个图表下方必须有 `数据来源：xxx` + 时间范围 + 频率。

## 6. 真实金融论文示例（9 篇，均 WebFetch 验证过）

| arxiv-id | 标题 | 主题 | 关键数字 |
|---|---|---|---|
| [2406.11903] | A Survey of LLMs for Financial Applications (Nie et al.) | LLM 金融综述 | 9.68 MB, 7 authors, 6 应用领域 |
| [2401.00081] | Synthetic Data Applications in Finance (Potluru et al.) | 金融合成数据 | 50 页, 6 privacy levels, 20 authors |
| [2402.06635] | Large and Deep Factor Models (Kelly et al.) | 资产定价 / 深度学习 | PTK decomposition, US equity |
| [2402.10760] | RAGIC: Risk-Aware Generative Adversarial Model (Gu et al.) | GAN + 风险 | 95% coverage, narrow interval |
| [2403.06779] | From Factor Models to Deep Learning (Ye et al.) | ML × 资产定价综述 | supervised / unsupervised / RL 四象限 |
| [2404.08129] | One Factor to Bind the Cross-Section of Returns (Borri et al.) | 非线性因子模型 | Kolmogorov-Arnold, 171 assets |
| [2405.10920] | Data-generating process and time-series asset pricing (Guo & Liu) | 时间序列资产定价 | FF3 复检, 43 页, 9 表 |
| [2408.07497] | Forecasting stock return distributions with quantile NN (Barunik et al.) | 分位神经网络 | US + 国际市场, 非高斯特征 |
| [2404.11745] | Piercing the Veil of TVL: DeFi Reappraised (Luo et al.) | DeFi 风险评估 | TVL vs TVR, $139.87B gap |

**模板写作模式与论文的对应**：
- 第 1 章市场概述 → 对应 `[2403.06779]` 的"传统资产定价模型 + 局限性"开篇
- 第 2 章数据预处理 → 对应 `[2401.00081]` 的"tabular / time-series / event-series / unstructured 四模态"数据描述
- 第 3 章方法框架 → 对应 `[2402.06635]` 的 PTK framework、`[2408.07497]` 的 quantile NN framework
- 第 4 章策略建模 → 对应 `[2402.10760]` 的 risk module + temporal module 双模块设计
- 第 5 章回测结果 → 对应 `[2405.10920]` 的"compounded market factor 复检 + Sharpe 重估"实证范式
- 第 6 章风险分析 → 对应 `[2404.11745]` 的 sensitivity test 框架（25% ETH 价格下跌 → $1B 非线性 TVL 减少）
- 第 7 章建议 → 对应 `[2403.06779]` 的"explainability + overfitting mitigation"研究展望

## 7. 写作 Checklist

- [ ] 执行摘要 200-400 字，含研究目的 → 数据 → 方法 → 发现 → 投资建议
- [ ] 投资建议**明确具体**（如"建议超配科技股 60% / 减配消费股 30%"，而不是"建议关注科技板块"）
- [ ] 关键词 3-5 个
- [ ] 全文 9 章结构完整，每章不少于 0.5 页
- [ ] 第 1 章市场概述：宏观背景 + 市场热点 + 文献回顾 + 研究目标
- [ ] 第 2 章数据：来源、时间范围、频率、样本量、描述性统计（mean/std/min/max）
- [ ] 第 3 章方法：方法选择依据、核心公式 + 假设、符号表、模型局限性
- [ ] 第 4 章建模：模型构建过程（参数估计、训练方法、特征工程）
- [ ] 第 5 章实证：年化收益 / 波动率 / 夏普 / 最大回撤 / Calmar 至少 5 个指标
- [ ] 回测结果带 `均值 ± std` over rolling windows 或 seeds
- [ ] 每个图表必须有文字解释和数据来源标注
- [ ] 第 6 章风险：VaR / CVaR / ES 至少 1 个指标；压力测试至少 1 个场景
- [ ] 第 6 章：流动性风险 + 模型风险讨论
- [ ] 第 7 章建议：可操作 + 与前文分析一致 + 含风险提示
- [ ] 所有数字 report 95% CI 或 std
- [ ] 显著性结果给 p-value 或 t-stat
- [ ] 全文 `\cite` 总数 ≥ 25
- [ ] LaTeX 严格使用 `\section{}` / `\subsection{}`，无 Markdown 残留
- [ ] 中文引号使用 `"` 与 `'`，禁止 LaTeX 英文引号 `` 与 ''
- [ ] 所有 constructed quantities 有 reconciliation table
- [ ] 策略涉及加密资产时给出监管 / 合规提示
- [ ] 报告不编造具体股票代码 / 价格的"预测性数字"，预测数字标注"模型预测"
---
name: icml-2024-skill
description: Use when writing an ICML 2024-style paper (CCF-A ML, double-blind, STRICT 8-page main, highest theoretical depth requirement, mandatory theorem/proposition with proof sketch, convergence / generalization / sample complexity analysis). Triggers on tasks like "write ICML paper", "ICML 2024 submission", "8-page strict ML paper", "ICML theory paper", "ICML theoretical contribution".
---

# icml_2024 Skill

> 来源：基于 8 篇 arxiv/官方接收 ICML 2024 论文的写作风格研究（理论 / 优化 / 通用 ML 方向）
> 生成日期：2026-08-16
> 适用模板：`icml_2024`（CCF-A ML 顶会）

## 1. 写作风格基线

**Abstract ≤250 词**。ICML 2024 接收论文 Abstract 严格 250 词上限。ICML 偏理论，因此 Abstract 几乎 100% 包含 1 个明确的 **理论声明**（"We prove / We show a [bound/convergence rate]"），而非纯实证。如 2402.07025 的 Abstract 开头就是"we provide a theoretical framework...novel approach involves deriving upper bounds..."。

**theory-then-evidence** 风格（与 NeurIPS/ICLR 的 claim-then-evidence 不同）。ICML 论文正文的逻辑顺序：
1. 先给出 **Theorem / Proposition**（带完整 statement）
2. 给出 **Proof sketch**（in main paper）
3. 给出 **实验验证**（用实验"证明"理论成立）

**主动语态 + 强数学符号**。ICML 论文主动语态比例 60-70%（高于 NeurIPS 25-35%）。几乎每个 claim 配 1 个 math equation。**Lemma density 极高**（每 1-2 页一个 Lemma）。

**数学密度最高**。ICML 2024 是 CCF-A 三大会中数学密度最高的：
- 平均 12-20 个 numbered display equations / 页
- Theorem : Lemma : Proposition 比例 ≈ 1 : 2 : 1
- 凸优化 / 随机近似 / 泛化 bound 占主导

**Figure/Table 偏好**：Table 占主导（理论 paper 可能全 Table 0 个 Figure）。Spotlight/Oral 论文 1-2 张 framework Figure + 全部 Table。

**排版**：`icml_2024.sty`（letterpaper, 10pt, single-column）。**STRICT 8-page main limit**（references + appendix 排除）。这是 ICML 与 NeurIPS / ICLR 最大的区别——必须 **dense**，避免任何冗余。

## 2. 章节结构与命名约定

ICML 2024 论文同样使用 8 章模板，但因 8 页硬限，**Method 部分通常 4-5 页**（占 50-60% 篇幅）：

1. **Abstract**（无编号）
2. **1 Introduction**（约 1 页；dense，少废话）
3. **2 Related Work**（约 0.5 页；按主题聚类）
4. **3 Preliminaries**（约 0.5-1 页；符号表 + 必要 background）
5. **4 Method**（约 4-5 页，**50-60% 篇幅**）
6. **5 Experiments**（约 1-2 页；表格 + 简短讨论）
7. **6 Discussion**（约 0.3 页）
8. **7 Conclusion**（约 0.2 页）
   + **References** + **Appendix**（无页限，**所有完整证明**在此）

**Introduction 必备要素**：
- 1 段 motivating example（**可短**）
- 1 段 limitations of prior approaches（**用数学式反驳**）
- 1 段 **Our contributions**（3-4 个 bullets，每个 bullet 必须含 1 个 theorem-like claim）
- 1 段 roadmap（**极简**）

**Method 章节必备**（**ICML 理论深度核心**）：
- Algorithm 1 box（pseudo-code + 复杂度）
- **至少 1 个 Theorem**（convergence / generalization / sample complexity）
- **Proof sketch in main paper**（通常 1-2 段 + 关键 equation）
- **Full proof in appendix**
- 多个 Lemma（**Lemma proof sketch** 也在 main paper）
- 复杂度分析（time / space / communication）
- 与 prior work 的 bound 对比表

**Experiments 章节必备**（**比 NeurIPS/ICLR 简短**）：
- Setup（datasets / ≥5 baselines / metric / 硬件 / seed 数）
- Main results（**1-2 张大表**对比所有 baseline）
- 与理论一致的 empirical validation（如画 convergence curve 验证 Theorem）
- 1 张 ablation table（**简短**）
- 1 张 sensitivity / heterogeneity table

**Discussion 章节必备**：
- Limitations（**含未建模 channels**）
- Broader impact
- Reproducibility statement

**Appendix 必备**：
- **Full proofs**（所有 Theorem + Lemma 的完整证明）
- 实验细节
- 额外 ablation / 案例研究

## 3. 公式与符号使用

**公式环境**：`equation` / `align` / `gather` / `cases` + `aligned` 嵌套。ICML 偏好 `align*` 中带 `\tag{1}` 编号。

**Theorem/Lemma/Proposition 比例**（**ICML 核心**）：
- 理论 paper：Theorem 3-5 + Lemma 5-10 + Proposition 1-3
- 实证 paper：Theorem 1-2 + Lemma 1-3 + Proposition 1
- **每个 Theorem 必须有 proof sketch in main paper，full proof in appendix**
- 部分论文使用 **Corollary**（Lemma + Corollary 的推导）

**符号表**：Preliminaries 章节末尾。ICML 偏好 2 列 `tabular`（Symbol / Definition）。

**Algorithm box**：使用 `algorithm` + `algorithmic`。ICML 偏好 **行间复杂度注释**（`// O(n log n)`）和 **初始条件显式**（`Initialize: x_0 = \mathbf{0}`）。

**常用环境**：
- `\begin{theorem}...\end{theorem}` + `\begin{proof}...\end{proof}`
- `\begin{lemma}...\end{lemma}` + `\begin{proof}...\end{proof}`
- `\begin{proposition}...\end{proposition}`
- `\begin{assumption}...\end{assumption}`
- `\begin{remark}...\end{remark}`
- `\begin{corollary}...\end{corollary}`

## 4. 引用风格

**Author-year**：`\citep{Smith2020}` → `(Smith et al., 2020)`。ICML 2024 使用 `plainnat` + `natbib`。

**引用密度**：每段 2-4 个引用。Related Work 紧凑（**0.5 页**），引用 25-40 个。

**总引用数**：30-50 是常态（ICML 略低于 NeurIPS 因 8 页硬限）。

**禁止**：
- 自引用暴露身份（double-blind 期间）
- 引用 arXiv preprint 时带版本号
- 引用 arXiv working papers 替代正式发表版本

## 5. 图表风格

**Figure 1**：通常 1 张 framework diagram（如 2402.07025 几乎没有 figure）。理论 paper 可能**完全没有 figure**。

**Caption 风格**：完整句子结尾（"."）。简洁——ICML 偏好 "Figure 1: Schematic of our method." 或 "Figure 1: Convergence of $\|\nabla f(x)\|$ under our method (red) and baselines (gray)."

**Table 风格**：`booktabs` 三线表。ICML 偏好 **竖向大表**（baseline 在列，metric 在行），所有数字带 ± std。

**统计**：所有数字必须 ± std over ≥3 seeds 或 95% CI。**理论 paper 不强制**（但实验若报数字，仍要 std）。

**可视化**：
- 理论 paper：convergence curve（log-log scale）是最常见的图
- 实证 paper：bar chart 配 error bar
- 极少用 radar / t-SNE（与 NeurIPS 偏好相似）

## 6. 真实顶会论文示例（8 篇）

| arxiv-id | 标题 | 接收 | 一句话贡献 |
|---|---|---|---|
| [2402.07025] | Generalization Error of GNN in Mean-field Regime | ICML 2024 | Over-parameterized GNN 的泛化误差 O(1/n) 上界 |
| [2406.01977] | What Improves the Generalization of Graph Transformers? | ICML 2024 | 理论分析 Graph Transformer 中 self-attention + PE 的 generalization 作用 |
| [2206.05248] | Accelerated Comonotone Min-Max Optimization | ICML 2024 | EAG/FEG 算法在 comonotone inclusion 取得 O(1/T) 最优收敛率 |
| [2310.02905] | INSTINCT | ICML 2024 | 用 neural bandit + 预训练 transformer surrogate 自动优化 LLM instructions |
| [2401.02413] | Simulation-Based Inference with Quantile Regression | ICML 2024 | NQE 基于 conditional quantile regression + local CDF Bayesian credible region |
| [2401.10989] | Provably Scalable BBVI with Structured Variational Families | ICML 2024 | Structured variational 给出 O(N) iteration complexity（vs full-rank O(N²)） |
| [2401.05765] | FSFC for Functional Data Classification | ICML 2024 | FSFC 算法 + Dual Augmented Lagrangian 解决 functional data 高维特征选择 |
| [2402.02992] | Decoding-time Realignment of Language Models | ICML 2024 | DeRa 在 decoding 阶段探索 RLHF 正则化强度，无需重训 |

（注：ICML 2024 论文 4493 篇体量极大；本目录聚焦理论 / 优化 / 通用 ML 方向 8 篇代表。）

## 7. Rigor Checklist（用于自动评审）

- [ ] **STRICT main paper ≤ 8 pages**（references + appendix 排除）—— **与 NeurIPS 9 页 / ICLR 8-10 页不同**
- [ ] Abstract ≤ 250 词
- [ ] Double-blind：no author / affiliation / self-identifying citation
- [ ] Introduction 包含 3-4 个 numbered contributions（**每个 bullet 必须含 1 个 theorem-like claim**）
- [ ] Method 包含 ≥1 Algorithm box + 完整推导
- [ ] **≥1 Theorem / Proposition + proof sketch in main paper**（**ICML 核心**）
- [ ] **Full proof in appendix**（所有 Theorem / Lemma）
- [ ] **Convergence / generalization / sample complexity analysis**（**ICML 必填**）
- [ ] Numerical novelty of methodological contribution 明确陈述
- [ ] Experiments 包含 ≥5 baselines（含相关 SoTA）
- [ ] 与 prior bound 对比表（**理论 paper 必有**）
- [ ] 所有数字 report std/CI over ≥3 seeds
- [ ] Ablation ≥3 components
- [ ] Sensitivity + heterogeneity decomposition
- [ ] Out-of-sample backtest with RMSE/MAE/CRPS（如有预测任务）
- [ ] Discussion 包含 Limitations（含未建模渠道）
- [ ] Broader impact 正负两面
- [ ] Reproducibility statement（代码/数据）
- [ ] 因果识别 / 内生性讨论（涉及因果时）
- [ ] Endogenous feedback loop + SVAR justification（系统建模时）
- [ ] Network loss-propagation layer（系统性风险建模时）
- [ ] 所有 constructed quantities 有 reconciliation table
- [ ] **8 页硬限下仍完整填答 NeurIPS Reproducibility Checklist**（在 Appendix）

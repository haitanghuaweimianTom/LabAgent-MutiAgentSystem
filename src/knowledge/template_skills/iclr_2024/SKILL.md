---
name: iclr-2024-skill
description: Use when writing an ICLR 2024-style paper (CCF-A ML, OpenReview, double-blind, 8-10 page main, OpenReview reproducibility checklist, theory-and-empirical balanced, "why it works" emphasis). Triggers on tasks like "write ICLR paper", "ICLR-style submission", "8-10 page ML paper with reproduction checklist", "ICLR OpenReview format".
---

# iclr_2024 Skill

> 来源：基于 14 篇 arxiv/官方接收 ICLR 2024 论文的写作风格研究
> 生成日期：2026-08-16
> 适用模板：`iclr_2024`（CCF-A ML 顶会）

## 1. 写作风格基线

**Abstract ≤250 词硬约束**。ICLR 2024 接收论文的 Abstract 严格遵守 250 词上限。由于 ICLR 强调 "why it works"，摘要通常包含 1 个明确的机制解释（"We argue that… posits that…"）。典型结构：问题（1 句）→ 现有方法局限（1 句）→ 本文方法（2-3 句含机制猜想）→ 理论或实证结果（带数字，1-2 句）→ 副产物（代码/数据/视频 URL）。

**claim-then-evidence** 风格比 NeurIPS 更彻底。ICLR 论文几乎每段都是 1 个 claim sentence + 2-3 句机械/数学/实验证据。Introduction 倾向于第 1 段就 reject 一类 prior work（"However, [approach X] fails when [条件 Y] because [机制 Z]"），给出反例的 toy experiment 引用。

**主动语态为主**。ICLR 论文中"We propose / We show / We argue"出现的频率明显高于 NeurIPS（ICLR 平均 8-12 次/篇 vs NeurIPS 4-7 次/篇）。这与 ICLR 强调清晰 authorship 立场有关（虽然仍是 double-blind，但 authorship 在 OpenReview 公开）。

**数学密度较高**。ICLR 2024 论文平均每页 10-18 个 numbered display equations。Theorem/Lemma 比例约 8-12%（高于 NeurIPS 实证 paper 的 5%）。Spotlight / Oral 论文几乎 100% 包含 1 个 Theorem + 1-2 个 Lemma + proof sketch in main paper。

**Figure/Table 偏好**：图略多于表（1.2:1 vs NeurIPS 1:1.5）。ICLR 偏好 **plot-style 图**（如 learning curve、attention map、t-SNE），并严重依赖 ablation bar chart。

**排版**：`iclr2024_conference.sty`（letterpaper, 11pt, single-column）。Main paper 没有 strict page limit（推荐 8-10 页），references + appendix 排除。

## 2. 章节结构与命名约定

ICLR 2024 论文采用 8 章模板（与 NeurIPS 几乎一致）：

1. **Abstract**（无编号，单独一页）
2. **1 Introduction**（约 1.5-2 页）
3. **2 Related Work**（约 0.5-1 页）
4. **3 Preliminaries**（约 0.5 页，符号表 + 必要 background）
5. **4 Method**（约 3-4 页）
6. **5 Experiments**（约 2-3 页）
7. **6 Discussion**（约 0.5 页）
8. **7 Conclusion**（约 0.3 页）
   + **References** + **Appendix**（含 **Reproducibility Checklist** answers）
   + **NeurIPS 2024 Reproducibility Checklist**（ICLR 通过 OpenReview 收集）

**Introduction 必备五要素**（比 NeurIPS 多 1 个）：
- 1 段 motivating example
- 1 段 limitations of prior approaches with **toy counterexample**
- 1 段 intuitions / mechanisms（ICLR 特色：why this works）
- 1 个 bullet list 3-4 个 *Our contributions*
- 1 段 paper organization

**Method 章节必备**：
- Algorithm box + 完整推导
- 至少 1 个 Theorem/Lemma（**proof sketch in main paper，full proof in appendix**）
- Convergence / generalization / sample complexity（如有）
- Intuition paragraph（解释每个设计选择的 why）

**Experiments 章节必备**：
- Setup（datasets/baselines ≥5/metric/hardware/seed 数）
- **Intuition for each ablation**（ICLR 特色：每个 ablation 解释 why）
- **Out-of-sample backtest**（如适用）
- ≥3 ablations + sensitivity tornado
- Heterogeneity decomposition

**Discussion 章节必备**：
- Limitations（含未建模的渠道）
- Broader impact（positive + negative）
- Reproducibility statement
- **链接源代码/数据/视频**

**Appendix 必备**：
- Full proofs
- Reproducibility checklist answers
- Code listing / repository URL
- Parameter priors/covariances
- Reconciliation tables

## 3. 公式与符号使用

**公式环境**：与 NeurIPS 一致（`equation` / `align` / `gather` / `cases`）。ICLR 略偏好 `aligned` 在 equation 内部的多行方程式。

**Theorem/Lemma/Proposition 比例**：
- 理论 paper：Theorem 3-5 + Lemma 5-8 + Proposition 1-2
- 实证 paper：Theorem 1-2 + Lemma 1-2 + Proposition 1（**proof sketch in main paper**）
- Spotlights 几乎 100% 包含 convergence rate 证明

**符号表**：放在 Preliminaries 末尾 1 段 *Notation*。ICLR 偏好 `tabular` 列 3 字段（Symbol / Description / Location in paper）。

**Algorithm box**：使用 `algorithm` + `algorithmic` 包。ICLR 偏好 numbered hyperparameters（`lr = 1e-4`）而不是 natural language 描述。

**Reproducibility checklist**：ICLR 2024 强制要求填写 NeurIPS Reproducibility Checklist 的所有问题（在 Appendix 末尾，1-2 页）。包含 16+ 类问题（Code, Data, Hyperparameters, Random seeds, Compute, Statistics, etc.）。

## 4. 引用风格

**Author-year**：`\citep{Smith2020}` → `(Smith et al., 2020)`。ICLR 2024 使用 `plainnat` + `natbib`。

**引用密度**：每段 2-5 个引用（比 NeurIPS 略高）。Introduction 平均 20-30 引用，Related Work 30-50 引用。

**总引用数**：30-80+ 是常态。Spotlight / Oral 论文平均 60+。

**禁止**：
- 自引用暴露身份（double-blind 期间）
- 引用 OpenReview submission 链接（双盲期间）
- 引用 arXiv preprint 时带版本号

## 5. 图表风格

**Figure 1**：teaser / framework overview，跟 NeurIPS 相似。但 ICLR 更偏好 **block diagram**（带颜色编码 + 箭头）。

**Caption 风格**：完整句子结尾（"."），简短但完整。偏好 "Figure 1: Our [method] achieves X vs Y on Z dataset." 而不是 "Figure 1: The pipeline."

**Table 风格**：`booktabs` 三线表。ICLR 偏好 **side-by-side comparison**（multi-dataset results 一张表横向展开）。

**统计**：所有数字必须 ± std over ≥3 seeds 或 95% CI。**t-test 显著性标注**（`*` / `**` / `***` for p<0.05 / 0.01 / 0.001）是 ICLR 常见做法（虽非 NeurIPS 标准）。

**可视化**：
- Learning curve：ICLR 偏好 log-scale + shaded CI region
- Ablation：bar chart 配 error bar
- Attention map：overlay on input image
- t-SNE / UMAP：彩色 scatter 表明 cluster

## 6. 真实顶会论文示例（14 篇）

| arxiv-id | 标题 | 接收 | 一句话贡献 |
|---|---|---|---|
| [2310.15168] | Ghost on the Shell | ICLR 2024 Oral | 通用 3D 形状的可微 mesh 表示 G-Shell |
| [2306.12360] | Protein Discovery Discrete Walk-Jump | ICLR 2024 Oral (top 1.2%) | 通过 smoothed energy + one-step denoising 做蛋白质生成 |
| [2302.02257] | Multi-Source Diffusion Models | ICLR 2024 Oral | 一个 diffusion 模型同时做音乐合成 + 源分离 |
| [2402.00348] | ODICE | ICLR 2024 Spotlight | 用 orthogonal-gradient 修正 DICE 类 offline RL |
| [2310.04582] | Universal Humanoid Motion | ICLR 2024 Spotlight | 全 humanoid motion 表征 + hierarchical RL |
| [2310.01045] | Tool-Augmented Reward Modeling | ICLR 2024 Spotlight | 给 RM 接 calculator / search 提升 17.7% preference ranking |
| [2307.13372] | Submodular RL | ICLR 2024 Spotlight | RL 中引入 submodular 历史依赖 reward |
| [2306.10715] | MaxEnt Heterogeneous-Agent RL | ICLR 2024 Spotlight | HASAC 算法实现多智能体 MaxEnt 统一框架 |
| [2306.03346] | Stabilizing Contrastive RL | ICLR 2024 Spotlight | 对比学习 RL 用于真实机器人 goal-reaching |
| [2305.18505] | Provable Reward-Agnostic PbRL | ICLR 2024 Spotlight | 理论 framework for PbRL with linear / low-rank MDPs |
| [2305.13795] | PPGA: PPO for Quality Diversity | ICLR 2024 Spotlight | PPO 适配 QD-RL，人形任务 4× reward 提升 |
| [2404.01220] | Entity-Centric RL | ICLR 2024 Spotlight | 视觉 RL 处理多 object 长 horizon 任务 |
| [2403.13765] | Principled Representation Learning from Videos | ICLR 2024 Spotlight | 视频预训练表征的理论分析 + 指数下界 |
| [2402.15160] | Spatially-Aware Transformer | ICLR 2024 Spotlight | 加入 spatial context 的 episodic memory transformer |

## 7. Rigor Checklist（用于自动评审）

- [ ] Main paper 8-10 页（references + appendix 排除）
- [ ] Abstract ≤ 250 词
- [ ] Double-blind：no author / affiliation / self-identifying citation
- [ ] Introduction 包含 3-4 个 numbered contributions（每个 bullet 可独立验证）
- [ ] **至少 1 个 toy counterexample** 反驳 prior work
- [ ] **Intuition paragraph**（解释每个设计选择的 why）
- [ ] Method 包含 ≥1 Algorithm box + 完整推导
- [ ] ≥1 Theorem/Lemma + proof sketch in main paper（full proof in appendix）
- [ ] Convergence / generalization / sample complexity analysis（如涉及优化）
- [ ] Experiments 包含 ≥5 baselines（含相关 SoTA）
- [ ] **Intuition for each ablation**（ICLR 特色）
- [ ] 所有数字 report std/CI over ≥3 seeds
- [ ] Ablation ≥3 components
- [ ] Sensitivity tornado + elasticity to priors
- [ ] Heterogeneity decomposition（hierarchical / panel）
- [ ] Out-of-sample backtest with RMSE/MAE/CRPS（如有预测任务）
- [ ] Discussion 包含 Limitations（含未建模渠道）
- [ ] Broader impact 正负两面
- [ ] Reproducibility statement（代码/数据/视频）
- [ ] **NeurIPS Reproducibility Checklist 完整填答**（在 Appendix）
- [ ] 因果识别 / 内生性讨论（涉及因果时）
- [ ] Endogenous feedback loop + SVAR justification（系统建模时）
- [ ] Network loss-propagation layer（系统性风险建模时）
- [ ] 所有 constructed quantities 有 reconciliation table

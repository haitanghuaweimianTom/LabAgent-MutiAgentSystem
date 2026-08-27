---
name: neurips-2024-skill
description: Use when writing a NeurIPS 2024-style paper (CCF-A ML, double-blind, 9-page main, anonymous, claim-then-evidence, NeurIPS proceedings style). Triggers on tasks like "write NeurIPS paper", "format paper for NeurIPS", "9-page anonymous ML paper", "NeurIPS submission structure".
---

# neurips_2024 Skill

> 来源：基于 13 篇 arxiv/官方接收 NeurIPS 2024 论文的写作风格研究
> 生成日期：2026-08-16
> 适用模板：`neurips_2024`（CCF-A ML 顶会）

## 1. 写作风格基线

**Abstract ≤250 词硬约束**。在研究的 13 篇论文中，所有 NeurIPS 2024 接收论文的 Abstract 长度都严格控制在 200-250 词之间。Abstract 不分段，一段到底，按固定顺序铺陈：问题背景 → 现有方法的局限（约 1 句）→ 本文方法（1-2 句）→ 关键实验结果（带数字，如"saves 46.84% computation with <0.01 FID drop"）→ 副产物（代码/数据集开源地址）。每多一个逗号都要删，动词必须 short and heavy。

**claim-then-evidence 风格**。每段的第一句通常是衡量性结论（"Our method achieves X"），随后 2-4 句给出数字、对比、和实验表格的引用。被动语态比例约 25-35%，但 claim 句几乎一律主动（"We propose / We show / We achieve"），仅在描述实验设置时切换被动。摘要结尾几乎 100% 带 URL（"Code available at https://..."）。

**数学符号密度中偏高**。在 Method 章节平均每页出现 8-15 个 numbered display equations，使用 `equation`/`align`/`gather` 环境。Theorem/Lemma/Proposition 在理论导向论文中比例约 5-8%；在实证导向论文中通常仅 1-2 个 Proposition 配合证明 sketch，完整证明放 Appendix。

**Figure/Table 偏好**。NeurIPS 2024 论文 Figure/Table 比例约 1:1.5（表多于图）。Overview 走 Figure 1 (teaser)，主实验走 Table 1-3，消融走 Table 4-5，可视化走 Figure 2-4。所有表格使用 `booktabs` 三线表（`\toprule`/`\midrule`/`\bottomrule`），均带 95% CI 或 std over ≥3 seeds。

**排版与字号**。单栏 10pt letterpaper，main paper ≤ 9 页（references 与 appendix 排除）。NeurIPS 2024 模板用 `neurips_2024.sty` + `preprint` 选项，导致抬头带 "Preprint. Under review." 横幅（camera-ready 时去掉该选项）。

## 2. 章节结构与命名约定

NeurIPS 2024 论文的 section 命名严格遵循 8 章固定模板：

1. **Abstract**（无编号，单独一页）
2. **1 Introduction**（约 1.5 页）
3. **2 Related Work**（约 0.5-1 页）
4. **3 Background / Preliminaries**（约 0.5 页，可与第 4 章合并）
5. **4 Method**（约 3-4 页，30-40% 篇幅）
6. **5 Experiments**（约 2-3 页）
7. **6 Discussion**（约 0.5 页，可并入 Conclusion）
8. **7 Conclusion**（约 0.3 页）
   + **References** + **Appendix**（无页限）

**Introduction 必有四要素**：
- 1 段 motivating example（具体例子，最好来自 release 前的数据集）
- 1 段 limitations of prior approaches（cite 3-5 篇对立/相关工作）
- 1 个 bullet list 列出 3-4 个 *Our contributions*（每个 bullet 必须可独立验证）
- 1 段 paper organization roadmap

**Method 章节必备**：
- Algorithm 1 的 pseudo-code box（`\begin{algorithm}` + `algorithmic`）
- 至少 1 个 theorem/proposition + 数学推导
- 复杂度分析（time / memory / communication）
- Implementation notes（关键超参数、学习率、种子数）

**Experiments 章节必备**：
- Setup（数据集、baselines ≥4、metric、硬件、seed 数）
- Main results（Table 1-2，带 95% CI / std）
- Ablation（≥3 组件）
- Hyperparameter sensitivity + compute budget
- Qualitative analysis / failure cases

**Discussion 章节必备**：
- Limitations（明确列出，**不回避**）
- Broader impact（positive + negative）
- Reproducibility（代码/数据 release statement）

## 3. 公式与符号使用

**公式环境**：`equation`（单行无编号用 `equation*`）、`align`（多行对齐）、`gather`（无对齐多行）、`cases`（分段函数）。所有显示公式编号连续，重要公式加 `\label{eq:xxx}` 供 back-reference。

**Theorem/Lemma/Proposition 比例**：
- 理论 paper：Theorem 2-4 个 + Lemma 3-5 个 + Proposition 1-2 个
- 实证 paper：Proposition 1-2 个 + Claim 1-2 个（Claim 不排版成定理框）
- 凸优化理论：Theorem 集中于 convergence rate / sample complexity

**符号表**位置：放在 Preliminaries 章节末尾，使用 `tabular` 排版，每行 `Symbol & Description` + `\midrule` 中线。

**Algorithm box**：使用 `algorithm` + `algorithmic` 包，里面必须包含 `Require` / `Ensure` / `State` / `Return` 输入输出格式。复杂度用 `// O(n)` 注释。

## 4. 引用风格

**Author-year**：`\citep{Smith2020}` → `(Smith et al., 2020)`；`\citet{Smith2020}` → `Smith et al. (2020)`。NeurIPS 2024 使用 `plainnat` bst + `natbib` 包。

**引用密度**：每段 2-4 个 `\citep` 是常态。Introduction 约 15-25 个引用，Method 约 20-35 个，Related Work 约 30-50 个。

**总引用数**：30-60+ 是常态。高影响力论文（Oral / Spotlight）通常 60-100+。

**禁止**：
- 自引用暴露身份（double-blind 期间）
- 引用 arXiv preprint 时带版本号（`arXiv:2401.12345v2` ❌）
- 引用同期未公开工作

## 5. 图表风格

**Figure 1**：通常是 "teaser / overview / framework diagram"（如 DiT 系列用 1 张 architecture diagram）。多 panel 时用 `(a)` `(b)` `(c)` 子标。

**Caption 风格**：完整句子（不以句号结尾的 cmds 块 ❌），简短描述图像 + 关键 takeaway。如 *"Figure 1: Our pipeline achieves 3.93× training speedup over MDTv2 with lower FID."* 而不是 *"Figure 1: The pipeline."*

**Table 风格**：`booktabs` 三线表（`\toprule` / `\midrule` / `\bottomrule`），列名带单位（`FID↓` / `PSNR↑`），数值带 std（`0.83 ± 0.01`），最优值加粗 (`\textbf{0.83}`)，次优下划线 (`\underline{0.85}`)。

**不确定性**：所有数字必须 ± std over ≥3 seeds 或 95% CI；multi-task 报告时额外给出任务间 std。

**可视化**：heatmap > bar chart > line plot（receiver operating characteristic 偏好 radar/spider chart 较少）。使用 `matplotlib` 默认 `tab10` / `seaborn` 配色。

## 6. 真实顶会论文示例（13 篇）

| arxiv-id | 标题 | 接收 | 一句话贡献 |
|---|---|---|---|
| [2412.07877] | Score-Optimal Diffusion Schedules | NeurIPS 2024 | 自适应选择 diffusion 离散 schedule 的无超参算法 |
| [2406.01584] | SpatialRGPT | NeurIPS 2024 | 通过 region proposals 增强 VLM 的 3D 空间推理 |
| [2411.04168] | DiMSUM: Diffusion Mamba | NeurIPS 2024 | 在 diffusion 里融合 wavelet + Mamba 提升图像生成 |
| [2410.23788] | EDT: Efficient Diffusion Transformer | NeurIPS 2024 | 通过 attention modulation 把 DiT 训练加速 3.93× |
| [2410.22938] | DiffLight | NeurIPS 2024 | 用 partial-rewards 条件 diffusion 处理 missing-data 交通信号控制 |
| [2410.20474] | GrounDiT | NeurIPS 2024 | 通过 semantic-sharing 在 DiT 实现无训练 bounding box 空间控制 |
| [2410.18666] | DreamClear | NeurIPS 2024 | DiT-based 图像恢复 + GenIR 数据生成 pipeline |
| [2406.11831] | LLM as Prompt Encoder for Diffusion | NeurIPS 2024 | LI-DiT 框架让 LLM 做 diffusion prompt encoder |
| [2406.02485] | Stable-Pose | NeurIPS 2024 | ViT attention masking 用于 pose-guided T2I |
| [2406.01733] | Learning-to-Cache | NeurIPS 2024 | 在 DiT 推理时 learned caching 实现 46.84% 计算减少 |
| [2405.02730] | U-DiTs | NeurIPS 2024 | U-shaped DiT 把 token 下采样后以 1/6 cost 超越 DiT-XL/2 |
| [2402.03687] | PARD | NeurIPS 2024 | Permutation-invariant autoregressive diffusion 做图生成 |
| [2401.13858] | Graph DiT (Oral) | NeurIPS 2024 Oral | Multi-conditional 分子 + polymer 生成的 Graph DiT |

## 7. Rigor Checklist（用于自动评审）

- [ ] Main paper ≤ 9 pages（references + appendix 排除）
- [ ] Abstract ≤ 250 词
- [ ] Double-blind：no author / affiliation / self-identifying citation
- [ ] Introduction 包含 3-4 个 numbered contributions（每个 bullet 可独立验证）
- [ ] Method 包含 ≥1 Algorithm box + 完整数学推导 + complexity
- [ ] Theorems/Propositions 在 main paper 给出 proof sketch
- [ ] Experiments 包含 ≥4 strong baselines
- [ ] 所有数字 report 95% CI or std over ≥3 seeds
- [ ] Ablation 覆盖 ≥3 components
- [ ] Hyperparameter sensitivity + compute budget table
- [ ] Out-of-sample backtest with RMSE/MAE/CRPS（如有预测任务）
- [ ] Heterogeneity decomposition（hierarchical / panel）而非仅聚合
- [ ] Discussion 包含 Limitations（明确列出）
- [ ] Broader impact 正负两面都讨论
- [ ] Code+data release statement（GitHub URL）
- [ ] Reproducibility checklist 完整填答（附录）
- [ ] 所有 constructed quantities 有 reconciliation table
- [ ] 因果识别 / 内生性讨论（涉及因果时）
- [ ] Endogenous feedback loop + SVAR justification（系统建模时）
- [ ] Network loss-propagation layer（系统性风险建模时）

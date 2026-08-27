---
name: ieee-conference-skill
description: Use when writing an IEEE conference paper (CCF-A: S&P / CCS / SIGCOMM / VLDB / CVPR / ICCV / ICASSP / INFOCOM) — 2-column IEEEtran conference mode, Roman-numeral section numbering (I, II, III), Roman citations, mandatory Index Terms, IEEE Reference Format. Triggers on tasks like "write IEEE paper", "IEEEtran conference submission", "S&P / CCS / VLDB / CVPR / INFOCOM paper".
---

# ieee_conference Skill

> 来源：基于 6 篇 arxiv 接收论文的写作风格研究（CVPR 2024 × 2, ICASSP 2024 × 1, IEEE INFOCOM 2024 × 2, CVPR 2024 Camera-Ready × 1）
> 生成日期：2026-08-16
> 适用模板：`ieee_conference`（CCF-A 安全/系统/网络/数据库/视觉/信号会议统一家族）

## 1. 写作风格基线

**Abstract 严格 150-250 词**。IEEE 接收论文的 Abstract 几乎都贴着上限。结构：1 句问题 → 1 句已有方法不足 → 1-2 句本文方法（强调 novelty 关键词如 "novel / first / effective / efficient"）→ 1-2 句最强结果（带数字 + dataset 名）→ 1 句结尾（"Code is available at …"）。**不引用图表，不写 "in this paper"**。

**Index Terms 紧随 Abstract**。IEEE 强制元数据，3-5 个 italicized comma-separated keywords（用 `\begin{IEEEkeywords}` 环境）。Index Terms 与 ACM 的 Keywords 是同一类信息但术语不同（IEEE 用 "Index Terms"，IEEE Computer Society 用 "Keywords"，必须匹配模板要求）。

**Introduction 五要素结构**：
1. **Concrete motivating example or measurement**（"We observe that …" / "Consider a real-world scenario …"）— 接收论文几乎都在 Introduction 第 1 段给一个具体数据集 / 测量 / 工业案例。
2. **Limitations of prior work**（直接说 "X is limited by Y" / "Despite progress, … remains constrained because …"）。
3. **Our Approach**（1-2 段，给 high-level overview，常含 1 个 teaser figure）。
4. **Contributions**（3-5 个 numbered bullet list，**每个 bullet 可独立验证**）。
5. **Roadmap**（"The remainder of this paper is organized as follows. Section II … Section VII concludes."）。

**Related Work 按主题聚类**（不按时间线）。每段 1 类（"A. Graph Neural Networks for Pose Estimation"，"B. Attention-based Methods"，"C. Occlusion-aware Approaches"），每段最后一句明确本文相对 SoTA 的位置（"Our method differs by …"）。**至少 20 篇近 3-5 年顶会/期刊引用**。

**Background / Preliminaries 必备**：Notation Table（Symbol / Description）+ Problem Formulation（formal definition）+ minimum preliminaries。**这是 IEEE 比 ACM 强制要求更强的部分**。

**Method 章节大块**：Overview（架构图 + 文字）→ Component 1-3（每个独立 subsection + 数学推导 + intuition + complexity）→ Theoretical analysis（如 correctness proof / convergence）。

**Experiments 章节大块**：Setup → Main Results（≥3 张结果表/图，**带 p-value / 显著性检验**）→ Ablation Study（≥3 components）→ Sensitivity Analysis（tornado / hyperparam curves）→ Case Study（推荐）。

**Discussion 章节必备**：Threats to Validity（internal / external / construct）+ Limitations + Ethical Considerations。

**Conclusion** 简明：总结核心贡献 + 1-2 段 future work。

**排版**：`IEEEtran` document class，`conference` 模式（two-column, 10pt）。**强制** `\IEEEoverridecommandlockouts`、`\usepackage{cite}`、`\usepackage{amsmath,amssymb,amsfonts}`、`\usepackage{algorithmic}`、`\usepackage{booktabs}`、`\usepackage{hyperref}`。页限制 6-12 main pages excluding references and appendix。

## 2. 章节结构与命名约定

IEEE Conference 论文采用 **罗马数字章节编号**（与 ACM 阿拉伯数字相反）：

1. **Abstract**（无编号）
2. **Index Terms**（无编号，IEEE 强制）
3. **I. Introduction**（约 1.5-2 页）
4. **II. Related Work**（约 0.5-1 页）
5. **III. Background and Preliminaries**（约 0.5-1 页，**符号表 + 问题形式化**）
6. **IV. Method**（约 3-5 页，最大块）
7. **V. Experiments**（约 2-3 页，含 ablation + sensitivity + case study）
8. **VI. Discussion**（约 0.5 页，Threats to Validity）
9. **VII. Conclusion**（约 0.3 页）
10. **Acknowledgments**（无编号）
11. **References**（无编号，IEEE Reference Format：数字 `[1]` + author. title. *Conference*, YEAR, pp.)
12. **Appendix**（可选，无编号）

**章节编号**：罗马数字大写 `I, II, III, IV, V, VI, VII`。

**小节编号**：`IV.A. Component 1`，`IV.B. Component 2`（注意 subsection 字母 + 句点；subsubsection 用阿拉伯数字 `IV.B.1`）。

**章节标题大小写**：Title Case（每个实词首字母大写），如 "Experimental Setup" 而非 "Experimental setup"。**IEEE 强制 sentence case 较少**，Title Case 是主流。

## 3. 公式与符号使用

**公式环境**：`equation`（带编号）、`align`（多行带编号）、`align*`（多行无编号）、`IEEEeqnarray`（IEEE 特有，传统 3 列环境）、`gather`、`cases`。IEEE 比 ACM 偏好更多 `IEEEeqnarray` 排版（带 left/center/right 三列对齐）。

**Display equation 平均每页 4-8 个**（高于 ACM）。视觉/signal 论文公式密度更高。

**符号表**：放在 Background 章节末尾 1 段 *Notation Table*。IEEE 偏好 `tabular` 三列（Symbol / Description / Value/Range）。**强制性高于 ACM**（IEEE review 直接扣分）。

**Theorem/Lemma/Proposition**：CVPR/ICCV 这类视觉会议较少使用（< 5%），但 INFOCOM/S&P/CCS 等系统会议约 10-15% 包含 1 个 Theorem + 简短 proof sketch。

**Algorithm box**：使用 `algorithm` + `algorithmic`（IEEE 风格）。CVPR/ICCV 偏好 numbered hyperparameters (`lr=1e-4, bs=32`)。

## 4. 引用风格

**IEEE numeric `[1]` + IEEE Reference Format**。使用 `ieeetr` bibstyle，参考文献格式如：
```
[1] A. Author, B. Author, "Title of the paper," in Proc. IEEE Conf. Computer Vision and Pattern Recognition (CVPR), YEAR, pp. 1234-1245.
```

**引用密度**：每段 3-5 个引用（高于 ACM）。Introduction 平均 20-30 引用，Related Work 30-50 引用。**总引用数 40-80+ 常态**。

**必须**：使用 `\usepackage{cite}` 启用 IEEE 风格引用压缩（如 [1, 2, 3] → [1-3]）。

**禁止**：
- 引用非公开来源（preprint 除外）
- 引用时使用 author-year 风格（IEEE 是纯数字）
- 引用自己 demo 时用冗余语言

## 5. 图表风格

**Figure 1 几乎总是 teaser / framework overview**。IEEE 偏好 **彩色 block diagram with arrows**（与 ACM 类似），但 CVPR/ICCV 类视觉会议偏好 **results teaser**（左右对比、attention map overlay、failure case）。

**Caption 风格**：完整句子结尾（"."）。偏好 "Figure 1: Overview of FooBar. (a) Module A processes X. (b) Module B refines Y. (c) Module C outputs Z." 子图 caption 用 `\subfloat[label]{...}`。

**Table 风格**：`booktabs` 三线表。IEEE 偏好 **best/second-best bold/underline**（best 加粗、second-best 加下划线），CVPR 几乎强制。

**子图 / Panel**：使用 `subfloat` 或 `subcaption`，标签 `(a)`, `(b)`, `(c)`。**CVPR/ICCV 4-panel 图极常见**（如 ablation + attention map + qualitative + t-SNE）。

**统计**：所有数字必须 ± std over ≥3 seeds 或 95% CI。**t-test 显著性标注 `*` / `**` / `***` for p<0.05 / 0.01 / 0.001** 是 CVPR/ICASSP 标准做法。

## 6. 真实顶会论文示例（6 篇）

| arxiv-id | 标题 | 接收 | 一句话贡献 |
|---|---|---|---|
| [2401.00029] | 6D-Diff | CVPR 2024 | Mixture-of-Cauchy 扩散 + reverse diffusion 做 6D 物体 pose 估计 |
| [2401.00094] | Generating Enhanced Negatives | CVPR 2024 | 用 LLM + diffusion 生成 enhanced negatives 训练 open-vocabulary detector |
| [2401.00155] | Occluded Human Pose Estimation (DAG) | ICASSP 2024 | DAG (Data, Attention, Graph) 综合框架处理 occlusion |
| [2401.00374] | EMAGE | CVPR 2024 | BEAT2 数据集 + Masked Audio Gesture Transformer 做 holistic 协同手势生成 |
| [2401.03812] | ORANUS | IEEE INFOCOM 2024 | 用 stochastic network calculus 在 6G O-RAN 中实现 latency-tailored orchestration |
| [2401.04996] | Distributed Experimental Design Networks | IEEE INFOCOM 2024 | 用 networked 实验设计分配 + bandit 推理实现 distributed A/B testing |

## 7. Rigor Checklist（用于自动评审）

- [ ] Main paper 6-12 页（references + appendix 排除）
- [ ] Abstract 150-250 词，**不引用图表**，不写 "in this paper"
- [ ] **Index Terms** 3-5 个（用 `\begin{IEEEkeywords}...\end{IEEEkeywords}`）
- [ ] 章节使用**罗马数字**编号 `I, II, III, IV, V, VI, VII`
- [ ] Introduction 含 concrete motivating example + 3-5 个 numbered contributions + roadmap
- [ ] Related Work 按主题聚类（≥3 类），每段明确本文相对 SoTA 位置
- [ ] Background 含 **Notation Table**（Symbol / Description / Range）+ **Problem Formulation**
- [ ] Method 包含 system overview + ≥3 components（独立 subsection）+ 数学推导 + complexity
- [ ] Experiments 含 **≥5 baselines** + ≥3 ablations + sensitivity tornado + case study
- [ ] 所有数字 report std/CI over ≥3 seeds + **p-value 显著性标注**
- [ ] **Discussion 包含 Threats to Validity**（internal / external / construct）+ Limitations + Ethical Considerations
- [ ] References 使用 IEEE Reference Format（`\bibliographystyle{ieeetr}` + `\usepackage{cite}`）
- [ ] 引入 `\IEEEoverridecommandlockouts` 防止 IEEEtran 锁住命令
- [ ] 因果识别 / 内生性讨论（涉及因果时）
- [ ] Endogenous feedback loop + SVAR justification（系统建模时）
- [ ] Network loss-propagation layer（系统性风险建模时）
- [ ] 所有 constructed quantities 有 reconciliation table
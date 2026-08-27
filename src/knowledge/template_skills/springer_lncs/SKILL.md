---
name: springer-lncs-skill
description: Use when writing a Springer LNCS paper (Lecture Notes in Computer Science, CCF-B class but widely used: ECIR / ECML-PKDD / SGAI / ADMA / DEXA / IFIP) — single-column compact A4, 10pt, llncs document class, numeric citations, author-year alternative, mandatory keyword footnote, Springer SVMonograph style. Triggers on tasks like "write LNCS paper", "Springer Lecture Notes paper", "ECML-PKDD / ECIR / SGAI submission".
---

# springer_lncs Skill

> 来源：基于 6 篇 arxiv 接收论文的写作风格研究（ECIR 2024 × 5, SGAI 2023 LNCS × 1）
> 生成日期：2026-08-16
> 适用模板：`springer_lncs`（Springer 旗下 LNCS 系列会议，覆盖 IFIP / EuroSys 类以及多数 CCF-C/B 国际会议）

## 1. 写作风格基线

**Abstract 严格 150-200 词**。LNCS 接收论文的 Abstract 普遍偏短、偏 compact。典型结构：1-2 句问题背景（"X has become a key challenge in …"）→ 1 句 gap（"However, existing methods …"）→ 2-3 句方法概要（"In this paper, we propose FooBar, which …"）→ 1-2 句最强结果（"Experiments on three benchmarks show that FooBar achieves …, outperforming the state-of-the-art by X%"）→ 1 句 contribution 总结。

**Keywords 紧随 Abstract**（脚注式）。LNCS 用同一段 `\textbf{Keywords:} ...` 放在 abstract 末尾（不是独立 section）。**3-5 个关键词**，逗号分隔，全小写或首字母大写均可。

**Introduction 结构**：
1. 1 段 motivation（具体应用场景或真实数据）
2. 1 段 limitations of prior work
3. 1 段 approach overview（"In this paper we propose …"）
4. **Bullet list of 3-4 contributions**（**比 IEEE/ACM 略短**，3-4 个 bullet，篇幅 0.5 段）
5. 1 段 paper organization（"The remainder of this paper is structured as follows. Section 2 … Section 6 concludes."）

**Related Work 短而精**。LNCS 论文 Related Work 通常 0.5-0.8 页（明显短于 ACM/IEEE 的 1-1.5 页）。倾向于 2-3 类聚类（不像 IEEE 强制 ≥3 类），每段 3-5 句话 + 1 句区分性陈述。

**Preliminaries 章节必备**（与 IEEE 类似）。Symbol Table + Problem Formulation 是 LNCS 严格期望。**Notation Table 必须存在**，3 列表格（Symbol / Description / Domain）。

**Method 章节**：Overview + 详细推导 + Algorithm box + Complexity。LNCS 偏好理论倾向（Theorem/Lemma 出现频率略高于 ACM，约 5-10%）。

**Experiments 章节**：Setup + Main Results + Ablation（≥3 components）+ Sensitivity。**Case Study 不是强制项**（不像 ACM）。

**排版**：`llncs` document class（two-column, 10pt, A4）。**强制** `\titlerunning{...}` + `\authorrunning{...}`（短标题 + 作者名 for header）。页限制 8-14 pages including references。

## 2. 章节结构与命名约定

LNCS 论文采用 **阿拉伯数字章节命名 + Springer 紧凑章节命名**：

1. **Abstract**（无编号，单独首页，含关键词）
2. **1 Introduction**（约 1-1.5 页）
3. **2 Related Work**（约 0.5-0.8 页）
4. **3 Preliminaries**（约 0.5-1 页，符号表 + 问题形式化）
5. **4 Method**（约 3-4 页，最大块）
6. **5 Experiments**（约 2-3 页）
7. **6 Conclusion**（约 0.3 页，无 Discussion 章节）
8. **References**（无编号）
9. **Appendix**（可选，无编号）

**章节编号**：阿拉伯数字 `1, 2, 3, 4, 5, 6`（与 ACM 相同，但**比 ACM 少**Discussion 章节）。

**小节编号**：`4.1 Overview`，`4.2 Component 1`，`4.3 Component 2`。

**章节标题大小写**：Sentence case（仅首词首字母大写 + 专有名词），如 "Experimental setup" 而非 "Experimental Setup"。**LNCS 强制 sentence case**（与 IEEE title case 不同）。

**关键差异**：LNCS 没有 Discussion 章节（与 ACM 不同），Conclusion 直接接 Experiments 之后，篇幅短。

## 3. 公式与符号使用

**公式环境**：`equation`（带编号）、`align`（多行）、`align*`、`gather`、`cases`。与 ACM/IEEE 类似，但 LNCS 偏好**更紧凑的 display equation 排版**（节省版面）。

**Display equation 平均每页 3-5 个**（介于 ACM 与 IEEE 之间）。

**符号表**：Preliminaries 末尾 1 段 *Notation Table*，强制存在。3 列（Symbol / Description / Domain/Range）。Springer style 偏好更密集（行高更紧）。

**Theorem/Lemma**：LNCS 出现频率高于 ACM（约 5-10%），使用 `\{theoremstyle{definition}` 或 `\theoremstyle{plain}` 切换样式。

**Algorithm box**：使用 `algorithm` + `algorithmic`，编号行 `\STATE` + 自然语言描述。LNCS 比 ACM 更接受 pseudo-code。

## 4. 引用风格

**Springer numeric `[1]` + alphabetical alternative `[AB12]`**。使用 `splncs04` bibstyle。引用样式：`\citep{Smith2020}` → `[1]`（numeric）或 `[Smi20]`（author-year）。

**引用密度**：每段 2-4 个引用。Introduction 平均 15-20 引用，Related Work 20-30 引用。**总引用数 25-50+ 常态**（比 ACM/IEEE 略少，反映 LNCS 偏 short paper 性质）。

**禁止**：
- 引用未发表工作（preprint 除外）
- 使用非 Springer 标准格式

## 5. 图表风格

**Figure 1 偏好方法 overview**。LNCS 偏好 **简化 block diagram**（比 ACM 略简单），常含 3-5 个组件 + 箭头标注数据流。

**Caption 风格**：完整句子结尾（"."）。偏好简洁 caption 如 "Fig. 1. Overview of FooBar."（注意 LNCS 用 "Fig." 而非 "Figure"）。

**Table 风格**：`booktabs` 三线表。LNCS 偏好**多列对比表**（数据集横向），但不强制 best/second-best 高亮。

**子图 / Panel**：使用 `\subfloat` 或 `\subcaption`，标签 `(a)`, `(b)`。LNCS 子图数量通常较少（1-3 panel），不像 CVPR 经常 4-panel。

**统计**：所有数字必须 ± std over ≥3 seeds 或 95% CI。**但显著性检验标注（`*` for p<0.05）在 LNCS 不如 CVPR 强制**。

## 6. 真实顶会论文示例（6 篇）

| arxiv-id | 标题 | 接收 | 一句话贡献 |
|---|---|---|---|
| [2401.01596] | MedSumm | ECIR 2024 | 多模态 Hindi-English 医疗问题摘要 (MMCQS dataset + LLM/VLM) |
| [2401.02827] | Let's Get It Started | ECIR 2024 | Deezer 流媒体冷启动发现的 industry talk |
| [2401.04810] | Translate-Distill | ECIR 2024 | 通过翻译 + distillation 做跨语言 dense retrieval |
| [2401.05939] | DREQ | ECIR 2024 | 基于 entity-based query understanding 的文档重排序 |
| [2401.05148] | On the Influence of Reading Sequences | ECIR 2024 | 研究 web search 中阅读顺序对 knowledge gain 的影响 |
| [2401.05822] | Towards Goal-Oriented Agents | SGAI 2023 (LNCS 14381) | 通过对话观察 evolving problems 的目标导向 agent |

## 7. Rigor Checklist（用于自动评审）

- [ ] Main paper 8-14 页（references + appendix 排除）
- [ ] Abstract 150-200 词，含 `\textbf{Keywords:}` 脚注式
- [ ] Keywords 3-5 个，紧随 Abstract 末尾
- [ ] 章节使用**阿拉伯数字**编号 `1, 2, 3, 4, 5, 6`（无 Discussion 章节）
- [ ] 章节标题使用 **Sentence case**（如 "Experimental setup"）
- [ ] `\titlerunning{...}` + `\authorrunning{...}` 已在 preamble 设置
- [ ] Introduction 含 concrete motivation + 3-4 个 numbered contributions + organization
- [ ] Related Work 0.5-0.8 页，2-3 类聚类
- [ ] Preliminaries 含 **Notation Table** + **Problem Formulation**
- [ ] Method 包含 overview + 完整推导 + Algorithm box + complexity analysis
- [ ] Experiments 含 **≥4 baselines** + ≥3 ablations + sensitivity
- [ ] 所有数字 report std/CI over ≥3 seeds
- [ ] Conclusion 简明（无 Discussion 章节直接接 Conclusion）
- [ ] References 使用 Springer numeric（`\bibliographystyle{splncs04}`）
- [ ] 因果识别 / 内生性讨论（涉及因果时）
- [ ] Endogenous feedback loop + SVAR justification（系统建模时）
- [ ] Network loss-propagation layer（系统性风险建模时）
- [ ] 所有 constructed quantities 有 reconciliation table
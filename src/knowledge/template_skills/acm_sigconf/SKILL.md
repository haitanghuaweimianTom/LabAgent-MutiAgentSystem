---
name: acm-sigconf-skill
description: Use when writing an ACM SIG Conference paper (CCF-A: SIGGRAPH / MobiCom / CHI / SOSP / OSDI / SIGMOD / CCS) — 2-column acmart/sigconf, mandatory CCS Concepts + Keywords, ACM Computing Classification, numeric citations, ACM Reference Format. Triggers on tasks like "write ACM paper", "acmart submission", "SIGMOD / SIGGRAPH / CHI / MobiCom paper".
---

# acm_sigconf Skill

> 来源：基于 6 篇 arxiv 接收论文的写作风格研究（SIGMOD 2024 × 2, ACM CHI 2024 × 1, ACM CSCW 2024 × 2, ACM SIGMETRICS 2024 × 1）
> 生成日期：2026-08-16
> 适用模板：`acm_sigconf`（CCF-A 系统/数据库/HCI/移动/图形/安全/操作系统会议统一家族）

## 1. 写作风格基线

**Abstract 严格 150–200 词**。ACM SIG 接收论文的 Abstract 几乎都贴着 200 词上限。首句 1 句问题陈述（"X is becoming increasingly important for…" 或 "Despite progress in Y, Z remains limited because…"），接下来 2-3 句方法概要（强调新颖机制或系统组件），末段 1-2 句最强结果（带具体数字，例如 "We achieve a 43.9× speedup over SOTA while maintaining the same accuracy"），可附 1 句 supplementary/demo URL。**不允许引用图表**。

**CCS Concepts + Keywords 紧随 Abstract**。CCS Concepts 是 ACM 强制元数据，按 ACM Computing Classification 2012 的层级树给出 1-3 个（最常见如 "Computing methodologies → Machine learning" 或 "Information systems → Data management systems"）。Keywords 紧随其后给 3-5 个逗号分隔的术语。这两个块在双栏版本里横跨两栏显示（`\settopmatter{printccs=true, printfolios=true}`）。

**Introduction 五要素结构**：
1. 1 段 motivating scenario（具体应用 / 真实用户痛点 / 真实测量数据）
2. 1 段 limitations of prior work（直接命名 "X is limited by Y" / "However, … fails when … because …"）
3. 1 段 approach overview（"In this paper we propose FooBar, a … that …"）
4. **Bullet list of 3-4 concrete contributions**（"Our contributions are: (i) … (ii) … (iii) …"，每个 bullet 可独立验证）
5. 1 段 paper organization（"The remainder of this paper is organized as follows. Section 2 … Section 7 concludes."）

**Method 章节强烈系统导向**。典型结构：System Overview Figure（图 1，block diagram with arrows）→ Component 1（subsection + 段落 + 可选 Algorithm box）→ Component 2 → … → Theoretical analysis（如适用）。在 sigconf 模式下，Algorithm box 倾向于使用 `algorithm` + `algorithmic` 包，编号超参数 (`lr = 1e-3`)。

**Evaluation 章节必有**：Experimental setup（datasets, baselines, metrics, hardware）→ Main results（表 + 图，**统计显著性**）→ Ablation study（≥3 components）→ Real-world case study / user study（ACM SIG 偏好 system papers 包含 throughput / latency / scalability）。

**排版**：`acmart` document class，`sigconf` 模式（two-column, 10pt, letterpaper）。**强制** `\acmConference[]'__YEAR__}{…}`、`\acmISBN{…}`、`\acmDOI{…}`、`\setcopyright{none}`。页限制 6-14 main pages（CHI 倾向 8-10 + supplementary）。

## 2. 章节结构与命名约定

ACM SIG 论文采用 **ACM 标准章节命名**：

1. **Abstract**（无编号，单独一页首页）
2. **CCS Concepts**（无编号，2-3 个，\ccsdesc[500]{…}）
3. **Keywords**（无编号，3-5 个，\keywords{…}）
4. **1 Introduction**（1.5-2 页，含上述五要素）
5. **2 Related Work**（0.5-1 页，按主题聚类）
6. **3 Method / System Design**（3-5 页，最大块）
7. **4 Implementation**（0.5-1 页，可选）
8. **5 Evaluation**（2-3 页，含 case study / user study）
9. **6 Discussion**（0.3-0.5 页，含 Limitations + Ethical Considerations）
10. **7 Conclusion**（0.3 页）
11. **Acknowledgments**（无编号）
12. **References**（无编号，ACM Reference Format：`[1] Author. Title. Conference 'YY. DOI.`）
13. **Appendix**（无编号，可选）

**章节编号**：阿拉伯数字 `1, 2, 3`，与 IEEE 罗马数字 `I, II, III` 形成显著差异。

**小节编号**：`3.1 Component 1`，`3.2 Component 2`。**Subsection 最多 2 层**（一般不用 subsubsection）。

## 3. 公式与符号使用

**公式环境**：`equation`（单行 + 编号）、`align*`（多行无编号）、`align`（多行有编号）、`gather`、`cases`。ACM sigconf 偏好单栏排版时公式尽量少；只在 Method 章节出现。**Display equation 平均每页 3-6 个**（低于 IEEE NeurIPS）。

**符号表**：通常放在 Preliminaries 末尾（如果论文含 Preliminaries 章节），1 段 tabular 三列（Symbol / Description / Units）。**不是强制项**，ACM sigconf 比 Springer LNCS 更容忍缺少完整 notation table。

**Theorem/Lemma**：ACM SIG 偏 system papers 时极少使用 Theorem 块（< 5% 的论文）；偏 theory-oriented 时（如 SIGMOD PODS、SIGACT）Theorem + proof 比例较高（10-20%）。

**Algorithm box**：使用 `\begin{algorithm}` + `\begin{algorithmic}[1]`，编号行用 `\STATE`。ACM SIG 偏好 pseudo-code 风格而非纯文字描述。

## 4. 引用风格

**ACM numeric `[1]` + ACM Reference Format**。使用 `acm` bibstyle，参考文献格式如：
```
[1] First Author, Second Author. 2023. Title of the paper. In Proceedings of the 30th ACM International Conference on Information & Knowledge Management (CIKM '21). Association for Computing Machinery, New York, NY, USA, 123–135. https://doi.org/10.1145/xxxxx
```

**引用密度**：每段 2-4 个引用。Introduction 平均 15-25 引用，Related Work 25-40 引用。**总引用数 30-60+ 常态**。

**禁止**：
- 引用未发表工作（preprint 除外）
- 引用自己 demo video / supplementary 时用 "in this paper" 风格冗余短语
- 使用非 ACM 标准格式（必须 `\bibliographystyle{acm}`）

## 5. 图表风格

**Figure 1 几乎总是系统 / 方法 overview**。ACM SIG 偏好 **彩色 block diagram**（不同模块不同颜色 + 箭头标注数据流），常含 5-8 个有名字的组件（如 [Starling: SIGMOD 2024] 用红/蓝/绿三色标注 data layout + block search 两阶段）。

**Caption 风格**：完整句子结尾（"."），首字母大写。偏好 "Figure 1: Architecture of FooBar, consisting of three modules: X (blue), Y (red), Z (green)." 简洁信息密集。

**Table 风格**：`booktabs` 三线表（`\toprule`, `\midrule`, `\bottomrule`），不使用 vertical lines。ACM sigconf 偏好 **side-by-side comparison table**（多数据集横向展开）。

**子图 / Panel**：使用 `subfloat` 或 `subcaption`，标签 `(a)`, `(b)`, `(c)`。CVPR 风格论文常用，但 ACM SIGMOD/SIGGRAPH 也接受 4-panel 图。

**统计**：所有数字必须 ± std over ≥3 seeds 或 95% CI。**粗体 best result** + 下划线 second-best 是 ACM 表的标准格式。

## 6. 真实顶会论文示例（6 篇）

| arxiv-id | 标题 | 接收 | 一句话贡献 |
|---|---|---|---|
| [2401.02116] | Starling | SIGMOD 2024 | 磁盘驻留图索引框架，33M 向量查询 < 1ms 延迟 |
| [2401.03359] | In-Database Data Imputation | SIGMOD 2024 | 在 PostgreSQL / DuckDB 内做 MICE imputation，2 数量级加速 |
| [2401.04118] | Towards Directive Explanations | ACM CHI 2024 | 给非技术用户的 directive XAI 框架 |
| [2401.01168] | FedQV | ACM SIGMETRICS 2024 | 用二次投票 (quadratic voting) 做 FL aggregation，抗 poisoning |
| [2401.04543] | Healthcare Voice AI Assistants | ACM CSCW 2024 | 300 人调查 + PLS-SEM 模型解释 HVA trust/intention |
| [2401.00928] | OSINT Research Studios | ACM CSCW 2024 | 灵活 crowdsourcing 框架加速 OSINT 调查 |

## 7. Rigor Checklist（用于自动评审）

- [ ] Main paper 6-14 页（references + appendix 排除）
- [ ] Abstract 150-200 词，**不引用图表**
- [ ] **CCS Concepts** 至少 1-3 个（按 ACM Computing Classification 2012）
- [ ] **Keywords** 3-5 个，紧随 CCS Concepts
- [ ] `\acmConference[]'__YEAR__}{...}` + `\acmISBN{...}` + `\acmDOI{...}` + `\setcopyright{none}` 完整
- [ ] `\settopmatter{printacmref=true, printccs=true, printfolios=true}` 已设置
- [ ] Introduction 含 3-5 个 numbered contributions（每个 bullet 可独立验证）
- [ ] Method 包含 system overview figure + Algorithm box + 完整组件描述
- [ ] Evaluation 包含 ≥5 baselines + ≥3 ablations + 真实 case study
- [ ] 所有数字 report std/CI over ≥3 seeds
- [ ] Discussion 包含 Limitations + Ethical Considerations + Broader Impact
- [ ] References 使用 ACM Reference Format（`\bibliographystyle{acm}`）
- [ ] 因果识别 / 内生性讨论（涉及因果时）
- [ ] Endogenous feedback loop + SVAR justification（系统建模时）
- [ ] Network loss-propagation layer（系统性风险建模时）
- [ ] 所有 constructed quantities 有 reconciliation table
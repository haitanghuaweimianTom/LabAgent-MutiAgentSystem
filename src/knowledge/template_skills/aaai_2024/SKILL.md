---
name: aaai-2024-skill
description: Use when writing an AAAI 2024 paper (CCF-A AI, 7-page main + 2-page appendix hard limit, letterpaper, 10pt, double-column, applied AI focus) — application-driven abstract, multiple datasets, ≥5 baselines, ablations ≥3, application case study. Triggers on tasks like "write AAAI paper", "AAAI 2024 submission", "7-page AI paper".
---

# aaai_2024 Skill

> 来源：基于 5 篇 arxiv 接收论文的写作风格研究（AAAI 2024 × 5）
> 生成日期：2026-08-16
> 适用模板：`aaai_2024`（CCF-A AI 通用会议，强调 application value + experimental thoroughness）

## 1. 写作风格基线

**Abstract 严格 150-250 词**。AAAI 接收论文的 Abstract 几乎贴着上限，且**强制 application-oriented**。典型结构：1-2 句 application motivation（"X plays a crucial role in real-world Y applications"）→ 1 句 gap（"However, existing methods …"）→ 2-3 句 method（含 mechanism/intuition）→ 1-2 句 strongest result + uncertainty（"Experiments on multiple benchmarks show FooBar outperforms SoTA by X% (p < 0.05)"）→ 1 句 application value 总结。

**AAAI 评审最高权重**：application value + experimental thoroughness。因此 Abstract 必须 explicit mention real-world application + 多数据集 evaluation + best quantitative result。

**Introduction 五要素结构**：
1. **Concrete real-world application scenario**（"In recent years, X has emerged as a key challenge in Y applications such as …"）
2. **Limitations of prior approaches**（直接说 "X suffers from Y limitation / fails when Z"）
3. **Our contributions**（3-4 个 bullet，**AAAI 强调 ≥1 个涉及因果识别 / 回测 / 网络层**）
4. 1 段 high-level approach
5. Roadmap（"Section 2 reviews related work. Section 3 introduces …"）

**Preliminaries 必备**：Symbol Table + Problem Formulation。AAAI 比 ACM 严格，比 IEEE 略宽松。

**Method 章节**：Overview（系统图）+ Algorithm box + 推导 + complexity。**AAAI 理论不是核心**（ICML/NeurIPS 才是），所以可以 lighter than ICML，但仍需要 rigor。

**Experiments 章节是 AAAI 最强章节**（AAAI 评审最看重）：
- **Setup**：multi-datasets（≥3，最好 5+）+ baselines (≥5, **含 systemic-risk/network models when relevant**) + metric + hardware + seed 数
- **Main Results**：至少 3 张结果表/图，**带 ± std**（AAAI 强偏好）
- **Ablation Study**：≥3 components
- **Sensitivity Analysis**：tornado + elasticity to priors
- **Application Case Study**（AAAI 特色，**强烈推荐**）
- **Discussion of Failure Cases**

**Discussion 章节必备**：Limitations（含未建模渠道）+ Broader Impact（正负两面）+ Reproducibility statement。

**Conclusion**：总结 + future work（1-2 段）。

**排版**：`aaai24.sty`（letterpaper, 10pt, double-column）。**STRICT 7-page main limit + 2-page appendix**（references 不计入 7 页）。

## 2. 章节结构与命名约定

AAAI 2024 论文采用 **阿拉伯数字章节命名 + 7 章节结构**：

1. **Abstract**（无编号，单独首页）
2. **1 Introduction**（约 1-1.5 页）
3. **2 Related Work**（约 0.5-1 页）
4. **3 Preliminaries**（约 0.5-1 页，符号表 + 问题形式化）
5. **4 Method**（约 2-3 页，比 ICML 略轻）
6. **5 Experiments**（约 2-3 页，**AAAI 最强章节**，多数据集 + ≥5 baselines）
7. **6 Discussion**（约 0.3-0.5 页）
8. **7 Conclusion**（约 0.3 页）
9. **References**（无编号，**不计入 7 页硬限**）
10. **Appendix**（无编号，**2 页硬限**）

**章节编号**：阿拉伯数字 `1, 2, 3, 4, 5, 6, 7`。

**小节编号**：`4.1 Overview`，`4.2 Algorithm`。

**章节标题大小写**：Title Case（每个实词首字母大写），如 "Experimental Results" 而非 "Experimental results"。

**页数硬约束**：
- **Main paper ≤ 7 页**（包含 references 之前的全部内容，但 **References 不计入 7 页**）
- **Appendix ≤ 2 页**（proofs、additional experiments、broader impact）

## 3. 公式与符号使用

**公式环境**：`equation`、`align`、`align*`、`gather`、`cases`。与 ACM/IEEE 一致。

**Display equation 平均每页 3-6 个**（AAAI 偏 applied，公式密度低于 ICML/NeurIPS）。

**符号表**：Preliminaries 末尾 1 段 Notation Table。3 列（Symbol / Description / Range）。AAAI 偏好简洁（行高紧）。

**Theorem/Lemma**：AAAI 论文 Theorem/Lemma 出现频率比 ICML 略低（约 5-10%），但 AAAI 仍然接受 theoretical contribution。实证 paper 可以跳过 Theorem 章节。

**Algorithm box**：使用 `algorithm` + `algorithmic`，编号行 + numbered hyperparameters。AAAI 偏好 pseudo-code 但可读性优先。

## 4. 引用风格

**AAAI numeric `[1]` + plain bibstyle**。参考文献格式如：
```
[1] Author, A., Author, B. (2020). Title of the paper. In Proceedings of the AAAI Conference on Artificial Intelligence (AAAI), 34(01), 1234-1241.
```

**引用密度**：每段 2-4 个引用。Introduction 平均 15-25 引用，Related Work 25-35 引用。**总引用数 30-50+ 常态**。

**注意**：AAAI 投稿时 **anonymized authors + affiliations**（double-blind），review 完成后才 author 公开。**禁止 self-identifying citation**。

## 5. 图表风格

**Figure 1 偏好 application + framework overview**。AAAI 比 ACM/IEEE 更偏好 **application photos / screenshots / real data visualizations**（而非纯 algorithm diagram）。

**Caption 风格**：完整句子结尾（"."）。偏好 "Figure 1: Overview of FooBar applied to Y application." 或 "Figure 2: Performance of FooBar vs baselines on 3 datasets."

**Table 风格**：`booktabs` 三线表。**AAAI 强烈偏好 best/second-best bold/underline**，multi-dataset comparison 一张表横向展开。

**子图 / Panel**：使用 `\subfloat`，标签 `(a)`, `(b)`, `(c)`。AAAI 子图常见 2-3 panel（less than CVPR's 4-panel）。

**统计**：所有数字必须 ± std over **≥5 seeds**（AAAI 比 ACM 严格），且 report 95% CI when possible。**t-test 显著性标注是 AAAI 标配**。

## 6. 真实顶会论文示例（5 篇）

| arxiv-id | 标题 | 接收 | 一句话贡献 |
|---|---|---|---|
| [2401.00298] | Principal-Agent Reward Shaping in MDPs | AAAI 2024 | Stackelberg game 下 budget-bounded reward shaping，给 stochastic tree + deterministic DP 近似算法 |
| [2401.00315] | Bidirectional Temporal Plan Graph (BTPG) | AAAI 2024 | MAPF plan execution 中允许切换 passing order，减少 8-20% 不必要等待 |
| [2401.03194] | Learning Persistent Community Structures | AAAI 2024 | MFC + persistence homology + TopoReg 做动态网络时序一致的 community detection |
| [2401.00268] | COMMA | AAAI 2024 | Co-Articulated vision-language prompt learning，保留 CLIP 预训练知识 |
| [2401.01377] | Does Few-shot Learning Suffer from Backdoor Attacks? | AAAI 2024 | 揭示 few-shot learning 中存在的 backdoor attack 漏洞 |

## 7. Rigor Checklist（用于自动评审）

- [ ] **STRICT 7-page main limit**（References 不计入）
- [ ] **STRICT 2-page appendix limit**
- [ ] Abstract 150-250 词，含 application motivation + strongest result + uncertainty
- [ ] Keywords 紧跟 Abstract 末尾
- [ ] 章节使用**阿拉伯数字**编号 `1, 2, 3, 4, 5, 6, 7`
- [ ] 章节标题使用 **Title Case**（如 "Experimental Results"）
- [ ] Introduction 含 **concrete real-world application scenario** + ≥3 numbered contributions（**≥1 涉及因果识别 / 回测 / 网络层**）
- [ ] Related Work 按主题聚类，与 prior systemic-risk/network models 对比（when relevant）
- [ ] Preliminaries 含 Notation Table + Problem Formulation
- [ ] Method 包含 overview + Algorithm box + 推导 + complexity analysis
- [ ] **Experiments 是最强章节**：multi-datasets (≥3) + **≥5 baselines (incl. systemic-risk/network)** + ≥3 ablations + sensitivity tornado + **Application Case Study**
- [ ] 所有数字 report std/CI over **≥5 seeds**（AAAI 严格）
- [ ] Discussion 包含 Limitations（含未建模渠道）+ Broader Impact（正负）+ Reproducibility statement
- [ ] Conclusion 简明
- [ ] Appendix ≤ 2 页（含 proofs / additional experiments / code listing）
- [ ] **因果断言或显式区分"已识别"与"假设"**（AAAI 强偏好）
- [ ] **Out-of-sample backtest with RMSE/MAE/CRPS**（涉及预测时）
- [ ] Endogenous feedback loop + SVAR justification（系统建模时）
- [ ] Network loss-propagation layer（系统性风险建模时）
- [ ] 所有 constructed quantities 有 reconciliation table
- [ ] 公开完整代码 + 参数先验/协方差 + 随机种子（reproducibility statement）
# math_modeling Skill

> 来源：基于 6 篇 arXiv 论文 / MCM 官方获奖论文的写作风格研究
> 生成日期：2026-08-16
> 适用模板：`math_modeling`（全国大学生数学建模竞赛 CUMCM，含 12 章标准结构）

## 1. 写作风格基线

通过对 MCM 2026 Finalist 获奖论文（arXiv:2605.09367）以及 5 篇建模类 arxiv 论文的完整研读，归纳出竞赛数学建模论文的写作风格特征：

- **段落平均长度**：4–7 句（约 80–150 字）。每段通常以"承上启下"的一句开头（"Before establishing the governing equations, we define..."），再展开具体论述，最后以小结或过渡句收尾。
- **句子平均长度**：20–28 字。技术性长句常见，但必须配从句或破折号分层，避免一逗到底。
- **主动 vs 被动语态**：约 6:4。**主语优先使用"We/Our framework/This paper"**，而不是"The model is..."。在描述方法推导时切换为被动式（"is defined as..."、"is coupled with..."）。
- **公式 vs 自然语言比例**：核心模型章节（3、4、5、6）公式密度极高，每页 6–12 个编号公式；引言、结论、可靠性分析章节以自然语言为主，公式密度 1–3 个/页。
- **图表密度**：全文 18–35 页通常包含 6–12 张图、5–9 张表。表优先用于"参数标定结果"和"消融实验"；图优先用于"轨迹/相图/敏感性曲线/流程图"。
- **章节-图表配比**：每节平均 1 张图 + 1 张表，4 模型的建立与求解是图表最密集的章节。

## 2. 章节结构与命名约定

数学建模竞赛论文（CUMCM/MCM/ICM）严格遵循 **"问题重述 → 问题分析 → 假设与符号 → 模型建立与求解 → 结果分析 → 可靠性分析 → 模型评价 → 结论 → 参考文献 → 附录"** 的标准骨架。参考 MCM 2026 Finalist 论文的命名：

| 编号 | 标准中文标题（CUMCM 12 章） | 英文/国际化对应（MCM 风格） | 推荐占比 |
|------|------------|------------|----------|
| 0 | 摘要 + 关键词 | Abstract + Keywords | 1 页 |
| 1 | 问题重述（1.1 研究背景 / 1.2 问题描述） | Problem Restatement | 1–2 页 |
| 2 | 问题分析 | Introduction / Problem Analysis | 1–2 页 |
| 3 | 模型假设与符号说明（3.1 假设 / 3.2 符号表） | Model Preparation / Assumptions and Notations | 1–2 页 |
| 4 | 模型的建立与求解（4.x 子问题） | Model I/II/III: ... | 8–15 页（占全文 50%） |
| 5 | 结果分析 | Simulation and Performance Evaluation | 2–3 页 |
| 6 | 可靠性分析（6.1 模型检验 / 6.2 敏感性分析） | Sensitivity and Robustness Analysis | 1–2 页 |
| 7 | 模型评价 | Discussion / Model Evaluation | 1 页 |
| 8 | 结论 | Conclusion | 0.5 页 |
| 9 | 参考文献 | References | 0.5–1 页 |
| 附录 | 核心代码 | Appendix: Code | 不限 |

**关键命名约定**：
- 子问题标题必须反映**所解决的问题或方法**（如"4.1 Thevenin 等效电路模型"、"4.2 随机混合自动机模型"），禁止空洞命名（"问题 1 的模型"、"模型一"）。
- 子问题内部推荐七环节结构：**问题分析 → 方法介绍 → 模型构建 → 算法设计 → 求解结果 → 结果验证 → 问题小结**。
- 章节起承转合：每章首段先用 1–2 句概括本章目标，最后一段或下一章首段做总结/过渡。

## 3. 公式与符号使用

从 6 篇论文中观察到的共识：

- **公式编号**：使用 LaTeX `\begin{equation}` 环境，**全文统一顺序编号 (1), (2), ...**，跨章节连续编号；不推荐按章节编号（如 4-1）。多行公式用 `\begin{aligned}` 或 `cases` 环境。
- **公式引用**：行内用 `Eq. (5)`，段落开头用 `Equation (5) shows...`。同一公式在多处出现时只需在首次出现处加编号。
- **数学符号**：建模论文中标准符号约定：
  - 决策变量：粗体小写 $\mathbf{x}$, $\mathbf{u}$
  - 状态变量：粗体大写 $\mathbf{X}$, $\mathbf{H}$
  - 集合/空间：花体 $\mathcal{M}$, $\mathcal{Q}$
  - 时间导数：`\dot{x}` 优于 `\frac{dx}{dt}`
  - 集合：$\mathbb{R}, \mathbb{N}, \mathbb{E}[\cdot]$
  - 概率：`\mathbb{P}(\cdot)`, `\mathcal{N}(\mu, \sigma^2)`
- **符号表**：必须放在第 3 章"模型假设与符号说明"内的 3.2 节，采用**三列表格**（符号 / 含义 / 单位），符号按"状态变量 → 物理参数 → 控制变量 → 集合算子"分组排列。
- **行内公式**：用 `$...$`；简单算式可与文字同行（如"the decay rate $\lambda \approx 0.05$"）。
- **特例约定**：建模中常用 `:=` 表示"定义为"（如 `$V_{\mathrm{term}} := U(z) - V_p - IR$`），用 `$\equiv$` 表示恒等，用 `$:=$ 表示"按定义等于"。

## 4. 引用风格

- **引用方式**：使用**数字方括号格式** `[1]`，多引用合并为 `[1, 2, 3]` 或连续区间 `[3–5]`。**不推荐作者-年格式**（如 "(Li and Zhou, 2026)"），因为 CUMCM 模板使用 `plain` bibstyle。
- **引用密度**：竞赛论文中**每段 0–2 个引用**为正常密度；方法介绍、模型准备章节引用最密集（每个核心方法 1–3 个引用），建模、求解章节引用较少（通常只引用基础方法或对比方法）。
- **参考文献列表**：使用 `\begin{thebibliography}{99}` 环境，按**作者-年-标题-期刊/会议**格式，按引用顺序编号。
- **网络资料引用**：数据集（如 NASA PCoE、IQ-OTH/NCCD）可作为**技术报告或数据集**引用，并附 URL。

## 5. 图表风格

- **图表命名**：全文统一使用 **"图 1 / Figure 1"**（CUMCM 中文模板用"图 1"）。MCM 英文版用 "Figure 1"。表统一为 "表 1 / Table 1"。
- **Caption 写法**：图 caption 放在图下方；表 caption 放在表上方。caption 格式：`图 1: X 随 Y 的变化曲线（来源：xxx）`。
- **引用方式**：段落中使用 **"如图 1 所示"** 或 **"Figure 1 shows..."**；避免"如下图所示"这种无指代描述。
- **子图使用**：使用 `subcaption` 宏包，标记为 `(a)`, `(b)`, `(c)`。在 caption 中显式说明子图含义（如"(a) 突发负载；(b) 低温环境；(c) 弱信号"）。
- **表设计要点**：
  - 使用 `booktabs` 宏包，`\toprule`/`\midrule`/`\bottomrule`，**避免竖线**。
  - 数字右对齐，单位写在表头括号内（如"$t_{0.05}$ (h)"）。
  - 比较表格用 **粗体** 突出最优值。
- **配色与字体**：技术性论文优先使用矢量图（PDF/EPS 格式）。MATLAB 默认配色、Python matplotlib `viridis`/`tab10`、seaborn `deep` 都可以。
- **坐标轴**：必须标注**变量名 + 单位**（如"Time (hours)"）；多子图共享坐标轴时只在最外层标注。

## 6. 真实获奖论文示例

以下论文均经实际 fetch 验证（arXiv ID 可点击访问），用作风格参考：

| 论文 ID | 标题 | 年份 | 与模板的关联 |
|---|---|---|---|
| arXiv:2605.09367 | A Stochastic Hybrid Automaton for Smartphone Battery Dynamics (MCM 2026 Problem A Finalist) | 2026 | **MCM 官方获奖论文直接范例**——含完整 10 章结构、模型 I/II/III 命名、Sobol 敏感性分析、用户级建议、Limitation 章节 |
| arXiv:2602.06437 | An attention economy model of co-evolution between content quality and audience selectivity | 2026 | 博弈论建模范例——含补充材料(Appendix)、3 种均衡稳定性分析、Basin of Attraction 图、参数阈值表 |
| arXiv:2604.04791 | How Far Are We? Systematic Evaluation of LLMs vs. Human Experts in Mathematical Contest in Modeling | 2026 | 关于 CUMCM 论文的元研究——揭示评阅标准与执行差距，可作为"模型评价"写作参考 |
| arXiv:2606.08675 | Explainable Optimization: A Call for Interdisciplinary Action | 2026 | 运筹学/优化建模——展示如何从"算法视角"转向"可解释性视角" |
| arXiv:2511.19726 | An Adaptive, Data-Integrated Agent-Based Modeling Framework for Explainable and Contestable Policy Design | 2025 | 多主体建模——含信息论诊断、结构因果模型、可解释政策设计章节 |
| arXiv:2602.09982 | Kelly Betting as Bayesian Model Evaluation: A Framework for Time-Updating Probabilistic Forecasts | 2026 | 31 页完整建模论文范例——含 10 张图、风险尾部分析、贝叶斯推断推导 |

## 7. 写作 Checklist（自动评审可用）

- [ ] 摘要字数 300–500 字，覆盖方法→模型→求解→结果→结论
- [ ] 关键词 3–5 个，分号分隔
- [ ] 问题重述用自己的语言，**禁止照抄原题**超过 50 字
- [ ] 模型假设逐条编号（≥3 条），每条说明必要性和合理性
- [ ] 符号说明用三列表格（符号 / 含义 / 单位）
- [ ] 4 章子问题标题反映方法或问题（如 "Thevenin 等效电路模型"）
- [ ] 每个子问题包含七环节：问题分析→方法介绍→模型构建→算法设计→求解结果→结果验证→问题小结
- [ ] 全文公式**顺序编号 (1), (2), ...** 跨章节连续
- [ ] 至少 1 张结果数据表 + 1 张参数/消融表
- [ ] 至少 1 张趋势/轨迹图 + 1 张流程/结构图
- [ ] 6.1 模型检验：与真实数据或已知结果对比（误差指标如 MAPE、RMSE）
- [ ] 6.2 敏感性分析：至少做局部 + 全局（Sobol / Morris）两种
- [ ] 7 模型评价分优点、缺点、创新点三段
- [ ] 8 结论对题目要求**逐条**明确回答
- [ ] 参考文献 ≥ 8 条，格式符合 `plain` bibstyle
- [ ] 附录包含核心代码（Python / MATLAB），使用 `lstlisting` 环境
- [ ] 全文页数 18–35 页（默认 25 页左右）
- [ ] 无引用照抄原题，无"显然"等空洞修辞
- [ ] 中英文标点正确（中文段落用全角，公式内用半角）

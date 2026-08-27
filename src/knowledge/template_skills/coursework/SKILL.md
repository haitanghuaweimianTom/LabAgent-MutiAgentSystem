# coursework Skill

> 来源：基于 7 篇 arXiv 大学课程报告/本科研究项目的写作风格研究
> 生成日期：2026-08-16
> 适用模板：`coursework`（课程作业 / 学术报告，8 章简化结构）

## 1. 写作风格基线

通过对 7 篇明确标注为"undergraduate research project"、"Final Year Project"、"undergraduate research"的 arXiv 论文研读，归纳课程报告的写作风格：

- **段落平均长度**：3–5 句（约 60–120 字）。比学术论文稍短，**优先使用短句**。长句通常带 1 个从句。
- **句子平均长度**：15–22 字。**避免一逗到底**，技术性术语用括号或破折号补充。
- **主动 vs 被动语态**：约 7:3。**主语优先使用"We/Our model/This work"**；被动语态主要用于方法描述（"The dataset was split into..."）。**第一人称复数（we）是常态**，这与期刊论文的"作者隐身"风格相反。
- **公式 vs 自然语言比例**：课程报告通常 5–15 个公式，**集中在方法章节**。每章平均 1–2 个公式，避免大型公式矩阵。
- **图表密度**：6–20 页通常含 3–8 张图、2–5 张表。**图主要展示实验结果**（学习曲线、混淆矩阵、ROC 曲线、SHAP 热力图），表主要用于模型对比与超参数表。
- **章节长度比例**：引言 15% / 方法 25% / 实验与结果 30% / 讨论 15% / 结论 5% / 参考文献 10%。

## 2. 章节结构与命名约定

课程报告通常采用 **IMRaD 简化结构**：引言 → 方法 → 实验与结果 → 讨论 → 结论。参考 arXiv:2508.10196（"An Explainable AI Approach for Lung Cancer Detection"）和 arXiv:2211.08475（"AutoDRIVE"）的命名：

| 编号 | 标准标题（coursework 8 章） | 典型英文标题 | 推荐占比 |
|------|------------|------------|----------|
| 0 | 摘要 + 关键词 | Abstract + Keywords | 0.5–1 页 |
| 1 | 引言 | Introduction | 1–2 页 |
| 2 | 问题描述 | Problem Description | 0.5–1 页 |
| 3 | 方法与模型（3.x 子方法） | Materials and Methods / Methodology | 3–5 页 |
| 4 | 实验与求解 | Experiments / Results | 3–5 页 |
| 5 | 结果分析 | Discussion | 1–2 页 |
| 6 | 总结与展望 | Conclusion and Future Scope | 0.5 页 |
| - | 参考文献 | References | 0.5–1 页 |

**关键命名约定**：
- **方法章节子标题按"方法/对象"划分**（如"3.1 Dataset"、"3.2 Preprocessing and Augmentation"、"3.3 Model Architectures"），不按章节号顺序。
- **结果章节按"结果类型"划分**（如"4.1 Learning Curves"、"4.2 Quantitative Performance"、"4.3 Confusion Matrices and ROC–AUC"）。
- **讨论章节可拆为 2–3 个 subsection**（如"5 Discussion" + "Limitations" + "Future Work"），不超过 3 个子标题。
- **结论必须短**——1 段 100–200 字，回顾主要工作并提出 1–2 个改进方向。
- **附录（可选）**：包含代码、补充材料、Bill of Materials 等。

## 3. 公式与符号使用

- **公式编号**：使用 `\begin{equation}` 环境，**按章节独立编号**（如 4-1、4-2、附录 A-1），或全文顺序编号 1–N。**课程报告规模小**，独立编号更易维护。
- **数学符号**：保持简洁：
  - 标量：斜体 $x, y, t$
  - 向量：粗体小写 $\mathbf{x}, \mathbf{w}$
  - 矩阵：粗体大写 $\mathbf{X}, \mathbf{W}$
  - 集合：花体 $\mathcal{D}, \mathcal{X}$
  - 损失函数：$\mathcal{L}$，优化目标：$J(\theta)$
- **符号表**：如果符号 > 10 个，建议放在 **"List of Symbols" 单独一页**（参考 arXiv:2211.08475），按"节号 + 符号 + 定义"三列组织。
- **行内公式**：简单算式可与文字同行（如"with $\alpha = 0.05$ and $\beta = 0.2$"），复杂公式必须独立成行。
- **算法伪代码**：使用 `algorithm` + `algorithmic` 宏包（独立编号 Algorithm 1、Algorithm 2）。

## 4. 引用风格

- **引用方式**：使用**数字方括号格式** `[1]`，多引用合并为 `[1, 2, 3]` 或 `[1]–[3]`。模板默认 `bib_style: "plain"`。
- **引用密度**：课程报告引用比学术论文**少**，**每段 0–1 个引用**。方法介绍和 Related Work 章节引用最密集（每个核心方法 1 个引用），实验和结论章节通常 0 引用。
- **参考文献列表**：标准 IEEE 数字格式或 ACM 格式。**典型课程报告 10–25 条参考文献**。
- **网络资料**：数据集 URL 写在参考文献中（如 arXiv:2508.10196 的参考 [19] 是 Kaggle 数据集），GitHub 代码可作为技术报告引用。

## 5. 图表风格

- **图表命名**：使用 "图 1 / Figure 1" 或 "Table 1" 统一编号。caption 简短但**自解释**（如 "Figure 3: Learning curves for Custom CNN"）。
- **Caption 写法**：
  - 图 caption 放在图下方，**首句是图的核心信息**（"DenseNet121 achieved the highest macro F1-score of 91%"），然后补充细节。
  - 表 caption 放在表上方，简短（"Table 3: Overall test accuracy"）。
- **引用方式**：**"如图 1 所示"** 或 **"Figure 1 shows..."**；避免"如下图所示"这种无指代。
- **子图使用**：使用 `subcaption` 宏包，标记为 `(a)`, `(b)`, `(c)`。在 caption 中列出子图含义（参考 arXiv:2508.10196 的 "Figure 7: Confusion matrices..."）。
- **图设计要点**：
  - 坐标轴必须标**变量名 + 单位**（如"Epoch"、"Accuracy (%)"）。
  - 多模型对比使用不同颜色 + 不同 marker（圆/方/三角）保证黑白打印可辨识。
  - 学习曲线图必须同时画**训练 + 验证**两条线。
- **表设计要点**：
  - 使用 `booktabs` 宏包，无竖线。
  - 数字右对齐。
  - **粗体标记最优值**（如"$\mathbf{97.3}$"）。

## 6. 真实课程报告示例

以下论文均经实际 fetch 验证（arXiv ID 可点击访问），用作风格参考：

| 论文 ID | 标题 | 年份 | 与模板的关联 |
|---|---|---|---|
| arXiv:2508.10196 | An Explainable AI Approach for Lung Cancer Detection Using Convolutional Neural Networks | 2025 | **本科研究项目报告直接范例**——注释明确写"Undergraduate research project report"，11 页/9 图/4 表，含 IMRaD 全套 + Limitations + Future Work |
| arXiv:2211.08475 | AutoDRIVE – An Integrated Platform for Autonomous Driving Research and Education | 2022 | **本科毕业设计范例**——注释明确写"2021 Undergraduate Final Year Project"，含 Acknowledgement、List of Tables/Figures、Abbreviations、Bill of Materials 附录 |
| arXiv:2405.06692 | Analyzing Language Bias Between French and English in Conventional Multilingual Sentiment Analysis Models | 2024 | **本科研究项目**——6 页短报告范例，含 SVM/Naive Bayes 对比、Fairlearn 公平性指标 |
| arXiv:2005.13597 | Steiner symmetrization along a certain equidistributed sequence of directions | 2020 | **NSERC 本科研究项目**——含"undergraduate-friendly"写作风格，避免晦涩术语 |
| arXiv:2005.00950 | Extracting Entities and Topics from News and Connecting Criminal Records | 2020 | **本科学生初步研究**——含 Entity Extraction + Topic Modeling + 简单犯罪图谱 |
| arXiv:1611.09435 | The analysis of topological structure in data using persistent homology: applications to lexical word association networks | 2016 | **本科研究项目终期报告**——含 Persistent Homology 完整推导 + 应用 |
| arXiv:2211.08637 | Near-Peer Mentoring in Data Science: A Plot for Mutual Growth | 2022 | **课程项目元研究**——展示 Data Science 项目报告的组织方式 |

## 7. 写作 Checklist（自动评审可用）

- [ ] 摘要字数 200–400 字，覆盖目的 / 方法 / 结果 / 结论
- [ ] 关键词 3–5 个
- [ ] 引言明确说明**研究目的、相关工作、贡献**（"Our contributions are: ..." 列表）
- [ ] 引言中至少 3 个相关工作引用
- [ ] 方法章节介绍**为什么选这个方法**（不只是描述）
- [ ] 实验环境、数据来源、超参数都在 Methods 或 Experiment 章节显式给出
- [ ] 至少 1 个**结果数值表**（如 test accuracy, F1-score）
- [ ] 至少 1 张**学习曲线 / 训练过程图**
- [ ] 至少 1 张**多模型对比图或表**（baseline vs proposed）
- [ ] 讨论章节包含 **Limitations** 子节
- [ ] 未来工作 Future Work 提出 ≥2 个具体方向
- [ ] 结论**不超过 200 字**，不引入新内容
- [ ] 参考文献 10–25 条，格式规范
- [ ] 全文页数 6–20 页（默认 12 页左右）
- [ ] 致谢（Acknowledgements）提到指导教师 / 实验室 / 数据集提供方
- [ ] 公式独立编号，跨章节或按章节均可
- [ ] 图表 caption 自解释，**不依赖正文**也能看懂
- [ ] 代码/超参数可在附录或 GitHub 链接找到
- [ ] 无大段照抄网络资料，所有引用均给出处

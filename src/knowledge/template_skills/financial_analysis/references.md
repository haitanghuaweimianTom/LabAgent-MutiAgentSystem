# financial_analysis References

> 基于 arxiv 真实条目的 q-fin 论文（含 1 篇 LLM 金融综述、1 篇 synthetic data 综述、7 篇实证论文）。所有条目均通过 https://arxiv.org/abs/<id> 验证。
> 适用于 `financial_analysis` 模板（金融分析报告 / 投资分析 / 量化策略）。

## LLM × 金融综述（必读类）

- **arXiv:2406.11903** — *A Survey of Large Language Models for Financial Applications: Progress, Prospects and Challenges* — Yuqi Nie, Yaxuan Kong, Xiaowen Dong, John M. Mulvey, H. Vincent Poor, Qingsong Wen, Stefan Zohren.
  - 一句话：截至当前最完整的 LLM × 金融综述，把文献分为 linguistic tasks / sentiment analysis / financial time series / financial reasoning / agent-based modeling 六大类。
  - URL: https://arxiv.org/abs/2406.11903
  - 学科：q-fin.GN（cs.AI 交叉）

- **arXiv:2401.00081** — *Synthetic Data Applications in Finance* — Vamsi K. Potluru, Daniel Borrajo, Andrea Coletta, Niccolò Dalmasso, Yousef El-Laham, Elizabeth Fons, Mohsen Ghassemi, Sriram Gopalakrishnan, Vikesh Gosai, Eleonora Kreačić, Ganapathy Mani, Saheed Obitayo, Deepak Paramanand, Natraj Raman, Mikhail Solonin, Srijan Sood, Svitlana Vyetrenko, Haibei Zhu, Manuela Veloso, Tucker Balch.
  - 一句话：50 页金融合成数据全景图，覆盖 tabular / time-series / event-series / unstructured 四模态 + 6 个 privacy levels。
  - URL: https://arxiv.org/abs/2401.00081
  - 学科：cs.LG（q-fin.GN 交叉）

- **arXiv:2403.06779** — *From Factor Models to Deep Learning: Machine Learning in Reshaping Empirical Asset Pricing* — Junyi Ye, Bhaskar Goswami, Jingyi Gu, Ajim Uddin, Guiling Wang.
  - 一句话：从 supervised / unsupervised / semi-supervised / RL 四象限系统梳理 ML 在资产定价的应用。
  - URL: https://arxiv.org/abs/2403.06779
  - 学科：q-fin.ST

## 资产定价 / 因子模型

- **arXiv:2402.06635** — *Large and Deep Factor Models* — Bryan Kelly, Boris Kuznetsov, Semyon Malamud, Yuan Zhang.
  - 一句话：深度神经网络构造 SDF 的加性分解，引出 Portfolio Tangent Kernel (PTK) 线性因子表达。
  - URL: https://arxiv.org/abs/2402.06635
  - 学科：q-fin.ST（cs.CE / cs.LG 交叉）

- **arXiv:2404.08129** — *One Factor to Bind the Cross-Section of Returns* — Nicola Borri, Denis Chetverikov, Yukun Liu, Aleh Tsyvinski.
  - 一句话：基于 Kolmogorov-Arnold 表达定理的非线性单因子资产定价模型，171 assets 实验。
  - URL: https://arxiv.org/abs/2404.08129
  - 学科：q-fin.GN（econ.EM 交叉）

- **arXiv:2405.10920** — *Data-generating process and time-series asset pricing* — Shuxin Guo, Qiang Liu.
  - 一句话：43 页、9 表，复检 FF3 模型在 compounded vs periodic-rebalancing 假设下的 Sharpe 估计偏差。
  - URL: https://arxiv.org/abs/2405.10920
  - 学科：q-fin.GN（q-fin.PM / q-fin.RM 交叉）

## 收益预测 / 量化策略

- **arXiv:2402.10760** — *RAGIC: Risk-Aware Generative Adversarial Model for Stock Interval Construction* — Jingyi Gu, Wenlu Du, Guiling Wang.
  - 一句话：GAN 序列生成构造股票区间预测，risk module + temporal module 双模块设计，全球 broad-based indices 95% coverage。
  - URL: https://arxiv.org/abs/2402.10760
  - 学科：q-fin.ST

- **arXiv:2408.07497** — *Forecasting stock return distributions around the globe with quantile neural networks* — Jozef Barunik, Martin Hronec, Ondrej Tobek.
  - 一句话：两阶段分位神经网络 + 样条插值构造 smooth 累积分布，US + 国际市场稳健。
  - URL: https://arxiv.org/abs/2408.07497
  - 学科：q-fin.GN（q-fin.PM 交叉）

## 市场结构 / 风险评估

- **arXiv:2403.15163** — *Nonlinear shifts and dislocations in financial market structure and composition* — Nick James, Max Menzies.
  - 一句话：53 页，构建 US equity 的精细 sector 划分 + sector-to-sector 网络 + Sharpe 比分布。
  - URL: https://arxiv.org/abs/2403.15163
  - 学科：q-fin.ST（Chaos 2024 期刊版本）

- **arXiv:2404.11745** — *Piercing the Veil of TVL: DeFi Reappraised* — Yichen Luo, Yebo Feng, Jiahua Xu, Paolo Tasca.
  - 一句话：提出 Total Value Redeemable (TVR) 替代 TVL，量化 double counting = $139.87B / TVL:TVR ≈ 2。
  - URL: https://arxiv.org/abs/2404.11745
  - 学科：q-fin.GN

## arxiv 目录验证源

- **arXiv q-fin.ST 2024** — Statistical Finance 全学科目录（331 entries）.
  - URL: https://arxiv.org/list/q-fin.ST/2024
  - 用于交叉验证金融时间序列 / 资产定价条目的覆盖完整性。

- **arXiv q-fin.GN 2024** — General Finance 全学科目录（152 entries）.
  - URL: https://arxiv.org/list/q-fin.GN/2024
  - 用于交叉验证通用金融 / DeFi / 公司金融条目的覆盖完整性。
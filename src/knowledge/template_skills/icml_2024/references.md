# icml_2024 References

> 基于 arxiv 真实条目的 ICML 2024 接收论文。所有条目均通过 https://arxiv.org/abs/<id> 验证。

## 通用规则 / 索引

- **Proceedings of Machine Learning Research (PMLR) v235** — ICML 2024 official proceedings.
  - URL: https://proceedings.mlr.press/v235/

## 神经网络泛化 / Mean-field Regime

- **arXiv:2402.07025** — *Generalization Error of Graph Neural Networks in the Mean-field Regime* — Aminian G., He Y., Reinert G., Szpruch Ł., Cohen S. N. — ICML 2024
  - 一句话：在 over-parameterized regime 给出 GCN / message-passing GNN 的泛化误差 O(1/n) 上界。
  - URL: https://arxiv.org/abs/2402.07025

## Graph Transformer 泛化理论

- **arXiv:2406.01977** — *What Improves the Generalization of Graph Transformers? A Theoretical Dive into the Self-attention and Positional Encoding* — Li H., Wang M., Ma T., Liu S., Zhang Z., Chen P.-Y. — ICML 2024
  - 一句话：首个 shallow Graph Transformer 半监督节点分类的 generalization 理论 + SGD 收敛迭代数。
  - URL: https://arxiv.org/abs/2406.01977

## 凸优化 / 加速方法

- **arXiv:2206.05248** — *Accelerated Algorithms for Constrained Nonconvex-Nonconcave Min-Max Optimization and Comonotone Inclusion* — Cai Y., Oikonomou A., Zheng W. — ICML 2024
  - 一句话：EAG / FEG 扩展到 constrained comonotone min-max，O(1/T) 最优收敛率且迭代收敛到解集。
  - URL: https://arxiv.org/abs/2206.05248

## Simulation-Based Inference / Bayesian

- **arXiv:2401.02413** — *Simulation-Based Inference with Quantile Regression* — Jia H. — ICML 2024
  - 一句话：NQE 基于 conditional quantile regression 自回归学习 1D quantiles + local CDF 定义新 Bayesian credible region。
  - URL: https://arxiv.org/abs/2401.02413

- **arXiv:2401.10989** — *Provably Scalable Black-Box Variational Inference with Structured Variational Families* — Ko J., Kim K., Kim W. C., Gardner J. R. — ICML 2024
  - 一句话：structured variational families 理论达到 O(N) iteration complexity（vs full-rank O(N²)）。
  - URL: https://arxiv.org/abs/2401.10989

## 高维统计 / 特征选择

- **arXiv:2401.05765** — *A new computationally efficient algorithm to solve Feature Selection for Functional Data Classification in high-dimensional spaces* — Boschi T., Bonin F., Ordonez-Hurtado R., Pascale A., Epperlein J. — ICML 2024
  - 一句话：FSFC 算法在 functional data 分类上比 ML/DL 方法更快 + 更准。
  - URL: https://arxiv.org/abs/2401.05765

## LLM Alignment / RLHF

- **arXiv:2310.02905** — *Use Your INSTINCT: INSTruction optimization for LLMs usIng Neural bandits Coupled with Transformers* — Lin X., Wu Z., Dai Z., Hu W., Shu Y., Ng S.-K., Jaillet P., Low B. K. H. — ICML 2024
  - 一句话：用 neural bandit 替换 BO 中的 GP，用预训练 transformer 表征优化 LLM instructions。
  - URL: https://arxiv.org/abs/2310.02905

- **arXiv:2402.02992** — *Decoding-time Realignment of Language Models* — Liu T., Guo S., Bianco L., Calandriello D., Berthet Q., Llinares F., Hoffmann J., Dixon L., Valko M., Blondel M. — ICML 2024
  - 一句话：DeRa 实现在 decoding 阶段探索 RLHF 正则化强度，无需重训。
  - URL: https://arxiv.org/abs/2402.02992

## 查找更多 ICML 2024 论文的方法

由于 ICML 2024 共接收 4493 篇，本目录聚焦理论 / 优化 / 通用 ML 方向的 8 篇代表。在 LabAgent 中需要更多方向（如 RL、CV、Bandits、Causal Inference）时，可：

1. 在 https://arxiv.org/search/?searchtype=all&query=%22ICML+2024%22+<关键词>&start=0 搜索
2. 直接访问 https://arxiv.org/list/stat.ML/2024 滚动浏览
3. 通过 OpenReview https://openreview.net/group?id=ICML.cc/2024/Conference 检索接收论文

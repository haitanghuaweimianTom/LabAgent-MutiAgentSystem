# neurips_2024 References

> 基于 arxiv 真实条目的 NeurIPS 2024 接收论文。所有条目均通过 https://arxiv.org/abs/<id> 验证。

## 扩散模型 / Diffusion Transformer（主线）

- **arXiv:2412.07877** — *Score-Optimal Diffusion Schedules* — Williams C., Campbell A., Doucet A., Syed S. — NeurIPS 2024
  - 一句话：基于 estimated Stein score 的 work-cost 自适应 diffusion 离散 schedule 算法，无需调参即可恢复高性能 schedule。
  - URL: https://arxiv.org/abs/2412.07877

- **arXiv:2411.04168** — *DiMSUM: Diffusion Mamba — A Scalable and Unified Spatial-Frequency Method for Image Generation* — Phung H., Dao Q., Dao T., Phan H., Metaxas D., Tran A. — NeurIPS 2024
  - 一句话：在 DiT 中用 wavelet + Mamba 融合空间 + 频率信息，比 DiT 更快收敛。
  - URL: https://arxiv.org/abs/2411.04168

- **arXiv:2410.23788** — *EDT: An Efficient Diffusion Transformer Framework Inspired by Human-like Sketching* — Chen X., Liu N., Zhu Y., Feng F., Tang J. — NeurIPS 2024
  - 一句话：通过 Attention Modulation Matrix 把 DiT 训练 + 推理同时加速 1.9-3.9×。
  - URL: https://arxiv.org/abs/2410.23788

- **arXiv:2410.20474** — *GrounDiT: Grounding Diffusion Transformers via Noisy Patch Transplantation* — Lee P. Y., Yoon T., Sung M. — NeurIPS 2024
  - 一句话：利用 DiT 的 semantic sharing 性质实现无训练 bounding box 空间控制。
  - URL: https://arxiv.org/abs/2410.20474

- **arXiv:2410.18666** — *DreamClear: High-Capacity Real-World Image Restoration with Privacy-Safe Dataset Curation* — Ai Y., Zhou X., Huang H., Han X., Chen Z., You Q., Yang H. — NeurIPS 2024
  - 一句话：DiT-based 图像恢复 + GenIR 数据生成 pipeline，无版权风险。
  - URL: https://arxiv.org/abs/2410.18666

- **arXiv:2406.11831** — *Exploring the Role of Large Language Models in Prompt Encoding for Diffusion Models* — Ma B., Zong Z., Song G., Li H., Liu Y. — NeurIPS 2024
  - 一句话：提出 LI-DiT 框架在 diffusion 中用 LLM 作 prompt encoder，超越 SD3/DALL-E 3/MJ6。
  - URL: https://arxiv.org/abs/2406.11831

- **arXiv:2406.02485** — *Stable-Pose: Leveraging Transformers for Pose-Guided Text-to-Image Generation* — Wang J., Ghahremani M., Li Y., Ommer B., Wachinger C. — NeurIPS 2024
  - 一句话：用 ViT 的 coarse-to-fine attention masking 在 SD 中精准控制人体姿态。
  - URL: https://arxiv.org/abs/2406.02485

- **arXiv:2406.01733** — *Learning-to-Cache: Accelerating Diffusion Transformer via Layer Caching* — Ma X., Fang G., Mi M. B., Wang X. — NeurIPS 2024
  - 一句话：在 DiT 推理中通过 learned caching 减少 46.84% 计算且 FID 下降 <0.01。
  - URL: https://arxiv.org/abs/2406.01733

- **arXiv:2405.02730** — *U-DiTs: Downsample Tokens in U-Shaped Diffusion Transformers* — Tian Y., Tu Z., Chen H., Hu J., Xu C., Wang Y. — NeurIPS 2024
  - 一句话：U-shaped DiT 在 self-attention 中下采样 QKV，1/6 cost 超越 DiT-XL/2。
  - URL: https://arxiv.org/abs/2405.02730

- **arXiv:2402.03687** — *PARD: Permutation-Invariant Autoregressive Diffusion for Graph Generation* — Zhao L., Ding X., Akoglu L. — NeurIPS 2024
  - 一句话：结合 autoregressive + diffusion 的图生成模型，在 MOSES 上 SOTA。
  - URL: https://arxiv.org/abs/2402.03687

- **arXiv:2401.13858** — *Graph Diffusion Transformers for Multi-Conditional Molecular Generation* — Liu G., Xu J., Luo T., Jiang M. — NeurIPS 2024 **Oral**
  - 一句话：Graph DiT + 节点/边联合噪声模型，实现 polymer + 分子 9 项指标 SOTA。
  - URL: https://arxiv.org/abs/2401.13858

## 视觉语言 / 3D 推理

- **arXiv:2406.01584** — *SpatialRGPT: Grounded Spatial Reasoning in Vision Language Models* — Cheng A.-C., Yin H., Fu Y., Guo Q., Yang R., Kautz J., Wang X., Liu S. — NeurIPS 2024
  - 一句话：通过 region proposals + 3D scene graph 增强 VLM 的空间推理。
  - URL: https://arxiv.org/abs/2406.01584

## 优化 / 梯度估计

- **arXiv:2410.08125** — *Generalizing Stochastic Smoothing for Differentiation and Gradient Estimation* — Petersen F., Borgelt C., Mishra A., Ermon S. — NeurIPS 2024
  - 一句话：弱化 stochastic smoothing 假设（无需 differentiable density / full support），三类正交方差缩减。
  - URL: https://arxiv.org/abs/2410.08125

## 索引与查询

- **NeurIPS 2024 Proceedings** — Official page listing 4493 papers.
  - URL: https://papers.nips.cc/paper_files/paper/2024

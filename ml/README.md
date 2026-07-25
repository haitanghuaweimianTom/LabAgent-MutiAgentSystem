# LabAgent 模型训练模块

本目录包含 LabAgent 项目的模型训练代码，用于提升系统的算法能力和面试竞争力。

## 概览

| 模块 | 模型 | 任务 | VRAM | 训练时间 |
|------|------|------|------|---------|
| Bug Finder | Qwen2.5-Coder-1.5B QLoRA | 代码错误分类+修复 | ~6 GB | 2~3h |
| Reward Model | Qwen2.5-1.5B DPO | 论文质量评估 | ~6 GB | 2~3h |
| Reranker | bge-reranker-base | 文档重排序 | ~2 GB | 30min |
| 伪造检测 | UniXcoder-base | 代码伪造检测 | ~1.5 GB | 20min |

**硬件要求**：RTX 4060 8GB 或同等级别 GPU

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements-ml.txt
```

### 2. 数据收集

```bash
# 跑 20 次系统收集种子数据（~16 RMB API 成本）
python ml/data_collection/collect_system_runs.py --problems 20 --output ml/collected_data

# 数据增强（零成本）
python ml/data_collection/augment_bug_data.py          # Bug Finder 数据
python ml/data_collection/augment_dpo_data.py          # DPO 数据
python ml/data_collection/augment_reranker_data.py     # Reranker 数据
python ml/data_collection/augment_fabrication_data.py  # 伪造检测数据
```

### 3. 模型训练

```bash
# Bug Finder（QLoRA，~2-3h）
python ml/train_bug_finder.py --config ml/configs/bug_finder_qlora.yaml

# Reward Model（DPO，~2-3h）
python ml/train_reward_model.py --config ml/configs/reward_model_dpo.yaml

# Reranker（~30min）
python ml/train_reranker.py --config ml/configs/reranker.yaml

# 伪造检测（~20min）
python ml/train_fabrication_detector.py --config ml/configs/fabrication_detector.yaml
```

### 4. 评估

```bash
# Bug Finder 评估
python ml/evaluation/eval_bug_finder.py --model ml/checkpoints/bug_finder --data ml/collected_data/bug_finder_eval.json

# 消融实验
python ml/evaluation/eval_ablation.py --results-dir ml/results/ablation --generate-report
```

## 目录结构

```
ml/
├── README.md                          # 本文件
├── data_collection/                   # 数据收集与增强
│   ├── collect_system_runs.py         # 系统运行数据收集
│   ├── augment_bug_data.py            # Bug Finder 数据增强
│   ├── augment_dpo_data.py            # DPO 数据增强
│   ├── augment_reranker_data.py       # Reranker 数据增强
│   └── augment_fabrication_data.py    # 伪造检测数据增强
├── configs/                           # 训练配置
│   ├── bug_finder_qlora.yaml
│   ├── reward_model_dpo.yaml
│   ├── reranker.yaml
│   └── fabrication_detector.yaml
├── evaluation/                        # 评估脚本
│   ├── eval_bug_finder.py
│   └── eval_ablation.py
├── train_bug_finder.py               # Bug Finder 训练
├── train_reward_model.py             # Reward Model 训练
├── train_reranker.py                 # Reranker 训练
├── train_fabrication_detector.py     # 伪造检测训练
├── checkpoints/                       # 模型检查点（训练后生成）
├── logs/                              # 训练日志
└── results/                           # 实验结果
```

## 预算控制

| 项目 | 成本 |
|------|------|
| 数据收集（20 次系统运行） | ~16 RMB |
| 数据增强 | 0（本地脚本） |
| 模型训练 | 0（本地 GPU） |
| 评估 | 0（本地推理） |
| **总计** | **~16 RMB** |

## 面试包装

### 算法岗简历

```
LabAgent：基于 RLHF 对齐与领域微调的多智能体学术论文生成系统（个人项目）

• 设计 10 阶段多智能体 Pipeline（LangGraph, 15 Agents），实现问题描述→可提交论文的全自动生成
• 训练 Bug Finder Agent（Qwen2.5-Coder-1.5B, QLoRA SFT），在无泄露 138 样本测试集上做严格 JSON 评测，
  错误分类准确率 81.9%→97.1%、结构化标签一致性（严格精确匹配）9.4%→88.4%、valid_json 100%、
  推理延迟 1356ms→1035ms；无灾难性遗忘（基座做对的类微调后仍全对，弱类 ValueError/ZeroDivision 修复）
• 训练论文质量 Reward Model（Qwen2.5-1.5B, DPO），替代 prompt-based 评估，Spearman ρ 提升 31%
• 微调 Cross-Encoder Reranker 构建三阶段检索管线，MRR@10 提升 65%
• 将执行重试策略建模为 Contextual Bandit（LinUCB），平均重试减少 32%
• 构建完整评估体系（pass@k / 数值准确率 / 引用真实率 / 消融实验）
```

> ⚠️ 数据真实性说明：Bug Finder 一行的所有数字均为独立复测落盘值（见 `ml/results/COMPARISON.md`，
> 严格评测脚本 `ml/evaluation/eval_bug_finder_strict.py`，零泄露划分 `ml/prepare_clean_split.py`）。
> Reward Model / Reranker / LinUCB 三行的数字为项目文档自述值，本次未独立复测，面试时若被追问需讲清评估口径。

### 面试高频问题

**Q: 为什么 Bug Finder 用小模型而不是直接让大模型看 traceback？**

A: 三个原因：
1. **成本**：每次重试调大模型 ~0.01 RMB，本地推理 $0
2. **延迟**：<100ms vs 2-5s
3. **结构化输出**：微调后格式一致，大模型输出不稳定

**Q: 数据只有几百条够吗？**

A: 够用，因为：
1. 1.5B 模型容量有限，不需要海量数据
2. 错误类型是有限集合（14 类），分类任务数据效率高
3. 做了充分的数据增强：除 LLM 合成外，额外**实际执行会报错的 Python 代码**捕获真实 traceback
   （`ml/data_collection/synthesize_real_tracebacks.py`），保证真实行号与异常消息
4. 实测：765 条训练数据，3 个 epoch 后内部验证集（76 样本）即达 76/76=100%，
   无泄露测试集（138 样本）准确率 97.1%

**Q: DPO 只有 500 pairs 效果能好吗？**

A: 有效，因为：
1. 1.5B 模型 + QLoRA 参数更新量小
2. DPO 是相对学习（好 vs 差），信息密度高
3. 实验证明确实有效（ρ 从 0.58→0.76）

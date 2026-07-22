#!/bin/bash
# LabAgent 模型训练一键脚本
# 用法：bash ml/run_all.sh

set -e

echo "=========================================="
echo "LabAgent 模型训练流程"
echo "=========================================="

# 检查 GPU
echo ""
echo "[1/6] 检查 GPU..."
python -c "import torch; print(f'CUDA: {torch.cuda.is_available()}, GPU: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"None\"}')"

# 安装依赖
echo ""
echo "[2/6] 安装 ML 依赖..."
pip install -r requirements-ml.txt -q

# 数据收集
echo ""
echo "[3/6] 数据收集（需要 API 预算 ~16 RMB）..."
echo "跳过数据收集（需要真实系统运行），使用合成数据"
python ml/data_collection/augment_bug_data.py
python ml/data_collection/augment_dpo_data.py
python ml/data_collection/augment_reranker_data.py
python ml/data_collection/augment_fabrication_data.py

# 模型训练
echo ""
echo "[4/6] 模型训练..."
echo "--- Bug Finder (QLoRA, ~2-3h) ---"
python ml/train_bug_finder.py --config ml/configs/bug_finder_qlora.yaml

echo "--- Reward Model (DPO, ~2-3h) ---"
python ml/train_reward_model.py --config ml/configs/reward_model_dpo.yaml

echo "--- Reranker (~30min) ---"
python ml/train_reranker.py --config ml/configs/reranker.yaml

echo "--- 伪造检测 (~20min) ---"
python ml/train_fabrication_detector.py --config ml/configs/fabrication_detector.yaml

# 评估
echo ""
echo "[5/6] 评估..."
python ml/evaluation/eval_bug_finder.py --model ml/checkpoints/bug_finder --data ml/collected_data/bug_finder_eval.json

# 消融实验
echo ""
echo "[6/6] 消融实验报告..."
python ml/evaluation/eval_ablation.py --results-dir ml/results/ablation --generate-report

echo ""
echo "=========================================="
echo "训练完成！模型保存在 ml/checkpoints/"
echo "=========================================="

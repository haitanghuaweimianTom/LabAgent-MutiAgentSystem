"""
代码伪造检测数据增强脚本
========================

构造正样本（伪造代码）和负样本（正常代码），用于训练 UniXcoder 检测模型。

数据来源：
- code_audit.py 的检测记录
- 合成：对正常代码注入 hardcoded metrics（~500 正 + 500 负）
- 公开：CodeXGLUE defect detection subset
"""
from __future__ import annotations

import json
import random
import re
from pathlib import Path
from typing import Any, Dict, List


# 硬编码指标变量名
HARDCODED_METRICS = [
    "accuracy", "acc", "precision", "recall", "f1", "f1_score",
    "auc", "rmse", "mse", "mae", "r2", "sharpe", "sortino",
    "loss", "val_loss", "train_loss",
]

# 正常代码模板（无伪造）
NORMAL_CODE_TEMPLATES = [
    """import numpy as np
from sklearn.metrics import accuracy_score, f1_score

def evaluate_model(y_true, y_pred):
    acc = accuracy_score(y_true, y_pred)
    f1 = f1_score(y_true, y_pred, average='weighted')
    return {'accuracy': acc, 'f1': f1}""",
    """import pandas as pd
from sklearn.model_selection import train_test_split

def load_data(path):
    df = pd.read_csv(path)
    X = df.drop('target', axis=1)
    y = df['target']
    return train_test_split(X, y, test_size=0.2)""",
    """import torch
import torch.nn as nn

class SimpleNet(nn.Module):
    def __init__(self, input_dim, output_dim):
        super().__init__()
        self.fc = nn.Linear(input_dim, output_dim)
    def forward(self, x):
        return self.fc(x)""",
    """def calculate_metrics(predictions, targets):
    correct = sum(p == t for p, t in zip(predictions, targets))
    total = len(targets)
    return correct / total""",
    """import numpy as np

def gradient_descent(X, y, lr=0.01, epochs=100):
    w = np.zeros(X.shape[1])
    for _ in range(epochs):
        pred = X @ w
        error = pred - y
        w -= lr * (X.T @ error) / len(y)
    return w""",
]


def inject_hardcoded_metric(code: str) -> str:
    """注入硬编码指标"""
    metric = random.choice(HARDCODED_METRICS)
    value = random.choice([0.85, 0.90, 0.92, 0.95, 0.97, 0.99])

    # 选择注入位置
    injection_styles = [
        f'{metric} = {value}',
        f'print(f"{metric}: {{{value}}}")',
        f'results["{metric}"] = {value}',
        f'self.{metric} = {value}',
    ]

    style = random.choice(injection_styles)

    # 在代码末尾或函数返回前注入
    lines = code.split("\n")
    insert_pos = len(lines) - 1

    # 找到最后一个 return 语句
    for i, line in enumerate(lines):
        if "return" in line:
            insert_pos = i
            break

    lines.insert(insert_pos, f"    {style}")
    return "\n".join(lines)


def inject_suspicious_print(code: str) -> str:
    """注入可疑的 print 语句"""
    patterns = [
        'print(f"Accuracy: {0.95}")',
        'print("F1 Score: 0.92")',
        'print(f"Loss: {0.05:.4f}")',
        'print("Sharpe Ratio: 1.85")',
        'print(f"Precision: {0.88}")',
    ]
    pattern = random.choice(patterns)

    lines = code.split("\n")
    # 在函数末尾插入
    insert_pos = len(lines) - 1
    for i, line in enumerate(lines):
        if "return" in line:
            insert_pos = i
            break

    lines.insert(insert_pos, f"    {pattern}")
    return "\n".join(lines)


class FabricationDataAugmenter:
    """代码伪造检测数据增强器"""

    def __init__(self, seed: int = 42):
        random.seed(seed)

    def generate_dataset(self, target_count: int = 1000) -> List[Dict[str, Any]]:
        """生成伪造检测数据集"""
        samples = []

        # 负样本（正常代码）
        for _ in range(target_count // 2):
            code = random.choice(NORMAL_CODE_TEMPLATES)
            # 可能做一些小变异
            code = self._mutate_code(code)
            samples.append({
                "code": code,
                "label": 0,  # 正常
                "source": "synthetic_normal",
            })

        # 正样本（伪造代码）
        for _ in range(target_count // 2):
            code = random.choice(NORMAL_CODE_TEMPLATES)

            # 选择注入策略
            strategy = random.choice(["hardcoded_metric", "suspicious_print", "both"])

            if strategy == "hardcoded_metric":
                code = inject_hardcoded_metric(code)
            elif strategy == "suspicious_print":
                code = inject_suspicious_print(code)
            else:
                code = inject_hardcoded_metric(code)
                code = inject_suspicious_print(code)

            samples.append({
                "code": code,
                "label": 1,  # 伪造
                "source": f"synthetic_{strategy}",
            })

        random.shuffle(samples)
        return samples

    def _mutate_code(self, code: str) -> str:
        """对正常代码进行小变异"""
        mutations = [
            # 变量名替换
            lambda c: c.replace("X_train", "features_train"),
            lambda c: c.replace("y_true", "targets"),
            lambda c: c.replace("model", "classifier"),
            # 添加注释
            lambda c: c + "\n# TODO: add more evaluation metrics",
            # 修改参数
            lambda c: c.replace("test_size=0.2", "test_size=0.3"),
        ]

        # 随机应用 0~2 个变异
        n_mutations = random.randint(0, 2)
        for _ in range(n_mutations):
            mutation = random.choice(mutations)
            code = mutation(code)

        return code


def main():
    import argparse

    parser = argparse.ArgumentParser(description="代码伪造检测数据增强")
    parser.add_argument("--output", type=str, default="ml/collected_data",
                       help="输出目录")
    parser.add_argument("--target-count", type=int, default=1000,
                       help="目标数据条数")
    args = parser.parse_args()

    # 生成数据
    augmenter = FabricationDataAugmenter()
    samples = augmenter.generate_dataset(args.target_count)

    # 划分训练/验证
    random.shuffle(samples)
    split = int(len(samples) * 0.9)
    train_data = samples[:split]
    eval_data = samples[split:]

    # 保存
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(output_dir / "fabrication_train.json", "w", encoding="utf-8") as f:
        json.dump(train_data, f, ensure_ascii=False, indent=2)

    with open(output_dir / "fabrication_eval.json", "w", encoding="utf-8") as f:
        json.dump(eval_data, f, ensure_ascii=False, indent=2)

    # 统计
    pos_count = sum(1 for s in samples if s["label"] == 1)
    neg_count = sum(1 for s in samples if s["label"] == 0)
    print(f"生成 {len(train_data)} 条训练数据, {len(eval_data)} 条验证数据")
    print(f"正样本（伪造）: {pos_count}, 负样本（正常）: {neg_count}")


if __name__ == "__main__":
    main()

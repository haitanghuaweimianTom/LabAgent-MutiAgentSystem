"""
Reranker 微调脚本
================

微调 Cross-Encoder Reranker，提升文档检索质量。

硬件要求：RTX 4060 8GB (VRAM ~2GB)
训练时间：30 分钟

用法：
    python ml/train_reranker.py --config ml/configs/reranker.yaml
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


@dataclass
class RerankerConfig:
    """Reranker 训练配置"""
    model_name: str = "BAAI/bge-reranker-base"
    max_length: int = 512

    # 训练
    batch_size: int = 16
    gradient_accumulation: int = 2
    epochs: int = 3
    learning_rate: float = 2e-5
    weight_decay: float = 0.01
    warmup_ratio: float = 0.1
    fp16: bool = True

    # 数据
    train_file: str = "ml/collected_data/reranker_train.json"
    eval_file: str = "ml/collected_data/reranker_eval.json"
    max_samples: int = 1500

    # 输出
    output_dir: str = "ml/checkpoints/reranker"
    logging_steps: int = 10
    save_steps: int = 100
    seed: int = 42

    @classmethod
    def from_yaml(cls, path: str) -> "RerankerConfig":
        """从 YAML 文件加载配置"""
        try:
            import yaml
            with open(path) as f:
                data = yaml.safe_load(f)
        except ImportError:
            return cls()

        config = cls()
        if "model" in data:
            config.model_name = data["model"].get("name_or_path", config.model_name)
            config.max_length = data["model"].get("max_length", config.max_length)
        if "training" in data:
            t = data["training"]
            config.batch_size = t.get("per_device_train_batch_size", config.batch_size)
            config.gradient_accumulation = t.get("gradient_accumulation_steps", config.gradient_accumulation)
            config.epochs = t.get("num_train_epochs", config.epochs)
            config.learning_rate = t.get("learning_rate", config.learning_rate)
            config.output_dir = t.get("output_dir", config.output_dir)
        if "data" in data:
            config.train_file = data["data"].get("train_file", config.train_file)
            config.eval_file = data["data"].get("eval_file", config.eval_file)
        return config


def load_reranker_data(file_path: str, max_samples: int = 1500) -> List[Dict[str, Any]]:
    """加载 Reranker 训练数据"""
    path = Path(file_path)
    if not path.exists():
        logger.error(f"数据文件不存在: {path}")
        return []

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    # 验证格式
    valid = [d for d in data if "query" in d and "document" in d and "label" in d]
    logger.info(f"加载 {len(valid)} 条有效数据（共 {len(data)} 条）")
    return valid[:max_samples]


def train_reranker(config: RerankerConfig):
    """训练 Cross-Encoder Reranker"""
    try:
        import torch
        from sentence_transformers import CrossEncoder
        from sentence_transformers.cross_encoder.losses import CrossEntropyLoss
        from sentence_transformers.cross_encoder.evaluation import CrossEncoderEvaluator
        from datasets import Dataset
    except ImportError as e:
        logger.error(f"缺少依赖: {e}")
        logger.info("请运行: pip install sentence-transformers datasets")
        return

    # 加载数据
    train_data = load_reranker_data(config.train_file, config.max_samples)
    eval_data = load_reranker_data(config.eval_file, config.max_samples // 5)

    if not train_data:
        logger.error("无训练数据，请先运行数据增强脚本")
        return

    # 准备数据集
    train_pairs = [(d["query"], d["document"]) for d in train_data]
    train_labels = [d["label"] for d in train_data]

    eval_pairs = [(d["query"], d["document"]) for d in eval_data]
    eval_labels = [d["label"] for d in eval_data]

    # 创建模型
    logger.info(f"加载模型: {config.model_name}")
    model = CrossEncoder(
        config.model_name,
        num_labels=2,
        max_length=config.max_length,
    )

    # 训练
    logger.info("开始训练 Reranker...")
    start_time = time.time()

    model.fit(
        train_pairs=[(q, d) for q, d in zip(
            [d["query"] for d in train_data],
            [d["document"] for d in train_data]
        )],
        train_labels=train_labels,
        eval_pairs=[(q, d) for q, d in zip(
            [d["query"] for d in eval_data],
            [d["document"] for d in eval_data]
        )],
        eval_labels=eval_labels,
        epochs=config.epochs,
        batch_size=config.batch_size,
        gradient_accumulation_steps=config.gradient_accumulation,
        warmup_ratio=config.warmup_ratio,
        evaluation_steps=config.save_steps,
        output_path=config.output_dir,
        show_progress_bar=True,
    )

    training_time = time.time() - start_time
    logger.info(f"训练完成，耗时 {training_time/60:.1f} 分钟")

    # 保存配置
    info = {
        "model": config.model_name,
        "training_time_minutes": training_time / 60,
        "train_samples": len(train_data),
        "eval_samples": len(eval_data),
        "epochs": config.epochs,
    }
    with open(Path(config.output_dir) / "training_info.json", "w") as f:
        json.dump(info, f, indent=2)


def evaluate_reranker(config: RerankerConfig):
    """评估 Reranker"""
    try:
        from sentence_transformers import CrossEncoder
        import numpy as np
    except ImportError:
        logger.error("缺少依赖")
        return

    eval_data = load_reranker_data(config.eval_file, config.max_samples)
    if not eval_data:
        return

    model = CrossEncoder(config.output_dir)

    # 预测
    pairs = [(d["query"], d["document"]) for d in eval_data]
    scores = model.predict(pairs)

    # 计算 MRR@10
    queries = {}
    for i, d in enumerate(eval_data):
        q = d["query"]
        if q not in queries:
            queries[q] = []
        queries[q].append((scores[i], d["label"]))

    mrr_sum = 0
    for q, results in queries.items():
        results.sort(key=lambda x: x[0], reverse=True)
        for rank, (score, label) in enumerate(results[:10], 1):
            if label == 1:
                mrr_sum += 1 / rank
                break

    mrr = mrr_sum / len(queries) if queries else 0
    logger.info(f"MRR@10: {mrr:.4f}")

    return mrr


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Reranker 微调")
    parser.add_argument("--config", type=str, default="ml/configs/reranker.yaml",
                       help="配置文件路径")
    parser.add_argument("--eval-only", action="store_true",
                       help="仅评估")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    config = RerankerConfig.from_yaml(args.config)

    if not Path(config.train_file).exists():
        logger.error(f"训练数据不存在: {config.train_file}")
        logger.info("请先运行: python ml/data_collection/augment_reranker_data.py")
        return

    if args.eval_only:
        evaluate_reranker(config)
    else:
        train_reranker(config)


if __name__ == "__main__":
    main()

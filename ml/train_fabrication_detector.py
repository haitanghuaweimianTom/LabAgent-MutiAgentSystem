"""
代码伪造检测模型训练脚本
========================

使用 UniXcoder-base 训练二分类模型，检测代码中的硬编码指标。

硬件要求：RTX 4060 8GB (VRAM ~1.5GB)
训练时间：20 分钟

用法：
    python ml/train_fabrication_detector.py --config ml/configs/fabrication_detector.yaml
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
class DetectorConfig:
    """伪造检测训练配置"""
    model_name: str = "microsoft/unixcoder-base"
    max_length: int = 512
    num_labels: int = 2

    # 训练
    batch_size: int = 32
    gradient_accumulation: int = 1
    epochs: int = 5
    learning_rate: float = 2e-5
    weight_decay: float = 0.01
    warmup_ratio: float = 0.1
    fp16: bool = True

    # 数据
    train_file: str = "ml/collected_data/fabrication_train.json"
    eval_file: str = "ml/collected_data/fabrication_eval.json"
    max_samples: int = 1000

    # 输出
    output_dir: str = "ml/checkpoints/fabrication_detector"
    logging_steps: int = 10
    save_steps: int = 100
    seed: int = 42

    @classmethod
    def from_yaml(cls, path: str) -> "DetectorConfig":
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
            config.epochs = t.get("num_train_epochs", config.epochs)
            config.learning_rate = t.get("learning_rate", config.learning_rate)
            config.output_dir = t.get("output_dir", config.output_dir)
        if "data" in data:
            config.train_file = data["data"].get("train_file", config.train_file)
            config.eval_file = data["data"].get("eval_file", config.eval_file)
        return config


def load_detector_data(file_path: str, max_samples: int = 1000) -> List[Dict[str, Any]]:
    """加载伪造检测数据"""
    path = Path(file_path)
    if not path.exists():
        logger.error(f"数据文件不存在: {path}")
        return []

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    valid = [d for d in data if "code" in d and "label" in d]
    logger.info(f"加载 {len(valid)} 条有效数据（共 {len(data)} 条）")
    return valid[:max_samples]


def train_detector(config: DetectorConfig):
    """训练伪造检测模型"""
    try:
        import torch
        from transformers import (
            AutoModelForSequenceClassification,
            AutoTokenizer,
            TrainingArguments,
            Trainer,
        )
        from datasets import Dataset
    except ImportError as e:
        logger.error(f"缺少依赖: {e}")
        logger.info("请运行: pip install transformers datasets accelerate")
        return

    # 加载数据
    train_data = load_detector_data(config.train_file, config.max_samples)
    eval_data = load_detector_data(config.eval_file, config.max_samples // 5)

    if not train_data:
        logger.error("无训练数据，请先运行数据增强脚本")
        return

    # 加载 tokenizer 和模型
    logger.info(f"加载模型: {config.model_name}")
    tokenizer = AutoTokenizer.from_pretrained(config.model_name, trust_remote_code=True)
    model = AutoModelForSequenceClassification.from_pretrained(
        config.model_name,
        num_labels=config.num_labels,
        trust_remote_code=True,
    )

    # 准备数据集
    def tokenize_function(examples):
        return tokenizer(
            examples["code"],
            truncation=True,
            max_length=config.max_length,
            padding="max_length",
        )

    train_dataset = Dataset.from_list(train_data).map(
        tokenize_function, batched=True,
        remove_columns=["code", "source"],
    )
    eval_dataset = Dataset.from_list(eval_data).map(
        tokenize_function, batched=True,
        remove_columns=["code", "source"],
    )

    # 训练参数
    training_args = TrainingArguments(
        output_dir=config.output_dir,
        num_train_epochs=config.epochs,
        per_device_train_batch_size=config.batch_size,
        gradient_accumulation_steps=config.gradient_accumulation,
        learning_rate=config.learning_rate,
        weight_decay=config.weight_decay,
        warmup_ratio=config.warmup_ratio,
        fp16=config.fp16,
        logging_steps=config.logging_steps,
        save_steps=config.save_steps,
        eval_strategy="steps",
        eval_steps=config.save_steps,
        load_best_model_at_end=True,
        metric_for_best_model="eval_accuracy",
        report_to="none",
        seed=config.seed,
    )

    # 评估指标
    import numpy as np
    from sklearn.metrics import accuracy_score, precision_recall_fscore_support

    def compute_metrics(eval_pred):
        logits, labels = eval_pred
        predictions = np.argmax(logits, axis=-1)
        acc = accuracy_score(labels, predictions)
        precision, recall, f1, _ = precision_recall_fscore_support(
            labels, predictions, average="binary"
        )
        return {
            "accuracy": acc,
            "precision": precision,
            "recall": recall,
            "f1": f1,
        }

    # 训练
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        compute_metrics=compute_metrics,
    )

    logger.info("开始训练伪造检测模型...")
    start_time = time.time()
    trainer.train()
    training_time = time.time() - start_time
    logger.info(f"训练完成，耗时 {training_time/60:.1f} 分钟")

    # 保存模型
    trainer.save_model(config.output_dir)
    tokenizer.save_pretrained(config.output_dir)
    logger.info(f"模型已保存到 {config.output_dir}")

    # 最终评估
    metrics = trainer.evaluate()
    logger.info(f"最终评估: {metrics}")

    # 保存信息
    info = {
        "model": config.model_name,
        "training_time_minutes": training_time / 60,
        "train_samples": len(train_data),
        "eval_samples": len(eval_data),
        "epochs": config.epochs,
        "final_metrics": metrics,
    }
    with open(Path(config.output_dir) / "training_info.json", "w") as f:
        json.dump(info, f, indent=2)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="代码伪造检测模型训练")
    parser.add_argument("--config", type=str, default="ml/configs/fabrication_detector.yaml",
                       help="配置文件路径")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    config = DetectorConfig.from_yaml(args.config)

    if not Path(config.train_file).exists():
        logger.error(f"训练数据不存在: {config.train_file}")
        logger.info("请先运行: python ml/data_collection/augment_fabrication_data.py")
        return

    train_detector(config)


if __name__ == "__main__":
    main()

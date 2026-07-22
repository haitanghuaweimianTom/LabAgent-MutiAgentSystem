"""
论文质量 Reward Model DPO 训练脚本
==================================

使用 DPO (Direct Preference Optimization) 训练论文质量评估模型。

硬件要求：RTX 4060 8GB (VRAM ~6GB)
训练时间：2~3 小时

用法：
    python ml/train_reward_model.py --config ml/configs/reward_model_dpo.yaml
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
class DPOConfig:
    """DPO 训练配置"""
    # 模型
    model_name: str = "Qwen/Qwen2.5-1.5B-Instruct"
    quantization_bit: int = 4
    max_length: int = 4096
    max_prompt_length: int = 2048

    # LoRA
    lora_rank: int = 32
    lora_alpha: int = 64
    lora_target: List[str] = field(default_factory=lambda: ["q_proj", "v_proj", "k_proj", "o_proj"])
    lora_dropout: float = 0.05

    # DPO
    beta: float = 0.1
    loss_type: str = "sigmoid"

    # 训练
    batch_size: int = 1
    gradient_accumulation: int = 8
    epochs: int = 3
    learning_rate: float = 5e-6
    weight_decay: float = 0.01
    warmup_ratio: float = 0.1
    fp16: bool = True

    # 数据
    train_file: str = "ml/collected_data/dpo_train_pairs.json"
    eval_file: str = "ml/collected_data/dpo_eval_pairs.json"
    max_samples: int = 500

    # 输出
    output_dir: str = "ml/checkpoints/reward_model"
    logging_steps: int = 10
    save_steps: int = 50
    seed: int = 42

    @classmethod
    def from_yaml(cls, path: str) -> "DPOConfig":
        """从 YAML 文件加载配置"""
        try:
            import yaml
            with open(path) as f:
                data = yaml.safe_load(f)
        except ImportError:
            logger.warning("PyYAML 未安装，使用默认配置")
            return cls()

        config = cls()
        if "model" in data:
            config.model_name = data["model"].get("name_or_path", config.model_name)
            config.quantization_bit = data["model"].get("quantization_bit", config.quantization_bit)
            config.max_length = data["model"].get("max_length", config.max_length)
        if "lora" in data:
            config.lora_rank = data["lora"].get("rank", config.lora_rank)
            config.lora_alpha = data["lora"].get("alpha", config.lora_alpha)
        if "dpo" in data:
            config.beta = data["dpo"].get("beta", config.beta)
            config.loss_type = data["dpo"].get("loss_type", config.loss_type)
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


def load_dpo_data(file_path: str, max_samples: int = 500) -> List[Dict[str, Any]]:
    """加载 DPO 训练数据"""
    path = Path(file_path)
    if not path.exists():
        logger.error(f"数据文件不存在: {path}")
        return []

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    # 验证数据格式
    valid_data = []
    for item in data:
        if "chosen" in item and "rejected" in item:
            valid_data.append(item)

    logger.info(f"加载 {len(valid_data)} 条有效 DPO pairs（共 {len(data)} 条）")
    return valid_data[:max_samples]


def train_with_trl(config: DPOConfig):
    """使用 TRL (Transformer Reinforcement Learning) 训练 DPO"""
    logger.info("使用 TRL DPOTrainer 训练")

    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from trl import DPOTrainer, DPOConfig as TRLDPOConfig
        from peft import LoraConfig, TaskType
        from datasets import Dataset
    except ImportError as e:
        logger.error(f"缺少依赖: {e}")
        logger.info("请运行: pip install trl transformers peft datasets accelerate bitsandbytes")
        return

    # 加载数据
    train_data = load_dpo_data(config.train_file, config.max_samples)
    eval_data = load_dpo_data(config.eval_file, config.max_samples // 5)

    if not train_data:
        logger.error("无训练数据，请先运行数据增强脚本")
        return

    # 加载 tokenizer
    logger.info(f"加载 tokenizer: {config.model_name}")
    tokenizer = AutoTokenizer.from_pretrained(
        config.model_name,
        trust_remote_code=True,
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # 加载模型
    logger.info(f"加载模型（{config.quantization_bit}-bit 量化）")
    model_kwargs = {"trust_remote_code": True}

    if config.quantization_bit == 4:
        from transformers import BitsAndBytesConfig
        model_kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_quant_type="nf4",
        )

    model = AutoModelForCausalLM.from_pretrained(config.model_name, **model_kwargs)

    # LoRA 配置
    lora_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=config.lora_rank,
        lora_alpha=config.lora_alpha,
        lora_dropout=config.lora_dropout,
        target_modules=config.lora_target,
        bias="none",
    )

    # 准备 DPO 数据集
    def format_dpo_sample(sample):
        return {
            "prompt": f"请评估以下论文的质量，从结构、创新、实验、写作四个维度打分。\n\n{sample['chosen'][:config.max_prompt_length]}",
            "chosen": sample["chosen"][config.max_prompt_length:config.max_length],
            "rejected": sample["rejected"][config.max_prompt_length:config.max_length],
        }

    train_dataset = Dataset.from_list([format_dpo_sample(d) for d in train_data])
    eval_dataset = Dataset.from_list([format_dpo_sample(d) for d in eval_data])

    # DPO 训练参数
    training_args = TRLDPOConfig(
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
        beta=config.beta,
        loss_type=config.loss_type,
        max_length=config.max_length,
        max_prompt_length=config.max_prompt_length,
        report_to="none",
        seed=config.seed,
    )

    # 创建 DPO Trainer
    trainer = DPOTrainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        peft_config=lora_config,
        tokenizer=tokenizer,
    )

    # 开始训练
    logger.info("开始 DPO 训练...")
    start_time = time.time()
    trainer.train()
    training_time = time.time() - start_time
    logger.info(f"DPO 训练完成，耗时 {training_time/3600:.1f} 小时")

    # 保存模型
    trainer.save_model(config.output_dir)
    tokenizer.save_pretrained(config.output_dir)
    logger.info(f"模型已保存到 {config.output_dir}")

    # 保存训练信息
    info = {
        "model": config.model_name,
        "training_time_hours": training_time / 3600,
        "train_pairs": len(train_data),
        "eval_pairs": len(eval_data),
        "epochs": config.epochs,
        "beta": config.beta,
        "loss_type": config.loss_type,
    }
    with open(Path(config.output_dir) / "training_info.json", "w") as f:
        json.dump(info, f, indent=2)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Reward Model DPO 训练")
    parser.add_argument("--config", type=str, default="ml/configs/reward_model_dpo.yaml",
                       help="配置文件路径")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # 加载配置
    config = DPOConfig.from_yaml(args.config)

    # 检查数据
    if not Path(config.train_file).exists():
        logger.error(f"训练数据不存在: {config.train_file}")
        logger.info("请先运行数据增强脚本:")
        logger.info("  python ml/data_collection/augment_dpo_data.py")
        return

    # 训练
    train_with_trl(config)


if __name__ == "__main__":
    main()

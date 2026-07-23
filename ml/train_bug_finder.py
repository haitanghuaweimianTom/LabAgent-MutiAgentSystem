"""
Bug Finder Agent 训练脚本
========================

使用 QLoRA 微调 Qwen2.5-Coder-1.5B-Instruct，训练代码错误分类和修复建议生成。

硬件要求：RTX 4060 8GB (VRAM ~6GB)
训练时间：2~3 小时

用法：
    python ml/train_bug_finder.py --config ml/configs/bug_finder_qlora.yaml
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class TrainingConfig:
    """训练配置"""
    # 模型
    model_name: str = "Qwen/Qwen2.5-Coder-1.5B-Instruct"
    quantization_bit: int = 4
    max_length: int = 2048

    # LoRA
    lora_rank: int = 32
    lora_alpha: int = 64
    lora_target: List[str] = field(default_factory=lambda: ["q_proj", "v_proj", "k_proj", "o_proj"])
    lora_dropout: float = 0.05

    # 训练
    batch_size: int = 2
    gradient_accumulation: int = 8
    epochs: int = 3
    learning_rate: float = 2e-5
    weight_decay: float = 0.01
    warmup_ratio: float = 0.1
    fp16: bool = True

    # 数据
    train_file: str = "ml/collected_data/bug_finder_train.json"
    eval_file: str = "ml/collected_data/bug_finder_eval.json"
    max_samples: int = 800

    # 输出
    output_dir: str = "ml/checkpoints/bug_finder"
    logging_steps: int = 10
    save_steps: int = 100
    seed: int = 42

    @classmethod
    def from_yaml(cls, path: str) -> "TrainingConfig":
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
            config.lora_target = data["lora"].get("target", config.lora_target)
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


def load_dataset(file_path: str, max_samples: int = 800) -> List[Dict[str, Any]]:
    """加载训练数据"""
    path = Path(file_path)
    if not path.exists():
        logger.error(f"数据文件不存在: {path}")
        return []

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        return data[:max_samples]
    return []


def format_instruction(sample: Dict[str, Any]) -> Dict[str, Any]:
    """格式化为 SFT 指令格式"""
    return {
        "instruction": sample.get("instruction", ""),
        "output": sample.get("output", ""),
    }


def check_gpu():
    """检查 GPU 可用性"""
    try:
        import torch
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            vram = torch.cuda.get_device_properties(0).total_memory / 1024**3
            logger.info(f"GPU: {gpu_name}, VRAM: {vram:.1f} GB")
            return True
        else:
            logger.warning("CUDA 不可用，将使用 CPU 训练（非常慢）")
            return False
    except ImportError:
        logger.error("PyTorch 未安装")
        return False


def train_with_llamafactory(config: TrainingConfig):
    """使用 LLaMA-Factory 训练（推荐）"""
    logger.info("使用 LLaMA-Factory 训练")

    # 检查 LLaMA-Factory 是否安装
    try:
        import llamafactory
        logger.info(f"LLaMA-Factory 版本: {llamafactory.__version__}")
    except ImportError:
        logger.error("LLaMA-Factory 未安装，请运行: pip install llamafactory")
        logger.info("备选方案：使用 transformers + peft 直接训练")
        train_with_peft(config)
        return

    # 构建 LLaMA-Factory 配置
    llfactory_config = {
        "model_name_or_path": config.model_name,
        "finetuning_type": "lora",
        "lora_rank": config.lora_rank,
        "lora_alpha": config.lora_alpha,
        "lora_target": ",".join(config.lora_target),
        "quantization_bit": config.quantization_bit,
        "dataset": "bug_finder_sft",
        "template": "qwen",
        "cutoff_len": config.max_length,
        "per_device_train_batch_size": config.batch_size,
        "gradient_accumulation_steps": config.gradient_accumulation,
        "num_train_epochs": config.epochs,
        "learning_rate": config.learning_rate,
        "fp16": config.fp16,
        "output_dir": config.output_dir,
        "logging_steps": config.logging_steps,
        "save_steps": config.save_steps,
    }

    # 保存配置
    config_dir = Path(config.output_dir)
    config_dir.mkdir(parents=True, exist_ok=True)

    with open(config_dir / "llfactory_config.json", "w") as f:
        json.dump(llfactory_config, f, indent=2)

    logger.info(f"配置已保存到 {config_dir / 'llfactory_config.json'}")
    logger.info("请运行以下命令训练：")
    logger.info(f"  llamafactory-cli train {config_dir / 'llfactory_config.json'}")


def train_with_peft(config: TrainingConfig):
    """使用 transformers + peft 直接训练（备选方案）"""
    logger.info("使用 transformers + peft 训练")

    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments
        from peft import LoraConfig, get_peft_model, TaskType
        from datasets import Dataset
    except ImportError as e:
        logger.error(f"缺少依赖: {e}")
        logger.info("请运行: pip install transformers peft datasets accelerate bitsandbytes")
        return

    # 加载数据
    train_data = load_dataset(config.train_file, config.max_samples)
    eval_data = load_dataset(config.eval_file, config.max_samples // 5)

    if not train_data:
        logger.error("无训练数据，请先运行数据收集和增强脚本")
        return

    logger.info(f"加载 {len(train_data)} 条训练数据, {len(eval_data)} 条验证数据")

    # 加载 tokenizer
    logger.info(f"加载 tokenizer: {config.model_name}")
    tokenizer = AutoTokenizer.from_pretrained(
        config.model_name,
        trust_remote_code=True,
        padding_side="right",
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # 加载模型（4-bit 量化）
    logger.info(f"加载模型（{config.quantization_bit}-bit 量化）")
    model_kwargs = {"trust_remote_code": True}

    if config.quantization_bit == 4:
        from transformers import BitsAndBytesConfig
        model_kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_quant_type="nf4",
        )
    elif config.quantization_bit == 8:
        from transformers import BitsAndBytesConfig
        model_kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_8bit=True,
        )

    model = AutoModelForCausalLM.from_pretrained(config.model_name, **model_kwargs)

    # 配置 LoRA
    lora_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=config.lora_rank,
        lora_alpha=config.lora_alpha,
        lora_dropout=config.lora_dropout,
        target_modules=config.lora_target,
        bias="none",
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    # 准备数据集
    def format_for_sft(sample):
        text = f"### Instruction:\n{sample['instruction']}\n\n### Response:\n{sample['output']}"
        tokenized = tokenizer(
            text,
            truncation=True,
            max_length=config.max_length,
            padding="max_length",
        )
        tokenized["labels"] = tokenized["input_ids"].copy()
        return tokenized

    train_dataset = Dataset.from_list(train_data).map(
        format_for_sft, remove_columns=train_data[0].keys()
    )
    eval_dataset = Dataset.from_list(eval_data).map(
        format_for_sft, remove_columns=eval_data[0].keys()
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
        eval_strategy="no",
        report_to="none",
        seed=config.seed,
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
    )

    # 开始训练
    from transformers import Trainer

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
    )

    logger.info("开始训练...")
    start_time = time.time()
    trainer.train()
    training_time = time.time() - start_time
    logger.info(f"训练完成，耗时 {training_time/3600:.1f} 小时")

    # 保存模型
    trainer.save_model(config.output_dir)
    tokenizer.save_pretrained(config.output_dir)
    logger.info(f"模型已保存到 {config.output_dir}")

    # 保存训练信息
    info = {
        "model": config.model_name,
        "training_time_hours": training_time / 3600,
        "train_samples": len(train_data),
        "eval_samples": len(eval_data),
        "epochs": config.epochs,
        "final_loss": trainer.state.log_history[-1].get("train_loss", 0),
    }
    with open(Path(config.output_dir) / "training_info.json", "w") as f:
        json.dump(info, f, indent=2)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Bug Finder Agent 训练")
    parser.add_argument("--config", type=str, default="ml/configs/bug_finder_qlora.yaml",
                       help="配置文件路径")
    parser.add_argument("--check-gpu", action="store_true",
                       help="仅检查 GPU")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if args.check_gpu:
        check_gpu()
        return

    # 加载配置
    config = TrainingConfig.from_yaml(args.config)

    # 检查 GPU
    check_gpu()

    # 检查数据
    if not Path(config.train_file).exists():
        logger.error(f"训练数据不存在: {config.train_file}")
        logger.info("请先运行数据收集和增强脚本:")
        logger.info("  python ml/data_collection/collect_system_runs.py --problems 20")
        logger.info("  python ml/data_collection/augment_bug_data.py")
        return

    # 尝试 LLaMA-Factory，回退到 transformers + peft
    train_with_llamafactory(config)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""QLoRA fine-tuning script for Bug Finder using Qwen2.5-Coder-1.5B-Instruct."""

import os
import json
import torch
import numpy as np
from pathlib import Path
from datasets import Dataset
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    TrainingArguments,
    Trainer,
    DataCollatorForSeq2Seq,
)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training


# ── Config ──────────────────────────────────────────────────────────────────

MODEL_PATH = "ml/models/qwen2.5-coder-1.5b-instruct"
TRAIN_DATA_PATH = "ml/collected_data/bug_finder_train.json"
EVAL_DATA_PATH = "ml/collected_data/bug_finder_eval.json"
OUTPUT_DIR = "ml/checkpoints/bug_finder_qlora"

MAX_LENGTH = 1024
SYSTEM_PROMPT = "You are a bug finder assistant. Given a code snippet, identify the bug and explain it clearly."


# ── Data ────────────────────────────────────────────────────────────────────

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def format_chatml(sample):
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": sample["instruction"]},
        {"role": "assistant", "content": sample["output"]},
    ]
    return messages


def tokenize_chatml(samples, tokenizer):
    """Tokenize samples using ChatML template and mask input tokens."""
    tokenized = []
    for sample in samples:
        messages = format_chatml(sample)
        text = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=False
        )
        tokenized_text = tokenizer(
            text,
            truncation=True,
            max_length=MAX_LENGTH,
            padding="max_length",
            return_tensors=None,
        )
        labels = tokenized_text["input_ids"].copy()

        # Mask the prompt portion (system + user) so loss only applies to output
        prompt_messages = messages[:2]
        prompt_text = tokenizer.apply_chat_template(
            prompt_messages, tokenize=False, add_generation_prompt=True
        )
        prompt_tokens = tokenizer(
            prompt_text, truncation=True, max_length=MAX_LENGTH, return_tensors=None
        )
        prompt_len = len(prompt_tokens["input_ids"])

        labels[:prompt_len] = [-100] * prompt_len
        tokenized_text["labels"] = labels
        tokenized.append(tokenized_text)

    return tokenized


# ── Model ───────────────────────────────────────────────────────────────────

def load_model_and_tokenizer():
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

    tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        MODEL_PATH,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
        torch_dtype=torch.bfloat16,
    )
    model = prepare_model_for_kbit_training(model)

    lora_config = LoraConfig(
        r=32,
        lora_alpha=64,
        target_modules=["q_proj", "v_proj", "k_proj", "o_proj"],
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()
    return model, tokenizer


# ── Training ────────────────────────────────────────────────────────────────

def train(model, tokenizer, train_dataset, eval_dataset):
    training_args = TrainingArguments(
        output_dir=OUTPUT_DIR,
        num_train_epochs=3,
        per_device_train_batch_size=2,
        per_device_eval_batch_size=2,
        gradient_accumulation_steps=8,
        learning_rate=2e-5,
        weight_decay=0.01,
        warmup_ratio=0.03,
        lr_scheduler_type="cosine",
        bf16=True,
        logging_steps=10,
        eval_strategy="epoch",
        save_strategy="epoch",
        save_total_limit=2,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        report_to="none",
        remove_unused_columns=False,
    )

    data_collator = DataCollatorForSeq2Seq(
        tokenizer=tokenizer, padding=True, return_tensors="pt"
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        data_collator=data_collator,
        processing_class=tokenizer,
    )

    print("Starting training...")
    trainer.train()

    print("Saving model...")
    trainer.save_model(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)
    print("Model saved to: {}".format(OUTPUT_DIR))


# ── Evaluation ──────────────────────────────────────────────────────────────

def evaluate(model, tokenizer, eval_data):
    """Run evaluation and compute error_type_accuracy."""
    model.eval()
    correct = 0
    total = 0

    print("\n--- Evaluation ---")
    for i, sample in enumerate(eval_data):
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": sample["instruction"]},
        ]
        prompt_text = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        inputs = tokenizer(prompt_text, return_tensors="pt").to(model.device)

        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=256,
                temperature=0.1,
                do_sample=False,
            )

        response = tokenizer.decode(
            outputs[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True
        )

        expected = sample["output"]
        # Simple accuracy: check if the key error type terms from expected appear in response
        if expected.strip().lower() in response.strip().lower():
            correct += 1
        total += 1

        if i < 5:
            print("Sample {}:".format(i + 1))
            print("  Expected: {}".format(expected[:120]))
            print("  Got:      {}".format(response[:120]))
            print()

    accuracy = correct / total if total > 0 else 0
    print("Error Type Accuracy: {}/{} = {:.4f}".format(correct, total, accuracy))
    return accuracy


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    print("Loading training data...")
    train_data = load_json(TRAIN_DATA_PATH)
    eval_data = load_json(EVAL_DATA_PATH)
    print("Train samples: {}".format(len(train_data)))
    print("Eval samples: {}".format(len(eval_data)))

    print("Loading model and tokenizer...")
    model, tokenizer = load_model_and_tokenizer()

    print("Tokenizing...")
    train_tokenized = tokenize_chatml(train_data, tokenizer)
    eval_tokenized = tokenize_chatml(eval_data, tokenizer)

    train_dataset = Dataset.from_list(train_tokenized)
    eval_dataset = Dataset.from_list(eval_tokenized)

    train(model, tokenizer, train_dataset, eval_dataset)

    print("Running evaluation...")
    evaluate(model, tokenizer, eval_data)


if __name__ == "__main__":
    main()

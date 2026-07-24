"""
Bug Finder QLoRA 微调 v2（修复版）
================================
相对旧脚本的关键修复（这些正是"微调后反而变差"的根因）：
1. ChatML + 仅对 assistant 输出计算 loss（旧 train_bug_finder.py 的 ### Instruction 格式
   且不对 prompt 做 label masking，loss 算在整段 instruction 上，浪费容量且与推理时
   的 chat template 不一致 —— 训练/推理格式不匹配导致输出退化）
2. 系统 prompt 明确要求只输出 JSON（旧脚本的 system prompt 只说"explain it clearly"，
   与"输出结构化 JSON"目标不一致）
3. 训练数据无泄露（来自 prepare_clean_split.py 的 clean_train，与 test 零重叠）
4. 按"严格 JSON 准确率"挑选最佳 checkpoint（不再用 eval_loss，因为 loss 低 ≠ JSON 对）
5. 显存安全：torch.cuda.set_per_process_memory_fraction 上限 + 梯度检查点，
   保证不占满显存导致桌面卡死

配置（与简历一致）：rank=32 / alpha=64 / target=q,k,v,o_proj / 8-bit 量化 / lr=2e-5

用法：
    python ml/train_bug_finder_v2.py
"""
from __future__ import annotations

import json
import logging
import random
import re
import time
from pathlib import Path

import torch
from datasets import Dataset
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    DataCollatorForSeq2Seq,
    Trainer,
    TrainingArguments,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("train_v2")

ROOT = Path(__file__).resolve().parent.parent
BASE = str(ROOT / "ml" / "models" / "qwen2.5-coder-1.5b-instruct")
TRAIN_FILE = str(ROOT / "ml" / "collected_data" / "bug_finder_clean_train.json")
OUT_DIR = str(ROOT / "ml" / "checkpoints" / "bug_finder_v2_clean")
VAL_OUT = str(ROOT / "ml" / "results" / "finetuned_val_history.json")

MAX_LEN = 1024
SEED = 42

JSON_SYSTEM_PROMPT = (
    "你是一个代码错误诊断助手。阅读给定的代码与报错信息，"
    "严格输出一个 JSON 对象，且只输出该 JSON，不要输出任何解释或额外文本。\n"
    "JSON 字段：error_type（错误类型）、error_location（出错位置，如 line 2）、"
    "root_cause（根本原因）、fix_suggestion（修复建议）、confidence（0 到 1 的浮点数）。"
)

# 显存安全：限制本进程 GPU 显存上限，留余量给桌面，防止卡死
if torch.cuda.is_available():
    torch.cuda.set_per_process_memory_fraction(0.78)

# ── 严格评测辅助函数（与 eval_bug_finder_strict.py 保持一致）────────────────
SYNONYM_MAP = {
    "ModuleNotFoundError": "ImportError",
    "torch.cuda.OutOfMemoryError": "OOM",
    "OutOfMemoryError": "OOM",
    "RecursionError": "LogicError",
    "NotFittedError": "LogicError",
}

CANONICAL_KEYWORDS = {
    "IndexError": ["indexerror", "index_error", "index out of range", "list index"],
    "KeyError": ["keyerror", "key_error", "key not found"],
    "TypeError": ["typeerror", "type_error"],
    "ValueError": ["valueerror", "value_error"],
    "ZeroDivisionError": ["zerodivisionerror", "zero_division", "division by zero", "divide by zero"],
    "AttributeError": ["attributeerror", "attribute_error", "has no attribute"],
    "ImportError": ["importerror", "import_error", "modulenotfound", "module_not_found", "no module named"],
    "FileNotFoundError": ["filenotfounderror", "file_not_found", "no such file"],
    "RuntimeError": ["runtimeerror", "runtime_error"],
    "SyntaxError": ["syntaxerror", "syntax_error"],
    "OOM": ["oom", "outofmemory", "out of memory", "cuda out of memory"],
    "ShapeMismatch": ["shapemismatch", "shape_mismatch", "shape mismatch", "size mismatch", "cannot be multiplied"],
    "LogicError": ["logicerror", "logic_error", "recursionerror", "recursion_error", "maximum recursion", "notfitted", "not fitted"],
    "Timeout": ["timeout", "time_out", "timed out"],
}


def normalize_label(label: str) -> str:
    return SYNONYM_MAP.get((label or "").strip(), (label or "").strip())


def canonicalize(label):
    if not label:
        return None
    exact = normalize_label(label)
    if exact in CANONICAL_KEYWORDS:
        return exact
    s = label.strip().lower()
    s_nound = s.replace("_", "")
    for canon, kws in CANONICAL_KEYWORDS.items():
        for kw in kws:
            if kw in s or kw in s_nound:
                return canon
    return None


def find_json_objects(text: str):
    starts = []
    for i, ch in enumerate(text):
        if ch == "{":
            starts.append(i)
        elif ch == "}" and starts:
            start = starts.pop()
            if not starts:
                yield text[start:i + 1]


def extract_error_type(text: str):
    for cand in find_json_objects(text):
        try:
            obj = json.loads(cand)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and "error_type" in obj:
            return str(obj["error_type"]), True
    m = re.search(r'"error_type"\s*:\s*"([^"]+)"', text)
    if m:
        return m.group(1), False
    return None, False


def predict_one(model, tokenizer, instruction: str) -> str:
    messages = [
        {"role": "system", "content": JSON_SYSTEM_PROMPT},
        {"role": "user", "content": instruction},
    ]
    text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(text, return_tensors="pt").to(model.device)
    with torch.no_grad():
        out = model.generate(
            **inputs, max_new_tokens=256, do_sample=False,
            pad_token_id=tokenizer.eos_token_id,
        )
    gen = out[0][inputs["input_ids"].shape[1]:]
    return tokenizer.decode(gen, skip_special_tokens=True)


def strict_val_accuracy(model, tokenizer, val_data) -> tuple[float, int, int]:
    model.eval()
    correct = 0
    total = 0
    with torch.no_grad():
        for s in val_data:
            try:
                exp_raw = json.loads(s["output"]).get("error_type", "")
            except Exception:
                exp_raw = ""
            exp = canonicalize(exp_raw) or exp_raw
            resp = predict_one(model, tokenizer, s["instruction"])
            pred_raw, _ = extract_error_type(resp)
            pred = canonicalize(pred_raw)
            correct += int(pred is not None and pred == exp)
            total += 1
    model.train()
    return correct / total if total else 0.0, correct, total


# ── 数据 ──────────────────────────────────────────────────────────────────
def load_split():
    with open(TRAIN_FILE, encoding="utf-8") as f:
        data = json.load(f)
    rng = random.Random(SEED)
    rng.shuffle(data)
    n_val = max(30, len(data) // 10)  # 10% 作内部验证集（仅用于挑最佳 checkpoint）
    return data[n_val:], data[:n_val]


def tokenize_sample(sample, tokenizer):
    messages = [
        {"role": "system", "content": JSON_SYSTEM_PROMPT},
        {"role": "user", "content": sample["instruction"]},
        {"role": "assistant", "content": sample["output"]},
    ]
    full = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)
    enc = tokenizer(full, truncation=True, max_length=MAX_LEN, return_tensors=None)
    # mask 掉 system+user 的 prompt，loss 只算 assistant 输出
    prompt = tokenizer.apply_chat_template(
        messages[:2], tokenize=False, add_generation_prompt=True)
    plen = len(tokenizer(prompt, truncation=True, max_length=MAX_LEN)["input_ids"])
    labels = enc["input_ids"].copy()
    labels[:plen] = [-100] * plen
    enc["labels"] = labels
    return enc


# ── 模型 ──────────────────────────────────────────────────────────────────
def load_model():
    log.info(f"加载 tokenizer / 模型: {BASE}")
    tokenizer = AutoTokenizer.from_pretrained(BASE, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    bnb = BitsAndBytesConfig(load_in_8bit=True)
    model = AutoModelForCausalLM.from_pretrained(
        BASE, quantization_config=bnb, device_map="auto", trust_remote_code=True,
    )
    model = prepare_model_for_kbit_training(model)
    model.config.use_cache = False

    lora = LoraConfig(
        r=32, lora_alpha=64, target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        lora_dropout=0.05, bias="none", task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lora)
    model.print_trainable_parameters()
    return model, tokenizer


class StrictBestCallback(__import__("transformers").TrainerCallback):
    """每个 epoch 结束用严格 JSON 准确率在验证集上评测，保存最佳 adapter。"""

    def __init__(self, val_data, tokenizer, out_dir):
        self.val = val_data
        self.tokenizer = tokenizer
        self.out_dir = out_dir
        self.best = -1.0
        self.history = []

    def on_epoch_end(self, args, state, control, **kwargs):
        model = kwargs["model"]
        acc, c, t = strict_val_accuracy(model, self.tokenizer, self.val)
        self.history.append({"epoch": state.epoch, "val_strict_acc": acc,
                             "correct": c, "total": t})
        log.info(f"[epoch {state.epoch:.1f}] 严格验证集准确率 = {acc:.4f} ({c}/{t}), 历史最佳 = {self.best:.4f}")
        if acc >= self.best:
            self.best = acc
            model.save_pretrained(self.out_dir)
            self.tokenizer.save_pretrained(self.out_dir)
            log.info(f"  -> 保存最佳 adapter 到 {self.out_dir}")
        # 持久化历史
        with open(VAL_OUT, "w", encoding="utf-8") as f:
            json.dump({"best_val_strict_acc": self.best, "history": self.history}, f, indent=2)


def main():
    train_data, val_data = load_split()
    log.info(f"train={len(train_data)}  val(internal)={len(val_data)}")
    model, tokenizer = load_model()

    log.info("tokenize ...")
    train_tok = [tokenize_sample(s, tokenizer) for s in train_data]
    train_ds = Dataset.from_list(train_tok)

    collator = DataCollatorForSeq2Seq(tokenizer=tokenizer, padding=True, return_tensors="pt")

    args = TrainingArguments(
        output_dir=OUT_DIR,
        num_train_epochs=3,
        per_device_train_batch_size=2,
        gradient_accumulation_steps=8,
        learning_rate=2e-5,
        weight_decay=0.01,
        warmup_ratio=0.03,
        lr_scheduler_type="cosine",
        bf16=True,
        logging_steps=10,
        save_strategy="no",
        eval_strategy="no",
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        remove_unused_columns=False,
        report_to="none",
        seed=SEED,
        dataloader_num_workers=0,
    )

    trainer = Trainer(
        model=model, args=args, train_dataset=train_ds,
        data_collator=collator, processing_class=tokenizer,
        callbacks=[StrictBestCallback(val_data, tokenizer, OUT_DIR)],
    )

    log.info("开始训练 ...")
    t0 = time.time()
    trainer.train()
    log.info(f"训练完成，耗时 {(time.time()-t0)/60:.1f} 分钟")
    # 训练结束再保一次最终（best 已在 callback 中保存）
    log.info(f"最佳验证集严格准确率 = {trainer.callback_handler.callbacks[-1].best:.4f}")
    log.info(f"adapter 已保存至 {OUT_DIR}")


if __name__ == "__main__":
    main()

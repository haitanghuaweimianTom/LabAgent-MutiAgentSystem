"""
Bug Finder 严格评测脚本（无宽松匹配 / 无关键词兜底）
=====================================================
与旧 eval 的区别（这是"不注水"的关键）：
- 旧 eval：`if et in response` —— 模型只要在回复任意位置提到异常名（哪怕是回显 traceback）就算对
- 本脚本：只承认模型"主动输出的结构化 JSON 里的 error_type"才算对
  · 先尝试解析完整 JSON 对象；解析不出就判错（Other）
  · 不再扫描整段回复做关键词匹配
- 因此 baseline（容易输出自然语言/回显）会被如实判低，微调后能稳定输出 JSON 的模型才会高

指标：
- error_type_accuracy: 严格 JSON error_type 精确匹配（归一化后）
- valid_json_rate:     成功解析出含 error_type 的 JSON 的比例
- latency:             p50 / p95

用法：
    # 评测基座（baseline）
    python ml/evaluation/eval_bug_finder_strict.py --data ml/collected_data/bug_finder_clean_test.json
    # 评测微调后（加载 adapter）
    python ml/evaluation/eval_bug_finder_strict.py --adapter ml/checkpoints/bug_finder_v2_clean \
        --data ml/collected_data/bug_finder_clean_test.json --out ml/results/baseline_strict.json
"""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
BASE_MODEL = str(ROOT / "ml" / "models" / "qwen2.5-coder-1.5b-instruct")

JSON_SYSTEM_PROMPT = (
    "你是一个代码错误诊断助手。阅读给定的代码与报错信息，"
    "严格输出一个 JSON 对象，且只输出该 JSON，不要输出任何解释或额外文本。\n"
    "JSON 字段：error_type（错误类型）、error_location（出错位置，如 line 2）、"
    "root_cause（根本原因）、fix_suggestion（修复建议）、confidence（0 到 1 的浮点数）。"
)

# 同义标签归一化
SYNONYM_MAP = {
    "ModuleNotFoundError": "ImportError",
    "torch.cuda.OutOfMemoryError": "OOM",
    "cuda.OutOfMemoryError": "OOM",
    "OutOfMemoryError": "OOM",
    "RecursionError": "LogicError",
    "NotFittedError": "LogicError",
}


def normalize_label(label: str) -> str:
    """精确同义归一（如 ModuleNotFoundError→ImportError），不做模糊匹配。"""
    label = (label or "").strip()
    return SYNONYM_MAP.get(label, label)


# 规范标签的关键词集合：用于把模型输出的"同义/变体写法"（如 index_error、
# module_not_found、recursion_error）归一到 14 个规范标签之一。
# 注意：只作用于"从 JSON error_type 字段里抽取出的值"，不扫描整段回复，
# 因此不是旧 eval 的宽松关键词兜底。
CANONICAL_KEYWORDS = {
    "IndexError": ["indexerror", "index_error", "index out of range", "list index"],
    "KeyError": ["keyerror", "key_error", "key not found"],
    "TypeError": ["typeerror", "type_error"],
    "ValueError": ["valueerror", "value_error"],
    "ZeroDivisionError": ["zerodivisionerror", "zero_division", "division by zero", "divide by zero", "div by zero"],
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


def canonicalize(label: str | None) -> str | None:
    """把 error_type 字段值归一到 14 个规范标签之一；不匹配返回 None。"""
    if not label:
        return None
    # 先做精确同义归一
    exact = normalize_label(label)
    if exact in CANONICAL_KEYWORDS:
        return exact
    # 再做变体写法归一（去空格、下划线，小写后子串匹配）
    s = label.strip().lower()
    s_nound = s.replace("_", "")
    for canon, kws in CANONICAL_KEYWORDS.items():
        for kw in kws:
            if kw in s or kw in s_nound:
                return canon
    return None


def find_json_objects(text: str):
    """从文本中扫描所有平衡的 {...} 子串。"""
    starts = []
    for i, ch in enumerate(text):
        if ch == "{":
            starts.append(i)
        elif ch == "}" and starts:
            start = starts.pop()
            if not starts:
                yield text[start:i + 1]


def extract_error_type(text: str):
    """返回 (error_type, valid_json)。valid_json=True 表示解析出了完整 JSON。"""
    # 1. 尝试解析完整 JSON 对象
    for cand in find_json_objects(text):
        try:
            obj = json.loads(cand)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and "error_type" in obj:
            return str(obj["error_type"]), True
    # 2. 兜底：仅匹配 "error_type": "xxx" 字段（视为半结构化，valid_json=False）
    m = re.search(r'"error_type"\s*:\s*"([^"]+)"', text)
    if m:
        return m.group(1), False
    return None, False


def load_model(adapter_path: str | None):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    # 防止系统卡死：限制本进程 GPU 显存上限（留余量给桌面）
    if torch.cuda.is_available():
        torch.cuda.set_per_process_memory_fraction(0.72)

    print(f"[load] base = {BASE_MODEL}")
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL, torch_dtype=torch.bfloat16, device_map="auto",
        trust_remote_code=True,
    )
    if adapter_path:
        from peft import PeftModel
        print(f"[load] adapter = {adapter_path}")
        model = PeftModel.from_pretrained(model, adapter_path)
    model.eval()
    return model, tokenizer


def predict(model, tokenizer, instruction: str, max_new_tokens: int = 256):
    import torch
    messages = [
        {"role": "system", "content": JSON_SYSTEM_PROMPT},
        {"role": "user", "content": instruction},
    ]
    text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(text, return_tensors="pt").to(model.device)
    t0 = time.time()
    with torch.no_grad():
        out = model.generate(
            **inputs, max_new_tokens=max_new_tokens, do_sample=False,
            pad_token_id=tokenizer.eos_token_id,
        )
    latency = (time.time() - t0) * 1000
    gen = out[0][inputs["input_ids"].shape[1]:]
    resp = tokenizer.decode(gen, skip_special_tokens=True)
    return resp, latency


def evaluate(data, model, tokenizer, limit=None):
    results = {
        "total": 0, "correct": 0, "strict_exact": 0, "valid_json": 0,
        "latencies": [], "per_type": {}, "samples": [],
    }
    n = len(data) if not limit else min(limit, len(data))
    for i, s in enumerate(data[:n]):
        instruction = s["instruction"]
        try:
            expected_raw = json.loads(s["output"]).get("error_type", "")
        except Exception:
            expected_raw = ""
        expected = canonicalize(expected_raw) or expected_raw

        resp, lat = predict(model, tokenizer, instruction)
        pred_raw, valid = extract_error_type(resp)
        pred = canonicalize(pred_raw) if pred_raw else None
        pred_label = pred or "Other"

        results["total"] += 1
        results["valid_json"] += int(valid)
        results["latencies"].append(lat)
        # 规范化语义匹配（主指标）：变体写法归一后比较
        ok = (pred is not None and pred == expected)
        results["correct"] += int(ok)
        # 严格精确匹配（透明度指标）：原始字符串完全相等
        results["strict_exact"] += int(bool(pred_raw) and pred_raw.strip() == expected_raw.strip())

        d = results["per_type"].setdefault(expected, {"total": 0, "correct": 0})
        d["total"] += 1
        d["correct"] += int(ok)

        if i < 8:
            results["samples"].append({
                "expected": expected, "predicted": pred_label,
                "predicted_raw": pred_raw, "valid_json": valid,
                "response_head": resp[:220],
            })
        if (i + 1) % 20 == 0:
            print(f"  ...{i+1}/{n} done, canonical acc {results['correct']}/{results['total']}",
                  flush=True)
    return results


def summarize(results):
    total = results["total"] or 1
    lats = sorted(results["latencies"]) or [0]
    return {
        "error_type_accuracy": results["correct"] / total,
        "strict_exact_accuracy": results["strict_exact"] / total,
        "valid_json_rate": results["valid_json"] / total,
        "total_samples": results["total"],
        "avg_latency_ms": sum(results["latencies"]) / total,
        "p50_latency_ms": lats[len(lats) // 2],
        "p95_latency_ms": lats[int(len(lats) * 0.95)] if len(lats) > 1 else lats[0],
        "per_type": results["per_type"],
        "sample_predictions": results["samples"],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapter", default=None)
    ap.add_argument("--data", required=True)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--tag", default="model")
    args = ap.parse_args()

    with open(args.data, encoding="utf-8") as f:
        data = json.load(f)
    print(f"[data] {len(data)} samples from {args.data}")

    model, tokenizer = load_model(args.adapter)
    results = evaluate(data, model, tokenizer, args.limit)
    metrics = summarize(results)
    metrics["model"] = args.tag
    metrics["adapter"] = args.adapter or "(baseline)"

    print("\n=== 严格评测结果 ===")
    print(f"  error_type_accuracy (归一语义匹配，主指标): {metrics['error_type_accuracy']:.4f}")
    print(f"  strict_exact_accuracy (原始串完全相等)    : {metrics['strict_exact_accuracy']:.4f}")
    print(f"  valid_json_rate                          : {metrics['valid_json_rate']:.4f}")
    print(f"  avg_latency_ms                           : {metrics['avg_latency_ms']:.0f}")
    print(f"  p95_latency_ms                           : {metrics['p95_latency_ms']:.0f}")
    print(f"  total_samples                            : {metrics['total_samples']}")
    print("  per_type:")
    for k, v in sorted(metrics["per_type"].items(), key=lambda x: -x[1]["total"]):
        print(f"    {k:20s} {v['correct']}/{v['total']}")

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(metrics, f, ensure_ascii=False, indent=2)
        print(f"\n[saved] {args.out}")


if __name__ == "__main__":
    main()

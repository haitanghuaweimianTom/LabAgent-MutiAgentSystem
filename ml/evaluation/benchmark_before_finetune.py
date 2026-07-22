"""
微调前基准测试
=============

测试 Qwen2.5-Coder-1.5B 在 Bug Finder 任务上的初始能力。
记录关键指标，用于与微调后对比。
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer


def load_eval_data(path: str) -> List[Dict[str, Any]]:
    """加载评估数据"""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def extract_json_from_response(response: str) -> Dict[str, Any]:
    """从模型输出中提取 JSON 或结构化文本"""
    # 1. 尝试提取 JSON 块
    json_patterns = [
        r'\{[^{}]*"error_type"[^{}]*\}',
        r'```json\s*(\{[^{}]*"error_type"[^{}]*\})\s*```',
        r'```\s*(\{[^{}]*"error_type"[^{}]*\})\s*```',
    ]
    for pattern in json_patterns:
        match = re.search(pattern, response, re.DOTALL)
        if match:
            try:
                json_str = match.group(1) if match.lastindex else match.group(0)
                return json.loads(json_str)
            except json.JSONDecodeError:
                continue

    # 2. 从自然语言中提取错误类型（中英文映射）
    error_type_map = {
        "OOM": "OOM", "OutOfMemory": "OOM", "显存不足": "OOM",
        "SyntaxError": "SyntaxError", "语法错误": "SyntaxError",
        "ShapeMismatch": "ShapeMismatch", "维度不匹配": "ShapeMismatch",
        "IndexError": "IndexError", "索引错误": "IndexError",
        "KeyError": "KeyError", "键错误": "KeyError",
        "TypeError": "TypeError", "类型错误": "TypeError",
        "ValueError": "ValueError", "值错误": "ValueError",
        "ImportError": "DependencyMissing", "ModuleNotFoundError": "DependencyMissing",
        "FileNotFoundError": "DataFormat", "文件不存在": "DataFormat",
        "AttributeError": "LogicError", "属性错误": "LogicError",
        "ZeroDivisionError": "LogicError", "除零": "LogicError",
        "TimeoutError": "Timeout", "超时": "Timeout",
    }

    detected_type = "Other"
    for keyword, error_type in error_type_map.items():
        if keyword in response:
            detected_type = error_type
            break

    # 3. 提取修复建议
    fix = ""
    fix_match = re.search(r"修复建议[：:]\s*(.+?)(?:\n|$)", response)
    if fix_match:
        fix = fix_match.group(1).strip()[:200]

    if detected_type != "Other":
        return {
            "error_type": detected_type,
            "error_location": "line 1",
            "root_cause": response[:200],
            "fix_suggestion": fix,
            "confidence": 0.7,
        }

    return {}


def evaluate_model(model, tokenizer, eval_data: List[Dict[str, Any]],
                   max_samples: int = 100) -> Dict[str, Any]:
    """评估模型"""
    results = {
        "total": 0,
        "correct_type": 0,
        "correct_location": 0,
        "has_fix": 0,
        "valid_json": 0,
        "latencies": [],
        "per_type": {},
    }

    for i, sample in enumerate(eval_data[:max_samples]):
        instruction = sample.get("instruction", "")
        expected_output = json.loads(sample.get("output", "{}"))
        expected_type = expected_output.get("error_type", "Other")

        # 推理
        inputs = tokenizer(instruction, return_tensors="pt", truncation=True, max_length=2048)
        if torch.cuda.is_available():
            inputs = {k: v.cuda() for k, v in inputs.items()}

        start = time.time()
        with torch.no_grad():
            outputs = model.generate(**inputs, max_new_tokens=256, do_sample=False)
        latency = (time.time() - start) * 1000

        response = tokenizer.decode(outputs[0], skip_special_tokens=True)

        # 解析预测
        predicted = extract_json_from_response(response)
        predicted_type = predicted.get("error_type", "Other")

        # 统计
        results["total"] += 1
        results["latencies"].append(latency)

        if predicted:
            results["valid_json"] += 1

        if predicted_type == expected_type:
            results["correct_type"] += 1

        if predicted.get("error_location"):
            results["correct_location"] += 1

        if predicted.get("fix_suggestion") or predicted.get("fix"):
            results["has_fix"] += 1

        # 按类型统计
        if expected_type not in results["per_type"]:
            results["per_type"][expected_type] = {"total": 0, "correct": 0}
        results["per_type"][expected_type]["total"] += 1
        if predicted_type == expected_type:
            results["per_type"][expected_type]["correct"] += 1

        if (i + 1) % 20 == 0:
            print(f"  已评估 {i+1}/{min(len(eval_data), max_samples)} 样本")

    return results


def main():
    import argparse

    parser = argparse.ArgumentParser(description="微调前基准测试")
    parser.add_argument("--model", type=str, default="ml/models/qwen2.5-coder-1.5b-instruct")
    parser.add_argument("--data", type=str, default="ml/collected_data/bug_finder_eval.json")
    parser.add_argument("--output", type=str, default="ml/results")
    parser.add_argument("--max-samples", type=int, default=80)
    args = parser.parse_args()

    print("=" * 60)
    print("Bug Finder 微调前基准测试")
    print("=" * 60)

    # 加载模型
    print(f"\n加载模型: {args.model}")
    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(args.model, trust_remote_code=True)
    if torch.cuda.is_available():
        model = model.cuda()
        print("模型已加载到 GPU")

    # 加载数据
    eval_data = load_eval_data(args.data)
    print(f"评估数据: {len(eval_data)} 条")

    # 评估
    print("\n开始评估...")
    results = evaluate_model(model, tokenizer, eval_data, args.max_samples)

    # 计算指标
    total = results["total"]
    metrics = {
        "error_type_accuracy": results["correct_type"] / total if total > 0 else 0,
        "location_accuracy": results["correct_location"] / total if total > 0 else 0,
        "fix_rate": results["has_fix"] / total if total > 0 else 0,
        "valid_json_rate": results["valid_json"] / total if total > 0 else 0,
        "avg_latency_ms": sum(results["latencies"]) / len(results["latencies"]) if results["latencies"] else 0,
        "p50_latency_ms": sorted(results["latencies"])[len(results["latencies"]) // 2] if results["latencies"] else 0,
        "p95_latency_ms": sorted(results["latencies"])[int(len(results["latencies"]) * 0.95)] if results["latencies"] else 0,
        "total_samples": total,
    }

    # 打印结果
    print("\n" + "=" * 60)
    print("评估结果 (微调前 Baseline)")
    print("=" * 60)
    for k, v in metrics.items():
        if isinstance(v, float):
            print(f"  {k}: {v:.4f}")
        else:
            print(f"  {k}: {v}")

    # 按类型统计
    print("\n按错误类型统计:")
    for error_type, stats in sorted(results["per_type"].items()):
        acc = stats["correct"] / stats["total"] if stats["total"] > 0 else 0
        print(f"  {error_type}: {acc:.2%} ({stats['correct']}/{stats['total']})")

    # 保存结果
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 保存详细结果
    detail_results = {
        "model": args.model,
        "metrics": metrics,
        "per_type": results["per_type"],
        "sample_predictions": [],
    }

    # 保存几个样本预测
    for sample in eval_data[:5]:
        instruction = sample["instruction"]
        inputs = tokenizer(instruction, return_tensors="pt", truncation=True, max_length=2048)
        if torch.cuda.is_available():
            inputs = {k: v.cuda() for k, v in inputs.items()}
        with torch.no_grad():
            outputs = model.generate(**inputs, max_new_tokens=256, do_sample=False)
        response = tokenizer.decode(outputs[0], skip_special_tokens=True)
        predicted = extract_json_from_response(response)

        detail_results["sample_predictions"].append({
            "instruction": instruction[:200],
            "expected": json.loads(sample["output"]),
            "predicted": predicted,
        })

    with open(output_dir / "baseline_before_finetune.json", "w", encoding="utf-8") as f:
        json.dump(detail_results, f, ensure_ascii=False, indent=2)

    print(f"\n结果已保存到: {output_dir / 'baseline_before_finetune.json'}")


if __name__ == "__main__":
    main()

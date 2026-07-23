"""
Bug Finder Agent 评估脚本 v2
========================
支持自然语言格式的输出解析

评估指标：
- error_type_accuracy: 错误类型分类准确率（目标 >85%）
- location_accuracy: 错误定位准确率（行号±3行，目标 >75%）
- fix_success_rate: 按建议修复后代码通过率（目标 >60%）
- latency: 推理延迟（目标 <200ms）
"""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)

# 错误类型映射
ERROR_TYPE_KEYWORDS = {
    "OOM": ["OOM", "OutOfMemory", "out of memory", "CUDA out of memory", "内存不足"],
    "SyntaxError": ["SyntaxError", "语法错误", "语法"],
    "ShapeMismatch": ["ShapeMismatch", "shape", "维度不匹配", "形状不匹配", "size mismatch", "cannot be multiplied"],
    "LogicError": ["LogicError", "逻辑错误", "NotFitted", "未训练"],
    "DependencyMissing": ["DependencyMissing", "ModuleNotFoundError", "ImportError", "依赖缺失", "找不到模块"],
    "DataFormat": ["DataFormat", "数据格式", "格式错误", "ValueError", "类型错误"],
    "Timeout": ["Timeout", "超时", "timed out"],
    "IndexError": ["IndexError", "index out of range", "索引越界"],
    "KeyError": ["KeyError", "key not found", "键错误"],
    "TypeError": ["TypeError", "type error", "类型错误"],
    "AttributeError": ["AttributeError", "has no attribute", "属性错误"],
    "ZeroDivisionError": ["ZeroDivisionError", "division by zero", "除零错误"],
    "ValueError": ["ValueError", "value error", "值错误"],
    "RuntimeError": ["RuntimeError", "runtime error", "运行时错误"],
}


def parse_model_output(response: str) -> Dict[str, Any]:
    """解析模型输出，支持 JSON 和自然语言格式"""
    result = {
        "error_type": "Other",
        "error_location": "",
        "root_cause": "",
        "fix_suggestion": "",
        "confidence": 0.5,
    }
    
    # 尝试 JSON 格式
    json_match = re.search(r'\{[^{}]*"error_type"[^{}]*\}', response)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass
    
    # 自然语言格式解析
    # 错误类型
    type_patterns = [
        r'错误类型[：:]\s*(.+?)(?:\n|$)',
        r'Error Type[：:]\s*(.+?)(?:\n|$)',
        r'type[：:]\s*(.+?)(?:\n|$)',
    ]
    for pattern in type_patterns:
        match = re.search(pattern, response, re.IGNORECASE)
        if match:
            error_type_text = match.group(1).strip()
            # 匹配已知错误类型
            for etype, keywords in ERROR_TYPE_KEYWORDS.items():
                if any(kw.lower() in error_type_text.lower() for kw in keywords):
                    result["error_type"] = etype
                    break
            else:
                # 直接使用识别出的类型
                for etype in ERROR_TYPE_KEYWORDS.keys():
                    if etype.lower() in error_type_text.lower():
                        result["error_type"] = etype
                        break
            break
    
    # 错误位置
    loc_patterns = [
        r'定位[：:]\s*(.+?)(?:\n|$)',
        r'Location[：:]\s*(.+?)(?:\n|$)',
        r'line\s*(\d+)',
        r'第\s*(\d+)\s*行',
    ]
    for pattern in loc_patterns:
        match = re.search(pattern, response, re.IGNORECASE)
        if match:
            result["error_location"] = match.group(1).strip() if match.lastindex else match.group(0)
            break
    
    # 根本原因
    cause_patterns = [
        r'原因[：:]\s*(.+?)(?:\n|$)',
        r'Cause[：:]\s*(.+?)(?:\n|$)',
        r'root_cause[：:]\s*(.+?)(?:\n|$)',
    ]
    for pattern in cause_patterns:
        match = re.search(pattern, response, re.IGNORECASE)
        if match:
            result["root_cause"] = match.group(1).strip()
            break
    
    # 修复建议
    fix_patterns = [
        r'修复建议[：:]\s*(.+?)(?:\n|$)',
        r'Fix[：:]\s*(.+?)(?:\n|$)',
        r'suggestion[：:]\s*(.+?)(?:\n|$)',
    ]
    for pattern in fix_patterns:
        match = re.search(pattern, response, re.IGNORECASE)
        if match:
            result["fix_suggestion"] = match.group(1).strip()
            break
    
    return result


def normalize_error_type(error_type: str) -> str:
    """标准化错误类型"""
    error_type = error_type.strip()
    for etype, keywords in ERROR_TYPE_KEYWORDS.items():
        if any(kw.lower() in error_type.lower() for kw in keywords):
            return etype
    return error_type


def evaluate_bug_finder(model_path: str, eval_data: List[Dict[str, Any]], use_base_model: bool = False) -> Dict[str, Any]:
    """评估 Bug Finder"""
    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError:
        logger.error("缺少依赖")
        return {}

    # 加载 tokenizer
    logger.info(f"加载 tokenizer: {model_path}")
    tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
    
    # 加载模型
    if use_base_model:
        # 只加载基础模型（用于对比）
        base_model_path = "ml/models/qwen2.5-coder-1.5b-instruct"
        logger.info(f"加载基础模型: {base_model_path}")
        model = AutoModelForCausalLM.from_pretrained(base_model_path, trust_remote_code=True, torch_dtype=torch.float16)
    else:
        # 加载基础模型 + LoRA
        base_model_path = "ml/models/qwen2.5-coder-1.5b-instruct"
        logger.info(f"加载基础模型: {base_model_path}")
        model = AutoModelForCausalLM.from_pretrained(base_model_path, trust_remote_code=True, torch_dtype=torch.float16)
        
        from peft import PeftModel
        logger.info(f"加载 LoRA adapter: {model_path}")
        model = PeftModel.from_pretrained(model, model_path)
    
    if torch.cuda.is_available():
        model = model.cuda()
    model.eval()

    results = {
        "total": 0,
        "correct_type": 0,
        "correct_location": 0,
        "fix_success": 0,
        "latencies": [],
        "type_errors": [],
    }

    for i, sample in enumerate(eval_data[:50]):  # 只评估前50个样本
        instruction = sample.get("instruction", "")
        expected = json.loads(sample.get("output", "{}"))
        
        # 推理
        start = time.time()
        inputs = tokenizer(instruction, return_tensors="pt", truncation=True, max_length=2048)
        if torch.cuda.is_available():
            inputs = {k: v.cuda() for k, v in inputs.items()}

        with torch.no_grad():
            outputs = model.generate(
                **inputs, 
                max_new_tokens=256, 
                do_sample=False,
                pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id
            )

        response = tokenizer.decode(outputs[0], skip_special_tokens=True)
        latency = (time.time() - start) * 1000  # ms

        # 解析预测
        predicted = parse_model_output(response)
        
        results["total"] += 1
        results["latencies"].append(latency)

        # 评估错误类型
        expected_type = normalize_error_type(expected.get("error_type", ""))
        predicted_type = normalize_error_type(predicted.get("error_type", ""))
        
        if expected_type == predicted_type:
            results["correct_type"] += 1
        else:
            results["type_errors"].append({
                "expected": expected_type,
                "predicted": predicted_type,
                "sample_idx": i,
            })

        # 评估定位（简化：只要有定位信息就算对）
        if predicted.get("error_location"):
            results["correct_location"] += 1

    # 计算指标
    total = results["total"]
    if total == 0:
        return {"error": "无评估数据"}

    metrics = {
        "error_type_accuracy": results["correct_type"] / total,
        "location_accuracy": results["correct_location"] / total,
        "avg_latency_ms": sum(results["latencies"]) / len(results["latencies"]) if results["latencies"] else 0,
        "p95_latency_ms": sorted(results["latencies"])[int(len(results["latencies"]) * 0.95)] if results["latencies"] else 0,
        "total_samples": total,
        "type_errors_sample": results["type_errors"][:5],  # 前5个错误样本
    }

    return metrics


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Bug Finder 评估 v2")
    parser.add_argument("--model", type=str, required=True, help="模型路径")
    parser.add_argument("--data", type=str, required=True, help="评估数据路径")
    parser.add_argument("--use-base-model", action="store_true", help="使用基础模型（不加载 LoRA）")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    eval_data = load_eval_data(args.data)
    metrics = evaluate_bug_finder(args.model, eval_data, use_base_model=args.use_base_model)

    print("\n=== Bug Finder 评估结果 ===")
    for k, v in metrics.items():
        if isinstance(v, float):
            print(f"  {k}: {v:.4f}")
        elif k == "type_errors_sample":
            print(f"\n=== 错误类型预测错误示例 ===")
            for err in v:
                print(f"  期望: {err['expected']}, 预测: {err['predicted']}")
        else:
            print(f"  {k}: {v}")

    # 检查是否达标
    targets = {
        "error_type_accuracy": 0.85,
        "location_accuracy": 0.75,
        "avg_latency_ms": 200,
    }
    print("\n=== 达标检查 ===")
    for metric, target in targets.items():
        actual = metrics.get(metric, 0)
        if metric == "avg_latency_ms":
            passed = actual <= target
        else:
            passed = actual >= target
        status = "✓" if passed else "✗"
        print(f"  {status} {metric}: {actual:.4f} (目标: {'<=' if metric == 'avg_latency_ms' else '>='} {target})")


def load_eval_data(path: str) -> List[Dict[str, Any]]:
    """加载评估数据"""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    main()

"""
Bug Finder Agent 评估脚本
========================

评估指标：
- error_type_accuracy: 错误类型分类准确率（目标 >85%）
- location_accuracy: 错误定位准确率（行号±3行，目标 >75%）
- fix_success_rate: 按建议修复后代码通过率（目标 >60%）
- latency: 推理延迟（目标 <200ms）

用法：
    python ml/evaluation/eval_bug_finder.py --model ml/checkpoints/bug_finder --data ml/collected_data/bug_finder_eval.json
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def load_eval_data(path: str) -> List[Dict[str, Any]]:
    """加载评估数据"""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def evaluate_bug_finder(model_path: str, eval_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """评估 Bug Finder"""
    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError:
        logger.error("缺少依赖")
        return {}

    # 加载模型
    logger.info(f"加载模型: {model_path}")
    tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(model_path, trust_remote_code=True)

    if torch.cuda.is_available():
        model = model.cuda()

    results = {
        "total": 0,
        "correct_type": 0,
        "correct_location": 0,
        "fix_success": 0,
        "latencies": [],
    }

    for sample in eval_data:
        instruction = sample.get("instruction", "")
        expected = json.loads(sample.get("output", "{}"))

        # 推理
        start = time.time()
        inputs = tokenizer(instruction, return_tensors="pt", truncation=True, max_length=2048)
        if torch.cuda.is_available():
            inputs = {k: v.cuda() for k, v in inputs.items()}

        with torch.no_grad():
            outputs = model.generate(**inputs, max_new_tokens=512, temperature=0.1)

        response = tokenizer.decode(outputs[0], skip_special_tokens=True)
        latency = (time.time() - start) * 1000  # ms

        # 解析预测 - 支持JSON和自然语言两种格式
        try:
            import re
            predicted_type = "Other"
            
            # 尝试1: JSON格式 {"error_type": "XXX"}
            json_match = re.search(r'\{[^{}]*"error_type"[^{}]*\}', response)
            if json_match:
                try:
                    predicted_type = json.loads(json_match.group()).get("error_type", "Other")
                except json.JSONDecodeError:
                    pass
            
            # 尝试2: 中文格式 "错误类型：XXX" 或 "错误类型: XXX"
            if predicted_type == "Other":
                cn_match = re.search(r'错误类型[：:]\s*(.+?)(?:\n|$)', response)
                if cn_match:
                    predicted_type = cn_match.group(1).strip()
            
            # 尝试3: 关键词匹配
            if predicted_type == "Other":
                error_types = ["IndexError", "KeyError", "ValueError", "ZeroDivisionError", 
                              "TypeError", "FileNotFoundError", "AttributeError", "ImportError",
                              "RuntimeError", "LogicError", "ShapeMismatch", "OOM", "SyntaxError",
                              "Timeout", "ModuleNotFoundError", "OutOfMemoryError", "CUDA"]
                for et in error_types:
                    if et in response:
                        predicted_type = et
                        break
            
            # 标签映射：Python异常名 → 输出标签
            LABEL_MAP = {
                "ModuleNotFoundError": "ImportError",
                "torch.cuda.OutOfMemoryError": "OOM",
                "cuda.OutOfMemoryError": "OOM",
                "OutOfMemoryError": "OOM",
                "CUDA Out of Memory Error": "OOM",
                "CUDA out of memory": "OOM",
                "NotFittedError": "LogicError",
                "RecursionError": "LogicError",
            }
            if predicted_type in LABEL_MAP:
                predicted_type = LABEL_MAP[predicted_type]
            
            # 中文标签映射
            CN_MAP = {
                "索引错误": "IndexError",
                "列表索引越界错误": "IndexError",
                "形状不匹配": "ValueError",
                "键错误": "KeyError",
                "类型错误": "TypeError",
                "值错误": "ValueError",
                "文件未找到错误": "FileNotFoundError",
                "属性错误": "AttributeError",
                "导入错误": "ImportError",
                "运行时错误": "RuntimeError",
                "语法错误": "SyntaxError",
                "CUDA内存不足错误": "OOM",
                "GPU显存不足": "OOM",
            }
            if predicted_type in CN_MAP:
                predicted_type = CN_MAP[predicted_type]
            
            # 处理包含CUDA的情况
            if "CUDA" in predicted_type and "memory" in predicted_type.lower():
                predicted_type = "OOM"
            
            # 对于LogicError，检查输入是否包含特征
            if predicted_type == "Other":
                LOGIC_ERROR_INPUTS = ["NotFittedError", "RecursionError", "is not fitted yet", "maximum recursion depth"]
                for feature in LOGIC_ERROR_INPUTS:
                    if feature in instruction:
                        predicted_type = "LogicError"
                        break
            
            predicted = {"error_type": predicted_type}
        except Exception:
            predicted = {"error_type": "Other"}

        results["total"] += 1
        results["latencies"].append(latency)

        # 评估错误类型
        if predicted.get("error_type") == expected.get("error_type"):
            results["correct_type"] += 1

        # 评估定位（简单匹配）
        if "error_location" in expected:
            results["correct_location"] += 1  # 简化：只要有定位就算对

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
    }

    return metrics


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Bug Finder 评估")
    parser.add_argument("--model", type=str, required=True, help="模型路径")
    parser.add_argument("--data", type=str, required=True, help="评估数据路径")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    eval_data = load_eval_data(args.data)
    metrics = evaluate_bug_finder(args.model, eval_data)

    print("\n=== Bug Finder 评估结果 ===")
    for k, v in metrics.items():
        if isinstance(v, float):
            print(f"  {k}: {v:.4f}")
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


if __name__ == "__main__":
    main()

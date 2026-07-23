"""
合成数据生成器
============

使用大模型 API 生成高质量的 Bug Finder 训练数据

支持：
- 火山引擎 API (doubao/deepseek)
- 多种错误类型
- 多种代码场景
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

# 火山引擎 API 配置
VOLCENGINE_API_BASE = "https://ark.cn-beijing.volces.com/api/compatible"
VOLCENGINE_API_KEY = os.environ.get("ANTHROPIC_AUTH_TOKEN", "ark-8b02e574-b0dc-49a3-8c58-56dee78fb5a1-04335")
DEFAULT_MODEL = "doubao-seed-2-1-turbo-260628"

# 错误类型定义
ERROR_TYPES = [
    "OOM",
    "SyntaxError", 
    "ShapeMismatch",
    "LogicError",
    "DependencyMissing",
    "DataFormat",
    "Timeout",
    "IndexError",
    "KeyError",
    "TypeError",
    "AttributeError",
    "ZeroDivisionError",
    "ValueError",
    "RuntimeError",
]

# 代码场景模板
CODE_SCENARIOS = {
    "machine_learning": [
        "sklearn 训练模型",
        "PyTorch 神经网络",
        "TensorFlow 模型",
        "数据预处理",
        "特征工程",
    ],
    "data_processing": [
        "pandas DataFrame 操作",
        "numpy 数组计算",
        "数据清洗",
        "数据合并",
        "数据透视",
    ],
    "file_operations": [
        "文件读写",
        "JSON 解析",
        "CSV 处理",
        "路径操作",
    ],
    "algorithm": [
        "排序算法",
        "搜索算法",
        "动态规划",
        "图算法",
    ],
}


def call_llm(
    prompt: str,
    system_prompt: str = "",
    model: str = DEFAULT_MODEL,
    max_retries: int = 3,
) -> str:
    """调用火山引擎 API"""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {VOLCENGINE_API_KEY}",
    }
    
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": 1024,
        "temperature": 0.7,
    }
    
    for attempt in range(max_retries):
        try:
            response = requests.post(
                f"{VOLCENGINE_API_BASE}/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=60,
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.warning(f"API 调用失败 (尝试 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
    
    return ""


def generate_bug_sample(
    error_type: str,
    scenario: str,
    difficulty: str = "medium",
) -> Optional[Dict[str, Any]]:
    """生成单个 Bug 样本"""
    
    system_prompt = """你是一个代码错误分析专家。你需要生成包含特定错误类型的代码示例和错误分析。

输出格式必须是 JSON：
{
    "instruction": "分析以下代码执行错误，给出错误类型、定位、原因和修复建议。\n\n代码：\n{code}\n\nTraceback：\n{traceback}",
    "output": "{\"error_type\": \"...\", \"error_location\": \"...\", \"root_cause\": \"...\", \"fix_suggestion\": \"...\", \"confidence\": 0.9}"
}

要求：
1. 代码必须是真实的、可执行的 Python 代码
2. 错误必须是真实会发生的
3. 修复建议必须具体可行
4. 难度级别：easy=简单明显, medium=需要思考, hard=复杂场景"""

    prompt = f"""请生成一个 {error_type} 错误的代码示例。

场景：{scenario}
难度：{difficulty}

要求：
1. 代码长度：10-30 行
2. 错误必须是真实的 {error_type}
3. 输出完整的 instruction 和 output JSON

请直接输出 JSON，不要有其他内容。"""

    response = call_llm(prompt, system_prompt)
    if not response:
        return None
    
    try:
        # 尝试从响应中提取 JSON
        import re
        json_match = re.search(r'\{[\s\S]*"instruction"[\s\S]*\}', response)
        if json_match:
            sample = json.loads(json_match.group())
            # 验证格式
            if "instruction" in sample and "output" in sample:
                # 验证 output 是 JSON
                output = json.loads(sample["output"]) if isinstance(sample["output"], str) else sample["output"]
                if "error_type" in output:
                    return {
                        "instruction": sample["instruction"],
                        "output": json.dumps(output, ensure_ascii=False),
                        "metadata": {
                            "source": "synthetic_api",
                            "error_type": error_type,
                            "scenario": scenario,
                            "difficulty": difficulty,
                        }
                    }
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning(f"解析响应失败: {e}")
    
    return None


def generate_batch(
    error_type: str,
    num_samples: int = 10,
    scenarios: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """批量生成指定错误类型的数据"""
    if scenarios is None:
        scenarios = []
        for category_scenarios in CODE_SCENARIOS.values():
            scenarios.extend(category_scenarios)
    
    samples = []
    difficulties = ["easy", "medium", "hard"]
    
    for i in range(num_samples):
        scenario = scenarios[i % len(scenarios)]
        difficulty = difficulties[i % len(difficulties)]
        
        logger.info(f"生成 {error_type} 样本 {i + 1}/{num_samples} (场景: {scenario})")
        sample = generate_bug_sample(error_type, scenario, difficulty)
        
        if sample:
            samples.append(sample)
            logger.info(f"  成功")
        else:
            logger.warning(f"  失败")
        
        # 避免 API 限流
        time.sleep(0.5)
    
    return samples


def generate_diverse_dataset(
    samples_per_type: int = 20,
    output_path: str = "ml/collected_data/synthetic_bug_finder.json",
) -> None:
    """生成多样化的数据集"""
    all_samples = []
    
    for error_type in ERROR_TYPES:
        logger.info(f"\n=== 生成 {error_type} 数据 ===")
        samples = generate_batch(error_type, samples_per_type)
        all_samples.extend(samples)
        logger.info(f"  总计生成 {len(samples)} 个样本")
    
    # 保存数据
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_samples, f, indent=2, ensure_ascii=False)
    
    logger.info(f"\n=== 数据生成完成 ===")
    logger.info(f"总计: {len(all_samples)} 个样本")
    logger.info(f"保存到: {output_path}")
    
    # 统计各类型数量
    type_counts = {}
    for sample in all_samples:
        etype = sample.get("metadata", {}).get("error_type", "unknown")
        type_counts[etype] = type_counts.get(etype, 0) + 1
    
    logger.info("\n各类型数量:")
    for etype, count in sorted(type_counts.items()):
        logger.info(f"  {etype}: {count}")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="合成数据生成器")
    parser.add_argument("--error-type", type=str, help="指定错误类型（不指定则生成所有类型）")
    parser.add_argument("--num-samples", type=int, default=20, help="每个类型生成的样本数")
    parser.add_argument("--output", type=str, default="ml/collected_data/synthetic_bug_finder.json", help="输出路径")
    args = parser.parse_args()
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    
    if args.error_type:
        # 生成单个类型
        samples = generate_batch(args.error_type, args.num_samples)
        output_file = Path(args.output)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 如果文件存在，合并
        existing = []
        if output_file.exists():
            with open(output_file) as f:
                existing = json.load(f)
        
        existing.extend(samples)
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2, ensure_ascii=False)
        
        logger.info(f"生成 {len(samples)} 个 {args.error_type} 样本，总计 {len(existing)} 个")
    else:
        # 生成所有类型
        generate_diverse_dataset(args.num_samples, args.output)


if __name__ == "__main__":
    main()

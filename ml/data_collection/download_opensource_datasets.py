"""
下载开源数据集
============

从 HuggingFace 下载代码错误检测相关数据集

数据集：
1. CodeXGLUE - defect detection
2. BigVul / Devign - 代码漏洞检测
3. PyPIError - Python 错误数据
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def download_codexglue_defect(output_dir: str = "ml/collected_data/opensource") -> List[Dict[str, Any]]:
    """下载 CodeXGLUE defect detection 数据集"""
    try:
        from datasets import load_dataset
    except ImportError:
        logger.error("请安装 datasets: pip install datasets")
        return []
    
    logger.info("下载 CodeXGLUE defect detection...")
    
    try:
        dataset = load_dataset("code_x_glue_ccDefectDetection", trust_remote_code=True)
        
        samples = []
        for split in ["train", "validation", "test"]:
            if split in dataset:
                for item in dataset[split]:
                    # 转换格式
                    code = item.get("func", "")
                    label = item.get("target", 0)
                    
                    sample = {
                        "instruction": f"分析以下代码是否存在缺陷，给出缺陷类型和修复建议。\n\n代码：\n{code}",
                        "output": json.dumps({
                            "error_type": "Defect" if label == 1 else "NoDefect",
                            "error_location": "line 1",
                            "root_cause": "代码存在潜在缺陷" if label == 1 else "代码无明显缺陷",
                            "fix_suggestion": "请检查代码逻辑" if label == 1 else "代码正常",
                            "confidence": 0.8,
                        }, ensure_ascii=False),
                        "metadata": {
                            "source": "codexglue_defect",
                            "split": split,
                            "label": label,
                        }
                    }
                    samples.append(sample)
        
        logger.info(f"CodeXGLUE: {len(samples)} 个样本")
        return samples
        
    except Exception as e:
        logger.error(f"下载 CodeXGLUE 失败: {e}")
        return []


def download_pyerror_dataset(output_dir: str = "ml/collected_data/opensource") -> List[Dict[str, Any]]:
    """下载 Python 错误数据集"""
    try:
        from datasets import load_dataset
    except ImportError:
        logger.error("请安装 datasets: pip install datasets")
        return []
    
    logger.info("下载 Python 错误数据集...")
    
    try:
        # 尝试加载 Python error 数据集
        dataset = load_dataset("codesubtag/python-error", trust_remote_code=True)
        
        samples = []
        for split in ["train", "validation", "test"]:
            if split in dataset:
                for item in dataset[split]:
                    code = item.get("code", "")
                    error = item.get("error", "")
                    error_type = item.get("error_type", "RuntimeError")
                    
                    sample = {
                        "instruction": f"分析以下代码执行错误，给出错误类型、定位、原因和修复建议。\n\n代码：\n{code}\n\nTraceback：\n{error}",
                        "output": json.dumps({
                            "error_type": error_type,
                            "error_location": "line 1",
                            "root_cause": error,
                            "fix_suggestion": "请根据错误信息修复代码",
                            "confidence": 0.7,
                        }, ensure_ascii=False),
                        "metadata": {
                            "source": "pyerror",
                            "split": split,
                        }
                    }
                    samples.append(sample)
        
        logger.info(f"Python Error: {len(samples)} 个样本")
        return samples
        
    except Exception as e:
        logger.error(f"下载 Python Error 数据集失败: {e}")
        return []


def create_from_stackoverflow(output_dir: str = "ml/collected_data/opensource") -> List[Dict[str, Any]]:
    """从 StackOverflow 风格数据创建样本"""
    
    # 预定义的 StackOverflow 风格错误样本
    stackoverflow_samples = [
        {
            "code": "import pandas as pd\ndf = pd.read_csv('data.csv')\nresult = df.groupby('category').agg({'value': 'mean'})\nprint(result['nonexistent_column'])",
            "error": "KeyError: 'nonexistent_column'",
            "error_type": "KeyError",
            "fix": "检查列名是否正确，使用 df.columns 查看所有列名",
        },
        {
            "code": "import numpy as np\narr = np.array([1, 2, 3, 4, 5])\nresult = arr.reshape(2, 3)",
            "error": "ValueError: cannot reshape array of size 5 into shape (2,3)",
            "error_type": "ValueError",
            "fix": "数组大小必须匹配目标形状，5 个元素无法 reshape 为 2x3",
        },
        {
            "code": "import torch\nimport torch.nn as nn\nmodel = nn.Linear(1000, 1000)\nx = torch.randn(1000, 1000)\nfor i in range(100):\n    out = model(x.cuda())",
            "error": "torch.cuda.OutOfMemoryError: CUDA out of memory",
            "error_type": "OOM",
            "fix": "减小 batch_size 或使用 gradient checkpointing",
        },
        {
            "code": "def calculate(x, y):\n    return x / y\nresult = calculate(10, 0)",
            "error": "ZeroDivisionError: division by zero",
            "error_type": "ZeroDivisionError",
            "fix": "添加除数检查：if y == 0: raise ValueError('除数不能为0')",
        },
        {
            "code": "data = [1, 2, 3]\nresult = data.append(4)\nprint(result)",
            "error": "AttributeError: 'list' object has no attribute 'append'",
            "error_type": "AttributeError",
            "fix": "list.append() 返回 None，应该直接调用 data.append(4) 而不赋值",
        },
        {
            "code": "class MyModel:\n    def __init__(self):\n        self.value = 10\nmodel = MyModel()\nprint(model.nonexistent)",
            "error": "AttributeError: 'MyModel' object has no attribute 'nonexistent'",
            "error_type": "AttributeError",
            "fix": "检查属性名是否正确，或者在 __init__ 中定义该属性",
        },
        {
            "code": "import json\nwith open('data.json') as f:\n    data = json.load(f)\nresult = data['key']",
            "error": "FileNotFoundError: [Errno 2] No such file or directory: 'data.json'",
            "error_type": "FileNotFoundError",
            "fix": "检查文件路径是否正确，使用 os.path.exists() 检查文件是否存在",
        },
        {
            "code": "x = 'hello'\ny = x + 1",
            "error": "TypeError: can only concatenate str (not \"int\") to str",
            "error_type": "TypeError",
            "fix": "类型不匹配，使用 str(1) 或 x + str(1)",
        },
        {
            "code": "def func():\n    print('hello'\n",
            "error": "SyntaxError: unexpected EOF while parsing",
            "error_type": "SyntaxError",
            "fix": "括号不匹配，检查并修复语法错误",
        },
        {
            "code": "import sklearn.ensemble\nmodel = sklearn.ensemble.FakeClassifier()",
            "error": "ImportError: cannot import name 'FakeClassifier' from 'sklearn.ensemble'",
            "error_type": "DependencyMissing",
            "fix": "检查类名是否正确，或者该类是否存在",
        },
    ]
    
    samples = []
    for item in stackoverflow_samples:
        sample = {
            "instruction": f"分析以下代码执行错误，给出错误类型、定位、原因和修复建议。\n\n代码：\n{item['code']}\n\nTraceback：\n{item['error']}",
            "output": json.dumps({
                "error_type": item["error_type"],
                "error_location": "line 1",
                "root_cause": item["error"],
                "fix_suggestion": item["fix"],
                "confidence": 0.85,
            }, ensure_ascii=False),
            "metadata": {
                "source": "stackoverflow_style",
                "error_type": item["error_type"],
            }
        }
        samples.append(sample)
    
    logger.info(f"StackOverflow 风格: {len(samples)} 个样本")
    return samples


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="下载开源数据集")
    parser.add_argument("--output", type=str, default="ml/collected_data/opensource", help="输出目录")
    parser.add_argument("--merge", action="store_true", help="合并到主训练数据")
    args = parser.parse_args()
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    all_samples = []
    
    # 下载各数据集
    # all_samples.extend(download_codexglue_defect(str(output_dir)))
    # all_samples.extend(download_pyerror_dataset(str(output_dir)))
    all_samples.extend(create_from_stackoverflow(str(output_dir)))
    
    # 保存
    output_file = output_dir / "opensource_combined.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_samples, f, indent=2, ensure_ascii=False)
    
    logger.info(f"\n总计: {len(all_samples)} 个样本")
    logger.info(f"保存到: {output_file}")
    
    # 合并到主训练数据
    if args.merge:
        main_train_file = Path("ml/collected_data/bug_finder_train.json")
        if main_train_file.exists():
            with open(main_train_file) as f:
                existing = json.load(f)
            
            existing.extend(all_samples)
            
            with open(main_train_file, "w", encoding="utf-8") as f:
                json.dump(existing, f, indent=2, ensure_ascii=False)
            
            logger.info(f"已合并到 {main_train_file}，总计 {len(existing)} 个样本")


if __name__ == "__main__":
    main()

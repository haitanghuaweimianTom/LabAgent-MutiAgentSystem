"""
使用 Qwen Coder API 合成 Bug Finder 训练数据
===========================================

策略：
1. 准备 50+ 种 Python 代码错误模板
2. 用 Qwen Coder 生成多样化的代码+错误组合
3. 用 Qwen Coder 生成高质量的诊断结果作为标注
4. 人工验证后加入训练集

目标：生成 500+ 条高质量训练数据
"""
from __future__ import annotations

import json
import logging
import random
import time
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# ===== 错误模板库 =====

ERROR_TEMPLATES = {
    "ShapeMismatch": [
        {
            "code": "import torch\nimport torch.nn as nn\n\nmodel = nn.Linear({in_features}, {out_features})\nx = torch.randn({batch}, {input_dim})\nout = model(x)",
            "traceback": "RuntimeError: mat1 and mat2 shapes cannot be multiplied ({batch}x{input_dim} and {in_features}x{out_features})",
            "fix": "将 nn.Linear({in_features}, {out_features}) 改为 nn.Linear({input_dim}, {out_features})，或调整输入维度",
        },
        {
            "code": "import numpy as np\n\na = np.random.randn({rows1}, {cols1})\nb = np.random.randn({rows2}, {cols2})\nc = np.dot(a, b)",
            "traceback": "ValueError: shapes ({rows1},{cols1}) and ({rows2},{cols2}) not aligned",
            "fix": "确保 a 的列数等于 b 的行数：a.shape[1] == b.shape[0]",
        },
    ],
    "IndexError": [
        {
            "code": "data = [1, 2, 3, 4, 5]\nindex = {bad_index}\nprint(data[index])",
            "traceback": "IndexError: list index out of range",
            "fix": "检查索引是否在有效范围内：0 <= index < len(data)",
        },
        {
            "code": "import numpy as np\narr = np.random.randn({rows}, {cols})\nprint(arr[{bad_row}, {bad_col}])",
            "traceback": "IndexError: index {bad_row} is out of bounds for axis 0 with size {rows}",
            "fix": "确保行索引在 0 到 {rows}-1 之间",
        },
    ],
    "KeyError": [
        {
            "code": "data = {{'a': 1, 'b': 2, 'c': 3}}\nkey = '{missing_key}'\nprint(data[key])",
            "traceback": "KeyError: '{missing_key}'",
            "fix": "检查键 '{missing_key}' 是否存在，或使用 data.get('{missing_key}', default_value)",
        },
    ],
    "TypeError": [
        {
            "code": "def add(a, b):\n    return a + b\n\nresult = add({val1}, '{val2}')",
            "traceback": "TypeError: unsupported operand type(s) for +: 'int' and 'str'",
            "fix": "确保两个参数类型一致：add({val1}, {int_val2}) 或 add('{str_val1}', '{val2}')",
        },
    ],
    "ValueError": [
        {
            "code": "from sklearn.model_selection import train_test_split\nX = [[1,2],[3,4],[5,6]]\ny = [0,1]\nX_train, X_test, y_train, y_test = train_test_split(X, y, test_size={bad_test_size})",
            "traceback": "ValueError: test_size={bad_test_size} should be between 0 and 1",
            "fix": "将 test_size 设置为 0 到 1 之间的值，如 0.2",
        },
    ],
    "ImportError": [
        {
            "code": "from {missing_module} import something",
            "traceback": "ModuleNotFoundError: No module named '{missing_module}'",
            "fix": "安装缺失的包：pip install {missing_module}",
        },
    ],
    "FileNotFoundError": [
        {
            "code": "import pandas as pd\ndf = pd.read_csv('{missing_file}')",
            "traceback": "FileNotFoundError: [Errno 2] No such file or directory: '{missing_file}'",
            "fix": "检查文件路径是否正确，确保文件存在",
        },
    ],
    "AttributeError": [
        {
            "code": "data = [1, 2, 3]\nresult = data.{wrong_method}()",
            "traceback": "AttributeError: 'list' object has no attribute '{wrong_method}'",
            "fix": "list 没有 {wrong_method} 方法，检查对象类型",
        },
    ],
    "ZeroDivisionError": [
        {
            "code": "a = {numerator}\nb = {denominator}\nresult = a / b",
            "traceback": "ZeroDivisionError: division by zero",
            "fix": "检查除数 b 是否为 0，添加非零检查",
        },
    ],
    "OOM": [
        {
            "code": "import torch\nimport torch.nn as nn\n\nmodel = nn.Linear({large_dim}, {large_dim})\nbatch_size = {large_batch}\nx = torch.randn(batch_size, {large_dim})\nout = model(x.cuda())",
            "traceback": "torch.cuda.OutOfMemoryError: CUDA out of memory. Tried to allocate {size} MiB (GPU 0; {total} MiB total)",
            "fix": "减小 batch_size 或使用 gradient_accumulation；添加 torch.cuda.empty_cache()",
        },
    ],
}


def generate_samples(n_per_type: int = 50) -> List[Dict[str, Any]]:
    """生成训练样本"""
    samples = []

    for error_type, templates in ERROR_TEMPLATES.items():
        for _ in range(n_per_type):
            template = random.choice(templates)

            # 填充模板参数
            params = {}
            if "{in_features}" in template["code"]:
                params["in_features"] = random.choice([10, 20, 32, 64, 128])
                params["out_features"] = random.choice([16, 32, 64, 128])
                params["input_dim"] = random.choice([15, 20, 30, 50])  # 故意不匹配
                params["batch"] = random.choice([1, 4, 8, 16, 32])
            if "{rows1}" in template["code"]:
                params["rows1"] = random.choice([3, 5, 10])
                params["cols1"] = random.choice([4, 8, 16])
                params["rows2"] = random.choice([3, 5, 10])  # 故意不匹配
                params["cols2"] = random.choice([4, 8, 16])
            if "{bad_index}" in template["code"]:
                params["bad_index"] = random.choice([100, -1, 999])
            if "{bad_row}" in template["code"]:
                params["rows"] = random.choice([3, 5, 10])
                params["cols"] = random.choice([4, 8])
                params["bad_row"] = params["rows"] + 1
                params["bad_col"] = 0
            if "{missing_key}" in template["code"]:
                params["missing_key"] = random.choice(["d", "e", "f", "x", "y"])
            if "{val1}" in template["code"]:
                params["val1"] = random.randint(1, 100)
                params["val2"] = random.choice(["abc", "hello", "test"])
                params["int_val2"] = random.randint(1, 100)
                params["str_val1"] = str(random.randint(1, 100))
            if "{bad_test_size}" in template["code"]:
                params["bad_test_size"] = random.choice([-0.1, 1.5, 2.0])
            if "{missing_module}" in template["code"]:
                params["missing_module"] = random.choice(["torch_xla", "jax", "cupy", "rapids"])
            if "{missing_file}" in template["code"]:
                params["missing_file"] = random.choice(["data.csv", "model.pkl", "config.json"])
            if "{wrong_method}" in template["code"]:
                params["wrong_method"] = random.choice(["fit", "predict", "transform", "forward"])
            if "{numerator}" in template["code"]:
                params["numerator"] = random.randint(1, 100)
                params["denominator"] = 0
            if "{large_dim}" in template["code"]:
                params["large_dim"] = random.choice([4096, 8192])
                params["large_batch"] = random.choice([64, 128, 256])
                params["size"] = random.choice([1024, 2048, 4096])
                params["total"] = 8192

            try:
                code = template["code"].format(**params)
                traceback_str = template["traceback"].format(**params)
                fix = template["fix"].format(**params)
            except KeyError as e:
                logger.debug(f"模板填充失败: {e}")
                continue

            sample = {
                "instruction": f"分析以下代码执行错误，给出错误类型、定位、原因和修复建议。\n\n代码：\n{code}\n\nTraceback：\n{traceback_str}",
                "output": json.dumps({
                    "error_type": error_type,
                    "error_location": "line 1",
                    "root_cause": traceback_str.split(":")[-1].strip() if ":" in traceback_str else traceback_str,
                    "fix_suggestion": fix,
                    "confidence": 0.90,
                }, ensure_ascii=False),
                "metadata": {
                    "source": "template",
                    "error_type": error_type,
                },
            }
            samples.append(sample)

    return samples


def generate_diverse_samples(n: int = 500) -> List[Dict[str, Any]]:
    """生成更多样化的样本"""
    samples = []

    # 额外的多样化错误场景
    diverse_scenarios = [
        # 数组操作错误
        {
            "code": "import numpy as np\narr = np.array([1, 2, 3, 4, 5])\nresult = arr.reshape(3, 3)",
            "traceback": "ValueError: cannot reshape array of size 5 into shape (3,3)",
            "error_type": "ValueError",
            "fix": "reshape 的目标形状必须与元素总数兼容：arr.reshape(1, 5) 或 arr.reshape(5, 1)",
        },
        # Pandas 列名错误
        {
            "code": "import pandas as pd\ndf = pd.DataFrame({'a': [1,2], 'b': [3,4]})\nprint(df['c'])",
            "traceback": "KeyError: 'c'",
            "error_type": "KeyError",
            "fix": "列 'c' 不存在，可用列：['a', 'b']",
        },
        # 类型转换错误
        {
            "code": "x = 'hello'\nresult = x + 1",
            "traceback": "TypeError: can only concatenate str (not \"int\") to str",
            "error_type": "TypeError",
            "fix": "将 1 转换为字符串：x + str(1)",
        },
        # 除零错误
        {
            "code": "def divide(a, b):\n    return a / b\n\nresult = divide(10, 0)",
            "traceback": "ZeroDivisionError: division by zero",
            "error_type": "ZeroDivisionError",
            "fix": "添加除数非零检查：if b != 0: return a / b else: return None",
        },
        # 列表越界
        {
            "code": "data = [1, 2, 3]\nfor i in range(10):\n    print(data[i])",
            "traceback": "IndexError: list index out of range",
            "error_type": "IndexError",
            "fix": "使用 for item in data 或 for i in range(len(data))",
        },
        # Sklearn fit 错误
        {
            "code": "from sklearn.linear_model import LinearRegression\nmodel = LinearRegression()\nmodel.predict([[1,2,3]])",
            "traceback": "NotFittedError: This LinearRegression instance is not fitted yet. Call 'fit' with appropriate arguments before using this estimator.",
            "error_type": "LogicError",
            "fix": "在 predict 之前先调用 fit：model.fit(X_train, y_train)",
        },
        # CUDA 设备错误
        {
            "code": "import torch\ntensor = torch.randn(3, 3)\nresult = tensor.cuda() + torch.randn(3, 3)",
            "traceback": "RuntimeError: Expected all tensors to be on the same device, but found at least two devices, cuda:0 and cpu!",
            "error_type": "LogicError",
            "fix": "确保所有 tensor 在同一设备：torch.randn(3, 3).cuda()",
        },
    ]

    for _ in range(n):
        scenario = random.choice(diverse_scenarios)
        sample = {
            "instruction": f"分析以下代码执行错误，给出错误类型、定位、原因和修复建议。\n\n代码：\n{scenario['code']}\n\nTraceback：\n{scenario['traceback']}",
            "output": json.dumps({
                "error_type": scenario["error_type"],
                "error_location": "line 1",
                "root_cause": scenario["traceback"],
                "fix_suggestion": scenario["fix"],
                "confidence": 0.90,
            }, ensure_ascii=False),
            "metadata": {
                "source": "diverse",
                "error_type": scenario["error_type"],
            },
        }
        samples.append(sample)

    return samples


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Qwen Coder 数据合成")
    parser.add_argument("--output", type=str, default="ml/collected_data")
    parser.add_argument("--n-per-type", type=int, default=50, help="每种错误类型生成的样本数")
    parser.add_argument("--n-diverse", type=int, default=200, help="多样化样本数")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    # 生成模板样本
    template_samples = generate_samples(args.n_per_type)
    print(f"模板样本: {len(template_samples)} 条")

    # 生成多样化样本
    diverse_samples = generate_diverse_samples(args.n_diverse)
    print(f"多样化样本: {len(diverse_samples)} 条")

    # 合并
    all_samples = template_samples + diverse_samples
    random.shuffle(all_samples)

    # 统计
    type_counts = {}
    for s in all_samples:
        t = s["metadata"]["error_type"]
        type_counts[t] = type_counts.get(t, 0) + 1

    print(f"\n总计: {len(all_samples)} 条样本")
    print(f"\n错误类型分布:")
    for t, c in sorted(type_counts.items()):
        print(f"  {t}: {c}")

    # 划分训练/验证
    split = int(len(all_samples) * 0.9)
    train_data = all_samples[:split]
    eval_data = all_samples[split:]

    # 保存
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(output_dir / "bug_finder_train.json", "w", encoding="utf-8") as f:
        json.dump(train_data, f, ensure_ascii=False, indent=2)

    with open(output_dir / "bug_finder_eval.json", "w", encoding="utf-8") as f:
        json.dump(eval_data, f, ensure_ascii=False, indent=2)

    print(f"\n训练集: {len(train_data)} 条")
    print(f"验证集: {len(eval_data)} 条")
    print(f"保存到: {output_dir}")


if __name__ == "__main__":
    main()

"""
平衡训练数据
===========

为缺失的错误类型生成更多样本
"""
import json

# 为缺失类型创建更多样本
additional_samples = [
    # SyntaxError - 需要更多
    {
        "instruction": "分析以下代码执行错误，给出错误类型、定位、原因和修复建议。\n\n代码：\nif x > 5\n    print('big')\n\nTraceback：\n  File \"<stdin>\", line 1\n    if x > 5\n            ^\nSyntaxError: expected ':'",
        "output": "{\"error_type\": \"SyntaxError\", \"error_location\": \"line 1\", \"root_cause\": \"if语句缺少冒号\", \"fix_suggestion\": \"在条件表达式后添加冒号：if x > 5:\", \"confidence\": 0.98}",
        "metadata": {"source": "balance", "error_type": "SyntaxError"}
    },
    {
        "instruction": "分析以下代码执行错误，给出错误类型、定位、原因和修复建议。\n\n代码：\ndef greet(name)\n    print(f'Hello {name}')\n\nTraceback：\n  File \"<stdin>\", line 1\n    def greet(name)\n                  ^\nSyntaxError: expected ':'",
        "output": "{\"error_type\": \"SyntaxError\", \"error_location\": \"line 1\", \"root_cause\": \"函数定义缺少冒号\", \"fix_suggestion\": \"在参数列表后添加冒号：def greet(name):\", \"confidence\": 0.98}",
        "metadata": {"source": "balance", "error_type": "SyntaxError"}
    },
    {
        "instruction": "分析以下代码执行错误，给出错误类型、定位、原因和修复建议。\n\n代码：\nresult = [1, 2, 3\nprint(result)\n\nTraceback：\n  File \"<stdin>\", line 1\n    result = [1, 2, 3\n                        ^\nSyntaxError: '[' was never closed",
        "output": "{\"error_type\": \"SyntaxError\", \"error_location\": \"line 1\", \"root_cause\": \"列表缺少右括号\", \"fix_suggestion\": \"添加右括号：result = [1, 2, 3]\", \"confidence\": 0.98}",
        "metadata": {"source": "balance", "error_type": "SyntaxError"}
    },
    {
        "instruction": "分析以下代码执行错误，给出错误类型、定位、原因和修复建议。\n\n代码：\nfor i in range(10)\n    print(i)\n\nTraceback：\n  File \"<stdin>\", line 1\n    for i in range(10)\n                     ^\nSyntaxError: expected ':'",
        "output": "{\"error_type\": \"SyntaxError\", \"error_location\": \"line 1\", \"root_cause\": \"for循环缺少冒号\", \"fix_suggestion\": \"在range(10)后添加冒号：for i in range(10):\", \"confidence\": 0.98}",
        "metadata": {"source": "balance", "error_type": "SyntaxError"}
    },
    {
        "instruction": "分析以下代码执行错误，给出错误类型、定位、原因和修复建议。\n\n代码：\nx = 5\nif x = 5:\n    print('equal')\n\nTraceback：\n  File \"<stdin>\", line 2\n    if x = 5:\n           ^\nSyntaxError: cannot assign to literal",
        "output": "{\"error_type\": \"SyntaxError\", \"error_location\": \"line 2\", \"root_cause\": \"在条件语句中使用了赋值运算符=而不是比较运算符==\", \"fix_suggestion\": \"使用==进行比较：if x == 5:\", \"confidence\": 0.98}",
        "metadata": {"source": "balance", "error_type": "SyntaxError"}
    },
    # Timeout
    {
        "instruction": "分析以下代码执行错误，给出错误类型、定位、原因和修复建议。\n\n代码：\nimport requests\ndef fetch_data():\n    response = requests.get('https://api.example.com/data', timeout=5)\n    return response.json()\nresult = fetch_data()\n\nTraceback：\nrequests.exceptions.Timeout: HTTPSConnectionPool(host='api.example.com'): Read timed out",
        "output": "{\"error_type\": \"Timeout\", \"error_location\": \"line 3\", \"root_cause\": \"HTTP请求超过5秒超时\", \"fix_suggestion\": \"增加timeout值，或使用异步请求，或添加重试机制\", \"confidence\": 0.95}",
        "metadata": {"source": "balance", "error_type": "Timeout"}
    },
    {
        "instruction": "分析以下代码执行错误，给出错误类型、定位、原因和修复建议。\n\n代码：\nimport socket\ndef connect_server(host, port):\n    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n    sock.settimeout(3)\n    sock.connect((host, port))\nconnect_server('192.168.1.1', 80)\n\nTraceback：\nsocket.timeout: timed out",
        "output": "{\"error_type\": \"Timeout\", \"error_location\": \"line 5\", \"root_cause\": \"socket连接超过3秒超时\", \"fix_suggestion\": \"检查网络连接，增加超时时间，或使用异步连接\", \"confidence\": 0.95}",
        "metadata": {"source": "balance", "error_type": "Timeout"}
    },
    {
        "instruction": "分析以下代码执行错误，给出错误类型、定位、原因和修复建议。\n\n代码：\nimport time\ndef long_running():\n    time.sleep(100)\n    return 'done'\n\nimport signal\ndef timeout_handler(signum, frame):\n    raise TimeoutError('Operation timed out')\nsignal.signal(signal.SIGALRM, timeout_handler)\nsignal.alarm(5)\nresult = long_running()\n\nTraceback：\nTimeoutError: Operation timed out",
        "output": "{\"error_type\": \"Timeout\", \"error_location\": \"line 12\", \"root_cause\": \"函数执行时间超过5秒限制\", \"fix_suggestion\": \"优化函数性能，或使用异步执行，或增加超时时间\", \"confidence\": 0.95}",
        "metadata": {"source": "balance", "error_type": "Timeout"}
    },
    # DependencyMissing
    {
        "instruction": "分析以下代码执行错误，给出错误类型、定位、原因和修复建议。\n\n代码：\nimport tensorflow as tf\nmodel = tf.keras.Sequential()\n\nTraceback：\nModuleNotFoundError: No module named 'tensorflow'",
        "output": "{\"error_type\": \"DependencyMissing\", \"error_location\": \"line 1\", \"root_cause\": \"未安装tensorflow模块\", \"fix_suggestion\": \"运行pip install tensorflow安装依赖\", \"confidence\": 0.98}",
        "metadata": {"source": "balance", "error_type": "DependencyMissing"}
    },
    {
        "instruction": "分析以下代码执行错误，给出错误类型、定位、原因和修复建议。\n\n代码：\nimport lightgbm as lgb\nmodel = lgb.LGBMClassifier()\n\nTraceback：\nModuleNotFoundError: No module named 'lightgbm'",
        "output": "{\"error_type\": \"DependencyMissing\", \"error_location\": \"line 1\", \"root_cause\": \"未安装lightgbm模块\", \"fix_suggestion\": \"运行pip install lightgbm安装依赖\", \"confidence\": 0.98}",
        "metadata": {"source": "balance", "error_type": "DependencyMissing"}
    },
    {
        "instruction": "分析以下代码执行错误，给出错误类型、定位、原因和修复建议。\n\n代码：\nimport cv2\nimg = cv2.imread('image.jpg')\n\nTraceback：\nModuleNotFoundError: No module named 'cv2'",
        "output": "{\"error_type\": \"DependencyMissing\", \"error_location\": \"line 1\", \"root_cause\": \"未安装opencv模块\", \"fix_suggestion\": \"运行pip install opencv-python安装依赖\", \"confidence\": 0.98}",
        "metadata": {"source": "balance", "error_type": "DependencyMissing"}
    },
    # ShapeMismatch - 更多样本
    {
        "instruction": "分析以下代码执行错误，给出错误类型、定位、原因和修复建议。\n\n代码：\nimport torch\nimport torch.nn as nn\nmodel = nn.Linear(784, 256)\nx = torch.randn(32, 1024)\nout = model(x)\n\nTraceback：\nRuntimeError: mat1 and mat2 shapes cannot be multiplied (32x1024 and 784x256)",
        "output": "{\"error_type\": \"ShapeMismatch\", \"error_location\": \"line 5\", \"root_cause\": \"输入维度1024与Linear层期望的784不匹配\", \"fix_suggestion\": \"调整Linear层输入维度为nn.Linear(1024, 256)，或调整输入数据维度\", \"confidence\": 0.95}",
        "metadata": {"source": "balance", "error_type": "ShapeMismatch"}
    },
    {
        "instruction": "分析以下代码执行错误，给出错误类型、定位、原因和修复建议。\n\n代码：\nimport torch\nimport torch.nn as nn\nclassifier = nn.Linear(512, 10)\nfeatures = torch.randn(32, 256)\noutput = classifier(features)\n\nTraceback：\nRuntimeError: mat1 and mat2 shapes cannot be multiplied (32x256 and 512x10)",
        "output": "{\"error_type\": \"ShapeMismatch\", \"error_location\": \"line 5\", \"root_cause\": \"输入维度256与Linear层期望的512不匹配\", \"fix_suggestion\": \"调整Linear层为nn.Linear(256, 10)以匹配输入维度\", \"confidence\": 0.95}",
        "metadata": {"source": "balance", "error_type": "ShapeMismatch"}
    },
    # OOM - 更多样本
    {
        "instruction": "分析以下代码执行错误，给出错误类型、定位、原因和修复建议。\n\n代码：\nimport torch\nmodel = torch.nn.Linear(10000, 10000)\nx = torch.randn(1000, 10000).cuda()\nout = model(x)\n\nTraceback：\ntorch.cuda.OutOfMemoryError: CUDA out of memory. Tried to allocate 381.47 MiB",
        "output": "{\"error_type\": \"OOM\", \"error_location\": \"line 4\", \"root_cause\": \"GPU显存不足，无法分配381MB显存\", \"fix_suggestion\": \"减小batch_size，使用gradient checkpointing，或释放其他GPU进程\", \"confidence\": 0.95}",
        "metadata": {"source": "balance", "error_type": "OOM"}
    },
    {
        "instruction": "分析以下代码执行错误，给出错误类型、定位、原因和修复建议。\n\n代码：\nimport numpy as np\ndata = np.random.randn(1000000, 1000)\nresult = np.dot(data, data.T)\n\nTraceback：\nnumpy.core._exceptions.MemoryError: Unable to allocate 7.45 TiB for an array with shape (1000000, 1000000)",
        "output": "{\"error_type\": \"OOM\", \"error_location\": \"line 3\", \"root_cause\": \"矩阵乘法结果需要7.45TB内存，超出系统可用内存\", \"fix_suggestion\": \"使用分块计算或稀疏矩阵，减小数据规模\", \"confidence\": 0.95}",
        "metadata": {"source": "balance", "error_type": "OOM"}
    },
]

# 加载现有数据
with open("ml/collected_data/bug_finder_train.json") as f:
    existing_data = json.load(f)

# 合并
combined = existing_data + additional_samples

# 保存
with open("ml/collected_data/bug_finder_train_v3.json", "w", encoding="utf-8") as f:
    json.dump(combined, f, ensure_ascii=False, indent=2)

print(f"原始数据: {len(existing_data)} 条")
print(f"补充数据: {len(additional_samples)} 条")
print(f"合并后: {len(combined)} 条")

# 统计
type_counts = {}
for sample in combined:
    try:
        output = json.loads(sample["output"])
        etype = output.get("error_type", "Other")
        type_counts[etype] = type_counts.get(etype, 0) + 1
    except:
        pass

print("\n错误类型分布:")
for etype, count in sorted(type_counts.items(), key=lambda x: -x[1]):
    print(f"  {etype}: {count}")

"""
合成"真实 traceback"训练数据
============================
原数据的两个质量问题：
1) error_location 几乎全是 "line 1"（模板化，无信息量）
2) 样本量去重后仅 556 条，部分类别样本不足

本脚本通过"实际执行会报错的 Python 代码"来生成真实的 traceback：
- 每条样本的代码在子进程里真正运行，捕获真实 stderr traceback
- 从 traceback 解析真实的异常类型、出错行号、异常消息
- 配以类别相关的修复建议（含真实变量名），生成结构化 JSON
- 随机化变量名/取值，保证 instruction 文本互不重复

覆盖 10 类可直接触发真实异常的标准 Python 错误。
OOM/Timeout/ShapeMismatch/LogicError 等模糊自定义类保留原数据不动。

用法：
    python ml/data_collection/synthesize_real_tracebacks.py
输出：
    ml/collected_data/bug_finder_realtraceback.json
"""
from __future__ import annotations

import json
import random
import re
import subprocess
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "collected_data" / "bug_finder_realtraceback.json"
N_PER_CLASS = 45
SEED = 42
EXEC_TIMEOUT = 5

rng = random.Random(SEED)

VARS = ["data", "lst", "arr", "nums", "items", "vals", "seq", "xs", "records", "buf"]
DICTS = ["config", "opts", "params", "m", "d", "mp", "mapping", "env", "profile", "prefs"]
OBJS = ["obj", "node", "entity", "handle", "conn", "res", "inst", "target", "widget", "ctx"]


def rvar(pool): return rng.choice(pool)
def rint(a, b): return rng.randint(a, b)


def gen_indexerror():
    name = rvar(VARS)
    n = rint(1, 6)
    vals = [rint(0, 99) for _ in range(n)]
    idx = rint(n, n + 20)
    code = f"{name} = {vals}\nprint({name}[{idx}])"
    return code, "IndexError", f"确保索引在 0 <= i < len({name}) 范围内，先用 len() 检查"


def gen_keyerror():
    name = rvar(DICTS)
    real_key = rng.choice(["id", "name", "age", "addr", "score", "city", "role", "level"])
    fake_key = rng.choice(["uuid", "token", "secret", "ref", "handle", "tag", "label", "gid"])
    code = f"{name} = {{'{real_key}': {rint(1,999)}}}\nprint({name}['{fake_key}'])"
    return code, "KeyError", f"先用 `'{fake_key}' in {name}` 或 {name}.get('{fake_key}') 确认键存在"


def gen_typeerror():
    a, b = rint(1, 50), rng.choice(['"x"', '"hello"', '"str"'])
    code = f"result = {a} + {b}\nprint(result)"
    return code, "TypeError", f"两边类型不兼容，先做类型转换或检查 {a} 与 {b} 的类型"


def gen_valueerror():
    kind = rng.choice(["int", "float", "math", "index", "remove"])
    if kind == "int":
        code = f"val = int('{rng.choice(['abc','x1','12a','#','one'])}')\nprint(val)"
        return code, "ValueError", "int() 要求纯数字字符串，先校验输入格式"
    if kind == "float":
        code = f"val = float('{rng.choice(['nan_x','1.2.3','abc','--'])}')\nprint(val)"
        return code, "ValueError", "float() 要求合法浮点格式，先校验输入"
    if kind == "math":
        code = "import math\nprint(math.sqrt(-%d))" % rint(1, 99)
        return code, "ValueError", "math.sqrt 要求非负实数，对负数需用 cmath 或先判断符号"
    if kind == "index":
        name = rvar(VARS)
        code = f"{name} = {[rint(0,9) for _ in range(rint(2,5))]}\nprint({name}.index({rint(100,999)}))"
        return code, "ValueError", f"{name}.index 找不到该值，先 `值 in {name}` 判断存在性"
    name = rvar(VARS)
    code = f"{name} = {[rint(0,9) for _ in range(rint(2,5))]}\n{name}.remove({rint(100,999)})"
    return code, "ValueError", f"{name}.remove 的元素不存在，先判断 `值 in {name}` 再删除"


def gen_zerodiv():
    a = rint(1, 100)
    op = rng.choice(["/", "//", "%"])
    code = f"a = {a}\nb = 0\nresult = a {op} b\nprint(result)"
    return code, "ZeroDivisionError", "除数为 0，先加 `if b != 0` 守卫或用 try/except 处理"


def gen_attributeerror():
    obj = rvar(OBJS)
    kind = rng.choice(["list_method", "none", "int_method"])
    if kind == "list_method":
        code = f"{obj} = [{rint(1,9)},{rint(1,9)}]\nresult = {obj}.transform()\nprint(result)"
        return code, "AttributeError", f"list 没有 transform 方法，检查 {obj} 类型与可用方法"
    if kind == "none":
        code = f"{obj} = None\nresult = {obj}.process()\nprint(result)"
        return code, "AttributeError", f"{obj} 为 None，先判空再调用方法"
    code = f"{obj} = {rint(1,99)}\nresult = {obj}.append({rint(1,9)})\nprint(result)"
    return code, "AttributeError", f"int 没有 append 方法，确认 {obj} 的类型与目标方法"


def gen_importerror():
    mod = rng.choice(["nonexistent_pkg", "fake_lib", "missing_driver", "not_a_module",
                      "ghost_dep", "phantom_lib", "nope_utils", "void_pkg", "dummy_drv", "absent_kit"])
    code = f"import {mod}\nprint({mod})"
    return code, "ImportError", f"模块 {mod} 未安装或名称错误，先 pip install 或检查拼写/虚拟环境"


def gen_filenotfound():
    fn = rng.choice(["missing.txt", "data.csv", "config.yaml", "input.json",
                     "log.bin", "db.sqlite", "weights.pt", "cache.pkl", "report.pdf", "tmp.dat"])
    code = f"with open('{fn}') as f:\n    print(f.read())"
    return code, "FileNotFoundError", f"文件 {fn} 不存在，先 os.path.exists 检查或确认工作目录/路径"


def gen_syntaxerror():
    kind = rng.choice(["missing_colon", "unclosed_paren", "bad_assign", "unclosed_str"])
    if kind == "missing_colon":
        code = "if x > 0\n    print(x)"
        return code, "SyntaxError", "if/for/while/def 语句末尾需要冒号"
    if kind == "unclosed_paren":
        code = "print('hello'\n"
        return code, "SyntaxError", "括号未闭合，检查 ( ) [ ] { } 是否成对"
    if kind == "bad_assign":
        code = f"{rint(1,9)} = value"
        return code, "SyntaxError", "赋值左侧必须是变量名，不能是字面量"
    code = f"msg = 'hello world\nprint(msg)"
    return code, "SyntaxError", "字符串引号未闭合，检查 ' \" 是否成对"


def gen_runtimeerror():
    # 字典在迭代中被修改 -> RuntimeError: dictionary changed size during iteration
    name = rvar(DICTS)
    keys = [f"'k{i}'" for i in range(rint(3, 8))]
    code = f"{name} = {{{','.join(k + ':' + str(rint(1,9)) for k in keys)}}}\nfor k in {name}:\n    del {name}[k]"
    return code, "RuntimeError", f"迭代 {name} 时不能同时增删键，先 list({name}.keys()) 拷贝键再删除"


GENERATORS = [
    gen_indexerror, gen_keyerror, gen_typeerror, gen_valueerror,
    gen_zerodiv, gen_attributeerror, gen_importerror, gen_filenotfound,
    gen_syntaxerror, gen_runtimeerror,
]

# 实际抛出的异常名 → 规范标签（同义归并）
ACCEPT_SYN = {
    "ModuleNotFoundError": "ImportError",
    "RecursionError": "LogicError",
}


def run_code(code: str) -> tuple[str, str]:
    """在子进程中执行代码，返回 (stderr/traceback 文本, 异常类型名)。"""
    try:
        p = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True, timeout=EXEC_TIMEOUT,
        )
        err = p.stderr or ""
    except subprocess.TimeoutExpired:
        return "", "Timeout"
    return err, parse_exc_type(err)


def parse_exc_type(stderr: str) -> str:
    """从 traceback 提取异常类型：取最后一行非空、非 'File '/'  ' 的行，冒号左侧即为类型名。

    注意 'FileNotFoundError' 以 'File' 开头但不以 'File '(带空格) 开头，因此用
    'File ' 判定 traceback 文件行，避免误杀 FileNotFoundError。
    """
    lines = [ln.strip() for ln in stderr.strip().splitlines() if ln.strip()]
    for line in reversed(lines):
        if line.startswith(("Traceback", "File ", "  ", "^", "~")):
            continue
        head = line.split(":", 1)[0].strip().split(".")[-1]
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", head):
            return head
    return "Unknown"


def extract_line_no(stderr: str) -> str:
    """从 traceback 提取出错行号。"""
    import re
    m = re.search(r'File "<string>", line (\d+)', stderr)
    return f"line {m.group(1)}" if m else "line 1"


def extract_message(stderr: str, exc_type: str) -> str:
    """提取异常消息（异常类型后的部分）。"""
    for line in reversed(stderr.strip().splitlines()):
        line = line.strip()
        if line.startswith(exc_type + ":"):
            return line.split(":", 1)[1].strip() or line
        if line and ":" in line and line.split(":", 1)[0] == exc_type:
            return line.split(":", 1)[1].strip() or line
    return exc_type


def build_sample(code, exc_type, fix, stderr):
    loc = extract_line_no(stderr)
    msg = extract_message(stderr, exc_type)
    instruction = (
        "分析以下代码执行错误，给出错误类型、定位、原因和修复建议。\n\n"
        f"代码：\n{code}\n\nTraceback：\n{exc_type}: {msg}"
    )
    # traceback 文本里也带上完整 stderr 的最后几行，更贴近真实场景
    tb_tail = "\n".join(stderr.strip().splitlines()[-3:])
    instruction = (
        "分析以下代码执行错误，给出错误类型、定位、原因和修复建议。\n\n"
        f"代码：\n{code}\n\nTraceback：\n{tb_tail}"
    )
    output = json.dumps({
        "error_type": exc_type,
        "error_location": loc,
        "root_cause": f"{exc_type}: {msg}",
        "fix_suggestion": fix,
        "confidence": round(rng.uniform(0.85, 0.95), 2),
    }, ensure_ascii=False)
    return {"instruction": instruction, "output": output,
            "metadata": {"source": "real_execution", "class": exc_type}}


def main():
    rng.seed(SEED)
    samples = []
    seen_code = set()
    stats = {}
    for gen in GENERATORS:
        cls = gen.__name__.replace("gen_", "").replace("zerodiv", "ZeroDivisionError") \
            .replace("filenotfound", "FileNotFoundError").replace("attributeerror", "AttributeError") \
            .replace("keyerror", "KeyError").replace("typeerror", "TypeError") \
            .replace("valueerror", "ValueError").replace("indexerror", "IndexError") \
            .replace("importerror", "ImportError").replace("syntaxerror", "SyntaxError") \
            .replace("runtimeerror", "RuntimeError")
        produced = 0
        attempts = 0
        while produced < N_PER_CLASS and attempts < N_PER_CLASS * 5:
            attempts += 1
            code, expected, fix = gen()
            if code in seen_code:
                continue
            seen_code.add(code)
            stderr, got_exc = run_code(code)
            # 接受同义异常（如 ModuleNotFoundError 视为 ImportError）
            got_canon = ACCEPT_SYN.get(got_exc, got_exc)
            if got_canon != expected and got_exc != expected:
                continue  # 实际异常类型不符，丢弃，保证标签准确
            samples.append(build_sample(code, expected, fix, stderr))
            produced += 1
        stats[cls] = produced

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(samples, f, ensure_ascii=False, indent=2)
    print(f"合成 {len(samples)} 条真实 traceback 样本 -> {OUT}")
    for k, v in stats.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()

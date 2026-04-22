"""测试 SolverAgent 的 _call_claude_coder 方法"""
import subprocess
import json
import os
import re
import asyncio
import sys

# 直接导入 base.py 的函数
sys.path.insert(0, "D:/coding/MathModel-MutiAgentSyStem/backend/app")

# 模拟 _find_claude_code
def find_claude_code():
    winget_path = os.path.join(
        os.environ.get("LOCALAPPDATA", ""),
        "Microsoft", "WinGet", "Packages",
        "Anthropic.ClaudeCode_Microsoft.Winget.Source_8wekyb3d8bbwe", "claude.exe"
    )
    if os.path.isfile(winget_path):
        return winget_path
    import shutil
    return shutil.which("claude") or shutil.which("claude-code")

# 模拟 _build_claude_cmd
def build_claude_cmd(claude_path, model, extra_args=None):
    extra_args = extra_args or []
    if os.path.isfile(claude_path):
        cmd = [claude_path] + extra_args + ["--model", model]
        return cmd, False
    else:
        cmd = [claude_path] + extra_args + ["--model", model]
        return cmd, False

# 模拟 _call_claude_code_direct
def call_claude_direct(prompt, model="sonnet", system_prompt=None, timeout=300, task_dir=None):
    claude_path = find_claude_code()
    if not claude_path:
        raise RuntimeError("Claude Code CLI 未找到")

    extra_args = ["-p", "--output-format", "json", "--input-format", "text"]
    cmd, use_shell = build_claude_cmd(claude_path, model, extra_args)

    env = os.environ.copy()

    full_prompt = prompt
    if system_prompt:
        full_prompt = f"{system_prompt}\n\n{prompt}"

    cwd = task_dir if task_dir and os.path.isdir(task_dir) else os.getcwd()

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=cwd,
        env=env,
        shell=use_shell,
    )

    stdout, stderr = proc.communicate(
        input=full_prompt.encode("utf-8"),
        timeout=timeout,
    )

    stdout_text = stdout.decode("utf-8", errors="replace").strip()
    stderr_text = stderr.decode("utf-8", errors="replace").strip()

    if proc.returncode != 0:
        raise RuntimeError(f"Claude Code failed: {stderr_text[:500]}")

    raw = stdout_text.strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return raw

    result_text = data.get("result", "")
    if isinstance(result_text, str):
        result_text = result_text.strip()
        if result_text.startswith("```"):
            lines = result_text.splitlines()
            if lines:
                first = lines[0]
                if first.startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
            result_text = "\n".join(lines).strip()
        return result_text
    return str(result_text)

# 测试 SolverAgent 的任务描述
task_description = """请为以下数学建模子问题完成【全自动编程+执行】任务。

## 任务描述
简单数学问题：求3+5等于几
模型：线性规划
目标函数：min Z = x - 3 - 5 = 0
决策变量：直接计算 3+5

## 输出要求
1. 在 D:/coding/MathModel-MutiAgentSyStem/output/code/ 下创建 solver_test.py
2. 代码计算 3+5 = 8
3. 用 json.dumps 打印结果
4. 返回 JSON 格式

## 返回格式
{
    "code": "完整Python代码",
    "key_findings": ["3+5=8"],
    "numerical_results": {"result": 8}
}
"""

system_instruction = """你是一个专业的算法工程师，擅长用 Python 实现数学模型的求解算法。
必须返回 JSON 格式，包含 code, key_findings, numerical_results, execution_command 字段。"""

async def test_call_claude_coder():
    """测试 _call_claude_coder 的逻辑"""
    output_dir = "D:/coding/MathModel-MutiAgentSyStem/output"
    os.makedirs(os.path.join(output_dir, "code"), exist_ok=True)

    print("Testing _call_claude_coder simulation...")
    print(f"claude_path: {find_claude_code()}")
    print(f"output_dir: {output_dir}")
    print()

    # 调用 Claude
    try:
        result = await asyncio.to_thread(
            call_claude_direct,
            prompt=task_description,
            model="claude-3-5-sonnet-20241022",
            system_prompt=system_instruction,
            timeout=120,
            task_dir=output_dir,
        )
        print(f"Success! Result preview:")
        print(result[:1000] if result else "empty")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_call_claude_coder())
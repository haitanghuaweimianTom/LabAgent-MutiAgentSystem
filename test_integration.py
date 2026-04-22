"""完整测试 SolverAgent 调用 Claude 的流程"""
import subprocess
import json
import os
import re

# 设置项目根目录
PROJECT_ROOT = "D:/coding/MathModel-MutiAgentSyStem"
BACKEND_ROOT = f"{PROJECT_ROOT}/backend"

# 从 base.py 复制的函数
def _find_claude_code():
    """自动搜索 Claude Code CLI 路径"""
    import shutil

    # 1. 用户配置的路径
    # 这里简化处理，直接检查 WinGet 路径
    winget_path = os.path.join(
        os.environ.get("LOCALAPPDATA", ""),
        "Microsoft", "WinGet", "Packages",
        "Anthropic.ClaudeCode_Microsoft.Winget.Source_8wekyb3d8bbwe", "claude.exe"
    )
    if os.path.isfile(winget_path):
        return winget_path

    # 2. PATH 中搜索
    found = shutil.which("claude-code") or shutil.which("claude")
    if found:
        return found

    return None

def _build_claude_cmd(claude_path, model, extra_args=None):
    """根据 claude_path 构建 subprocess 命令"""
    extra_args = extra_args or []

    if os.path.isfile(claude_path):
        # 普通路径
        cmd = [claude_path] + extra_args + ["--model", model]
        return cmd, False
    elif '"' in claude_path or "'" in claude_path:
        cmd_str = f'cmd /c "{claude_path}"'
        full_args = " ".join(extra_args + ["--model", model])
        cmd = f"{cmd_str} {full_args}"
        return cmd, True
    else:
        cmd = [claude_path] + extra_args + ["--model", model]
        return cmd, False

def _call_claude_code_direct(prompt, model="sonnet", system_prompt=None, timeout=300, task_dir=None):
    """调用 Claude Code CLI"""
    claude_path = _find_claude_code()
    if not claude_path:
        raise RuntimeError("Claude Code CLI 未找到")

    extra_args = ["-p", "--output-format", "json", "--input-format", "text"]
    cmd, use_shell = _build_claude_cmd(claude_path, model, extra_args)

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

# 测试
if __name__ == "__main__":
    print("=" * 50)
    print("Testing Claude Code Integration")
    print("=" * 50)

    claude_path = _find_claude_code()
    print(f"1. Found claude_path: {claude_path}")

    # 测试直接调用
    print("\n2. Testing direct call...")
    try:
        result = _call_claude_code_direct(
            prompt='返回 JSON 格式: {"test": "integration", "value": 123}',
            model="claude-3-5-sonnet-20241022",
            timeout=60,
            task_dir=f"{PROJECT_ROOT}/output"
        )
        print(f"   Result: {result[:500]}")
        print("\n   SUCCESS!")
    except Exception as e:
        print(f"   Error: {e}")
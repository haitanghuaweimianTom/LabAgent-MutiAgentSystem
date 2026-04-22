"""模拟 orchestrator 调用 solver_agent 的完整流程"""
import subprocess
import json
import os
import sys

# 模拟 base.py 中的 _build_claude_cmd 函数
def build_claude_cmd(claude_path, model, extra_args=None):
    extra_args = extra_args or []
    cli_js_path = None

    if claude_path.startswith('node'):
        import re
        match = re.search(r'"([^"]+\.js)"', claude_path)
        if match:
            cli_js_path = match.group(1)

    if cli_js_path and os.path.isfile(cli_js_path):
        cmd = ["node", cli_js_path] + extra_args + ["--model", model]
        return cmd, False
    elif '"' in claude_path or "'" in claude_path:
        cmd_str = f'cmd /c "{claude_path}"'
        full_args = " ".join(extra_args + ["--model", model])
        cmd = f"{cmd_str} {full_args}"
        return cmd, True
    else:
        cmd = [claude_path] + extra_args + ["--model", model]
        return cmd, False

# 测试用 WinGet 路径
claude_path = "C:/Users/hhh/AppData/Local/Microsoft/WinGet/Packages/Anthropic.ClaudeCode_Microsoft.Winget.Source_8wekyb3d8bbwe/claude.exe"

print(f"Testing with claude_path: {claude_path}")
print(f"File exists: {os.path.isfile(claude_path)}")

# 测试 _build_claude_cmd
cmd, use_shell = build_claude_cmd(claude_path, "claude-3-5-sonnet-20241022", ["-p", "--output-format", "json", "--input-format", "text"])
print(f"Built cmd: {cmd}")
print(f"use_shell: {use_shell}")

# 直接调用测试
test_input = '返回 JSON: {"test": "direct call success"}'
proc = subprocess.Popen(
    cmd,
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    cwd=os.path.dirname(claude_path),
    shell=use_shell,
)

stdout, stderr = proc.communicate(
    input=test_input.encode("utf-8"),
    timeout=60
)

stdout_text = stdout.decode("utf-8", errors="replace").strip()
stderr_text = stderr.decode("utf-8", errors="replace").strip()

print(f"Return code: {proc.returncode}")
if proc.returncode == 0:
    try:
        data = json.loads(stdout_text)
        result = data.get("result", "")
        if "```json" in result:
            json_str = result.split("```json")[1].split("```")[0].strip()
            parsed = json.loads(json_str)
            print(f"SUCCESS: {parsed}")
        else:
            print(f"Result: {result[:200]}")
    except Exception as e:
        print(f"Parse error: {e}")
        print(f"Raw output: {stdout_text[:300]}")
else:
    print(f"Failed. Stderr: {stderr_text[:200]}")
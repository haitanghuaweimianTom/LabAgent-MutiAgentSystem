"""测试 Claude Code 集成 - 使用 WinGet 路径"""
import subprocess
import json
import os

def test_claude_win():
    """测试使用 WinGet 安装的 claude.exe"""
    claude_exe = "C:/Users/hhh/AppData/Local/Microsoft/WinGet/Packages/Anthropic.ClaudeCode_Microsoft.Winget.Source_8wekyb3d8bbwe/claude.exe"

    if not os.path.isfile(claude_exe):
        print(f"ERROR: {claude_exe}")
        return False

    print(f"Testing: {claude_exe}")

    # Test -p mode
    test_input = '返回 JSON: {"result": "success", "value": 42}'

    proc = subprocess.Popen(
        [claude_exe, "-p",
         "--model", "claude-3-5-sonnet-20241022",
         "--output-format", "json",
         "--input-format", "text"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=os.path.dirname(claude_exe),
    )

    stdout, stderr = proc.communicate(
        input=test_input.encode("utf-8"),
        timeout=60
    )

    stdout_text = stdout.decode("utf-8", errors="replace").strip()

    if proc.returncode == 0:
        try:
            data = json.loads(stdout_text)
            result = data.get("result", "")
            if "```json" in result:
                json_str = result.split("```json")[1].split("```")[0].strip()
                parsed = json.loads(json_str)
                print(f"SUCCESS: {parsed}")
                return True
        except Exception as e:
            print(f"Parse error: {e}")
    else:
        print(f"Failed: {stderr.decode('utf-8', errors='replace')[:200]}")

    return False

if __name__ == "__main__":
    test_claude_win()
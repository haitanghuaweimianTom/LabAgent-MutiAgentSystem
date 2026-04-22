"""测试 Claude Code 集成"""
import subprocess
import json
import os

def test_claude_code():
    """测试 claude-code 集成"""
    # WinGet 安装路径
    claude_exe = "C:/Users/hhh/AppData/Local/Microsoft/WinGet/Packages/Anthropic.ClaudeCode_Microsoft.Winget.Source_8wekyb3d8bbwe/claude.exe"

    if not os.path.isfile(claude_exe):
        print(f"ERROR: claude.exe not found at {claude_exe}")
        return False

    print(f"claude.exe found at: {claude_exe}")

    # Test 1: claude --version
    result = subprocess.run(
        [claude_exe, "--version"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10
    )
    print(f"claude version: {result.stdout.strip()}")

    # Test 2: claude -p (prompt mode)
    print("\nTest: Claude -p prompt mode...")
    test_input = '返回 JSON: {"test": "hello", "value": 123}'

    proc = subprocess.Popen(
        [claude_exe, "-p", "--model", "claude-3-5-sonnet-20241022",
         "--output-format", "json", "--input-format", "text"],
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
    stderr_text = stderr.decode("utf-8", errors="replace").strip()

    print(f"Return code: {proc.returncode}")
    if proc.returncode == 0:
        try:
            data = json.loads(stdout_text)
            result_val = data.get("result", "")
            # Extract JSON from ```json block
            if "```json" in result_val:
                json_str = result_val.split("```json")[1].split("```")[0].strip()
                parsed = json.loads(json_str)
                print(f"Parsed JSON: {parsed}")
                print("SUCCESS!")
                return True
        except Exception as e:
            print(f"Parse error: {e}")
            print(f"Raw output: {stdout_text[:300]}")
    else:
        print(f"Stderr: {stderr_text[:200]}")

    return False

if __name__ == "__main__":
    success = test_claude_code()
    print(f"\n{'SUCCESS' if success else 'FAILED'}")
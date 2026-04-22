"""测试 Claude Code 集成"""
import subprocess
import json
import os

def test_claude_code():
    """测试 claude-code-source 集成"""
    cli_js_path = "d:/coding/MathModel-MutiAgentSyStem/claude-code-source/cli.js"

    if not os.path.isfile(cli_js_path):
        print(f"ERROR: cli.js not found at {cli_js_path}")
        return False

    print(f"cli.js found at: {cli_js_path}")

    # Test 1: node --version
    result = subprocess.run(
        ["node", "--version"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10
    )
    print(f"node version: {result.stdout.strip()}")

    # Test 2: claude --version
    result = subprocess.run(
        ["node", cli_js_path, "--version"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10
    )
    print(f"claude version: {result.stdout.strip()}")

    # Test 3: claude -p (prompt mode)
    print("\nTest 3: Claude -p prompt mode...")
    test_input = '返回 JSON 格式: {"test": "hello", "value": 123}'

    proc = subprocess.Popen(
        ["node", cli_js_path, "-p", "--model", "claude-3-5-sonnet-20241022",
         "--output-format", "json", "--input-format", "text"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=os.path.dirname(cli_js_path),
    )

    stdout, stderr = proc.communicate(
        input=test_input.encode("utf-8"),
        timeout=60
    )

    stdout_text = stdout.decode("utf-8", errors="replace").strip()
    stderr_text = stderr.decode("utf-8", errors="replace").strip()

    print(f"Return code: {proc.returncode}")
    print(f"Stdout: {stdout_text[:500]}")
    if stderr_text:
        print(f"Stderr: {stderr_text[:200]}")

    if proc.returncode == 0:
        try:
            data = json.loads(stdout_text)
            print(f"\nParsed JSON: {data}")
        except json.JSONDecodeError as e:
            print(f"\nJSON parse error: {e}")
            print(f"Raw output: {stdout_text[:300]}")

    return proc.returncode == 0

if __name__ == "__main__":
    success = test_claude_code()
    print(f"\n{'SUCCESS' if success else 'FAILED'}")
"""Claude Code CLI 集成模块

提供 Claude Code CLI 的查找和调用功能。
从 base.py 中提取，减少 BaseAgent 类的职责。
"""
import json
import logging
import os
import shutil
import subprocess
from typing import List, Optional

logger = logging.getLogger(__name__)

# Claude Code CLI 路径缓存
_CLAUDE_CODE_PATH: Optional[str] = None


def find_claude_code() -> Optional[str]:
    """自动搜索 Claude Code CLI 路径"""
    global _CLAUDE_CODE_PATH
    if _CLAUDE_CODE_PATH is not None:
        return _CLAUDE_CODE_PATH if _CLAUDE_CODE_PATH else None

    # 1. 用户配置的路径
    try:
        from ..config import get_settings
        settings = get_settings()
        if settings.claude_code_path:
            if os.path.isfile(settings.claude_code_path):
                _CLAUDE_CODE_PATH = settings.claude_code_path
                return _CLAUDE_CODE_PATH
            found = shutil.which(settings.claude_code_path)
            if found:
                _CLAUDE_CODE_PATH = found
                return _CLAUDE_CODE_PATH
    except Exception:
        pass

    # 2. PATH 中搜索
    found = shutil.which("claude-code") or shutil.which("claude")
    if found:
        _CLAUDE_CODE_PATH = found
        return _CLAUDE_CODE_PATH

    # 3. 环境变量
    env_path = os.environ.get("CLAUDE_CODE_PATH", "")
    if env_path and os.path.isfile(env_path):
        _CLAUDE_CODE_PATH = env_path
        return _CLAUDE_CODE_PATH

    _CLAUDE_CODE_PATH = ""
    return None


def call_claude_code(
    prompt: str,
    model: str = "sonnet",
    system_prompt: Optional[str] = None,
    timeout: int = 300,
    task_dir: Optional[str] = None,
    mode: str = "print",
    mcp_config_path: Optional[str] = None,
    allowed_tools: Optional[List[str]] = None,
) -> str:
    """Claude Code CLI 调用的公共实现

    Args:
        prompt: 用户提示
        model: 模型名称
        system_prompt: 系统提示
        timeout: 超时时间（秒）
        task_dir: 工作目录
        mode: 调用模式 (direct/print/agent)
        mcp_config_path: MCP 配置文件路径
        allowed_tools: 允许的工具列表

    Returns:
        Claude Code 的响应文本
    """
    claude_path = find_claude_code()
    if not claude_path:
        raise RuntimeError("Claude Code CLI 未找到，请确保已安装 Claude Code 并添加到 PATH")

    cmd = [claude_path]

    if mode == "agent":
        cmd.append("--agent")
    else:
        cmd.extend(["-p", "--input-format", "text"])

    cmd.extend(["--model", model, "--output-format", "json"])

    if mcp_config_path:
        cmd.extend(["--mcp-config", mcp_config_path])
    if allowed_tools:
        cmd.extend(["--allowedTools", ",".join(allowed_tools)])

    env = os.environ.copy()
    full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt

    try:
        cwd = task_dir if task_dir and os.path.isdir(task_dir) else os.getcwd()
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            env=env,
        )
        stdout, stderr = proc.communicate(
            input=full_prompt.encode("utf-8"),
            timeout=timeout,
        )
        stdout_text = stdout.decode("utf-8", errors="replace").strip()
        stderr_text = stderr.decode("utf-8", errors="replace").strip()

        if proc.returncode != 0:
            logger.warning(f"Claude Code {mode} 失败 (code={proc.returncode}): {stderr_text[:300]}")
            raise RuntimeError(f"Claude Code {mode} 调用失败: {stderr_text[:500]}")

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

    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Claude Code {mode} 调用超时（{timeout}秒）")
    except FileNotFoundError:
        raise RuntimeError("Claude Code CLI 未找到")


# 便捷函数
def call_claude_code_direct(prompt: str, model: str = "sonnet", **kwargs) -> str:
    """直接调用 Claude Code CLI"""
    return call_claude_code(prompt, model, mode="direct", **kwargs)


def call_claude_code_print(prompt: str, model: str = "sonnet", **kwargs) -> str:
    """通过 --print 模式调用 Claude Code CLI"""
    return call_claude_code(prompt, model, mode="print", **kwargs)


def call_claude_code_agent(prompt: str, model: str = "sonnet", **kwargs) -> str:
    """通过 --agent 模式调用 Claude Code CLI"""
    return call_claude_code(prompt, model, mode="agent", **kwargs)

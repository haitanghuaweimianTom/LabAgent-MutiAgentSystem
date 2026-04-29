"""
Claude CLI Provider
===================

保留原有的 Claude Code CLI 调用方式，实现向后兼容。
当用户已安装 Claude Code CLI 但未配置 API Key 时，可作为 fallback 使用。
"""

import os
import sys
import json
import time
import shutil
import subprocess
from typing import Optional, AsyncGenerator

from ..base import BaseLLMProvider, ProviderConfig, LLMResponse, ProviderType


class ClaudeCLIProvider(BaseLLMProvider):
    """Claude Code CLI Provider (向后兼容)"""

    DEFAULT_MODEL = "sonnet"

    def __init__(self, config: Optional[ProviderConfig] = None):
        if config is None:
            config = ProviderConfig(
                provider_type=ProviderType.CLAUDE_CLI,
                name="claude_cli",
                model=os.getenv("CLAUDE_CLI_MODEL", self.DEFAULT_MODEL),
                timeout=int(os.getenv("CLAUDE_CLI_TIMEOUT", "600")),
            )
        if not config.model:
            config.model = self.DEFAULT_MODEL
        super().__init__(config)
        self._claude_path = self._find_claude_code()

    def _find_claude_code(self) -> Optional[str]:
        """自动搜索 Claude Code CLI 路径"""
        return shutil.which("claude-code") or shutil.which("claude")

    def _validate_config(self) -> None:
        if not self._claude_path:
            raise RuntimeError(
                "Claude Code CLI 未找到，请确保已安装 Claude Code 并添加到 PATH"
            )

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_retries: int = 3,
        retry_wait: int = 5,
        **kwargs
    ) -> LLMResponse:
        """通过 Claude Code CLI 调用 LLM"""
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"

        cmd = [
            self._claude_path,
            "-p",
            "--model", self.config.model,
            "--output-format", "json",
            full_prompt
        ]

        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    time.sleep(retry_wait)

                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                stdout, stderr = proc.communicate(timeout=self.config.timeout)
                stdout_text = stdout.decode("utf-8", errors="replace").strip()

                if proc.returncode != 0:
                    error_msg = stderr.decode("utf-8", errors="replace")
                    if attempt < max_retries - 1:
                        continue
                    raise RuntimeError(f"Claude CLI 调用失败: {error_msg[:500]}")

                # 尝试解析 JSON
                try:
                    data = json.loads(stdout_text.strip())
                    result_text = data.get("result", "")
                except json.JSONDecodeError:
                    result_text = stdout_text.strip()

                # 去除 markdown 代码块
                if isinstance(result_text, str) and result_text.startswith("```"):
                    lines = result_text.splitlines()
                    if lines and lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].strip() == "```":
                        lines = lines[:-1]
                    result_text = "\n".join(lines).strip()

                return LLMResponse(
                    content=str(result_text),
                    model=self.config.model,
                )

            except subprocess.TimeoutExpired:
                if attempt < max_retries - 1:
                    continue
                raise RuntimeError(
                    f"Claude CLI 调用超时（{self.config.timeout}秒），已重试{max_retries}次"
                )
            except FileNotFoundError:
                raise RuntimeError("Claude Code CLI 未找到")

        raise RuntimeError("Claude CLI 调用失败，已达到最大重试次数")

    async def generate_async(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> LLMResponse:
        """异步生成（实际为同步调用的包装）"""
        return self.generate(prompt, system_prompt, **kwargs)

    async def stream_generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """流式生成（CLI 不支持真正的流式，返回完整结果）"""
        response = self.generate(prompt, system_prompt, **kwargs)
        yield response.content

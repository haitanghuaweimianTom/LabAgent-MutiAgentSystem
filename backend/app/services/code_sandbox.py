"""向后兼容 shim — 实际实现已合并到 core/sandbox.py。"""
from ..core.sandbox import (  # noqa: F401
    CodeSandbox,
    SandboxConfig,
    SandboxResult,
    execute_code_sandboxed,
)

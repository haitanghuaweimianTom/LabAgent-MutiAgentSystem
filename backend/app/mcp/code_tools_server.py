#!/usr/bin/env python3
"""代码执行 + 文件读写 MCP 服务器（内置 Python 实现）。

暴露工具：code_execute / file_read / file_write / latex_compile。

为什么需要这个服务器？
之前 file_read/file_write/code_execute 被映射到 npx
`@modelcontextprotocol/server-filesystem`，该服务器有两个致命问题：
1. 启动参数用相对路径 `./workspace ./output`，后端进程 cwd 下不存在
   → "None of the specified directories are accessible" → 服务器立即退出
   → MCPClient 收到 "Connection closed"（base.py:_execute_mcp_tool 全部失败）。
2. 它只暴露 `read_file`/`write_file`，根本没有 `code_execute` 工具。

本服务器用纯 Python 实现，工作目录在启动时自动创建（绝不因目录缺失退出），
文件操作被沙箱限制在工作目录内，code_execute 用当前解释器子进程执行。
"""
import os
import shutil
import sys
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import TextContent, Tool
except ImportError:
    print("Error: mcp package not installed. Run: pip install mcp", file=sys.stderr)
    sys.exit(1)

app = Server("code-tools")

# 工作目录列表（启动时从 argv 读取并创建；文件操作被沙箱限制在这些目录内）
_WORKSPACES: List[Path] = []

# 单次执行输出截断阈值，避免撑爆 LLM 上下文
_MAX_OUTPUT = 8000
# code_execute 默认/最大超时
_DEFAULT_TIMEOUT = 120
_MAX_TIMEOUT = 180


def _init_workspaces(argv: List[str]) -> None:
    """从命令行参数解析工作目录，解析为绝对路径并创建。"""
    for a in argv:
        if not a:
            continue
        try:
            p = Path(a).expanduser().resolve()
            p.mkdir(parents=True, exist_ok=True)
            if p not in _WORKSPACES:
                _WORKSPACES.append(p)
        except Exception:
            # 单个目录创建失败不致命，跳过
            pass
    if not _WORKSPACES:
        # 兜底：永远保证至少一个工作目录，服务器绝不因目录缺失退出
        p = Path(tempfile.gettempdir()) / "labagent_workspace"
        p.mkdir(parents=True, exist_ok=True)
        _WORKSPACES.append(p)


def _resolve(path: str) -> Path:
    """解析路径（相对路径基于第一个工作目录）并做沙箱检查。"""
    if not path:
        raise ValueError("path is required")
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = (_WORKSPACES[0] / path)
    p = p.resolve()
    for ws in _WORKSPACES:
        try:
            p.relative_to(ws)
            return p
        except ValueError:
            continue
    raise PermissionError(f"路径 {path} 不在允许的工作目录内，拒绝访问")


@app.list_tools()
async def list_tools() -> List[Tool]:
    """声明可用工具。"""
    return [
        Tool(
            name="code_execute",
            description="执行 Python 代码并返回 stdout/stderr。代码以第一个工作目录为 cwd 运行，"
                        "因此相对路径的文件读写和 import 会落在该目录。用于求解、数据处理、绘图等。",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Python 代码"},
                    "timeout": {"type": "integer", "description": "超时秒数（默认 120，上限 180）", "default": 120},
                },
                "required": ["code"],
            },
        ),
        Tool(
            name="file_read",
            description="读取文件内容（限工作目录内）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径（相对路径基于工作目录）"},
                },
                "required": ["path"],
            },
        ),
        Tool(
            name="file_write",
            description="写入文件内容（限工作目录内，自动创建父目录）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径（相对路径基于工作目录）"},
                    "content": {"type": "string", "description": "文件内容"},
                },
                "required": ["path", "content"],
            },
        ),
        Tool(
            name="latex_compile",
            description="用 xelatex 编译 .tex 文件（若系统未安装则返回错误）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": ".tex 文件路径"},
                },
                "required": ["file_path"],
            },
        ),
    ]


def _truncate(text: str) -> str:
    if len(text) <= _MAX_OUTPUT:
        return text
    return text[:_MAX_OUTPUT] + f"\n...[输出已截断，共 {len(text)} 字符]"


@app.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    """处理工具调用。"""
    try:
        if name == "code_execute":
            code = arguments.get("code", "")
            if not code:
                return [TextContent(type="text", text="Error: code is required")]
            timeout = arguments.get("timeout", _DEFAULT_TIMEOUT)
            try:
                timeout = int(timeout)
            except (TypeError, ValueError):
                timeout = _DEFAULT_TIMEOUT
            timeout = max(1, min(timeout, _MAX_TIMEOUT))

            ws = _WORKSPACES[0]
            # 写入工作目录下的临时文件，保证 cwd 一致 + 相对 import 生效
            fd, tmp_path = tempfile.mkstemp(prefix="_exec_", suffix=".py", dir=str(ws))
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(code)
                env = os.environ.copy()
                # 保证子进程能 import 项目已装依赖
                proc = subprocess.run(
                    [sys.executable, tmp_path],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=timeout,
                    cwd=str(ws),
                    env=env,
                )
                out = proc.stdout or ""
                err = proc.stderr or ""
                combined = out
                if err:
                    combined += (("\n" if combined else "") + "[stderr]\n" + err)
                combined = combined.strip()
                if not combined:
                    combined = f"(无输出, exit={proc.returncode})"
                else:
                    combined = f"[exit={proc.returncode}]\n" + combined
                return [TextContent(type="text", text=_truncate(combined))]
            except subprocess.TimeoutExpired:
                return [TextContent(type="text", text=f"执行超时（{timeout} 秒）")]
            except Exception as e:
                return [TextContent(type="text", text=f"code_execute 执行失败: {e}")]
            finally:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

        elif name == "file_read":
            path = arguments.get("path", "")
            try:
                p = _resolve(path)
            except (PermissionError, ValueError) as e:
                return [TextContent(type="text", text=f"file_read 拒绝: {e}")]
            if not p.exists() or not p.is_file():
                return [TextContent(type="text", text=f"文件不存在: {path}")]
            try:
                content = p.read_text(encoding="utf-8", errors="replace")
                return [TextContent(type="text", text=_truncate(content))]
            except Exception as e:
                return [TextContent(type="text", text=f"file_read 失败: {e}")]

        elif name == "file_write":
            path = arguments.get("path", "")
            content = arguments.get("content", "")
            try:
                p = _resolve(path)
            except (PermissionError, ValueError) as e:
                return [TextContent(type="text", text=f"file_write 拒绝: {e}")]
            try:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(content, encoding="utf-8")
                return [TextContent(type="text", text=f"已写入 {len(content)} 字符到 {p}")]
            except Exception as e:
                return [TextContent(type="text", text=f"file_write 失败: {e}")]

        elif name == "latex_compile":
            tex = arguments.get("file_path", "")
            if not tex:
                return [TextContent(type="text", text="Error: file_path is required")]
            try:
                p = _resolve(tex)
            except (PermissionError, ValueError) as e:
                return [TextContent(type="text", text=f"latex_compile 拒绝: {e}")]
            xelatex = shutil.which("xelatex") if shutil.which("xelatex") else "xelatex"
            try:
                # 两趟编译以解析 \ref/\cite，避免交叉引用显示 ??
                proc = None
                for _ in range(2):
                    proc = subprocess.run(
                        [xelatex, "-interaction=nonstopmode", "-halt-on-error", p.name],
                        capture_output=True, text=True, encoding="utf-8", errors="replace",
                        timeout=60, cwd=str(p.parent),
                    )
                pdf = p.with_suffix(".pdf")
                ok = proc.returncode == 0 and pdf.exists()
                msg = f"latex_compile {'成功' if ok else '失败'} (exit={proc.returncode}, 2 passes)"
                if proc.stdout:
                    msg += f"\n[stdout]\n{_truncate(proc.stdout)}"
                if proc.stderr:
                    msg += f"\n[stderr]\n{_truncate(proc.stderr)}"
                return [TextContent(type="text", text=msg)]
            except subprocess.TimeoutExpired:
                return [TextContent(type="text", text="latex_compile 超时（60 秒）")]
            except FileNotFoundError:
                return [TextContent(type="text", text="latex_compile 失败: xelatex 未安装")]
            except Exception as e:
                return [TextContent(type="text", text=f"latex_compile 失败: {e}")]

        return [TextContent(type="text", text=f"未知工具: {name}")]
    except Exception as e:
        return [TextContent(type="text", text=f"工具 {name} 异常: {e}")]


async def main():
    _init_workspaces(sys.argv[1:])
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options(),
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

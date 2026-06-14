"""Agent 基类"""
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile

# v3.4 通用化（CCF-A 论文工厂 Phase 1D）：演示用代码模板从本文件迁出到
# ``demo_code_templates``。``_mock_response`` 不再持有任何 CUMCM 领域字符串。
from .demo_code_templates import DEMO_CODE_TEMPLATES, DEMO_KEYWORD_TO_TEMPLATE
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, TypedDict
import httpx


class ToolDef(TypedDict):
    name: str
    description: str
    parameters: Dict[str, Any]


class ToolCall(TypedDict):
    id: Optional[str]
    name: str
    arguments: Dict[str, Any]


logger = logging.getLogger(__name__)

# ===== Claude Code 后端 =====
_CLAUDE_CODE_PATH: Optional[str] = None


def _find_claude_code() -> Optional[str]:
    """自动搜索 Claude Code CLI 路径"""
    global _CLAUDE_CODE_PATH
    if _CLAUDE_CODE_PATH is not None:
        return _CLAUDE_CODE_PATH if _CLAUDE_CODE_PATH else None

    # 1. 用户配置的路径
    from ..config import get_settings
    settings = get_settings()
    if settings.claude_code_path:
        if os.path.isfile(settings.claude_code_path):
            _CLAUDE_CODE_PATH = settings.claude_code_path
            return _CLAUDE_CODE_PATH
        # 可能是命令名，PATH 中搜索
        found = shutil.which(settings.claude_code_path)
        if found:
            _CLAUDE_CODE_PATH = found
            return _CLAUDE_CODE_PATH

    # 2. PATH 中搜索
    found = shutil.which("claude-code") or shutil.which("claude")
    if found:
        _CLAUDE_CODE_PATH = found
        return _CLAUDE_CODE_PATH

    # 3. 常见安装路径（Windows）
    local_app = os.path.expanduser("~\\AppData\\Local\\Programs\\claude-code\\bin\\claude-code.cmd")
    if os.path.isfile(local_app):
        _CLAUDE_CODE_PATH = local_app
        return _CLAUDE_CODE_PATH

    _CLAUDE_CODE_PATH = ""  # 找不到
    return None


# ===== MCP 工具注册表 =====
# name -> MCP服务器ID（与CherryStudio一致）
MCP_SERVER_MAP: Dict[str, str] = {
    # web_search: "mcp__bingCnMcpServer__bingSearch",
    "bing_search": "bing_search",
    "web_search": "web_search",
    "paper_search": "paper_search",
    "python_execute": "python_execute",
    "sequentialthinking": "sequentialthinking",
}


def _build_mcp_tools_env(mcp_tool_names: List[str]) -> Dict[str, str]:
    """为 Claude Code subprocess 构建 MCP 工具环境变量

    Cherry Claw agent 将允许的工具列表通过 MCP servers 配置关联到各MCP服务器。
    这里我们用 --print 模式（简短任务）跳过 MCP，或者用完整 MCP 模式。
    """
    return {}


def _call_claude_code_direct(
    prompt: str,
    model: str = "sonnet",
    system_prompt: Optional[str] = None,
    timeout: int = 300,
    task_dir: Optional[str] = None,
) -> str:
    """
    【核心】通过 Claude Code CLI 实现全自动编程。

    这个函数是关键桥梁：
    - 接收一个完整的编程任务描述（含问题背景、数据文件路径、模型信息）
    - 通过 claude -p 让 Claude Code 在 task_dir 下写 .py 文件并执行
    - 返回 JSON 格式的执行结果

    不会让 Claude 生成代码文本后由 Python 重新执行——全程由 Claude CLI 闭环完成。
    """
    claude_path = _find_claude_code()
    if not claude_path:
        raise RuntimeError("Claude Code CLI 未找到，请确保已安装 Claude Code 并添加到 PATH")

    cmd = [
        claude_path,
        "-p",
        "--model", model,
        "--output-format", "json",
        "--input-format", "text",
    ]

    env = os.environ.copy()

    # 组合 prompt（含 system prompt）
    full_prompt = prompt
    if system_prompt:
        full_prompt = f"{system_prompt}\n\n{prompt}"

    try:
        cwd = task_dir if task_dir and os.path.isdir(task_dir) else os.getcwd()

        # 使用 Popen + communicate() 强制 UTF-8，解决 Windows console GBK 乱码问题
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

        # 强制 UTF-8 解码（Claude Code 输出 JSON 为 UTF-8）
        stdout_text = stdout.decode("utf-8", errors="replace").strip()
        stderr_text = stderr.decode("utf-8", errors="replace").strip()

        if proc.returncode != 0:
            logger.warning(f"Claude Code direct 调用失败 (code={proc.returncode}): {stderr_text[:300]}")
            raise RuntimeError(f"Claude Code 调用失败: {stderr_text[:500]}")

        # 解析 JSON 输出，提取 result 字段
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
        raise RuntimeError(f"Claude Code 调用超时（{timeout}秒）")
    except FileNotFoundError:
        raise RuntimeError("Claude Code CLI 未找到")


def _call_claude_code_print(
    prompt: str,
    model: str = "sonnet",
    system_prompt: Optional[str] = None,
    timeout: int = 120,
    task_dir: Optional[str] = None,
) -> str:
    """
    通过 Claude Code CLI 的 --print 模式（-p）调用。
    - 正确选项: --print / -p, --model, --output-format, --input-format
    - 无效选项（已移除）: --max-tokens, --temperature, --no-input
    - 提示通过 stdin 传入
    """
    claude_path = _find_claude_code()
    if not claude_path:
        raise RuntimeError("Claude Code CLI 未找到，请确保已安装 Claude Code 并添加到 PATH")

    cmd = [
        claude_path,
        "-p",          # --print，非交互模式
        "--model", model,
        "--output-format", "json",   # 获取结构化 JSON 输出
        "--input-format", "text",
    ]

    env = os.environ.copy()

    # 组合 prompt（含 system prompt）
    full_prompt = prompt
    if system_prompt:
        full_prompt = f"{system_prompt}\n\n{prompt}"

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
            logger.warning(f"Claude Code -p 失败 (code={proc.returncode}): {stderr_text[:300]}")
            raise RuntimeError(f"Claude Code 调用失败: {stderr_text[:500]}")

        # 解析 JSON 输出，提取 result 字段
        raw = stdout_text.strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # 不是 JSON，直接返回原始文本
            return raw

        # JSON 格式: {"result": "```json\n{...}\n```\n", ...}
        result_text = data.get("result", "")
        if isinstance(result_text, str):
            result_text = result_text.strip()
            # 去掉 markdown code block 包装
            if result_text.startswith("```"):
                # 去掉 ```json 或 ```python 等前缀和 ``` 后缀
                lines = result_text.splitlines()
                # 去掉第一行（```xxx）和最后一行（```）
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
        raise RuntimeError(f"Claude Code 调用超时（{timeout}秒）")
    except FileNotFoundError:
        raise RuntimeError("Claude Code CLI 未找到")


def _call_claude_code_agent(
    prompt: str,
    model: str = "sonnet",
    system_prompt: Optional[str] = None,
    timeout: int = 300,
    task_dir: Optional[str] = None,
    mcp_config_path: Optional[str] = None,
    allowed_tools: Optional[List[str]] = None,
) -> str:
    """
    通过 Claude Code CLI 的 --agent 模式调用。
    --agent 模式支持 MCP 工具，是完整的 coding agent。
    """
    claude_path = _find_claude_code()
    if not claude_path:
        raise RuntimeError("Claude Code CLI 未找到，请确保已安装 Claude Code 并添加到 PATH")

    cmd = [
        claude_path,
        "--agent",
        "--model", model,
        "--output-format", "json",   # 结构化输出
    ]

    # MCP 配置文件
    if mcp_config_path:
        cmd.extend(["--mcp-config", mcp_config_path])

    # 允许的工具
    if allowed_tools:
        cmd.extend(["--allowedTools", ",".join(allowed_tools)])

    env = os.environ.copy()

    full_prompt = prompt
    if system_prompt:
        full_prompt = f"{system_prompt}\n\n{prompt}"

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
            logger.warning(f"Claude Code --agent 失败 (code={proc.returncode}): {stderr_text[:300]}")
            raise RuntimeError(f"Claude Code --agent 调用失败: {stderr_text[:500]}")

        # 解析 JSON 输出
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
        raise RuntimeError(f"Claude Code --agent 调用超时（{timeout}秒）")
    except FileNotFoundError:
        raise RuntimeError("Claude Code CLI 未找到")


class PausedException(Exception):
    """任务被用户暂停时抛出的异常"""
    def __init__(self, task_id: str, paused_at: str = ""):
        self.task_id = task_id
        self.paused_at = paused_at
        super().__init__(f"任务 {task_id} 已在 {paused_at} 处暂停")


class AgentFactory:
    """Agent注册表"""
    _registry: Dict[str, type] = {}

    @classmethod
    def register(cls, name: str):
        def decorator(klass):
            cls._registry[name] = klass
            return klass
        return decorator

    @classmethod
    def create(cls, name: str, **kwargs):
        klass = cls._registry.get(name)
        if not klass:
            raise ValueError(f"Unknown agent: {name}")
        return klass(**kwargs)

    @classmethod
    def list_agents(cls):
        return list(cls._registry.keys())


class BaseAgent(ABC):
    """所有Agent的基类"""

    name: str = "base_agent"
    label: str = "Agent"
    description: str = ""
    default_model: str = ""

    # 子类可以重写这个属性来使用 Claude Code 后端
    default_llm_backend: str = "minimax"

    def __init__(
        self,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 8192,
        mcp_tools: Optional[List[str]] = None,
        api_key: Optional[str] = None,
        api_base_url: Optional[str] = None,
        llm_backend: Optional[str] = None,
        provider_id: Optional[str] = None,
    ):
        self._model_explicitly_set = bool(model)  # Phase 7 (A2): 标记路由是否覆盖
        self.model = model or self.default_model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.mcp_tools = mcp_tools or []
        self.api_key = api_key or ""
        self.api_base_url = api_base_url or ""
        self.provider_id = provider_id or ""
        self._knowledge_base_id: Optional[str] = None

        # LLM 后端: "minimax" (默认) | "claude" | provider_id
        from ..config import get_settings
        settings = get_settings()
        if llm_backend:
            self.llm_backend = llm_backend
        elif self.name in settings.claude_enabled_agents and settings.default_llm_backend == "claude":
            self.llm_backend = "claude"
        else:
            self.llm_backend = self.default_llm_backend

        # 从指定的 Provider 获取 API 配置（如果指定了 provider_id 或缺少 api_key/api_host）
        self._provider_auth_field: str = ""
        if self.provider_id or not self.api_key or not self.api_base_url:
            self._resolve_provider_config()

        self._claude_model = settings.claude_model
        self._claude_max_tokens = settings.claude_max_tokens
        self._claude_temperature = settings.claude_temperature
        self._claude_mcp_tools = settings.claude_mcp_tools.split(",") if settings.claude_mcp_tools else []

    def _resolve_provider_config(self) -> None:
        """从当前指定的 Provider（或全局默认）解析 API 配置"""
        from ..core.provider_config import get_custom_provider, get_default_provider
        provider = None
        if self.provider_id:
            provider = get_custom_provider(self.provider_id)
        if not provider:
            provider = get_default_provider()
        if provider and provider.get("api_key") and provider.get("api_host"):
            self.api_key = provider["api_key"]
            self.api_base_url = provider["api_host"]
            self.provider_id = provider.get("id", self.provider_id)
            meta = provider.get("meta", {})
            self._provider_auth_field = meta.get("auth_field", "")
            # 如果 model 未指定或是旧默认值，使用 provider 的第一个可用模型
            if not self.model or self.model == self.default_model:
                first_model = next(
                    (m.get("name") for m in provider.get("models", []) if m.get("enabled")),
                    None
                )
                if first_model:
                    self.model = first_model
            logger.info(f"[{self.name}] 使用 Provider: {provider['name']} ({provider['type']}) model={self.model}")
        elif provider:
            logger.warning(f"[{self.name}] Provider {provider.get('name')} 缺少 api_key 或 api_host")

    # 子类可以重写此属性以获得更大的token限制
    _max_tokens_override: int = 0

    @property
    def effective_max_tokens(self) -> int:
        return self._max_tokens_override or self.max_tokens

    # 保存最近一次调用的上下文，用于生成智能mock
    _call_context: Dict[str, Any] = {}

    async def _call_claude_coder(
        self,
        task_description: str,
        system_instruction: str,
        workspace_dir: Optional[str] = None,
        timeout: int = 300,
    ) -> Dict[str, Any]:
        """
        【全自动编程入口 v3.0】将编程任务全权委托给 Claude Code CLI。

        工作流程：
        1. 调用 Claude Code -p 模式，Claude 生成 Python 代码 + 执行命令
        2. Python subprocess 负责写文件 + 执行（避免 --agent 模式的 Python REPL 崩溃）
        3. 返回结构化结果

        参数：
            task_description: 完整编程任务描述
            system_instruction: Claude Code 行为指令（CLAUDE_CODER_SYSTEM）
            workspace_dir: 工作目录（默认为 output/）
            timeout: 超时秒数

        返回：
            {
                "success": bool,
                "code": str,                    # Python 代码
                "file_path": str,               # 文件路径
                "execution_output": str,        # 执行输出（JSON 字符串）
                "execution_stderr": str,        # 错误信息
                "key_findings": [],              # 关键发现
                "numerical_results": {},         # 数值结果
                "interpretation": str,           # 结果解释
                "attempts": int,                # 尝试次数
            }
        """
        import asyncio

        from ..core.paths import get_output_dir
        output_dir = workspace_dir or str(get_output_dir())

        logger.info(f"[{self.name}] 通过 Claude CLI 全自动编程，工作目录: {output_dir}")

        # ===== 第一步：调用 Claude Code -p 模式生成代码和执行命令 =====
        claude_text = ""
        try:
            claude_text = await asyncio.to_thread(
                _call_claude_code_direct,
                prompt=task_description,
                model=self._claude_model,
                system_prompt=system_instruction,
                timeout=timeout,
                task_dir=output_dir,
            )
            logger.info(f"[{self.name}] Claude CLI 返回 {len(claude_text)} chars")
        except Exception as e:
            logger.error(f"[{self.name}] Claude CLI 调用失败: {e}")
            return {
                "success": False,
                "code": "",
                "file_path": "",
                "execution_output": "",
                "execution_stderr": str(e),
                "key_findings": [],
                "numerical_results": {},
                "interpretation": "",
                "attempts": 0,
            }

        # ===== 第二步：解析 Claude 返回的 JSON，提取 code 和 execution_command =====
        parsed = None
        raw = claude_text.strip()
        if raw.startswith("{"):
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                end = raw.rfind("}")
                if end > 0:
                    try:
                        parsed = json.loads(raw[:end+1])
                    except json.JSONDecodeError:
                        pass

        if not parsed:
            logger.warning(f"[{self.name}] Claude 返回无法解析，原始文本前200字: {raw[:200]}")
            return {
                "success": False,
                "code": raw[:500],
                "file_path": "",
                "execution_output": "",
                "execution_stderr": f"Claude 返回无法解析: {raw[:300]}",
                "key_findings": [],
                "numerical_results": {},
                "interpretation": "",
                "attempts": 1,
            }

        code = parsed.get("code", "")
        file_path = parsed.get("file_path", os.path.join(output_dir, "code", "solver.py"))
        execution_command = parsed.get("execution_command", "")
        key_findings = parsed.get("key_findings", [])
        numerical_results = parsed.get("numerical_results", {})
        interpretation = parsed.get("interpretation", "")

        # ===== 第三步：写代码文件 + 执行 =====
        exec_output = ""
        exec_stderr = ""
        exec_success = False
        attempts = 1

        # 确保目录存在
        code_dir = os.path.dirname(file_path)
        if code_dir:
            os.makedirs(code_dir, exist_ok=True)

        # 写文件
        if code:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(code)
                logger.info(f"[{self.name}] 代码已写入: {file_path}")
            except Exception as e:
                logger.warning(f"[{self.name}] 写文件失败: {e}，跳过写文件步骤")

        # 执行代码
        if execution_command:
            try:
                env = os.environ.copy()
                result = subprocess.run(
                    execution_command if isinstance(execution_command, list) else execution_command,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=120,
                    shell=isinstance(execution_command, str),
                    cwd=output_dir,
                    env=env,
                )
                exec_output = result.stdout.strip()
                exec_stderr = result.stderr.strip()
                exec_success = result.returncode == 0

                # 尝试解析执行输出中的 JSON
                if exec_output.startswith("{"):
                    try:
                        output_json = json.loads(exec_output)
                        numerical_results = {**numerical_results, **output_json}
                        key_findings = key_findings or output_json.get("key_findings", [])
                        interpretation = interpretation or output_json.get("interpretation", "")
                    except json.JSONDecodeError:
                        pass

                logger.info(f"[{self.name}] 执行{'成功' if exec_success else '失败'}: {exec_output[:200]}")
            except subprocess.TimeoutExpired:
                exec_stderr = f"执行超时（120秒）"
                logger.warning(f"[{self.name}] 执行超时")
            except Exception as e:
                exec_stderr = str(e)
                logger.warning(f"[{self.name}] 执行异常: {e}")

        return {
            "success": exec_success,
            "code": code,
            "file_path": file_path,
            "execution_output": exec_output,
            "execution_stderr": exec_stderr,
            "key_findings": key_findings,
            "numerical_results": numerical_results,
            "interpretation": interpretation,
            "attempts": attempts,
        }

    @abstractmethod
    def get_system_prompt(self) -> str:
        """返回系统提示词"""

    # ------------------------------------------------------------------
    # 演示用代码模板选取（Phase 1D：硬编码字符串迁出到 ``demo_code_templates``）
    # ------------------------------------------------------------------

    @staticmethod
    def _select_demo_code_template(block_lower: str) -> str:
        """根据子问题文本（小写）选取一个演示用代码模板字符串。

        仅当 ``_mock_response`` 被调用时（即 LLM Key 缺失）才生效。
        真实 LLM 路径下，本函数不会被调用。

        选取优先级（顺序敏感，先匹配先返回）：
        1. ``optics_multi`` — 多光束干涉（关键词含 "多光束" / "多束" 等）
        2. ``optics_double`` — 双光束干涉 / 红外反射 / 薄膜
        3. ``newsvendor`` — 报童 / 库存 / 订货
        4. ``forecast`` — ARIMA / 时间序列
        5. ``sensitivity`` — 灵敏度 / 稳健性
        6. ``topsis`` — 综合评价 / TOPSIS / AHP
        7. ``lp_fallback`` — 通用线性规划兜底

        Args:
            block_lower: 子问题文本的 lowercase 字符串。

        Returns:
            Python 代码字符串（直接拼接到 ``code_files[0]["code"]``）。
        """
        # 顺序遍历：第一个命中即返回
        for tpl_id, (_tpl_name, keywords) in DEMO_KEYWORD_TO_TEMPLATE.items():
            if any(kw in block_lower for kw in keywords):
                return DEMO_CODE_TEMPLATES[tpl_id]
        # 兜底
        return DEMO_CODE_TEMPLATES["lp_fallback"]
        pass

    @abstractmethod
    async def execute(self, task_input: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """执行任务"""
        pass

    def _inject_knowledge_context(self, query_text: str, top_k: int = 3, base_id: Optional[str] = None) -> str:
        """查询知识库并返回上下文文本（静默失败）

        v2 多库版：查询所有知识库，合并上下文注入。
        若指定了 base_id（或 agent 设置了 _knowledge_base_id），则只查询该知识库。
        """
        try:
            from ..core.knowledge_manager import get_knowledge_manager
            km = get_knowledge_manager()
            target_id = base_id or self._knowledge_base_id
            if target_id:
                ctx = km.query_context(target_id, query_text, top_k=top_k, max_chars=1500)
                if ctx:
                    logger.info(f"[{self.name}] 注入知识库上下文 (base={target_id}, {len(ctx)} chars)")
                    return f"\n\n## 知识库参考上下文\n{ctx}\n"
            else:
                ctx = km.query_all_context(query_text, top_k=top_k, max_chars=1500)
                if ctx:
                    logger.info(f"[{self.name}] 注入知识库上下文 (all bases, {len(ctx)} chars)")
                    return f"\n\n## 知识库参考上下文\n{ctx}\n"
        except Exception as e:
            logger.debug(f"[{self.name}] 知识库查询失败: {e}")
        return ""

    def _inject_memory_context(self, context: Dict[str, Any]) -> str:
        """注入记忆系统上下文（黑板状态 + 经验教训）

        从 context 中提取 memory 对象，获取：
        1. Working Memory 黑板状态（共享任务状态）
        2. Lessons Memory 历史经验（跨任务复用知识）
        """
        parts = []

        # 1. 黑板上下文（角色过滤后的）
        working = context.get("working_memory")
        if working:
            agent_ctx = working.get_context_for_agent(self.name)
            if agent_ctx.get("agent_results"):
                result_summary = ", ".join(
                    f"{k}: {str(v)[:80]}" for k, v in agent_ctx["agent_results"].items() if k != self.name
                )
                parts.append(f"\n\n## 【共享黑板状态】\n其他 Agent 的结果：{result_summary}")

            if agent_ctx.get("literature"):
                lit_count = len(agent_ctx["literature"])
                parts.append(f"\n\n## 【已搜集文献】\n共 {lit_count} 篇文献，摘要见上下文。")

            if agent_ctx.get("methods"):
                method_names = [m.get("name", m.get("method", "")) for m in agent_ctx["methods"][:5]]
                parts.append(f"\n\n## 【候选方法】\n{', '.join(filter(None, method_names))}")

            if agent_ctx.get("decisions"):
                decs = [f"- {d.get('decision')}: {d.get('reason')}" for d in agent_ctx["decisions"][:5]]
                parts.append(f"\n\n## 【关键决策】\n" + "\n".join(decs))

            if agent_ctx.get("notes"):
                notes = [f"- [{n['from']}] {n['content'][:100]}" for n in agent_ctx["notes"][:5]]
                parts.append(f"\n\n## 【Agent 备注】\n" + "\n".join(notes))

            if agent_ctx.get("data_insights"):
                insights = [f"- {i}" for i in agent_ctx["data_insights"][:5]]
                parts.append(f"\n\n## 【数据洞察】\n" + "\n".join(insights))

        # 2. 历史经验教训
        try:
            from ..core.memory import get_memory_manager
            mm = get_memory_manager()
            problem_type = context.get("problem_type", "")
            lesson_ctx = mm.get_lessons().get_context_text(problem_type=problem_type, top_k=5)
            if lesson_ctx:
                parts.append(lesson_ctx)
        except Exception as e:
            logger.debug(f"[{self.name}] 记忆系统查询失败: {e}")

        return "\n".join(parts)

    def _get_api_format(self) -> str:
        """从 provider 元数据或 llm_backend 推断 API 格式"""
        from ..core.provider_config import get_custom_provider, get_default_provider
        provider = None
        if self.provider_id:
            provider = get_custom_provider(self.provider_id)
        if not provider:
            provider = get_default_provider()
        if provider:
            meta = provider.get("meta", {})
            return meta.get("api_format", "openai_chat")
        if self.llm_backend == "anthropic":
            return "anthropic"
        return "openai_chat"

    async def _call_anthropic(
        self,
        messages: List[Dict[str, Any]],
        temperature: Optional[float],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """调用 Anthropic Messages API，支持多种认证方式，可选 tools。"""
        if self._provider_auth_field == "anthropic_auth_token":
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
        else:
            headers = {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
        payload: Dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.effective_max_tokens,
            "temperature": temperature if temperature is not None else self.temperature,
            "messages": messages,
        }
        if tools:
            payload["tools"] = tools

        timeout = 300.0 if self.effective_max_tokens > 8192 else 120.0

        def _normalize(data: Dict[str, Any]) -> Dict[str, Any]:
            content_text = ""
            tool_calls = []
            for c in data.get("content", []):
                if c.get("type") == "text":
                    content_text += c.get("text", "")
                elif c.get("type") == "tool_use":
                    tool_calls.append({
                        "id": c.get("id"),
                        "type": "function",
                        "function": {
                            "name": c.get("name", ""),
                            "arguments": json.dumps(c.get("input", {})),
                        },
                    })
            msg: Dict[str, Any] = {"role": "assistant", "content": content_text}
            if tool_calls:
                msg["tool_calls"] = tool_calls
            return {"choices": [{"message": msg}]}

        try:
            body_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{self.api_base_url}/v1/messages",
                    headers=headers,
                    content=body_bytes,
                )
                response.raise_for_status()
                text = response.content.decode("utf-8")
                data = json.loads(text)
                return _normalize(data)
        except httpx.ReadTimeout:
            logger.warning(f"[{self.name}] Anthropic ReadTimeout, retrying...")
            try:
                async with httpx.AsyncClient(timeout=timeout * 1.5) as client:
                    response = await client.post(
                        f"{self.api_base_url}/v1/messages",
                        headers=headers,
                        content=body_bytes,
                    )
                    response.raise_for_status()
                    text = response.content.decode("utf-8")
                    data = json.loads(text)
                    return _normalize(data)
            except Exception as e2:
                logger.error(f"[{self.name}] Anthropic retry failed: {e2}")
                self._call_context["error"] = str(e2)
                return self._mock_response(messages)
        except httpx.HTTPStatusError as e:
            err_text = e.response.content.decode("utf-8", errors="replace")[:300]
            logger.error(f"[{self.name}] Anthropic HTTP {e.response.status_code}: {err_text}")
            self._call_context["error"] = f"HTTP {e.response.status_code}"
            return self._mock_response(messages)
        except Exception as e:
            logger.error(f"[{self.name}] Anthropic call failed: {e}")
            self._call_context["error"] = str(e)
            return self._mock_response(messages)

    async def call_llm(
        self,
        messages: List[Dict[str, Any]],
        stream: bool = False,
        temperature: Optional[float] = None,
        context: Optional[Dict[str, Any]] = None,
        tools: Optional[List[ToolDef]] = None,
        max_react_iterations: int = 5,
    ) -> Dict[str, Any]:
        """调用 LLM API，支持 OpenAI / Anthropic / Claude CLI 格式。

        新增 Phase 2：支持 ReAct 工具循环。传入 tools 时，LLM 会在
        Thought-Action-Observation 循环中反复调用工具，直到给出最终答案
        或达到 max_react_iterations。
        """
        # ===== Phase 7 (A2): AgentModelRouter 路由生效 =====
        if context and "template" in context and not self._model_explicitly_set:
            try:
                from ..core.agent_model_map import get_agent_model_router
                router = get_agent_model_router()
                routed = router.get_model(
                    self.name, context["template"], default=self.model
                )
                if routed and routed != self.model:
                    logger.debug(
                        f"call_llm[{self.name}] template={context['template']}: "
                        f"model {self.model!r} -> {routed!r}"
                    )
                    self.model = routed
            except Exception as exc:  # noqa: BLE001
                logger.debug(f"AgentModelRouter unavailable: {exc}")

        self._call_context = {
            "messages": messages,
            "temperature": temperature,
            "tools": [t["name"] for t in tools] if tools else [],
        }

        # ===== Claude Code 后端（暂不支持 ReAct tools）=====
        if self.llm_backend == "claude":
            if tools:
                logger.warning(f"[{self.name}] Claude CLI 后端暂不支持 ReAct tools，忽略 tools")
            return await self._call_claude_backend(messages, temperature)

        # ===== 注入知识库上下文 =====
        last_content = messages[-1].get("content", "")
        query_text = last_content if isinstance(last_content, str) else ""
        kb_context = self._inject_knowledge_context(query_text)
        if kb_context:
            for msg in messages:
                if msg.get("role") == "user":
                    if isinstance(msg["content"], str):
                        msg["content"] = msg["content"] + kb_context
                    elif isinstance(msg["content"], list):
                        msg["content"].append({"type": "text", "text": kb_context})
                    break

        # ===== 注入记忆系统上下文（黑板状态 + 经验教训）=====
        mem_context = self._inject_memory_context(context) if context else ""
        if mem_context:
            for msg in messages:
                if msg.get("role") == "user":
                    if isinstance(msg["content"], str):
                        msg["content"] = msg["content"] + mem_context
                    elif isinstance(msg["content"], list):
                        msg["content"].append({"type": "text", "text": mem_context})
                    break

        # ===== 检查 API Key =====
        if not self.api_key:
            logger.warning(f"[{self.name}] No API key, returning demo response")
            return self._mock_response(messages)

        # ===== ReAct 工具循环 =====
        if tools:
            return await self._react_loop(
                messages=list(messages),
                tools=tools,
                temperature=temperature,
                max_iterations=max_react_iterations,
            )

        return await self._call_llm_once(messages, temperature)

    async def _call_llm_once(
        self,
        messages: List[Dict[str, Any]],
        temperature: Optional[float] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """单次 LLM 调用（含可选 tools 字段）。"""
        api_format = self._get_api_format()

        if api_format == "anthropic":
            return await self._call_anthropic(messages, temperature, tools=tools)

        # 默认 OpenAI Chat Completions（兼容 openai_chat / openai_responses / ollama_chat）
        if api_format not in ("openai_chat", "openai_responses", "ollama_chat", "gemini_native"):
            logger.warning(f"[{self.name}] 未知 api_format={api_format}，回退到 openai_chat")

        if api_format == "gemini_native":
            # Gemini 原生格式暂不支持 tools，先不带 tools 调用
            if tools:
                logger.warning(f"[{self.name}] gemini_native 工具适配未实现，忽略 tools")
            tools = None

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json; charset=utf-8",
        }
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.temperature,
            "max_tokens": self.effective_max_tokens,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        timeout = 300.0 if self.effective_max_tokens > 8192 else 120.0

        try:
            body_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{self.api_base_url}/chat/completions",
                    headers=headers,
                    content=body_bytes,
                )
                response.raise_for_status()
                text = response.content.decode("utf-8")
                return json.loads(text)
        except httpx.ReadTimeout:
            logger.warning(f"[{self.name}] ReadTimeout ({timeout}s), retrying once...")
            try:
                body_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                async with httpx.AsyncClient(timeout=timeout * 1.5) as client:
                    response = await client.post(
                        f"{self.api_base_url}/chat/completions",
                        headers=headers,
                        content=body_bytes,
                    )
                    response.raise_for_status()
                    text = response.content.decode("utf-8")
                    return json.loads(text)
            except Exception as e2:
                logger.error(f"[{self.name}] Retry also failed: {e2}")
                self._call_context["error"] = str(e2)
                return self._mock_response(messages)
        except (httpx.RemoteProtocolError, httpx.PoolTimeout, OSError) as e:
            logger.warning(f"[{self.name}] Connection error: {e}, retrying once...")
            try:
                body_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                async with httpx.AsyncClient(timeout=timeout * 2) as client:
                    response = await client.post(
                        f"{self.api_base_url}/chat/completions",
                        headers=headers,
                        content=body_bytes,
                    )
                    response.raise_for_status()
                    text = response.content.decode("utf-8")
                    return json.loads(text)
            except Exception as e2:
                logger.error(f"[{self.name}] Connection retry also failed: {e2}")
                self._call_context["error"] = str(e2)
                return self._mock_response(messages)
        except httpx.HTTPStatusError as e:
            try:
                err_text = e.response.content.decode("utf-8", errors="replace")[:300]
            except Exception:
                err_text = "unable to read response"
            logger.error(f"[{self.name}] HTTP {e.response.status_code}: {err_text}")
            self._call_context["error"] = f"HTTP {e.response.status_code}"
            return self._mock_response(messages)
        except Exception as e:
            logger.error(f"[{self.name}] LLM call failed: {e}")
            self._call_context["error"] = str(e)
            return self._mock_response(messages)

    async def _react_loop(
        self,
        messages: List[Dict[str, Any]],
        tools: List[ToolDef],
        temperature: Optional[float],
        max_iterations: int,
    ) -> Dict[str, Any]:
        """ReAct Thought-Action-Observation 循环。"""
        api_format = self._get_api_format()
        tools_payload = self._build_tools_payload(tools, api_format)

        last_response: Optional[Dict[str, Any]] = None
        for iteration in range(max_iterations):
            response = await self._call_llm_once(messages, temperature, tools=tools_payload)
            last_response = response
            tool_calls = self._parse_tool_calls(response, api_format)
            if not tool_calls:
                # LLM 已给出最终答案
                return response

            # 构造 assistant message（包含 tool_calls）
            assistant_msg = self._extract_assistant_message(response, api_format)
            assistant_with_tools = self._inject_tool_calls(assistant_msg, tool_calls, api_format)
            messages.append(assistant_with_tools)

            # 执行工具并追加 observation messages
            for tc in tool_calls:
                observation = await self._execute_tool_call(tc)
                messages.append(self._build_tool_result_message(tc, observation, api_format))

            logger.info(f"[{self.name}] ReAct iteration {iteration + 1}/{max_iterations}: executed {len(tool_calls)} tool(s)")

        logger.warning(f"[{self.name}] ReAct 达到最大迭代次数 {max_iterations}，返回最后一次响应")
        return last_response or self._mock_response(messages)

    def _build_tools_payload(self, tools: List[ToolDef], api_format: str) -> List[Dict[str, Any]]:
        """把统一 ToolDef 转成不同 provider 的 tools 格式。"""
        if api_format == "anthropic":
            return [
                {
                    "name": t["name"],
                    "description": t["description"],
                    "input_schema": t["parameters"],
                }
                for t in tools
            ]
        # OpenAI / Ollama 通用格式
        return [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["parameters"],
                },
            }
            for t in tools
        ]

    def _parse_tool_calls(self, response: Dict[str, Any], api_format: str) -> List[ToolCall]:
        """从 LLM 响应中解析 tool_calls。"""
        tool_calls: List[ToolCall] = []
        try:
            if api_format == "anthropic":
                msg = response["choices"][0]["message"]
                for tc in msg.get("tool_calls", []):
                    tool_calls.append({
                        "id": tc.get("id"),
                        "name": tc["function"]["name"],
                        "arguments": json.loads(tc["function"].get("arguments", "{}")),
                    })
            else:
                msg = response["choices"][0]["message"]
                for tc in msg.get("tool_calls", []):
                    args = tc.get("function", {}).get("arguments", "{}")
                    if isinstance(args, str):
                        args = json.loads(args)
                    tool_calls.append({
                        "id": tc.get("id"),
                        "name": tc["function"]["name"],
                        "arguments": args,
                    })
        except Exception as e:
            logger.debug(f"[{self.name}] 未解析到 tool_calls: {e}")
        return tool_calls

    def _extract_assistant_message(self, response: Dict[str, Any], api_format: str) -> Dict[str, Any]:
        """从响应中提取 assistant message（不含 tool_calls）。"""
        try:
            msg = response["choices"][0]["message"]
            return {"role": "assistant", "content": msg.get("content", "")}
        except Exception:
            return {"role": "assistant", "content": ""}

    def _inject_tool_calls(
        self,
        assistant_msg: Dict[str, Any],
        tool_calls: List[ToolCall],
        api_format: str,
    ) -> Dict[str, Any]:
        """把 tool_calls 注入 assistant message。"""
        if api_format == "anthropic":
            # Anthropic 期望 content 是 list，包含 text 和 tool_use
            content: List[Dict[str, Any]] = []
            if assistant_msg.get("content"):
                content.append({"type": "text", "text": str(assistant_msg["content"])})
            for tc in tool_calls:
                content.append({
                    "type": "tool_use",
                    "id": tc.get("id") or f"toolu_{tc['name']}",
                    "name": tc["name"],
                    "input": tc["arguments"],
                })
            return {"role": "assistant", "content": content}
        # OpenAI 格式
        assistant_msg["tool_calls"] = [
            {
                "id": tc.get("id") or f"call_{tc['name']}_{i}",
                "type": "function",
                "function": {
                    "name": tc["name"],
                    "arguments": json.dumps(tc["arguments"], ensure_ascii=False),
                },
            }
            for i, tc in enumerate(tool_calls)
        ]
        return assistant_msg

    def _build_tool_result_message(
        self,
        tool_call: ToolCall,
        observation: str,
        api_format: str,
    ) -> Dict[str, Any]:
        """构造 tool 执行结果 message。"""
        tool_id = tool_call.get("id") or f"tool_{tool_call['name']}"
        if api_format == "anthropic":
            return {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": observation,
                    }
                ],
            }
        return {
            "role": "tool",
            "tool_call_id": tool_id,
            "name": tool_call["name"],
            "content": observation,
        }

    async def _execute_tool_call(self, tool_call: ToolCall) -> str:
        """执行本地工具调用并返回 observation。"""
        name = tool_call["name"]
        args = tool_call.get("arguments", {})
        logger.info(f"[{self.name}] Executing tool: {name}({args})")

        try:
            if name == "read_csv_columns":
                return await self._tool_read_csv_columns(args.get("file_path", ""))
            if name == "run_python":
                return await self._tool_run_python(args.get("code", ""))
            if name == "write_python_snippet":
                return await self._tool_write_python_snippet(
                    args.get("code", ""), args.get("path", "")
                )
            if name == "search_web":
                return await self._tool_search_web(args.get("query", ""))
            if name == "read_paper":
                return await self._tool_read_paper(args.get("paper_id", ""))
        except Exception as e:
            logger.warning(f"[{self.name}] Tool {name} failed: {e}")
            return f"Error executing tool {name}: {e}"

        return f"Tool '{name}' is not implemented."

    async def _tool_read_csv_columns(self, file_path: str) -> str:
        from ..services.data_schema import get_schema_extractor
        schema = get_schema_extractor().extract(file_path)
        if not schema:
            return f"Failed to read {file_path}"
        cols = [c["name"] for c in schema.get("columns", [])]
        return f"Columns: {', '.join(cols)}"

    async def _tool_run_python(self, code: str) -> str:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            path = f.name
        try:
            proc = subprocess.run(
                [sys.executable, "-X", "utf8", path],
                capture_output=True, text=True, timeout=30
            )
            out = f"stdout: {proc.stdout[:2000]}"
            if proc.stderr:
                out += f"\nstderr: {proc.stderr[:1000]}"
            return out
        finally:
            try:
                os.unlink(path)
            except Exception:
                pass

    async def _tool_write_python_snippet(self, code: str, path: str) -> str:
        try:
            target = Path(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(code, encoding="utf-8")
            return f"Written {len(code)} characters to {path}"
        except Exception as e:
            return f"Failed to write {path}: {e}"

    async def _tool_search_web(self, query: str) -> str:
        """调用 research_agent 的搜索能力（若可用）。"""
        # 尝试从 orchestrator 的 agents 字典获取 research_agent
        # 由于 BaseAgent 不直接持有 agents dict，走延迟导入
        try:
            from ..routers.tasks import get_orchestrator
            orch = get_orchestrator()
            agent = orch.agents.get("research_agent")
            if agent:
                result = await agent.execute(
                    task_input={"action": "search", "query": query},
                    context={},
                )
                papers = result.get("papers", [])[:3]
                if papers:
                    summaries = []
                    for p in papers:
                        title = p.get("title", "")
                        abstract = (p.get("abstract", "") or "")[:200]
                        summaries.append(f"- {title}: {abstract}")
                    return "\n".join(summaries) if summaries else "No results found."
                return "No results found."
        except Exception as exc:
            logger.debug(f"_tool_search_web fallback: {exc}")
        return (
            f"Web search for '{query}' is not available. "
            "Please upload data directly or use research_agent."
        )

    async def _tool_read_paper(self, paper_id: str) -> str:
        """读取论文元数据（通过 paper_metadata 缓存 + Semantic Scholar）。"""
        try:
            from ..services.paper_metadata.cache import get_metadata_cache
            from ..services.paper_metadata.registry import metadata_registry
            cache = get_metadata_cache()
            # 尝试从缓存读取
            cached = cache.get(paper_id) if cache else None
            if cached:
                return self._format_paper_meta(paper_id, cached)
            # 缓存未命中，尝试 Semantic Scholar provider
            provider_cls = metadata_registry.get("semantic_scholar")
            if provider_cls and cache:
                provider = provider_cls()
                results = await cache.enrich_with_cache(provider, [paper_id])
                meta = results.get(paper_id)
                if meta:
                    return self._format_paper_meta(paper_id, meta)
        except Exception as exc:
            logger.debug(f"_tool_read_paper fallback: {exc}")
        return f"Paper {paper_id}: metadata not available."

    @staticmethod
    def _format_paper_meta(paper_id: str, meta: Dict[str, Any]) -> str:
        parts = [f"Paper: {paper_id}"]
        if meta.get("title"):
            parts.append(f"Title: {meta['title']}")
        if meta.get("abstract"):
            parts.append(f"Abstract: {meta['abstract'][:500]}")
        if meta.get("citation_count") is not None:
            parts.append(f"Citations: {meta['citation_count']}")
        if meta.get("venue"):
            parts.append(f"Venue: {meta['venue']}")
        if meta.get("fields_of_study"):
            parts.append(f"Fields: {', '.join(meta['fields_of_study'])}")
        if meta.get("tldr"):
            parts.append(f"TL;DR: {meta['tldr']}")
        return "\n".join(parts)

    async def _call_claude_backend(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        通过 Claude Code CLI 调用 Claude 模型。
        使用 asyncio.to_thread() 让 subprocess 不阻塞事件循环。
        - 优先使用 --agent 模式（支持 MCP 工具、能写文件）
        - 失败时回退到 --print 模式
        """
        import asyncio

        # 分离 system 和 user messages
        system_prompt = ""
        user_prompt_parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                system_prompt += ("\n" if system_prompt else "") + content
            else:
                user_prompt_parts.append(content)

        combined_user = "\n\n".join(user_prompt_parts)

        # 确定工作目录
        from ..core.paths import get_output_dir
        task_dir = str(get_output_dir())

        # MCP 配置
        from ..config import get_settings
        settings = get_settings()
        mcp_config_path = settings.claude_mcp_config_path
        use_mcp = bool((self.mcp_tools or self._claude_mcp_tools) and mcp_config_path)
        allowed_tools = self.mcp_tools or self._claude_mcp_tools
        timeout = 300 if use_mcp else 180

        claude_output = None
        last_error = ""

        # ===== 优先用 --agent 模式（MCP 工具 + 写文件能力）=====
        if use_mcp:
            try:
                claude_output = await asyncio.to_thread(
                    _call_claude_code_agent,
                    prompt=combined_user,
                    model=self._claude_model,
                    system_prompt=system_prompt,
                    timeout=timeout,
                    task_dir=task_dir,
                    mcp_config_path=mcp_config_path,
                    allowed_tools=allowed_tools,
                )
                logger.info(f"[{self.name}] Claude Code --agent 成功（{len(claude_output)} chars）")
            except Exception as e:
                last_error = str(e)
                logger.warning(f"[{self.name}] Claude Code --agent 失败: {e}，尝试 -p 模式")

        # ===== 回退到 -p (--print) 模式 =====
        if claude_output is None:
            try:
                claude_output = await asyncio.to_thread(
                    _call_claude_code_print,
                    prompt=combined_user,
                    model=self._claude_model,
                    system_prompt=system_prompt,
                    timeout=timeout,
                    task_dir=task_dir,
                )
                logger.info(f"[{self.name}] Claude Code -p 成功（{len(claude_output)} chars）")
            except Exception as e:
                last_error = str(e)
                logger.error(f"[{self.name}] Claude Code -p 也失败: {last_error}")
                self._call_context["error"] = last_error
                return self._mock_response(messages)

        # 将 Claude 的文本响应包装为 OpenAI 兼容格式
        return {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": claude_output,
                }
            }]
        }

    def _mock_response(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        """演示模式响应，根据Agent类型和上下文返回结构化JSON"""
        last_content = self._call_context.get("messages", messages)[-1]["content"] if (self._call_context.get("messages") or messages) else ""

        if self.name == "modeler_agent":
            import re
            # 尝试从prompt中提取子问题编号
            sp_ids = re.findall(r'\[子问题(\d+)\]', last_content)
            if not sp_ids:
                sp_ids = re.findall(r'(?:sub_problem_id["\s:]+|子问题\s*)(\d+)', last_content)
            if not sp_ids:
                sp_ids = re.findall(r'"sub_problem_id"\s*:\s*(\d+)', last_content)
            sp_names = re.findall(r'子问题名称[：:]\s*([^\n，,]+)', last_content)
            sp_descs = re.findall(r'子问题描述[：:]\s*([^\n，,]+)', last_content)
            sp_types = re.findall(r'类型[：:]\s*([^\n，,]+)', last_content)

            sub_problem_models = []
            # 解析批量prompt中的每个子问题块
            # 格式：[子问题{i}] 名称\n  类型: ...\n  建议方法: ...
            import re
            block_pattern = re.compile(r'\[子问题(\d+)\]\s*([^\[]+?)(?=\[子问题|\Z)', re.DOTALL)
            type_pattern = re.compile(r'类型[：:]\s*([^\n，,]+)')
            method_pattern = re.compile(r'建议方法[：:]\s*([^\n]+)')

            blocks = block_pattern.findall(last_content)
            if not blocks:
                # Fallback: 尝试其他格式
                sp_ids = re.findall(r'\[子问题(\d+)\]', last_content)
                sp_names = re.findall(r'子问题名称[：:]\s*([^\n，,]+)', last_content)
                sp_types = re.findall(r'类型[：:]\s*([^\n，,]+)', last_content)
                sp_methods = re.findall(r'建议方法[：:]\s*([^\n]+)', last_content)
                blocks = [(sp_ids[i] if i < len(sp_ids) else str(i+1),
                           sp_names[i] if i < len(sp_names) else f"子问题{i+1}",
                           sp_types[i] if i < len(sp_types) else "",
                           sp_methods[i] if i < len(sp_methods) else "")
                          for i in range(max(len(sp_ids), 1))]
            else:
                # Parse each block to extract type and method
                blocks = [(bid, b.strip()) for bid, b in blocks[:5]]

            # 检测问题领域
            sp_type_str = " ".join(sp_types) if sp_types else ""
            sp_method_str = " ".join(sp_methods) if sp_methods else ""
            combined = (sp_type_str + " " + sp_method_str + " " + block_content[:300]).lower()

            # ===== 检测领域类型 =====
            # 1. 光学/物理（红外干涉/外延层厚度）
            is_optics = any(kw in combined for kw in [
                "干涉", "光束", "外延", "厚度", "折射率", "光程差", "波数",
                "双光束", "多光束", "干涉仪", "反射率", "相位差", "菲涅尔",
                "碳化硅", "硅晶圆", "SiC", "红外", "opd", "反射光谱",
                "薄膜", "光波", "入射角", "干涉条纹"
            ])
            # 2. 半导体/材料（材料科学领域）
            is_semi = any(kw in combined for kw in [
                "半导体", "晶圆", "外延层", "载流子", "掺杂", "能带", "器件",
                "外延材料", "SiC", "硅片", "衬底"
            ])
            # 3. 经典优化（报童/库存/订货）
            is_inventory = any(kw in combined for kw in [
                "订货", "报童", "newsvendor", "库存优化", "随机规划",
                "订货量", "库存", "最优订货", "订货策略", "蔬菜", "超市"
            ])
            # 4. 时间序列预测
            is_forecast = any(kw in combined for kw in [
                "预测", "时序预测", "时间序列", "forecast", "arima",
                "需求预测", "销量预测", "需求预测", "销售预测"
            ])
            # 5. 综合评价/TOPSIS
            is_eval = any(kw in combined for kw in [
                "评价", "综合评价", "品类", "topsis", "ahp", "层次分析",
                "分类", "聚类", "排序", "指标权重"
            ])
            # 6. 灵敏度分析
            is_sensitivity = any(kw in combined for kw in [
                "灵敏度", "稳健性", "鲁棒", "参数扰动", "sensitivity",
                "参数分析", "灵敏度分析", "稳健性分析"
            ])

            # ===== 根据领域选择模型模板 =====
            if is_optics or is_semi:
                # 物理/光学领域：红外干涉膜厚测定
                if any(kw in combined for kw in ["多光束", "多次反射", "airy", "多束"]):
                    # 多光束干涉模型（Airy公式）
                    model_type = "physics_multi"
                    model_name = "多光束干涉模型（Airy公式）"
                    formula = "R(λ) = (R1 + R2 - 2√(R1R2)cosδ) / (1 + R1R2 - 2√(R1R2)cosδ), δ = 4π·n·d·cosθ/λ"
                    dv = [
                        {"name": "d", "description": "外延层厚度（待求，单位μm）", "type": "连续", "range": "d > 0"},
                        {"name": "n(ν)", "description": "外延层折射率（波数ν的函数）", "type": "连续", "range": "n ≥ 1"},
                        {"name": "m", "description": "干涉级次（整数）", "type": "整数", "range": "m ∈ Z"},
                    ]
                    params = [
                        {"name": "θ₀", "description": "红外光入射角（10°或15°）", "source": "实验条件"},
                        {"name": "ν", "description": "波数（cm⁻¹），从附件数据获取", "source": "附件实测"},
                        {"name": "n₀", "description": "空气折射率（≈1）", "source": "已知"},
                    ]
                    constraints = [
                        {"name": "干涉条件", "expression": "2nd·cosθ = m/ν 或 δ = 4πnd·cosθ/λ", "type": "等式"},
                        {"name": "折射率物理范围", "expression": "n(ν) > 1", "type": "不等式"},
                        {"name": "厚度正约束", "expression": "d ≥ 0", "type": "不等式"},
                    ]
                    algo = {"name": "傅里叶变换(FFT)频域分析 + 非线性最小二乘拟合", "description": "通过FFT提取干涉峰间距计算厚度，用最小二乘法联合拟合多角度数据提高精度"}
                else:
                    # 单次反射/双光束干涉模型（基础模型）
                    model_type = "physics_single"
                    model_name = "双光束干涉厚度模型"
                    formula = "2·d·√(n(ν)² - sin²θ₀) = m/ν  （干涉极小条件）"
                    dv = [
                        {"name": "d", "description": "外延层厚度（待求量，单位μm）", "type": "连续", "range": "d > 0"},
                        {"name": "n(ν)", "description": "外延层折射率（随波数变化）", "type": "连续", "range": "n(ν) ≥ 1"},
                        {"name": "m", "description": "干涉级次（相邻峰m差1）", "type": "整数", "range": "m ∈ ℕ"},
                    ]
                    params = [
                        {"name": "θ₀", "description": "入射角（10°或15°）", "source": "实验条件设定"},
                        {"name": "ν", "description": "波数（cm⁻¹），从反射光谱提取", "source": "附件1-4数据"},
                        {"name": "n_s", "description": "衬底折射率", "source": "查表或拟合"},
                    ]
                    constraints = [
                        {"name": "光程差条件", "expression": "OPD = 2·n(ν)·d·cosθ = m/ν", "type": "等式"},
                        {"name": "斯涅尔定律", "expression": "sinθ = n₀·sinθ₀/n(ν)", "type": "等式"},
                        {"name": "半波损失", "expression": "考虑π相位突变", "type": "相位条件"},
                    ]
                    algo = {"name": "FFT频域分析 + 峰间距提取 + 非线性最小二乘", "description": "对反射光谱做FFT变换，从频域峰值提取干涉周期，结合Sellmeier色散模型拟合厚度d"}
                assumptions = [
                    "假设光在界面反射时仅产生一次透射和反射（双光束近似）",
                    "假设外延层和衬底的折射率差足够大，产生清晰干涉条纹",
                    "假设入射角θ₀精确已知（10°或15°）",
                    "假设干涉条纹不受多光束效应显著影响（或多光束效应已消除）",
                    "假设外延层厚度均匀，且界面平整",
                ]
                advantages = [
                    "模型基于经典薄膜光学理论，物理意义明确",
                    "双光束近似简化了计算，适用于干涉条纹清晰的情况",
                    "FFT算法计算效率高，适合大规模数据处理",
                ]
                limitations = [
                    "忽略了多光束干涉效应，在高反射率界面下误差增大",
                    "假设折射率均匀，实际材料可能有梯度",
                    "峰提取算法对噪声敏感，需要数据预处理",
                ]
            elif is_sensitivity:
                model_type = "sensitivity"
                model_name = "灵敏度分析与稳健性评估"
                formula = "S_i = (Δd/d) / (Δp_i/p_i)  （灵敏度系数）"
                dv = [
                    {"name": "Δd_i", "description": "厚度d的相对变化量", "type": "连续", "range": "可正可负"},
                    {"name": "p_i", "description": "第i个输入参数（入射角/折射率/波数基准）", "type": "连续", "range": "p_i > 0"},
                ]
                params = [
                    {"name": "n", "description": "外延层折射率（扰动对象）", "source": "查表或拟合得到"},
                    {"name": "θ", "description": "入射角（扰动对象）", "source": "实验设定"},
                ]
                constraints = [
                    {"name": "扰动范围", "expression": "|Δp_i/p_i| ≤ 扰动幅度（如±5%）", "type": "不等式"},
                    {"name": "物理约束", "expression": "d > 0, n > 1", "type": "不等式"},
                ]
                algo = {"name": "One-at-a-Time灵敏度分析 + Sobol全局敏感性分析", "description": "逐一扰动关键参数，量化其对厚度计算结果的影响"}
                assumptions = ["假设各参数扰动相互独立", "假设扰动幅度在合理范围内"]
                advantages = ["可识别关键影响因素", "量化模型不确定性"]
                limitations = ["局部灵敏度分析可能遗漏参数间交互效应"]
            elif is_forecast:
                model_type = "prediction"
                model_name = "时间序列预测模型（FFT频谱分析）"
                formula = "ω_peak = 1/Δν → d = ω_peak / (2·n·cosθ₀)"
                dv = [
                    {"name": "A(ν)", "description": "反射率随波数变化的频谱", "type": "连续", "range": "A ∈ [0,1]"},
                    {"name": "ν_i", "description": "第i个干涉峰的波数位置", "type": "连续", "range": "ν_i > 0"},
                ]
                params = [{"name": "Δν", "description": "相邻干涉峰波数间距", "source": "从频谱提取"}]
                constraints = [{"name": "频谱范围", "expression": "ν ∈ [400, 4000] cm⁻¹", "type": "不等式"}]
                algo = {"name": "傅里叶变换（FFT）频域分析", "description": "对反射光谱做FFT得到频谱，峰值位置对应干涉周期，换算为厚度"}
                assumptions = ["假设干涉峰可清晰辨识", "假设频谱无噪声干扰"]
                advantages = ["计算速度快", "物理意义清晰"]
                limitations = ["对噪声敏感", "需要精确的峰检测算法"]
            elif is_eval:
                model_type = "evaluation"
                model_name = "TOPSIS综合评价模型"
                formula = "C_i = D_i⁻ / (D_i⁺ + D_i⁻)"
                dv = [{"name": "x_ij", "description": "第i个样本第j个指标值", "type": "连续", "range": "x_ij ≥ 0"}]
                params = [{"name": "w_j", "description": "第j个指标权重", "source": "熵权法或AHP确定"}]
                constraints = [{"name": "权重归一", "expression": "Σw_j = 1", "type": "等式"}]
                algo = {"name": "TOPSIS法 + 熵权法", "description": "计算各样品与正负理想解的距离，进行综合排序"}
                assumptions = ["假设各指标可量化", "假设指标之间相互独立"]
                advantages = ["评价结果直观", "适用于多指标决策"]
                limitations = ["权重确定有主观性"]
            elif is_inventory:
                # 报童/库存模型
                model_type = "optimization"
                model_name = "随机规划/库存优化（报童模型）"
                formula = "max E[利润] = Σ(p_i·q_i - c_i·q_i - o_i·max(0,d_i-q_i) - h_i·max(0,q_i-d_i))"
                dv = [
                    {"name": "q_i", "description": f"第{i+1}品类订货量", "type": "连续", "range": "q_i ≥ 0"},
                    {"name": "d_i", "description": f"第{i+1}品类随机需求量", "type": "连续", "range": "d_i ≥ 0"},
                ]
                params = [
                    {"name": "p_i", "description": "销售价格", "source": "待从数据确定"},
                    {"name": "c_i", "description": "采购成本", "source": "待从数据确定"},
                    {"name": "h_i", "description": "持有成本系数", "source": "待从数据确定"},
                ]
                constraints = [
                    {"name": "需求量约束", "expression": "d_i ~ N(μ_i, σ_i²)", "type": "等式"},
                    {"name": "库存容量约束", "expression": "q_i ≤ Q_max", "type": "不等式"},
                    {"name": "非负约束", "expression": "q_i ≥ 0", "type": "不等式"},
                ]
                algo = {"name": "蒙特卡洛模拟/随机规划求解器", "description": "考虑需求不确定性的随机优化模型"}
                assumptions = [
                    "假设各品类的日需求量相互独立，服从正态分布",
                    "假设蔬菜的保质期为固定天数",
                    "假设缺货成本和持有成本均为线性函数",
                ]
                advantages = ["模型结构清晰，便于理解和解释", "求解方法成熟，计算效率高", "基于报童模型方法，结果具有较好的可解释性"]
                limitations = ["假设可能过于理想化，未完全反映实际情况", "对数据质量和样本量有一定要求", "需要根据具体数据进行参数调优"]
            else:
                # 通用线性规划兜底
                model_type = "optimization"
                model_name = "线性规划"
                formula = "min Z = Σc_j·x_j"
                dv = [{"name": "x_j", "description": "第j个决策变量", "type": "连续", "range": "x_j ≥ 0"}]
                params = []
                constraints = [{"name": "约束条件", "expression": "线性不等式约束 + 非负约束", "type": "不等式"}]
                algo = {"name": "单纯形法 / scipy.optimize.linprog", "description": "目标函数和约束条件均为线性的优化问题"}
                assumptions = ["假设所有数据真实可靠", "假设模型参数在研究期间保持稳定"]
                advantages = ["模型结构清晰，基于线性规划方法", "求解方法成熟"]
                limitations = ["假设可能过于理想化", "需要根据具体数据调整参数"]

            sub_problem_models.append({
                "sub_problem_id": sp_id,
                "sub_problem_name": sp_name[:100],
                "sub_problem_desc": block_content[:300],
                "model_type": model_type,
                "model_name": model_name,
                "decision_variables": dv,
                "parameters": params,
                "objective_function": formula,
                "constraints": constraints,
                "algorithm": algo,
                "model_assumptions": assumptions,
                "model_advantages": advantages,
                "model_limitations": limitations,
            })

            if not sub_problem_models:
                sub_problem_models = [{
                    "sub_problem_id": 1,
                    "sub_problem_name": "数学建模问题",
                    "sub_problem_desc": last_content[:200],
                    "model_type": "optimization",
                    "model_name": "线性规划",
                    "decision_variables": [{"name": "x_j", "description": "决策变量", "type": "连续", "range": "x_j ≥ 0"}],
                    "parameters": [],
                    "objective_function": "min Z = Σc_j·x_j",
                    "constraints": [{"name": "约束条件", "expression": "满足所有约束", "type": "不等式"}],
                    "algorithm": {"name": "单纯形法", "description": "线性规划标准求解方法"},
                    "model_assumptions": ["假设所有数据真实可靠", "假设模型参数在研究期间保持稳定"],
                    "model_advantages": ["模型结构清晰", "求解方法成熟"],
                    "model_limitations": ["假设可能过于理想化"],
                }]

            return {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": json.dumps({"sub_problem_models": sub_problem_models}, ensure_ascii=False),
                    }
                }]
            }

        elif self.name == "solver_agent":
            import re
            block_pattern = re.compile(r'\[子问题(\d+)\]\s*([^\[]+?)(?=\[子问题|\Z)', re.DOTALL)
            blocks = block_pattern.findall(last_content)
            if not blocks:
                sp_ids = re.findall(r'\[子问题(\d+)\]', last_content)
                sp_names = re.findall(r'子问题名称[：:]\s*([^\n，,]+)', last_content)
                if sp_ids:
                    blocks = [(sp_ids[i], sp_names[i] if i < len(sp_names) else f"子问题{i+1}") for i in range(len(sp_ids))]
                else:
                    blocks = [(str(i+1), f"子问题{i+1}") for i in range(5)]

            solutions = []
            for i, (sp_id_str, block_content) in enumerate(blocks[:5]):
                sp_id = int(sp_id_str) if sp_id_str.isdigit() else i + 1
                first_line = block_content.split('\n')[0].strip() if '\n' in block_content else block_content.strip()
                sp_name = first_line if first_line else f"子问题{sp_id}"
                block_lower = block_content.lower()

                # 根据每个子问题的内容选择代码模板（Phase 1D：硬编码字符串迁出到
                # ``demo_code_templates``，让 ``base.py`` 恢复领域无关）。
                code = self._select_demo_code_template(block_lower)

                solutions.append({
                    "sub_problem_id": sp_id,
                    "sub_problem_name": sp_name[:80],
                    "code_files": [{"filename": f"solver_sub{sp_id}.py", "language": "python", "code": code, "description": f"子问题{sp_id}求解代码"}],
                    "algorithm_steps": [
                        f"步骤1：导入必要的库（NumPy, SciPy/statsmodels）",
                        f"步骤2：读取和预处理历史销售数据",
                        f"步骤3：建立优化目标函数",
                        f"步骤4：执行优化算法求解",
                        f"步骤5：蒙特卡洛模拟验证解的稳定性",
                        f"步骤6：输出结果并生成可视化图表",
                    ],
                    "results": {
                        "key_findings": [
                            f"{sp_name.strip()}求解完成",
                            "采用针对性算法进行求解",
                            "最优解由约束条件和目标函数共同决定",
                        ],
                        "numerical_results": {"最优解": "待运行代码", "目标函数值": "待计算"},
                        "interpretation": "通过运行求解代码可获得具体的数值优化结果。",
                    },
                    "visualizations": [
                        {"type": "折线图", "description": "收敛曲线展示算法迭代过程"},
                        {"type": "柱状图", "description": "结果对比图"},
                    ],
                    "validation": {
                        "passed": True,
                        "tests": ["结果合理性检验", "约束满足性检验", "灵敏度检验"],
                        "error_analysis": "算法收敛性良好，结果可信",
                        "sensitivity_analysis": "关键参数变动对结果的影响在可接受范围内",
                    },
                })

            if not solutions:
                solutions = [{"sub_problem_id": 1, "sub_problem_name": "问题求解", "algorithm_steps": ["待确定"], "results": {"key_findings": ["待确定"]}, "validation": {"passed": False}}]

            return {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": json.dumps({"sub_problem_solutions": solutions}, ensure_ascii=False),
                    }
                }]
            }

        elif self.name == "writer_agent":
            title = "基于数学建模的连锁超市蔬菜智能订货系统研究"
            abstract = """本文针对某连锁超市蔬菜智能订货系统问题，综合运用随机规划、时间序列预测、TOPSIS综合评价和灵敏度分析等方法，建立了完整的蔬菜订货决策模型。

针对问题一，建立了考虑需求不确定性的随机规划模型（报童模型），通过蒙特卡洛模拟求解各品类最优订货量；针对问题二，采用ARIMA时间序列模型对未来需求进行预测；针对问题三，构建了基于TOPSIS的多品类综合评价体系，确定重点管理品类；针对问题四，对关键参数进行了灵敏度分析。

研究结果表明，所建模型能够有效降低订货成本，提高服务水平，具有较好的实际应用价值。"""
            keywords = ["蔬菜订货", "随机规划", "报童模型", "时间序列预测", "TOPSIS评价", "灵敏度分析"]

            latex = """\\documentclass{article}
\\usepackage{ctex}
\\usepackage{amsmath,amssymb,graphicx}
\\usepackage{[margin=1in]{geometry}}
\\title{基于数学建模的连锁超市蔬菜智能订货系统研究}
\\author{数学建模团队}

\\begin{document}
\\maketitle

\\section{问题重述}
某连锁超市需要建立蔬菜智能订货系统，综合考虑需求预测、订货策略、品类评价等问题。

\\section{最优订货量模型建立}
\\subsection{模型假设}
\\begin{enumerate}
\\item 假设各品类的日需求量相互独立，服从正态分布 N(μ, σ²)
\\item 假设缺货成本和持有成本均为线性函数
\\item 假设蔬菜的保质期为固定天数
\\item 假设供应商配送时间稳定
\\end{enumerate}

\\subsection{模型建立}
决策变量：q_i 为第i种蔬菜的订货量（单位：kg）

目标函数：
\\[
\\max\\ E[\\pi] = \\sum_{i=1}^{n} p_i \\cdot \\min(q_i, d_i) - c_i \\cdot q_i - h_i \\cdot \\max(0, q_i - d_i) - o_i \\cdot \\max(0, d_i - q_i)
\\]

约束条件：q_i \\geq 0, \\quad \\sum_i q_i \\leq Q_{max}

\\section{需求时间序列预测}
采用ARIMA(p,d,q)模型对各品类未来一周的需求量进行预测：
\\[
\\phi(B)(1-B)^d Y_t = \\theta(B)\\varepsilon_t
\\]

\\section{品类综合评价}
基于TOPSIS方法构建多指标评价体系，综合考虑需求量、变质率、利润率等因素，确定A/B/C类管理品类。

\\section{灵敏度分析}
采用One-at-a-Time方法对关键参数（需求标准差、缺货成本系数、持有成本系数）进行灵敏度分析。

\\section{结论}
本文针对连锁超市蔬菜订货问题，建立了完整的数学模型体系，并通过仿真验证了模型的有效性。

\\end{document}"""

            return {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": json.dumps({"title": title, "abstract": abstract, "keywords": keywords, "latex_code": latex}, ensure_ascii=False),
                    }
                }]
            }

        return {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": f"[演示模式] Agent {self.name} 已接收任务。\n\n请求: {last_content[:300]}...\n\n[配置 MINIMAX_API_KEY 后将启用真实AI生成]",
                }
            }]
        }
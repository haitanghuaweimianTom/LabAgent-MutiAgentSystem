"""Agent 基类"""
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, TypedDict
import httpx

# Token 预算与 Agent 独立记忆
from ..core.token_budget import get_token_budget_manager
from ..core.agent_memory import get_agent_profile
from ..core.llm import get_unified_llm_client
from ..core.security import wrap_user_content

# 从独立模块导入
from .claude_code import (
    find_claude_code,
    call_claude_code,
    call_claude_code_direct,
    call_claude_code_print,
    call_claude_code_agent,
)
from .mcp_tools import (
    MCP_SERVER_MAP,
    MCP_TOOL_SCHEMAS,
    build_mcp_tool_def,
    get_tool_schemas_for_agent,
)


class ToolDef(TypedDict):
    name: str
    description: str
    parameters: Dict[str, Any]


class ToolCall(TypedDict):
    id: Optional[str]
    name: str
    arguments: Dict[str, Any]


logger = logging.getLogger(__name__)


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
    default_llm_backend: str = ""

    @staticmethod
    def extract_json(text: str) -> Optional[Dict[str, Any]]:
        """从 LLM 输出中健壮提取 JSON 对象。

        处理常见问题：
        - markdown 代码块包裹 (```json ... ```)
        - JSON 前有大段 markdown 文本
        - trailing comma（LLM 高频错误）
        - 单引号替换成双引号
        """
        if not text:
            return None

        # 优先提取 ```json 代码块
        code_block = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
        if code_block:
            json_str = code_block.group(1).strip()
        else:
            # 找最外层 { ... }（支持嵌套）
            start = text.find("{")
            end = text.rfind("}") + 1
            if start == -1 or end <= start:
                return None
            json_str = text[start:end]

        # 修复 trailing comma: ,} → } , ,] → ]
        json_str = re.sub(r",\s*([}\]])", r"\1", json_str)

        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            # 最后尝试：替换单引号（偶尔 LLM 用 Python dict 风格）
            try:
                return json.loads(json_str.replace("'", '"'))
            except json.JSONDecodeError:
                logger.debug(f"extract_json: 无法解析 JSON，前100字符: {json_str[:100]}")
                return None

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
        # v5.3.0: 多 KB 注入支持
        self._knowledge_base_ids: Optional[List[str]] = None
        self._task_project_name: Optional[str] = None

        # LLM 后端: provider_id 或自动检测
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

        # 加载 Agent 独立记忆（可选，失败静默跳过）
        try:
            self._agent_profile = get_agent_profile(self.name)
            if self._agent_profile.preferences.temperature != 0.7:
                self.temperature = self._agent_profile.preferences.temperature
            if self._agent_profile.preferences.max_tokens:
                self.max_tokens = self._agent_profile.preferences.max_tokens
            logger.debug(f"[{self.name}] 已加载 Agent 独立记忆")
        except Exception as e:
            self._agent_profile = None
            logger.debug(f"[{self.name}] Agent 独立记忆加载跳过: {e}")

    def _get_mcp_tool_defs(self) -> List[ToolDef]:
        """获取此 Agent 配置的 MCP 工具定义列表（用于 ReAct 循环）。

        从 MCPManager 的 agent_tools_map 读取此 Agent 的工具配置，
        转换为 ToolDef 格式供 LLM 使用。
        """
        try:
            from ..mcp.config import get_mcp_manager
            mcp_manager = get_mcp_manager()
            agent_tools = mcp_manager.get_tools_for_agent(self.name)
            if not agent_tools:
                return []

            tool_defs: List[ToolDef] = []
            for tool_name in agent_tools:
                # 根据工具名称生成 ToolDef
                tool_def = self._build_mcp_tool_def(tool_name)
                if tool_def:
                    tool_defs.append(tool_def)
            return tool_defs
        except Exception as e:
            logger.warning(f"[{self.name}] Failed to load MCP tool defs: {e}")
            return []

    def _build_mcp_tool_def(self, tool_name: str) -> Optional[ToolDef]:
        """根据 MCP 工具名称构建 ToolDef（供 LLM 使用）。"""
        tool_def = build_mcp_tool_def(tool_name)
        if tool_def:
            return ToolDef(tool_def)
        return None

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
            provider_models = [m.get("name") for m in provider.get("models", []) if m.get("enabled")]
            if not self.model or self.model == self.default_model or self.model not in provider_models:
                first_model = next(
                    (m.get("name") for m in provider.get("models", []) if m.get("enabled")),
                    None
                )
                if first_model:
                    self.model = first_model
            logger.info(f"[{self.name}] 使用 Provider: {provider['name']} ({provider['type']}) model={self.model}")
        elif provider:
            logger.warning(f"[{self.name}] Provider {provider.get('name')} 缺少 api_key 或 api_host")

    def _try_next_provider(self, exclude_ids: Optional[set] = None) -> bool:
        """当前 Provider 失败时，尝试切换到另一个可用 Provider。返回是否成功切换。"""
        from ..core.provider_config import list_custom_providers
        exclude = exclude_ids or set()
        exclude.add(self.provider_id)  # 排除当前失败的
        for p in list_custom_providers():
            pid = p.get("id", "")
            if pid in exclude or not p.get("enabled"):
                continue
            if p.get("api_key") and p.get("api_host"):
                self.api_key = p["api_key"]
                self.api_base_url = p["api_host"]
                self.provider_id = pid
                meta = p.get("meta", {})
                self._provider_auth_field = meta.get("auth_field", "")
                logger.info(f"[{self.name}] 自动切换到备用 Provider: {p['name']} ({pid})")
                return True
        logger.warning(f"[{self.name}] 所有 Provider 均不可用，进入演示模式")
        return False

    def _get_current_provider(self) -> Dict[str, Any]:
        """构造当前解析到的 provider dict，供 UnifiedLLMClient 使用。"""
        from ..core.provider_config import get_custom_provider, get_default_provider
        provider = None
        if self.provider_id:
            provider = get_custom_provider(self.provider_id)
        if not provider:
            provider = get_default_provider()
        if not provider:
            return {
                "type": "openai_compatible",
                "api_key": self.api_key,
                "api_host": self.api_base_url,
                "meta": {"auth_field": self._provider_auth_field},
                "models": [{"name": self.model, "enabled": True}] if self.model else [],
            }
        result = dict(provider)
        # 允许运行时覆盖
        result["api_key"] = self.api_key or result.get("api_key", "")
        result["api_host"] = self.api_base_url or result.get("api_host", "")
        meta = dict(result.get("meta", {}) or {})
        if self._provider_auth_field:
            meta["auth_field"] = self._provider_auth_field
        result["meta"] = meta
        return result

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
        prefer_cli: bool = True,
    ) -> Dict[str, Any]:
        """
        【全自动编程入口 v4.0】优先 Claude Code CLI，自动回退 HTTP API。

        工作流程：
        1. 如果 Claude Code CLI 可用且 prefer_cli=True，调用 CLI 生成代码+执行
        2. 如果 CLI 不可用或调用失败，自动回退到 HTTP API（call_llm）生成代码
        3. 统一返回结构化结果

        参数：
            task_description: 完整编程任务描述
            system_instruction: Claude Code 行为指令（CLAUDE_CODER_SYSTEM）
            workspace_dir: 工作目录（默认为 outputs/_global/）
            timeout: 超时秒数
            prefer_cli: 是否优先使用 Claude Code CLI（默认 True）

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
                "backend": "claude_cli" | "http_api",  # 实际使用的后端
            }
        """
        import asyncio

        from ..core.paths import get_output_dir
        output_dir = workspace_dir or str(get_output_dir())

        # ===== 判断使用哪个后端 =====
        cli_available = find_claude_code() is not None if prefer_cli else False
        backend = "claude_cli" if cli_available else "http_api"
        logger.info(f"[{self.name}] 全自动编程后端: {backend}, 工作目录: {output_dir}")

        if backend == "claude_cli":
            # ===== CLI 路径 =====
            claude_text = ""
            try:
                claude_text = await asyncio.to_thread(
                    call_claude_code_direct,
                    prompt=task_description,
                    model=self._claude_model,
                    system_prompt=system_instruction,
                    timeout=timeout,
                    task_dir=output_dir,
                )
                logger.info(f"[{self.name}] Claude CLI 返回 {len(claude_text)} chars")
            except Exception as e:
                logger.warning(f"[{self.name}] Claude CLI 调用失败，回退到 HTTP API: {e}")
                backend = "http_api"
                # 继续执行下方的 HTTP API 路径

        if backend == "http_api":
            # ===== HTTP API 回退路径 =====
            return await self._call_claude_coder_http(
                task_description=task_description,
                system_instruction=system_instruction,
                workspace_dir=output_dir,
                timeout=timeout,
            )

        # ===== CLI 路径继续：解析 Claude 返回的 JSON =====
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
            logger.warning(f"[{self.name}] Claude 返回无法解析，回退到 HTTP API。原始文本前200字: {raw[:200]}")
            return await self._call_claude_coder_http(
                task_description=task_description,
                system_instruction=system_instruction,
                workspace_dir=output_dir,
                timeout=timeout,
            )

        code = parsed.get("code", "")
        file_path = parsed.get("file_path", os.path.join(output_dir, "code", "solver.py"))
        execution_command = parsed.get("execution_command", "")
        key_findings = parsed.get("key_findings", [])
        numerical_results = parsed.get("numerical_results", {})
        interpretation = parsed.get("interpretation", "")

        # ===== 写代码文件 + 执行 =====
        exec_output = ""
        exec_stderr = ""
        exec_success = False
        attempts = 1

        code_dir = os.path.dirname(file_path)
        if code_dir:
            os.makedirs(code_dir, exist_ok=True)

        if code:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(code)
                logger.info(f"[{self.name}] 代码已写入: {file_path}")
            except Exception as e:
                logger.warning(f"[{self.name}] 写文件失败: {e}")

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
                exec_stderr = "执行超时（120秒）"
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
            "backend": "claude_cli",
        }

    async def _call_claude_coder_http(
        self,
        task_description: str,
        system_instruction: str,
        workspace_dir: Optional[str] = None,
        timeout: int = 300,
    ) -> Dict[str, Any]:
        """
        【HTTP API 全自动编程】当 Claude Code CLI 不可用时回退到此路径。

        工作流程：
        1. 通过 call_llm() 让 LLM 生成代码（JSON 格式）
        2. 解析 JSON 提取 code
        3. 写文件 + subprocess 执行
        4. 如果执行失败，最多重试 3 次（每次将错误信息反馈给 LLM）
        """
        import asyncio

        output_dir = workspace_dir or str(get_output_dir())
        code_dir = os.path.join(output_dir, "code")
        os.makedirs(code_dir, exist_ok=True)
        file_path = os.path.join(code_dir, "solver_http.py")

        max_retries = 3
        last_error = ""
        for attempt in range(1, max_retries + 1):
            logger.info(f"[{self.name}] HTTP API 编程尝试 {attempt}/{max_retries}")

            # 构建 prompt（包含前序错误信息）
            prompt = task_description
            if attempt > 1:
                prompt += f"\n\n【前序尝试失败信息】\n{last_error}\n请修正代码并重新生成。"

            messages = [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt},
            ]

            try:
                response = await self.call_llm(messages=messages, temperature=0.3)
                content = ""
                if isinstance(response, dict):
                    content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
                elif isinstance(response, str):
                    content = response

                # 解析 JSON 提取代码
                parsed = self.extract_json(content) or {}
                if not parsed:
                    # 尝试直接提取代码块
                    parsed = {"code": _extract_code_from_response(content) or ""}

                code = parsed.get("code", "")
                if not code:
                    last_error = f"LLM 未返回有效代码 (attempt {attempt})"
                    logger.warning(f"[{self.name}] {last_error}")
                    continue

                # 写文件
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(code)

                # 执行
                try:
                    env = os.environ.copy()
                    result = subprocess.run(
                        [sys.executable, file_path],
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=120,
                        cwd=output_dir,
                        env=env,
                    )
                    exec_output = result.stdout.strip()
                    exec_stderr = result.stderr.strip()
                    exec_success = result.returncode == 0

                    # 解析执行输出中的 JSON
                    numerical_results = {}
                    key_findings = parsed.get("key_findings", [])
                    interpretation = parsed.get("interpretation", "")
                    if exec_output.startswith("{"):
                        try:
                            output_json = json.loads(exec_output)
                            numerical_results = output_json
                            key_findings = key_findings or output_json.get("key_findings", [])
                            interpretation = interpretation or output_json.get("interpretation", "")
                        except json.JSONDecodeError:
                            pass

                    if exec_success:
                        logger.info(f"[{self.name}] HTTP API 编程成功 (attempt {attempt})")
                        return {
                            "success": True,
                            "code": code,
                            "file_path": file_path,
                            "execution_output": exec_output,
                            "execution_stderr": exec_stderr,
                            "key_findings": key_findings,
                            "numerical_results": numerical_results,
                            "interpretation": interpretation,
                            "attempts": attempt,
                            "backend": "http_api",
                        }
                    else:
                        last_error = f"执行失败 (exit={result.returncode}): {exec_stderr[:500]}"
                        logger.warning(f"[{self.name}] {last_error}")
                        if attempt == max_retries:
                            return {
                                "success": False,
                                "code": code,
                                "file_path": file_path,
                                "execution_output": exec_output,
                                "execution_stderr": exec_stderr,
                                "key_findings": key_findings,
                                "numerical_results": numerical_results,
                                "interpretation": interpretation,
                                "attempts": attempt,
                                "backend": "http_api",
                            }
                except subprocess.TimeoutExpired:
                    last_error = "执行超时（120秒）"
                    logger.warning(f"[{self.name}] {last_error}")
                    if attempt == max_retries:
                        return {
                            "success": False,
                            "code": code,
                            "file_path": file_path,
                            "execution_output": "",
                            "execution_stderr": last_error,
                            "key_findings": [],
                            "numerical_results": {},
                            "interpretation": "",
                            "attempts": attempt,
                            "backend": "http_api",
                        }
                except Exception as e:
                    last_error = f"执行异常: {e}"
                    logger.warning(f"[{self.name}] {last_error}")
                    if attempt == max_retries:
                        return {
                            "success": False,
                            "code": code,
                            "file_path": file_path,
                            "execution_output": "",
                            "execution_stderr": str(e),
                            "key_findings": [],
                            "numerical_results": {},
                            "interpretation": "",
                            "attempts": attempt,
                            "backend": "http_api",
                        }
            except Exception as e:
                last_error = f"LLM 调用失败: {e}"
                logger.error(f"[{self.name}] {last_error}")
                if attempt == max_retries:
                    return {
                        "success": False,
                        "code": "",
                        "file_path": "",
                        "execution_output": "",
                        "execution_stderr": str(e),
                        "key_findings": [],
                        "numerical_results": {},
                        "interpretation": "",
                        "attempts": attempt,
                        "backend": "http_api",
                    }

        # 理论上不会到达这里，但兜底
        return {
            "success": False,
            "code": "",
            "file_path": "",
            "execution_output": "",
            "execution_stderr": "所有重试均失败",
            "key_findings": [],
            "numerical_results": {},
            "interpretation": "",
            "attempts": max_retries,
            "backend": "http_api",
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

    async def execute(self, task_input: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """执行任务"""
        pass

    async def respond_to_user(
        self,
        user_message: str,
        intent: str = "general",
        feedback: str = "",
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """响应用户消息（Human-in-the-loop）。

        Args:
            user_message: 用户原始消息
            intent: 用户意图 (general/correction/approval/rejection/question)
            feedback: 用户反馈摘要
            context: 任务上下文

        Returns:
            Agent 的响应内容
        """
        chat_room = context.get("chat_room") if context else None

        # 构建响应提示
        system_prompt = self.get_system_prompt()
        wrapped_message = wrap_user_content(user_message, "user_message")

        prompt = f"""用户向你发送了一条消息，请根据你的专业角色回复。

【你的角色】{self.name}
【用户消息】{wrapped_message}
【用户意图】{intent}
"""
        if feedback:
            prompt += f"\n【用户历史反馈】\n{feedback}\n"

        prompt += """
请给出专业、简洁的回复。如果用户提出的是修正建议，请确认已收到并说明如何在后续工作中考虑。
如果用户询问的是专业问题，请给出详细解答。
"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]

        response = await self.call_llm(messages, context=context)
        content = response["choices"][0]["message"].get("content", "")

        # 如果有聊天室，自动发送回复
        if chat_room and hasattr(chat_room, 'post'):
            chat_room.post(self.name, content, "text")

        return {
            "agent": self.name,
            "response": content,
            "intent": intent,
        }

    def _inject_knowledge_context(
        self,
        query_text: str,
        top_k: int = 3,
        base_id: Optional[str] = None,
        base_ids: Optional[List[str]] = None,
        project_name: Optional[str] = None,
    ) -> str:
        """查询知识库并返回上下文文本（静默失败）

        v6.0: 使用混合检索引擎（语义 + BM25），支持来源追踪。

        优先级：
          1. base_ids / self._knowledge_base_ids（多 KB，按 KB 均分 max_chars）
          2. base_id / self._knowledge_base_id（旧版单 KB，向后兼容）
          3. 自动选（项目私有 + 全局公共，由 query_context_for_task 处理）
          4. 全部 KB（旧兜底）
        """
        try:
            from ..core.knowledge_manager import get_knowledge_manager
            km = get_knowledge_manager()

            # 优先级 1: 多 KB
            effective_ids = base_ids or self._knowledge_base_ids
            if effective_ids:
                results = self._search_knowledge_bases(km, effective_ids, query_text, top_k, project_name)
                if results:
                    return self._format_knowledge_context(results, "多 KB")

            # 优先级 2: 单 KB（向后兼容）
            target_id = base_id or self._knowledge_base_id
            if target_id:
                results = self._search_knowledge_bases(km, [target_id], query_text, top_k, project_name)
                if results:
                    return self._format_knowledge_context(results, f"KB={target_id}")

            # 优先级 3: 自动选（项目私有 + 全局公共）
            eff_project = project_name or self._task_project_name
            if eff_project:
                results = self._search_knowledge_bases(km, None, query_text, top_k, project_name)
                if results:
                    return self._format_knowledge_context(results, f"project={eff_project}")

            # 优先级 4: 全部 KB（旧兜底）
            all_results = []
            for bid in km._bases:
                results = self._search_knowledge_bases(km, [bid], query_text, top_k, project_name)
                all_results.extend(results)
            if all_results:
                # 按分数排序，取 top_k
                all_results.sort(key=lambda x: x.get("score", 0), reverse=True)
                return self._format_knowledge_context(all_results[:top_k], "all bases")
        except Exception as e:
            logger.debug(f"[{self.name}] 知识库查询失败: {e}")
        return ""

    def _inject_graph_context(self, query: str) -> str:
        """查询知识图谱并返回上下文文本（静默失败）

        通过 Neo4j 图数据库检索实体和关系，为 Agent 提供结构化知识。
        如果 Neo4j 不可用或未连接，返回空字符串，不中断流程。
        """
        try:
            from ..core.neo4j_store import get_kg_store
            from ..services.kg_search import get_graph_searcher

            store = get_kg_store()
            if store is None:
                return ""

            searcher = get_graph_searcher(store)
            context = searcher.get_context_for_query(query)
            if context and context != "No relevant entities found in knowledge graph.":
                return f"\n\n## 知识图谱参考\n{context}\n"
        except Exception as e:
            logger.debug(f"[{self.name}] 知识图谱查询失败: {e}")
        return ""

    def _search_knowledge_bases(
        self,
        km,
        base_ids: Optional[List[str]],
        query_text: str,
        top_k: int,
        project_name: Optional[str],
    ) -> List[Dict[str, Any]]:
        """搜索知识库，返回带来源信息的结果"""
        all_results = []

        if base_ids:
            for bid in base_ids:
                try:
                    results = km.search(bid, query_text, top_k=top_k)
                    for r in results:
                        r["kb_id"] = bid
                        r["kb_name"] = km._bases.get(bid, type("", (), {"name": bid})()).name
                    all_results.extend(results)
                except Exception as e:
                    logger.debug(f"[{self.name}] KB {bid} 搜索失败: {e}")
        else:
            # 自动模式：项目私有 + 全局公共
            for bid, base in km._bases.items():
                scope = getattr(base, "scope", "global")
                bproj = getattr(base, "project_name", None)
                if scope == "global" or (scope == "project" and bproj == project_name):
                    try:
                        results = km.search(bid, query_text, top_k=top_k)
                        for r in results:
                            r["kb_id"] = bid
                            r["kb_name"] = base.name
                        all_results.extend(results)
                    except Exception as e:
                        logger.debug(f"[{self.name}] KB {bid} 搜索失败: {e}")

        # 按分数排序，去重
        all_results.sort(key=lambda x: x.get("score", 0), reverse=True)
        return all_results[:top_k * 2]

    def _format_knowledge_context(self, results: List[Dict[str, Any]], source_label: str) -> str:
        """格式化知识库上下文，包含来源追踪信息"""
        if not results:
            return ""

        lines = [f"\n\n## 知识库参考上下文 ({source_label})"]
        lines.append("以下信息来自知识库，仅供参考，使用时请标注来源：\n")

        for i, r in enumerate(results, 1):
            title = r.get("title", "未知")
            content = r.get("content", "")
            source = r.get("source", "")
            kb_name = r.get("kb_name", "")
            score = r.get("score", 0)
            retrieval_method = r.get("retrieval_method", "unknown")

            # 来源追踪信息（用于论文末尾的参考文献）
            source_info = f"[来源: {kb_name}]" if kb_name else ""
            if source:
                source_info += f" ({source})"

            lines.append(f"### [{i}] {title} {source_info}")
            lines.append(f"相关度: {score:.2f} | 检索方式: {retrieval_method}")
            lines.append(content[:500])
            lines.append("")

        return "\n".join(lines)

    def _inject_memory_context(self, context: Dict[str, Any], max_tokens: Optional[int] = None) -> str:
        """注入记忆系统上下文（黑板状态 + 经验教训）

        从 context 中提取 memory 对象，获取：
        1. Working Memory 黑板状态（共享任务状态）
        2. Lessons Memory 历史经验（跨任务复用知识）
        """
        parts = []

        # 1. 黑板上下文（角色过滤后的）
        working = context.get("working_memory")
        if working:
            agent_ctx = working.get_context_for_agent(self.name, max_tokens=max_tokens)
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

    def _build_paper_query_for_agent(self) -> str:
        """根据 Agent 角色构建查询论文知识库的问题。"""
        queries = {
            "research_agent": "这篇论文的研究背景、核心问题和主要贡献是什么？",
            "analyzer_agent": "这些论文研究的问题类型、使用的方法和关键结论是什么？",
            "modeler_agent": "论文中提出了哪些数学模型或算法？核心公式、输入输出和步骤是什么？",
            "solver_agent": "论文实验用了什么数据集、评估指标、超参数和主要结果？",
            "writer_agent": "与当前章节相关的论文论点、实验结果和引用素材有哪些？",
        }
        return queries.get(self.name, "这篇论文的核心方法、实验结果和主要结论是什么？")

    def _inject_paper_reading_context(self, context: Dict[str, Any], query_text: str) -> str:
        """查询任务级论文知识库，注入按需检索的论文片段。"""
        task_kb_id = context.get("task_kb_id")
        if not task_kb_id:
            return ""
        try:
            from ..core.knowledge_manager import get_knowledge_manager
            km = get_knowledge_manager()
            ctx = km.query_context(task_kb_id, query_text, top_k=5, max_chars=2500)
            if ctx and ctx.strip():
                return f"【基于论文全文的按需检索结果】\n{ctx}\n"
        except Exception as e:
            logger.debug(f"[{self.name}] 论文阅读上下文注入失败: {e}")
        return ""

    def _get_api_format(self) -> str:
        """从 provider 元数据或 llm_backend 推断 API 格式。"""
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

        # ===== v5.3.0: 自动注入 MCP 工具 =====
        # 如果调用者没有显式传入 tools，自动从 MCPManager 加载此 Agent 配置的工具
        if tools is None:
            tools = self._get_mcp_tool_defs()
        elif tools:
            # 合并用户传入的 tools 和 MCP 工具
            mcp_tools = self._get_mcp_tool_defs()
            if mcp_tools:
                existing_names = {t["name"] for t in tools}
                for mt in mcp_tools:
                    if mt["name"] not in existing_names:
                        tools = tools + [mt]

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

        # ===== Token 预算管理 =====
        budget_mgr = get_token_budget_manager(self.model or "default")
        user_query_tokens = budget_mgr.estimate_tokens(messages[-1].get("content", ""))
        system_tokens = sum(budget_mgr.estimate_tokens(m.get("content", "")) for m in messages if m.get("role") == "system")
        budget_mgr.reserve("user_query", user_query_tokens)
        budget_mgr.reserve("system_prompt", system_tokens)

        # ===== 注入 Agent 独立记忆 =====
        agent_profile_context = ""
        if self._agent_profile:
            problem_type = context.get("problem_type", "") if context else ""
            agent_profile_context = self._agent_profile.get_profile_prompt(problem_type, top_k=2)
            allowed = budget_mgr.remaining("agent_profile")
            if budget_mgr.estimate_tokens(agent_profile_context) > allowed:
                agent_profile_context = budget_mgr.clip_text(agent_profile_context, allowed)
            budget_mgr.reserve("agent_profile", budget_mgr.estimate_tokens(agent_profile_context))
            if agent_profile_context:
                # 将 Agent 个人经验作为 system prompt 追加
                messages.insert(0, {"role": "system", "content": agent_profile_context})

        # ===== 注入知识库上下文 =====
        last_content = messages[-1].get("content", "")
        query_text = last_content if isinstance(last_content, str) else ""
        kb_context = self._inject_knowledge_context(query_text)
        if kb_context:
            allowed = budget_mgr.remaining("knowledge_context")
            if budget_mgr.estimate_tokens(kb_context) > allowed:
                kb_context = budget_mgr.clip_text(kb_context, allowed)
            budget_mgr.reserve("knowledge_context", budget_mgr.estimate_tokens(kb_context))
            if kb_context:
                for msg in messages:
                    if msg.get("role") == "user":
                        if isinstance(msg["content"], str):
                            msg["content"] = msg["content"] + "\n\n【知识库参考】\n" + kb_context
                        elif isinstance(msg["content"], list):
                            msg["content"].append({"type": "text", "text": "\n\n【知识库参考】\n" + kb_context})
                        break

        # ===== 注入知识图谱上下文 =====
        graph_context = self._inject_graph_context(query_text)
        if graph_context:
            allowed = budget_mgr.remaining("knowledge_context")
            if budget_mgr.estimate_tokens(graph_context) > allowed:
                graph_context = budget_mgr.clip_text(graph_context, allowed)
            budget_mgr.reserve("knowledge_context", budget_mgr.estimate_tokens(graph_context))
            if graph_context:
                for msg in messages:
                    if msg.get("role") == "user":
                        if isinstance(msg["content"], str):
                            msg["content"] = msg["content"] + "\n\n【知识图谱参考】\n" + graph_context
                        elif isinstance(msg["content"], list):
                            msg["content"].append({"type": "text", "text": "\n\n【知识图谱参考】\n" + graph_context})
                        break

        # ===== 注入记忆系统上下文（黑板状态 + 经验教训）=====
        mem_allowed = budget_mgr.remaining("memory_context")
        mem_context = self._inject_memory_context(context, max_tokens=mem_allowed) if context else ""
        if mem_context:
            if budget_mgr.estimate_tokens(mem_context) > mem_allowed:
                mem_context = budget_mgr.clip_text(mem_context, mem_allowed)
            budget_mgr.reserve("memory_context", budget_mgr.estimate_tokens(mem_context))
            if mem_context:
                for msg in messages:
                    if msg.get("role") == "user":
                        if isinstance(msg["content"], str):
                            msg["content"] = msg["content"] + "\n\n【任务记忆】\n" + mem_context
                        elif isinstance(msg["content"], list):
                            msg["content"].append({"type": "text", "text": "\n\n【任务记忆】\n" + mem_context})
                        break

        # ===== 注入论文全文阅读上下文 =====
        if context and context.get("task_kb_id"):
            paper_query = self._build_paper_query_for_agent()
            paper_context = self._inject_paper_reading_context(context, paper_query)
            if paper_context:
                allowed = budget_mgr.remaining("knowledge_context")
                if budget_mgr.estimate_tokens(paper_context) > allowed:
                    paper_context = budget_mgr.clip_text(paper_context, allowed)
                budget_mgr.reserve("knowledge_context", budget_mgr.estimate_tokens(paper_context))
                if paper_context:
                    for msg in messages:
                        if msg.get("role") == "user":
                            if isinstance(msg["content"], str):
                                msg["content"] = msg["content"] + "\n\n【论文全文阅读】\n" + paper_context
                            elif isinstance(msg["content"], list):
                                msg["content"].append({"type": "text", "text": "\n\n【论文全文阅读】\n" + paper_context})
                            break

        # ===== 注入用户反馈（Human-in-the-loop）=====
        if context and context.get("chat_room"):
            chat_room = context["chat_room"]
            if hasattr(chat_room, "get_latest_feedback_summary"):
                feedback_summary = chat_room.get_latest_feedback_summary()
                if feedback_summary:
                    allowed = budget_mgr.remaining("user_feedback")
                    if budget_mgr.estimate_tokens(feedback_summary) > allowed:
                        feedback_summary = budget_mgr.clip_text(feedback_summary, allowed)
                    budget_mgr.reserve("user_feedback", budget_mgr.estimate_tokens(feedback_summary))
                    if feedback_summary:
                        for msg in messages:
                            if msg.get("role") == "user":
                                if isinstance(msg["content"], str):
                                    msg["content"] = msg["content"] + "\n\n【用户反馈】\n" + feedback_summary
                                elif isinstance(msg["content"], list):
                                    msg["content"].append({"type": "text", "text": "\n\n【用户反馈】\n" + feedback_summary})
                                break

        # 最终检查总预算
        try:
            budget_mgr.check_overflow()
        except Exception as e:
            logger.warning(f"[{self.name}] {e}")

        # ===== 检查 API Key =====
        if not self.api_key:
            logger.error(
                f"[{self.name}] No API key configured. "
                f"v5.3: 抛错而非返回 mock_response，避免假数据 + 触发熔断器。"
            )
            raise RuntimeError(
                f"[{self.name}] No API key configured. "
                f"请在 Provider 设置或 .env 中配置 API_KEY"
            )

        # ===== ReAct 工具循环 =====
        if tools:
            return await self._react_loop(
                messages=list(messages),
                tools=tools,
                temperature=temperature,
                max_iterations=max_react_iterations,
            )

        # ===== v5.3: CircuitBreaker 包装 =====
        # 防 API key 被刷爆：连续 N 次失败熔断
        task_id = (context or {}).get("task_id") if context else None
        try:
            from ..core.circuit_breaker import get_breaker, CircuitOpenError
        except ImportError:
            get_breaker = None
            CircuitOpenError = RuntimeError

        breaker = get_breaker(task_id) if (get_breaker and task_id) else None
        if breaker:
            breaker.check_or_raise()  # OPEN 时直接抛 CircuitOpenError

        try:
            result = await self._call_llm_once(messages, temperature)
        except Exception:
            # 真失败（不是 mock_response）→ 计入熔断器
            if breaker:
                breaker.record_failure()
            raise
        else:
            if breaker:
                breaker.record_success()
            return result

    async def _call_llm_once(
        self,
        messages: List[Dict[str, Any]],
        temperature: Optional[float] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """单次 LLM 调用，统一路由到 UnifiedLLMClient。"""
        provider = self._get_current_provider()

        # kimi-for-coding 等模型只支持 temperature=1
        if (self.model and "kimi-for-coding" in self.model) or (self.api_base_url and "kimi.com" in self.api_base_url):
            temp = 1
        else:
            temp = temperature if temperature is not None else self.temperature

        client = get_unified_llm_client()
        return await client.chat_completion(
            provider=provider,
            messages=messages,
            model=self.model,
            temperature=temp,
            max_tokens=self.effective_max_tokens,
            tools=tools,
        )

    async def _react_loop(
        self,
        messages: List[Dict[str, Any]],
        tools: List[ToolDef],
        temperature: Optional[float],
        max_iterations: int,
    ) -> Dict[str, Any]:
        """ReAct Thought-Action-Observation 循环（统一使用 OpenAI 格式消息）。

        v7.1 改进：
        1. 动态迭代次数：基于任务复杂度预估 × 1.5 作为上限
        2. 实时监控：每60秒检查 token 使用情况，动态调整策略
        3. 滑动窗口+摘要混合：旧的 tool call 历史自动压缩
        """
        import asyncio
        import time

        tools_payload = self._build_tools_payload(tools)

        # ===== 动态迭代次数估算 =====
        # 基于工具数量和任务复杂度预估所需迭代次数
        estimated_iterations = self._estimate_react_iterations(tools, messages)
        actual_max = max(max_iterations, int(estimated_iterations * 1.5))
        actual_max = min(actual_max, 20)  # 硬上限 20 次

        logger.info(
            f"[{self.name}] ReAct: estimated={estimated_iterations}, "
            f"max_iterations={max_iterations}, actual_max={actual_max}"
        )

        # ===== 滑动窗口配置 =====
        # 保留最近 N 轮完整历史，更早的压缩为摘要
        WINDOW_SIZE = 6  # 保留最近6轮（12条消息：assistant+tool各6）
        COMPRESS_EVERY = 3  # 每3轮压缩一次旧历史

        last_response: Optional[Dict[str, Any]] = None
        start_time = time.time()
        monitoring_interval = 60  # 60秒监控间隔
        last_monitor_time = start_time

        for iteration in range(actual_max):
            # ===== 实时监控：每60秒检查一次 =====
            current_time = time.time()
            if current_time - last_monitor_time >= monitoring_interval:
                elapsed = current_time - start_time
                tokens_used = self._estimate_messages_tokens(messages)
                logger.info(
                    f"[{self.name}] ReAct monitor: iteration={iteration+1}/{actual_max}, "
                    f"elapsed={elapsed:.1f}s, tokens_est={tokens_used}"
                )
                # 如果 token 使用量超过预算的80%，触发压缩
                try:
                    from ..core.token_budget import get_token_budget_manager
                    budget_mgr = get_token_budget_manager(self.model or "default")
                    react_budget = budget_mgr.remaining("react_history")
                    if tokens_used > react_budget * 0.8:
                        logger.warning(
                            f"[{self.name}] ReAct: token usage {tokens_used} > 80% of budget {react_budget}, "
                            f"compressing history"
                        )
                        self._compress_react_history(messages, keep_recent=WINDOW_SIZE)
                except Exception:
                    pass
                last_monitor_time = current_time

            # ===== 滑动窗口压缩 =====
            if iteration > 0 and iteration % COMPRESS_EVERY == 0:
                self._compress_react_history(messages, keep_recent=WINDOW_SIZE)

            response = await self._call_llm_once(messages, temperature, tools=tools_payload)
            last_response = response
            tool_calls = self._parse_tool_calls(response)
            if not tool_calls:
                # LLM 已给出最终答案
                return response

            # 构造 assistant message（包含 tool_calls）
            assistant_msg = self._extract_assistant_message(response)
            assistant_with_tools = self._inject_tool_calls(assistant_msg, tool_calls)
            messages.append(assistant_with_tools)

            # 执行工具并追加 observation messages
            for tc in tool_calls:
                observation = await self._execute_tool_call(tc)
                messages.append(self._build_tool_result_message(tc, observation))

            logger.info(f"[{self.name}] ReAct iteration {iteration + 1}/{actual_max}: executed {len(tool_calls)} tool(s)")

        logger.warning(f"[{self.name}] ReAct 达到最大迭代次数 {actual_max}，返回最后一次响应")
        if last_response:
            return last_response
        return {
            "choices": [{"message": {
                "content": json.dumps({
                    "error": "ReAct loop exhausted without final answer",
                    "status": "failed",
                    "iterations_used": actual_max,
                    "estimated_iterations": estimated_iterations,
                    "message": f"Agent {self.name} reached max iterations ({actual_max}) without producing a valid response."
                }),
                "role": "assistant"
            }}]
        }

    def _estimate_react_iterations(self, tools: List[ToolDef], messages: List[Dict]) -> int:
        """基于任务复杂度预估所需的 ReAct 迭代次数。

        启发式规则：
        - 每个独立工具调用约需 1 轮迭代
        - 复杂任务（多工具协作）需更多轮
        - 已有上下文越长，可能需要越多轮来消化
        """
        n_tools = len(tools) if tools else 0
        msg_count = len(messages) if messages else 0

        # 基础估计：工具数量的1.5倍（考虑工具链式调用）
        base_estimate = max(3, int(n_tools * 1.5))

        # 上下文长度修正：消息越多，LLM 可能需要更多轮来处理
        if msg_count > 20:
            base_estimate += 2
        elif msg_count > 10:
            base_estimate += 1

        return base_estimate

    def _estimate_messages_tokens(self, messages: List[Dict]) -> int:
        """估算 messages 列表的 token 数量。"""
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += max(1, len(content) // 3)  # 粗略估算：3字符≈1token
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and "text" in block:
                        total += max(1, len(block["text"]) // 3)
        return total

    def _compress_react_history(self, messages: List[Dict], keep_recent: int = 6):
        """压缩 ReAct 历史：保留最近 N 轮，旧的替换为摘要。

        参考 MemGPT 的虚拟上下文管理思想：
        - 核心信息（system prompt + 最近对话）保留在"主存"
        - 旧的 tool call 压缩后存入"摘要区"
        """
        if len(messages) <= keep_recent + 2:  # +2 for system prompt
            return  # 不需要压缩

        # 保留：system prompt (index 0) + 最近 keep_recent 条消息
        system_msg = messages[0] if messages and messages[0].get("role") == "system" else None
        recent_messages = messages[-keep_recent:]
        old_messages = messages[1:-keep_recent] if system_msg else messages[:-keep_recent]

        if not old_messages:
            return

        # 将旧消息压缩为摘要
        summary_parts = []
        for msg in old_messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if isinstance(content, str):
                # 截断到合理长度
                truncated = content[:200] + "..." if len(content) > 200 else content
                summary_parts.append(f"[{role}]: {truncated}")

        if summary_parts:
            summary = "[历史摘要] " + " | ".join(summary_parts[-5:])  # 最多保留5条摘要

            # 重建 messages：system + summary + recent
            new_messages = []
            if system_msg:
                new_messages.append(system_msg)

            # 添加压缩摘要作为一条 user message
            new_messages.append({
                "role": "user",
                "content": f"[系统提示：以下是之前的工具调用历史摘要，仅供上下文参考]\n{summary}"
            })
            new_messages.extend(recent_messages)

            # 清空并重建
            messages.clear()
            messages.extend(new_messages)

            logger.debug(
                f"[{self.name}] ReAct history compressed: {len(old_messages)} old messages → summary, "
                f"keeping {len(recent_messages)} recent messages"
            )

    def _build_tools_payload(self, tools: List[ToolDef]) -> List[Dict[str, Any]]:
        """把统一 ToolDef 转成 OpenAI 格式 tools。"""
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

    def _parse_tool_calls(self, response: Dict[str, Any]) -> List[ToolCall]:
        """从已归一化的 LLM 响应中解析 tool_calls。"""
        tool_calls: List[ToolCall] = []
        try:
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

    def _extract_assistant_message(self, response: Dict[str, Any]) -> Dict[str, Any]:
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
    ) -> Dict[str, Any]:
        """把 tool_calls 注入 assistant message（OpenAI 格式）。"""
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
    ) -> Dict[str, Any]:
        """构造 tool 执行结果 message（OpenAI 格式）。"""
        tool_id = tool_call.get("id") or f"tool_{tool_call['name']}"
        return {
            "role": "tool",
            "tool_call_id": tool_id,
            "name": tool_call["name"],
            "content": observation,
        }

    async def _execute_tool_call(self, tool_call: ToolCall) -> str:
        """执行本地工具调用并返回 observation。
        v5.3.0: 支持 MCP 工具调用（web_search, paper_search, file_read, file_write 等）。
        """
        name = tool_call["name"]
        args = tool_call.get("arguments", {})
        logger.info(f"[{self.name}] Executing tool: {name}({args})")

        try:
            # ===== 内置工具（硬编码 Python 实现）=====
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

            # ===== v5.3.0: MCP 工具（通过外部 MCP 服务器调用）=====
            # 检查是否是 MCP 工具（由用户配置给此 Agent 的）
            mcp_result = await self._execute_mcp_tool(name, args)
            if mcp_result is not None:
                return mcp_result

        except Exception as e:
            logger.warning(f"[{self.name}] Tool {name} failed: {e}")
            return f"Error executing tool {name}: {e}"

        return f"Tool '{name}' is not implemented."

    async def _execute_mcp_tool(self, tool_name: str, args: Dict[str, Any]) -> Optional[str]:
        """通过 MCP 服务器执行工具调用。

        返回工具执行结果，如果该工具不是此 Agent 配置的 MCP 工具则返回 None。
        支持 fallback 降级：MCP 失败时尝试本地替代方案。
        """
        import asyncio

        # 获取此 Agent 配置的 MCP 工具列表
        from ..mcp.config import get_mcp_manager
        mcp_manager = get_mcp_manager()
        agent_tools = mcp_manager.get_tools_for_agent(self.name)

        if tool_name not in agent_tools:
            return None  # 不是此 Agent 的 MCP 工具，返回 None 让上层处理

        # 查找工具对应的服务器
        server_name = mcp_manager.BUILTIN_TOOLS.get(tool_name)
        if not server_name:
            # 可能是自定义工具，尝试从 tools 映射中查找
            tool_config = mcp_manager.tools.get(tool_name)
            if tool_config:
                server_name = tool_config.server

        if not server_name:
            logger.warning(f"MCP tool '{tool_name}' has no associated server, attempting fallback")
            fallback = await self._mcp_fallback(tool_name, args)
            return fallback

        # 获取服务器配置
        server_config = mcp_manager.get_server_config(server_name)
        if not server_config:
            logger.warning(f"MCP server '{server_name}' not found, attempting fallback")
            fallback = await self._mcp_fallback(tool_name, args)
            return fallback

        if not server_config.enabled:
            logger.warning(f"MCP server '{server_name}' is disabled, attempting fallback")
            fallback = await self._mcp_fallback(tool_name, args)
            return fallback

        # 调用 MCP 工具（带重试）
        from ..mcp.client import MCPClient, MCPServerConfig as ClientConfig
        client_config = ClientConfig(
            name=server_name,
            command=server_config.command,
            args=server_config.args,
            env=server_config.env,
        )

        last_error = None
        for attempt in range(2):  # 最多重试 1 次
            client = MCPClient(client_config)
            try:
                await asyncio.wait_for(client.connect(), timeout=10.0)
                result = await asyncio.wait_for(
                    client.call_tool(tool_name, args),
                    timeout=30.0
                )
                await client.disconnect()
                if result:
                    return result
                # 空结果视为失败
                last_error = f"MCP tool '{tool_name}' returned empty result"
                logger.warning(f"[{self.name}] {last_error} (attempt {attempt + 1})")
            except asyncio.TimeoutError:
                last_error = f"MCP tool '{tool_name}' timed out"
                logger.warning(f"[{self.name}] {last_error} (attempt {attempt + 1})")
            except Exception as e:
                last_error = f"MCP tool '{tool_name}' failed: {e}"
                logger.warning(f"[{self.name}] {last_error} (attempt {attempt + 1})")
            finally:
                try:
                    await client.disconnect()
                except Exception:
                    pass

            # 第一次失败后等待一下再重试
            if attempt == 0:
                await asyncio.sleep(1)

        # 所有重试都失败，尝试 fallback
        logger.warning(f"[{self.name}] MCP tool '{tool_name}' failed after retries, attempting fallback")
        fallback = await self._mcp_fallback(tool_name, args)
        if fallback:
            return fallback

        return f"MCP tool '{tool_name}' failed: {last_error}"

    async def _mcp_fallback(self, tool_name: str, args: Dict[str, Any]) -> Optional[str]:
        """MCP 工具失败时的本地 fallback 降级。

        对于关键工具提供本地替代实现，确保系统不会因 MCP 服务不可用而完全中断。
        """
        # file_write fallback: 直接写入本地文件
        if tool_name == "file_write":
            file_path = args.get("file_path", "")
            content = args.get("content", "")
            if file_path and content:
                try:
                    from pathlib import Path
                    path = Path(file_path)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(content, encoding="utf-8")
                    logger.info(f"[{self.name}] file_write fallback: wrote {len(content)} chars to {file_path}")
                    return f"File written successfully (fallback): {file_path}"
                except Exception as e:
                    logger.warning(f"[{self.name}] file_write fallback failed: {e}")
                    return f"file_write fallback failed: {e}"

        # latex_compile fallback: 尝试本地调用 pdflatex/xelatex
        if tool_name == "latex_compile":
            tex_file = args.get("file_path", args.get("tex_file", ""))
            if tex_file:
                try:
                    import subprocess
                    result = subprocess.run(
                        ["xelatex", "-interaction=nonstopmode", tex_file],
                        capture_output=True,
                        text=True,
                        timeout=60,
                    )
                    if result.returncode == 0:
                        pdf_file = tex_file.replace(".tex", ".pdf")
                        logger.info(f"[{self.name}] latex_compile fallback: compiled {tex_file}")
                        return f"LaTeX compiled successfully (fallback): {pdf_file}"
                    else:
                        logger.warning(f"[{self.name}] latex_compile fallback: xelatex failed")
                        return f"LaTeX compilation failed (fallback): {result.stderr[:200]}"
                except FileNotFoundError:
                    logger.warning(f"[{self.name}] latex_compile fallback: xelatex not found")
                    return "latex_compile fallback failed: xelatex not installed"
                except Exception as e:
                    logger.warning(f"[{self.name}] latex_compile fallback failed: {e}")
                    return f"latex_compile fallback failed: {e}"

        # web_search fallback: 使用 LLM 生成模拟搜索结果
        if tool_name in ("web_search", "bing_search", "brave_search"):
            query = args.get("query", "")
            if query:
                logger.info(f"[{self.name}] web_search fallback: generating simulated results for '{query[:50]}'")
                return json.dumps({
                    "results": [
                        {
                            "title": f"Simulated result for: {query[:50]}",
                            "url": "https://example.com",
                            "snippet": f"This is a simulated search result. MCP search service is unavailable. Query: {query[:100]}",
                        }
                    ],
                    "fallback": True,
                    "message": "MCP search service unavailable, using simulated results",
                })

        # paper_search fallback: 返回空结果 + 提示
        if tool_name in ("paper_search", "arxiv_search", "scholar_search"):
            logger.info(f"[{self.name}] paper_search fallback: MCP unavailable")
            return json.dumps({
                "papers": [],
                "fallback": True,
                "message": "MCP paper search unavailable. Using LLM-generated references.",
            })

        # file_read fallback: 直接读取本地文件
        if tool_name == "file_read":
            file_path = args.get("file_path", "")
            if file_path:
                try:
                    from pathlib import Path
                    content = Path(file_path).read_text(encoding="utf-8")
                    logger.info(f"[{self.name}] file_read fallback: read {len(content)} chars from {file_path}")
                    return content
                except Exception as e:
                    logger.warning(f"[{self.name}] file_read fallback failed: {e}")
                    return f"file_read fallback failed: {e}"

        # 其他工具：返回明确的 fallback 不可用提示
        logger.info(f"[{self.name}] No fallback available for MCP tool '{tool_name}'")
        return None

    async def _tool_read_csv_columns(self, file_path: str) -> str:
        from ..services.data_schema import get_schema_extractor
        schema = get_schema_extractor().extract(file_path)
        if not schema:
            return f"Failed to read {file_path}"
        cols = [c["name"] for c in schema.get("columns", [])]
        return f"Columns: {', '.join(cols)}"

    async def _tool_run_python(self, code: str) -> str:
        """执行 Python 代码（使用沙箱隔离）。
        v5.3.0: 从直接 subprocess 升级为 CodeSandbox，提供资源限制和文件系统隔离。"""
        from ..core.sandbox import CodeSandbox, SandboxConfig

        config = SandboxConfig(
            max_cpu_time=30,
            max_memory_mb=256,
            workspace_persist=False,
        )
        sandbox = CodeSandbox(config)
        result = sandbox.execute(code)

        if result.success:
            out = f"stdout: {result.stdout[:2000]}"
            if result.stderr:
                out += f"\nstderr: {result.stderr[:1000]}"
            return out
        else:
            msg = f"执行失败: {result.message}"
            if result.timeout_reached:
                msg += " (超时)"
            if result.memory_exceeded:
                msg += " (内存超限)"
            if result.stderr:
                msg += f"\nstderr: {result.stderr[:1000]}"
            return msg

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
                    call_claude_code_agent,
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
                    call_claude_code_print,
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
                # v5.3: 失败必须抛
                raise RuntimeError(f"Claude Code -p failed: {last_error}") from e

        # 将 Claude 的文本响应包装为 OpenAI 兼容格式
        return {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": claude_output,
                }
            }]
        }


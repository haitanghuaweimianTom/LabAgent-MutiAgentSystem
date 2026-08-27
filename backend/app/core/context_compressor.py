"""主动上下文压缩（v5.2）。

模仿 Claude Code /compact 的原理：在多 Agent 串联时，主动压缩前序输出，
避免长程任务（CCF-A 论文、深度调研）上下文超过 LLM 限制或质量下降。

设计目标：
1. 不丢关键交付信息（latex_code / title / abstract / key_findings / citations）
2. 三级压缩策略：软压缩 → LLM 摘要 → 截断
3. 透明：每个 Agent context 里能看到压缩摘要 + 完整输出（按需 lazy load）
4. 通用：不绑定特定 Agent / 模板 / 任务

何时触发：
- 在每个 Agent execute() 之前调用 `compressor.maybe_compress(task_id, results)`
- 当累计 token > threshold（默认 30K）时触发
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ==================== Token 预估 ====================
# 优先用 tiktoken 精确计数（与 OpenAI 模型 tokenizer 对齐），
# 未安装或编码不可用时回退到字符数粗估（1 token ≈ 3 字符），保证向后兼容。
CHARS_PER_TOKEN = 3

try:
    import tiktoken  # type: ignore

    _ENCODER = None
    _TIKTOKEN_AVAILABLE = True

    def _get_encoder() -> Any:
        global _ENCODER
        if _ENCODER is None:
            # cl100k_base 覆盖 GPT-4/4o/gpt-3.5-turbo 等主流模型；对国产模型也接近
            _ENCODER = tiktoken.get_encoding("cl100k_base")
        return _ENCODER

    def _count_tokens_str(text: str) -> int:
        try:
            return len(_get_encoder().encode(text))
        except Exception:
            return max(1, len(text) // CHARS_PER_TOKEN)
except Exception:  # tiktoken 未安装
    _TIKTOKEN_AVAILABLE = False

    def _count_tokens_str(text: str) -> int:
        return max(1, len(text) // CHARS_PER_TOKEN)


def estimate_tokens(obj: Any) -> int:
    """精确估计对象的 token 数。

    优先用 tiktoken（cl100k_base）对字符串精确编码计数；未安装时回退到
    字符数粗估（1 token ≈ 3 字符，中英文混合）。dict/list 递归求和。
    """
    try:
        if isinstance(obj, str):
            return _count_tokens_str(obj)
        if isinstance(obj, (int, float, bool)):
            return 1
        if isinstance(obj, dict):
            return sum(estimate_tokens(k) + estimate_tokens(v) for k, v in obj.items())
        if isinstance(obj, (list, tuple)):
            return sum(estimate_tokens(x) for x in obj)
        return _count_tokens_str(str(obj))
    except Exception:
        return 0


# ==================== 关键字段保护 ====================

# 这些字段在任何压缩级别下都必须保留原始内容
# 原因：这些是最终交付物的核心，丢了就没法写论文/交付
PROTECTED_FIELDS = {
    "latex_code",         # WriterAgent 生成的完整 LaTeX
    "title",              # 论文标题
    "abstract",           # 论文摘要
    "keywords",           # 关键词
    "sub_problem_models", # 建模输出（writer/solver 直接消费）
    "sub_problem_solutions",  # 求解输出（writer 直接消费）
    "code_files",         # 求解代码
    "numerical_results",  # 数值结果
    "key_findings",       # 关键发现
    "bib_entries",        # 参考文献
    "citations",          # 论文引用
    "experiment_result",  # 实验结果（writer 注入论文用）
    "figures",            # 图表清单
    "plan",               # 实验/图表计划
}

# 这些字段可以安全丢弃（debug / metadata / raw 透传 / 内部状态）
DROPPABLE_FIELDS = {
    "_contract",          # schema 校验元数据
    "_raw_output",        # 原始未归一化输出
    "_agent_source",      # 来源标记
    "_revision_count",    # 修订计数
    "_latex_source",      # 内部标记
    "_placeholder",       # citation 占位标记
    "raw_response",       # LLM 原始响应
    "raw_log",            # 求解器运行日志（不影响后续步骤）
    "raw_data",           # 原始实验数据（已被 experiment_result 总结过）
    "debug_info",         # 调试信息
    "trace",              # 调用栈
    "_fabrication_check", # 防编造检查（已用过的中间结果）
}


# ==================== 压缩策略 ====================


def soft_compress(agent_output: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """L0 软压缩：丢弃 droappable 字段与过长的字符串。

    protected 字段（latex_code / title / abstract 等）永不截断 —— 它们是
    论文/报告的核心交付物，丢了就没法写后续步骤。

    Returns:
        (压缩后的 dict, 节省的 token 数)
    """
    saved = 0
    result: Dict[str, Any] = {}
    for k, v in agent_output.items():
        original_tokens = estimate_tokens(v)
        if k in DROPPABLE_FIELDS:
            saved += original_tokens
            continue
        # protected 字段：不截断、不裁剪（哪怕是 100K 字符也保留）
        if k in PROTECTED_FIELDS:
            result[k] = v
            continue
        # 单字符串超过 6K 字符 → 截断到前 5000 字符
        if isinstance(v, str) and len(v) > 6000:
            v = v[:5000] + "\n\n[... content truncated for context budget ...]\n"
            saved += original_tokens - estimate_tokens(v)
        # 大 list（>20 元素）保留前 5 + 末尾标记
        elif isinstance(v, list) and len(v) > 20:
            kept = v[:5]
            v = kept + [{"_truncated": True, "_original_count": len(agent_output.get(k, []))}]
            saved += original_tokens - estimate_tokens(v)
        result[k] = v
    return result, saved


# LLM 摘要 prompt（每个 Agent 输出压缩为 2-3 句）
SUMMARY_PROMPT = """请把以下 Agent 输出压缩为简洁摘要（不超过 200 字 / 80 tokens），
供后续 Agent 参考。保留：核心结论、关键数值、与其他模块的接口契约（字段名）。
丢弃：debug 信息、原始 LLM 响应、trace。

【Agent 类型】{agent_name}
【字段名】{field}

【原输出】
{content}

【摘要】（中文，简洁）:"""


def build_summary_prompt(agent_name: str, field: str, content: str) -> str:
    """构造摘要 prompt。"""
    # 截断 content 到 ~3000 字符（避免摘要 prompt 自己就超长）
    truncated = content[:3000]
    if len(content) > 3000:
        truncated += "\n\n[... content truncated for summarization ...]"
    return SUMMARY_PROMPT.format(
        agent_name=agent_name,
        field=field,
        content=truncated,
    )


# ==================== 压缩器主类 ====================


@dataclass
class CompressionStats:
    """单次压缩的统计。"""
    original_tokens: int = 0
    compressed_tokens: int = 0
    saved_tokens: int = 0
    level_used: str = "none"  # "none" / "L0" / "L1" / "L2"
    agents_compressed: List[str] = field(default_factory=list)

    def ratio(self) -> float:
        if self.original_tokens == 0:
            return 1.0
        return self.compressed_tokens / self.original_tokens


@dataclass
class CompressorConfig:
    """压缩器配置。

    三层阈值（按优先级，从粗到细）：
    1. ``max_context_length``：当前模型的绝对上限（默认 500_000，推理 Agent 512_000）。
    2. ``auto_compress_ratio``：触发自动压缩的比例（默认 0.9 = 90%）。
    3. ``auto_compress_threshold`` = ``max_context_length * ratio``：触发压缩的 token 数。

    旧字段 ``threshold_tokens`` / ``per_agent_threshold_tokens`` 仍保留作
    向后兼容的"绝对 token 兜底"——当模型上下文未知时使用。
    """
    # 自定义上下文长度（tokens）。None 时按 per_call 传入。
    max_context_length: Optional[int] = None
    # 自动压缩触发比例（0-1，默认 0.9）
    auto_compress_ratio: float = 0.9
    # 兜底绝对阈值（当 max_context_length 未指定时使用）
    threshold_tokens: int = 30_000
    # 单 Agent 输出超过此值优先压缩该 Agent
    per_agent_threshold_tokens: int = 8_000
    # L1 摘要的目标 token 数
    summary_target_tokens: int = 80
    # 软压缩时单字符串截断长度（字符）
    soft_truncate_chars: int = 5000
    # L2 截断时每个 Agent 摘要的最大字符
    hard_truncate_chars: int = 800

    @property
    def auto_compress_threshold(self) -> Optional[int]:
        """自动压缩阈值 token 数。None 表示用绝对兜底。"""
        if self.max_context_length is None or self.max_context_length <= 0:
            return None
        return int(self.max_context_length * self.auto_compress_ratio)


class ContextCompressor:
    """主动上下文压缩器。

    使用方式：
        compressor = ContextCompressor()
        compressor.maybe_compress(task_id, results, llm_caller=agent.call_llm)
        # results 现在包含压缩摘要 + 关键字段保留
    """

    def __init__(self, config: Optional[CompressorConfig] = None):
        self.config = config or CompressorConfig()
        # 记录每个 task 的压缩历史（避免重复压缩）
        self._task_history: Dict[str, CompressionStats] = {}

    def maybe_compress(
        self,
        task_id: str,
        results: Dict[str, Dict[str, Any]],
        llm_caller: Optional[Any] = None,
        force: bool = False,
        max_context_length: Optional[int] = None,
        auto_compress_ratio: Optional[float] = None,
    ) -> CompressionStats:
        """检查是否需要压缩，是则执行。返回统计。

        触发条件（任一满足即触发）：
        1. ``max_context_length`` 已指定，且累计 token >= ``max_context_length × ratio``。
        2. ``max_context_length`` 未指定，但累计 token >= ``threshold_tokens``（兜底）。

        Args:
            task_id: 任务 ID（用于去重 & 日志）
            results: 当前所有 Agent 的输出 dict {agent_name: output}
            llm_caller: 可选的 LLM 调用函数（用于 L1 摘要）。
                        签名：async def call_llm(messages, ...) -> response
                        缺省时退化为 L2 截断。
            force: 强制压缩（测试用）
            max_context_length: 覆盖配置中的 max_context_length（per-call 用）。
            auto_compress_ratio: 覆盖配置中的 auto_compress_ratio（per-call 用）。

        Returns:
            :class:`CompressionStats`
        """
        stats = CompressionStats()
        total_tokens = sum(estimate_tokens(out) for out in results.values())
        stats.original_tokens = total_tokens

        # 计算本次调用的有效阈值
        ctx = max_context_length if max_context_length is not None else self.config.max_context_length
        ratio = auto_compress_ratio if auto_compress_ratio is not None else self.config.auto_compress_ratio
        if ctx and ctx > 0:
            effective_threshold = int(ctx * ratio)
        else:
            effective_threshold = self.config.threshold_tokens

        if not force and total_tokens < effective_threshold:
            logger.debug(
                f"[Compressor] task {task_id}: {total_tokens} tokens < threshold "
                f"{effective_threshold} (ctx={ctx}, ratio={ratio}), skip compression"
            )
            stats.compressed_tokens = total_tokens
            return stats

        logger.info(
            f"[Compressor] task {task_id}: {total_tokens} tokens >= threshold "
            f"{effective_threshold} (ctx={ctx}, ratio={ratio:.0%}), starting compression"
        )

        # 第一步：对每个 Agent 先做 L0 软压缩
        # per_agent 阈值 = 每个 Agent 的"公平份额"。
        # 公式：min(绝对兜底, max(50, effective_threshold // n_agents))。
        # - 500K 阈值 + 15 Agents → 30000 per agent（合理）
        # - 100 阈值 + 1 Agent → 100 per agent（小上下文也能触发）
        n_agents = max(1, len(results))
        per_agent_cap = min(
            self.config.per_agent_threshold_tokens,
            max(50, effective_threshold // n_agents),
        )
        for agent_name, output in list(results.items()):
            if not isinstance(output, dict):
                continue
            per_agent_tokens = estimate_tokens(output)
            if per_agent_tokens > per_agent_cap or force:
                compressed, saved = soft_compress(output)
                results[agent_name] = compressed
                stats.saved_tokens += saved
                stats.agents_compressed.append(agent_name)

        # 第二步：如果还超阈值 → 尝试 L1 摘要（仅对超大 Agent 输出）
        post_l0 = sum(estimate_tokens(out) for out in results.values())
        if post_l0 > effective_threshold and llm_caller is not None:
            big_agents = [
                (name, out) for name, out in results.items()
                if isinstance(out, dict)
                and estimate_tokens(out) > per_agent_cap
            ]
            for agent_name, output in big_agents:
                protected = {k: v for k, v in output.items() if k in PROTECTED_FIELDS}
                droppable = {k: v for k, v in output.items() if k not in PROTECTED_FIELDS}
                if not droppable:
                    continue
                summary = self._llm_summarize(agent_name, droppable, llm_caller)
                if summary:
                    new_output = dict(protected)
                    new_output["_summary"] = summary
                    new_output["_compressed"] = True
                    stats.saved_tokens += estimate_tokens(output) - estimate_tokens(new_output)
                    results[agent_name] = new_output
                    stats.agents_compressed.append(f"{agent_name}(L1)")
            stats.level_used = "L1"

        # 第三步：如果还超阈值 → L2 硬截断
        post_l1 = sum(estimate_tokens(out) for out in results.values())
        if post_l1 > effective_threshold:
            for agent_name, output in list(results.items()):
                if not isinstance(output, dict):
                    continue
                if estimate_tokens(output) > per_agent_cap:
                    new_output = {}
                    for k, v in output.items():
                        if k in PROTECTED_FIELDS:
                            new_output[k] = v
                        elif isinstance(v, str) and len(v) > self.config.hard_truncate_chars:
                            new_output[k] = v[:self.config.hard_truncate_chars] + "...[L2]"
                        elif isinstance(v, (list, dict)):
                            if isinstance(v, list):
                                new_output[k] = v[:3]
                                if len(v) > 3:
                                    new_output[k].append({"_truncated": True, "_count": len(v)})
                            else:
                                new_output[k] = dict(list(v.items())[:3])
                        else:
                            new_output[k] = v
                    stats.saved_tokens += estimate_tokens(output) - estimate_tokens(new_output)
                    results[agent_name] = new_output
                    stats.agents_compressed.append(f"{agent_name}(L2)")
            stats.level_used = stats.level_used or "L2"

        stats.compressed_tokens = sum(estimate_tokens(out) for out in results.values())
        if stats.saved_tokens > 0:
            if not stats.level_used or stats.level_used == "none":
                stats.level_used = "L0"
        else:
            stats.level_used = "none"

        self._task_history[task_id] = stats

        logger.info(
            f"[Compressor] task {task_id}: {stats.original_tokens} → {stats.compressed_tokens} "
            f"tokens (saved {stats.saved_tokens}, ratio={stats.ratio():.2f}, "
            f"level={stats.level_used}, agents={stats.agents_compressed})"
        )
        return stats

    def _llm_summarize(
        self,
        agent_name: str,
        droppable: Dict[str, Any],
        llm_caller: Any,
    ) -> str:
        """调用 LLM 把 droppable 字段摘要为短文本。失败时返回空串（降级到 L2）。

        llm_caller 期望签名（与 BaseAgent.call_llm 一致）：
            async def call_llm(messages: List[Dict], ...) -> Dict

        我们包装一个同步入口，内部用 asyncio.run 在新线程中跑。
        """
        import asyncio
        import concurrent.futures

        async def _call():
            return await llm_caller(
                messages=[{"role": "user", "content": build_summary_prompt(
                    agent_name, "agent_output",
                    json.dumps(droppable, ensure_ascii=False, indent=2, default=str)[:3000],
                )}],
                temperature=0.3,
                tools=[],
            )

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                fut = ex.submit(asyncio.run, _call())
                response = fut.result(timeout=30)

            if isinstance(response, dict):
                choices = response.get("choices", [])
                if choices:
                    msg = choices[0].get("message", {})
                    return msg.get("content", "").strip()
            return str(response).strip()
        except Exception as exc:
            logger.warning(f"[Compressor] LLM 摘要失败，降级到 L2: {exc}")
            return ""

    def get_history(self, task_id: str) -> Optional[CompressionStats]:
        return self._task_history.get(task_id)


# ==================== 全局单例 ====================

_global_compressor: Optional[ContextCompressor] = None


def get_compressor(
    max_context_length: Optional[int] = None,
    auto_compress_ratio: float = 0.9,
) -> ContextCompressor:
    """获取全局压缩器单例。

    第一次调用时按传入参数初始化；后续调用复用同一实例（per-process 单例）。
    若需要切换上下文长度，调用 :func:`reset_compressor` 后重新获取。
    """
    global _global_compressor
    if _global_compressor is None:
        cfg = CompressorConfig(
            max_context_length=max_context_length,
            auto_compress_ratio=auto_compress_ratio,
        )
        _global_compressor = ContextCompressor(cfg)
    return _global_compressor


def reset_compressor() -> None:
    """重置全局压缩器（用于测试或 reload）。"""
    global _global_compressor
    _global_compressor = None
